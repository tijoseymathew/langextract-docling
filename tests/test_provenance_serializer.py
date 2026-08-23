"""Tests for langextract_docling.provenance_serializer."""

import ast
import pathlib

from docling_core.types.doc.base import BoundingBox
from docling_core.types.doc.base import CoordOrigin
from docling_core.types.doc.base import Size
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.document import ProvenanceItem
from docling_core.types.doc.document import TableCell
from docling_core.types.doc.document import TableData
from docling_core.types.doc.labels import DocItemLabel
import pytest

from langextract_docling import provenance
from langextract_docling import provenance_serializer
from langextract_docling.markdown_chunker import HierarchicalMarkdownChunker

DATA_DIR = pathlib.Path(__file__).parent / "data"
FIXTURES = ["report_pdf", "notes_md"]

DELIM = "\n\n"


def _load(name: str) -> DoclingDocument:
  return DoclingDocument.load_from_json(DATA_DIR / f"{name}.docling.json")


def _serialize(name: str):
  serializer = provenance_serializer.ProvenanceMarkdownSerializer(
      doc=_load(name)
  )
  return serializer.serialize_with_provenance()


@pytest.fixture(params=FIXTURES)
def fixture_name(request):
  return request.param


_PAGE_WIDTH = 400.0
_PAGE_HEIGHT = 200.0


def _cell_bbox(row: int, col: int) -> BoundingBox:
  """A cell's box on the page, in the top-left origin docling reports."""
  left = 10.0 + 100.0 * col
  top = 10.0 + 20.0 * row
  return BoundingBox(
      l=left,
      t=top,
      r=left + 80.0,
      b=top + 12.0,
      coord_origin=CoordOrigin.TOPLEFT,
  )


def _table_bbox(rows: int, cols: int) -> BoundingBox:
  """The box enclosing every cell, in the bottom-left origin tables use."""
  return BoundingBox(
      l=10.0,
      t=_PAGE_HEIGHT - 10.0,
      r=10.0 + 100.0 * (cols - 1) + 80.0,
      b=_PAGE_HEIGHT - (10.0 + 20.0 * (rows - 1) + 12.0),
      coord_origin=CoordOrigin.BOTTOMLEFT,
  )


def _table_span(
    rows: list[list[str]],
    *,
    paginated: bool = True,
    drop_box: tuple[int, int] | None = None,
    stray_box: tuple[int, int] | None = None,
    caption: str | None = None,
):
  """Serializes a one-table document; returns (markdown, the table's span).

  Args:
      rows: Cell text, row by row, laid out on a grid of known boxes.
      paginated: False places the table nowhere, as a markdown source does.
      drop_box: (row, col) of a cell to leave without a bounding box.
      stray_box: (row, col) of a cell to place outside the table's box.
      caption: Caption text, serialized with the table as one result.
  """
  doc = DoclingDocument(name="table")
  cells = []
  for row_index, row in enumerate(rows):
    for col_index, text in enumerate(row):
      position = (row_index, col_index)
      if position == drop_box:
        bbox = None
      elif position == stray_box:
        bbox = BoundingBox(
            l=300.0, t=180.0, r=380.0, b=192.0, coord_origin=CoordOrigin.TOPLEFT
        )
      else:
        bbox = _cell_bbox(row_index, col_index)
      cells.append(
          TableCell(
              text=text,
              bbox=bbox,
              start_row_offset_idx=row_index,
              end_row_offset_idx=row_index + 1,
              start_col_offset_idx=col_index,
              end_col_offset_idx=col_index + 1,
          )
      )
  prov = None
  if paginated:
    doc.add_page(page_no=1, size=Size(width=_PAGE_WIDTH, height=_PAGE_HEIGHT))
    prov = ProvenanceItem(
        page_no=1,
        bbox=_table_bbox(len(rows), len(rows[0])),
        charspan=(0, 0),
    )
  doc.add_table(
      data=TableData(
          num_rows=len(rows), num_cols=len(rows[0]), table_cells=cells
      ),
      prov=prov,
      caption=(
          None
          if caption is None
          else doc.add_text(label=DocItemLabel.CAPTION, text=caption)
      ),
  )
  serializer = provenance_serializer.ProvenanceMarkdownSerializer(doc=doc)
  text, pmap = serializer.serialize_with_provenance()
  (span,) = [s for s in pmap.spans if s.doc_item_ref.startswith("#/tables/")]
  return text, span


