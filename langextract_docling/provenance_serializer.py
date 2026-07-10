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

from langextract_docling.provenance import ProvenanceMap
from langextract_docling.provenance import SourceLocation
from langextract_docling.provenance import SpanProvenance

_DELIM = "\n\n"


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
        character range of the text, the source DocItem refs and their
        physical page locations; the "\\n\\n" delimiters between items
        belong to no span.
    """
    parts: list[str] = []
    spans: list[SpanProvenance] = []
    offset = 0
    for ser_res in self.iter_item_results(**kwargs):
      start = offset + (len(_DELIM) if parts else 0)
      end = start + len(ser_res.text)
      parts.append(ser_res.text)
      spans.extend(
          SpanProvenance(
              start=start,
              end=end,
              doc_item_ref=span.item.self_ref,
              doc_item_label=str(span.item.label),
              locations=_locations_of(span.item),
          )
          for span in ser_res.spans
      )
      offset = end
    return _DELIM.join(parts), ProvenanceMap(spans)


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
