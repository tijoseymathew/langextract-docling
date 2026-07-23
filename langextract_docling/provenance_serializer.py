"""Markdown serializer that reports output-offset provenance.

docling-core's SerializationResult.spans carries only the source items, not
character offsets, so offsets into the assembled document text are tracked
here while joining the per-item serializations.

This module must stay importable without the docling-core [chunking] extra:
it imports only from docling_core.transforms.serializer.* and
docling_core.types.doc.
"""

import typing

from docling_core.transforms.serializer.markdown import MarkdownDocSerializer
from docling_core.types.doc.document import DocItem
from docling_core.types.doc.document import InlineGroup
from docling_core.types.doc.document import ListGroup

from langextract_docling import text_alignment
from langextract_docling.provenance import ProvenanceMap
from langextract_docling.provenance import SourceLocation
from langextract_docling.provenance import SpanProvenance
from langextract_docling.provenance import TextSegment

_DELIM = "\n\n"

# Serializing an item can at most escape every character ("_" -> "\_") and
# wrap the result in a prefix, marker and suffix ("## ", "**...**", ": ").
# Searching that far past an item's expected start is enough to find it,
# and stopping there keeps a group of many items from costing O(n^2).
_SEARCH_SLACK = 64


class ProvenanceMarkdownSerializer(MarkdownDocSerializer):
  """Markdown serializer that also reports output-offset provenance.

  Produces text identical to iterating the document with
  MarkdownDocSerializer item-by-item and joining non-empty results with
  "\\n\\n" — i.e., identical to the HierarchicalMarkdownChunker output.
  """

  def iter_item_results(
      self, **kwargs: typing.Any
  ) -> typing.Iterator[typing.Any]:
    """Yields one non-empty SerializationResult per top-level item.

    This is the single document walk shared by serialize_with_provenance
    and HierarchicalMarkdownChunker: items are serialized in document
    order, skipping excluded refs, already-visited items, and results
    without text or source items.

    Args:
        **kwargs: Forwarded to get_excluded_refs (e.g. serializer filters).
    """
    excluded_refs = self.get_excluded_refs(**kwargs)
    visited: set[str] = set()
    for item, _ in self.doc.iterate_items(with_groups=True):
      if item.self_ref in excluded_refs:
        continue
      if not isinstance(item, (ListGroup, InlineGroup, DocItem)):
        continue
      if item.self_ref in visited:
        continue
      ser_res = self.serialize(item=item, visited=visited)
      if not ser_res.text or not ser_res.spans:
        continue
      yield ser_res

  def serialize_with_provenance(
      self, **kwargs: typing.Any
  ) -> tuple[str, ProvenanceMap]:
    """Serializes the document to markdown with a provenance map.

    Args:
        **kwargs: Forwarded to get_excluded_refs (e.g. serializer filters).

    Returns:
        A (text, provenance_map) tuple. The map's spans record, for every
        character range of the text, the source DocItem refs, their
        physical page locations, and the runs the markdown shares with
        each item's own text (which is what narrows an interval below
        item granularity); the "\\n\\n" delimiters between items belong
        to no span.
    """
    parts: list[str] = []
    spans: list[SpanProvenance] = []
    offset = 0
    for ser_res in self.iter_item_results(**kwargs):
      start = offset + (len(_DELIM) if parts else 0)
      end = start + len(ser_res.text)
      parts.append(ser_res.text)
      # One serialization can cover several items (a ListGroup, an
      # InlineGroup, a captioned table), so each item is located in turn
      # from where the previous one ended.
      cursor = 0
      for span in ser_res.spans:
        item_text = getattr(span.item, "text", None) or ""
        segments, cursor = _align_item(ser_res.text, item_text, cursor)
        spans.append(
            SpanProvenance(
                start=start,
                end=end,
                doc_item_ref=span.item.self_ref,
                doc_item_label=str(span.item.label),
                locations=_locations_of(span.item),
                item_text=item_text,
                text_segments=tuple(
                    TextSegment(
                        start=start + segment_start,
                        item_start=item_start,
                        length=length,
                    )
                    for segment_start, item_start, length in segments
                ),
            )
        )
      offset = end
    return _DELIM.join(parts), ProvenanceMap(spans)


def _align_item(
    serialized: str, item_text: str, cursor: int
) -> tuple[list[text_alignment.Block], int]:
  """Locates one item's own text inside a serialization, after `cursor`.

  Args:
      serialized: Markdown for the whole serialization result, which may
        cover several items.
      item_text: The item's own, unescaped text; "" for items that have
        none (groups, tables, pictures).
      cursor: Offset in `serialized` past the previously located item.

  Returns:
      A (blocks, cursor) tuple: the runs shared by `serialized` and
      `item_text` in `serialized` coordinates, and the offset the next
      item's search starts from. Blocks are empty — disabling sub-item
      narrowing for this item, nothing more — when the text has no
      recognisable counterpart in the markdown.
  """
  if not item_text:
    return [], cursor
  limit = cursor + 2 * len(item_text) + _SEARCH_SLACK
  window = serialized[cursor:limit]

  # The overwhelmingly common case: nothing in the item needed escaping,
  # so its text appears verbatim and no diffing is required.
  found = window.find(item_text)
  if found >= 0:
    start = cursor + found
    return [(start, 0, len(item_text))], start + len(item_text)

  blocks = text_alignment.invert(
      text_alignment.trusted_blocks(item_text, window)
  )
  if not blocks:
    return [], cursor
  last_start, _, last_length = blocks[-1]
  return (
      [
          (cursor + start, item_start, length)
          for start, item_start, length in blocks
      ],
      cursor + last_start + last_length,
  )


def _locations_of(item: DocItem) -> tuple[SourceLocation, ...]:
  """Flattens a DocItem's ProvenanceItems; empty for non-paginated sources."""
  return tuple(
      SourceLocation(
          page_no=prov.page_no,
          bbox=(prov.bbox.l, prov.bbox.t, prov.bbox.r, prov.bbox.b),
          coord_origin=str(prov.bbox.coord_origin.value),
          charspan=tuple(prov.charspan),
      )
      for prov in getattr(item, "prov", None) or ()
  )