class TestTextInvariant:
  """The serialized text must be byte-identical to the chunker pipeline."""

  def test_matches_golden_file(self, fixture_name):
    text, _ = _serialize(fixture_name)
    golden = (DATA_DIR / f"{fixture_name}.golden.md").read_text()
    assert text == golden

  def test_matches_live_chunker_join(self, fixture_name):
    text, _ = _serialize(fixture_name)
    chunks = HierarchicalMarkdownChunker().chunk(_load(fixture_name))
    assert text == DELIM.join(chunk.text for chunk in chunks)


class TestSpanIntegrity:

  def test_returns_provenance_map(self, fixture_name):
    _, pmap = _serialize(fixture_name)
    assert isinstance(pmap, provenance.ProvenanceMap)
    assert pmap.spans

  def test_spans_are_sorted_and_within_text(self, fixture_name):
    text, pmap = _serialize(fixture_name)
    starts = [s.start for s in pmap.spans]
    assert starts == sorted(starts)
    for span in pmap.spans:
      assert 0 <= span.start < span.end <= len(text)
      assert text[span.start : span.end].strip()

  def test_spans_do_not_partially_overlap(self, fixture_name):
    # Spans either share an identical range (group members) or are disjoint.
    _, pmap = _serialize(fixture_name)
    for a, b in zip(pmap.spans, pmap.spans[1:]):
      assert (a.start, a.end) == (b.start, b.end) or a.end <= b.start

  def test_gaps_between_spans_are_exactly_the_delimiter(self, fixture_name):
    text, pmap = _serialize(fixture_name)
    covered = set()
    for span in pmap.spans:
      covered.update(range(span.start, span.end))
    uncovered = sorted(set(range(len(text))) - covered)
    # Group consecutive uncovered offsets into maximal gaps
    gaps = []
    for pos in uncovered:
      if gaps and gaps[-1][-1] == pos - 1:
        gaps[-1].append(pos)
      else:
        gaps.append([pos])
    assert gaps, "expected at least one delimiter gap between items"
    for gap in gaps:
      assert text[gap[0] : gap[-1] + 1] == DELIM

  def test_doc_item_refs_resolve_into_the_document(self, fixture_name):
    doc = _load(fixture_name)
    serializer = provenance_serializer.ProvenanceMarkdownSerializer(doc=doc)
    _, pmap = serializer.serialize_with_provenance()
    valid_refs = {
        item.self_ref for item, _ in doc.iterate_items(with_groups=True)
    }
    for span in pmap.spans:
      assert span.doc_item_ref in valid_refs
      assert span.doc_item_label


class TestPdfLocations:

  def test_every_span_has_a_page_location(self):
    _, pmap = _serialize("report_pdf")
    for span in pmap.spans:
      assert span.locations, f"span {span.doc_item_ref} has no locations"
      for loc in span.locations:
        assert loc.page_no >= 1
        assert len(loc.bbox) == 4
        assert loc.coord_origin in ("TOPLEFT", "BOTTOMLEFT")

  def test_second_page_content_maps_to_page_2(self):
    text, pmap = _serialize("report_pdf")
    pos = text.index("In conclusion")
    spans = pmap.lookup(pos, pos + len("In conclusion"))
    assert spans
    assert all(loc.page_no == 2 for s in spans for loc in s.locations)

  def test_lookup_of_list_item_text(self):
    text, pmap = _serialize("report_pdf")
    pos = text.index("Bernoulli")
    spans = pmap.lookup(pos, pos + len("Bernoulli"))
    assert spans
    assert any("Bernoulli" in text[s.start : s.end] for s in spans)


