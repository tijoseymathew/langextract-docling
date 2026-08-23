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
from docling_core.types.doc.base import CoordOrigin
from docling_core.types.doc.document import DocItem
from docling_core.types.doc.document import InlineGroup
from docling_core.types.doc.document import ListGroup
from docling_core.types.doc.document import TableItem

from langextract_docling import text_alignment
from langextract_docling.provenance import ProvenanceMap
from langextract_docling.provenance import SourceLocation
from langextract_docling.provenance import SpanProvenance
from langextract_docling.provenance import TextSegment

_DELIM = "\n\n"

# A table has no text of its own, so one is assembled from its cells in
# reading order, joined by this. It is the coordinate system the table's
# text_segments and cell locations are expressed in.
_CELL_DELIM = "\n"

# Cell text made of nothing but markdown table furniture ("-", ":", "|")
# would match the header separator row instead of the cell, so it is left
# unmapped rather than mapped to the wrong offsets.
_TABLE_SYNTAX = set("-:| \t")

# A cell box docling derived from the page must sit within the box it
# derived for the whole table. A little slack absorbs the rounding of
# coordinate conversions; more than that means the two are not in the
# same coordinate space, and no cell geometry is trustworthy.
_CELL_CONTAINMENT_SLACK = 2.0

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
        item_text, segments, sub_locations, cursor = _align_span_item(
            ser_res.text, span.item, cursor, self.doc
        )
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
                sub_locations=sub_locations,
            )
        )
      offset = end
    return _DELIM.join(parts), ProvenanceMap(spans)


def _align_span_item(
    serialized: str, item: typing.Any, cursor: int, doc: typing.Any
) -> tuple[str, list[text_alignment.Block], tuple[SourceLocation, ...], int]:
  """Locates one item's text in a serialization and boxes its parts.

  Args:
      serialized: Markdown for the whole serialization result, which may
        cover several items.
      item: The DocItem to locate.
      cursor: Offset in `serialized` past the previously located item.
      doc: The document being serialized, for page geometry.

  Returns:
      An (item_text, blocks, sub_locations, cursor) tuple: the text that
      is the item's own coordinate system, the runs it shares with
      `serialized`, the boxes of its parts (table cells; empty for items
      located only as a whole), and the offset the next item's search
      starts from.
  """
  if isinstance(item, TableItem):
    return _align_table(serialized, item, cursor, doc)
  item_text = getattr(item, "text", None) or ""
  segments, cursor = _align_item(serialized, item_text, cursor)
  return item_text, segments, (), cursor


def _align_table(
    serialized: str, table: TableItem, cursor: int, doc: typing.Any
) -> tuple[str, list[text_alignment.Block], tuple[SourceLocation, ...], int]:
  """Aligns a table through its cells, which is all the text it has.

  A TableItem has no text of its own, so one is assembled from the cells
  in reading order: each cell is found in the markdown after the previous
  one — the same sequential walk that pins repeated text to the right
  item — and contributes both a run of shared text and the box it
  occupies on the page.

  Cells the markdown does not spell out (escaped text, a serializer that
  reflows them) are skipped: they cost their own narrowing, nothing more.
  Geometry is all or nothing, so a table can never mix boxes read from
  its cells with boxes read from somewhere else.

  Args:
      serialized: Markdown for the whole serialization result.
      table: The table to align.
      cursor: Offset in `serialized` past the previously located item.
      doc: The document being serialized, for page geometry.

  Returns:
      The same (item_text, blocks, sub_locations, cursor) tuple as
      _align_span_item; ("", [], (), cursor) when neither the cells nor
      their boxes can be trusted, which leaves the table reported as a
      whole exactly as it was before cells were read.
  """
  parts: list[str] = []
  blocks: list[text_alignment.Block] = []
  located: list[tuple[typing.Any, int]] = []
  item_cursor = 0
  scan = cursor
  for cell in _cells_in_reading_order(table):
    text = cell.text or ""
    if not text.strip() or set(text) <= _TABLE_SYNTAX:
      continue
    found = serialized.find(text, scan)
    if found < 0:
      continue
    blocks.append((found, item_cursor, len(text)))
    located.append((cell, item_cursor))
    parts.append(text)
    item_cursor += len(text) + len(_CELL_DELIM)
    scan = found + len(text)

  if not blocks:
    return "", [], (), cursor
  locations = _cell_locations(table, located, doc)
  if locations is None:
    return "", [], (), cursor
  return _CELL_DELIM.join(parts), blocks, locations, scan


def _cells_in_reading_order(table: TableItem) -> list[typing.Any]:
  """Returns the table's cells ordered as the markdown writes them."""
  return sorted(
      getattr(table.data, "table_cells", None) or (),
      key=lambda cell: (cell.start_row_offset_idx, cell.start_col_offset_idx),
  )


def _cell_locations(
    table: TableItem, located: list[tuple[typing.Any, int]], doc: typing.Any
) -> tuple[SourceLocation, ...] | None:
  """Boxes each located cell, in the coordinate system of the table's box.

  Args:
      table: The table the cells belong to.
      located: (cell, item_start) pairs for the cells found in the
        markdown, where item_start is the cell's offset in the assembled
        table text.
      doc: The document being serialized, for the page height every
        coordinate conversion needs.

  Returns:
      One location per cell; () when the table has no geometry at all, so
      that a table from a markdown source still narrows to cell text; or
      None when the table is placed on a page but its cells are not
      placed within it, which makes every cell box untrustworthy.
  """
  prov = next(iter(getattr(table, "prov", None) or ()), None)
  if prov is None:
    return ()
  page = (doc.pages or {}).get(prov.page_no) if doc is not None else None
  if page is None:
    return None
  height = page.size.height
  table_box = prov.bbox.to_bottom_left_origin(height)
  locations = []
  for cell, item_start in located:
    if cell.bbox is None:
      return None
    box = cell.bbox.to_bottom_left_origin(height)
    if not _within(box, table_box):
      return None
    placed = (
        box
        if prov.bbox.coord_origin == CoordOrigin.BOTTOMLEFT
        else box.to_top_left_origin(height)
    )
    locations.append(
        SourceLocation(
            page_no=prov.page_no,
            bbox=(placed.l, placed.t, placed.r, placed.b),
            coord_origin=str(prov.bbox.coord_origin.value),
            charspan=(item_start, item_start + len(cell.text)),
        )
    )
  return tuple(locations)


def _within(inner: typing.Any, outer: typing.Any) -> bool:
  """True when one bottom-left box sits inside another, within slack."""
  slack = _CELL_CONTAINMENT_SLACK
  return (
      min(inner.l, inner.r) >= min(outer.l, outer.r) - slack
      and max(inner.l, inner.r) <= max(outer.l, outer.r) + slack
      and min(inner.b, inner.t) >= min(outer.b, outer.t) - slack
      and max(inner.b, inner.t) <= max(outer.b, outer.t) + slack
  )


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