class TestGroupProvenance:

  def test_list_group_emits_one_span_per_item_with_shared_range(self):
    text, pmap = _serialize("notes_md")
    pos = text.index("- Write the serializer")
    group = pmap.lookup(pos, pos + 1)
    assert len(group) == 3, "expected one span per list item"
    assert len({(s.start, s.end) for s in group}) == 1
    assert len({s.doc_item_ref for s in group}) == 3
    covered = text[group[0].start : group[0].end]
    assert "- Write the serializer" in covered
    assert "- Map the offsets" in covered
    assert "- Ship version 1.1.0" in covered


class TestEmptyProvenanceItems:

  def test_markdown_source_yields_empty_locations(self):
    _, pmap = _serialize("notes_md")
    assert pmap.spans
    for span in pmap.spans:
      assert span.locations == ()
      assert span.doc_item_ref


class TestTextSegments:
  """Spans record where each item's own text sits in the markdown."""

  def test_segments_recover_the_item_text(self, fixture_name):
    text, pmap = _serialize(fixture_name)
    for span in pmap.spans:
      for segment in span.text_segments:
        markdown = text[segment.start : segment.start + segment.length]
        item = span.item_text[
            segment.item_start : segment.item_start + segment.length
        ]
        assert markdown == item

  def test_segments_stay_inside_their_span(self, fixture_name):
    _, pmap = _serialize(fixture_name)
    for span in pmap.spans:
      for segment in span.text_segments:
        assert span.start <= segment.start
        assert segment.start + segment.length <= span.end

  def test_segments_advance_through_both_texts(self, fixture_name):
    _, pmap = _serialize(fixture_name)
    for span in pmap.spans:
      for current, following in zip(span.text_segments, span.text_segments[1:]):
        assert current.start + current.length <= following.start
        assert current.item_start + current.length <= following.item_start

  def test_items_with_text_are_all_aligned(self, fixture_name):
    _, pmap = _serialize(fixture_name)
    for span in pmap.spans:
      if span.item_text:
        assert span.text_segments, f"{span.doc_item_ref} was not aligned"

  def test_heading_prefix_is_excluded_from_the_segments(self):
    text, pmap = _serialize("report_pdf")
    start = text.index("## Introduction")
    (span,) = pmap.lookup(start, start + len("## Introduction"))
    (segment,) = span.text_segments
    assert text[segment.start] == "I", "the '## ' prefix is not item text"

  def test_group_members_are_located_separately(self):
    text, pmap = _serialize("notes_md")
    pos = text.index("- Write the serializer")
    group = pmap.lookup(pos, pos + 1)
    starts = [span.text_segments[0].start for span in group]
    assert starts == sorted(starts), "items must be found in document order"
    assert len(set(starts)) == 3, "each item sits at its own offset"

  def test_table_is_aligned_through_its_cells(self):
    text, pmap = _serialize("report_pdf")
    tables = [s for s in pmap.spans if s.doc_item_ref.startswith("#/tables/")]
    assert tables, "the report fixture contains a table"
    for span in tables:
      assert "Mathematician" in span.item_text
      assert span.text_segments
      for segment in span.text_segments:
        markdown = text[segment.start : segment.start + segment.length]
        assert (
            markdown
            == span.item_text[
                segment.item_start : segment.item_start + segment.length
            ]
        )


class TestTableCells:
  """A table is aligned and boxed cell by cell, or not at all."""

  def test_cells_become_the_tables_own_text(self):
    _, span = _table_span([["Site", "Lead"], ["Reykjavik", "Amara Osei"]])
    assert span.item_text == "Site\nLead\nReykjavik\nAmara Osei"

  def test_every_cell_carries_its_own_box(self):
    _, span = _table_span([["Site", "Lead"], ["Reykjavik", "Amara Osei"]])
    assert len(span.sub_locations) == 4
    assert len({loc.bbox for loc in span.sub_locations}) == 4
    for location in span.sub_locations:
      start, end = location.charspan
      assert span.item_text[start:end] in (
          "Site",
          "Lead",
          "Reykjavik",
          "Amara Osei",
      )

  def test_cell_boxes_use_the_coordinate_system_of_the_table(self):
    _, span = _table_span([["Site"], ["Reykjavik"]])
    (table_box,) = span.locations
    for location in span.sub_locations:
      assert location.coord_origin == table_box.coord_origin
      assert location.page_no == table_box.page_no

  def test_segments_place_each_cell_where_the_markdown_writes_it(self):
    text, span = _table_span([["Site", "Lead"], ["Reykjavik", "Amara Osei"]])
    for segment in span.text_segments:
      markdown = text[segment.start : segment.start + segment.length]
      assert (
          markdown
          == span.item_text[
              segment.item_start : segment.item_start + segment.length
          ]
      )

  def test_repeated_cell_text_pins_to_the_cell_that_holds_it(self):
    rows = [["Site"], ["Reykjavik"], ["Reykjavik"]]
    text, span = _table_span(rows)
    second = text.index("Reykjavik", text.index("Reykjavik") + 1)
    (sub,) = provenance.ProvenanceMap([span]).narrow(
        second, second + len("Reykjavik")
    )
    (location,) = sub.locations
    assert location.bbox == span.sub_locations[2].bbox
    assert location.bbox != span.sub_locations[1].bbox

  def test_table_without_a_page_narrows_to_cell_text_without_boxes(self):
    _, span = _table_span([["Site"], ["Reykjavik"]], paginated=False)
    assert span.item_text == "Site\nReykjavik"
    assert span.sub_locations == ()

  def test_cell_without_a_box_leaves_the_whole_table_unaligned(self):
    _, span = _table_span([["Site"], ["Reykjavik"]], drop_box=(1, 0))
    assert span.item_text == ""
    assert span.text_segments == ()
    assert span.sub_locations == ()
    assert span.locations, "the table's own box survives"

  def test_cells_outside_the_tables_box_are_not_trusted(self):
    _, span = _table_span([["Site"], ["Reykjavik"]], stray_box=(1, 0))
    assert span.item_text == ""
    assert span.sub_locations == ()

  def test_cell_the_markdown_rewrites_costs_only_itself(self):
    # docling writes a pipe inside a cell as "&#124;", so that cell has no
    # verbatim counterpart to align against; its neighbours still do.
    text, span = _table_span([["Site", "A|B"], ["Reykjavik", "x"]])
    assert "A&#124;B" in text
    assert span.item_text == "Site\nReykjavik\nx"
    assert len(span.sub_locations) == 3

  def test_cells_are_not_matched_against_the_caption(self):
    text, span = _table_span(
        [["Yield"], ["94%"]], caption="Yield by site, quarter three."
    )
    first = span.text_segments[0]
    assert text[first.start : first.start + first.length] == "Yield"
    assert first.start > text.index("|"), "the cell, not the caption"

  def test_dashes_are_not_matched_against_the_separator_row(self):
    _, span = _table_span([["Site", "Drift"], ["Reykjavik", "-"]])
    assert span.item_text == "Site\nDrift\nReykjavik"
    assert len(span.sub_locations) == 3


class TestImportLightness:

  def test_module_does_not_import_chunker_namespaces(self):
    # The serializer must work without the docling-core [chunking] extra, so
    # it may only import from docling_core.transforms.serializer and
    # docling_core.types (see spec §6.1).
    source = pathlib.Path(provenance_serializer.__file__).read_text()
    imported = set()
    for node in ast.walk(ast.parse(source)):
      if isinstance(node, ast.Import):
        imported.update(alias.name for alias in node.names)
      elif isinstance(node, ast.ImportFrom):
        imported.add(node.module or "")
    banned = ("docling_core.transforms.chunker", "docling.chunking")
    offenders = {
        mod for mod in imported if mod.startswith(banned) or "chunker" in mod
    }
    assert not offenders, f"import-heavy modules imported: {offenders}"
