"""Tests for word_layout: character geometry read back from the PDF.

These run against the generated two-page report.pdf and the docling
document converted from it, so the item boxes under test are the ones
docling really produced. Ground truth is relational rather than literal —
a narrowed box must sit inside the item's box, be a fraction of its area,
and split where the source text wraps — because exact coordinates belong
to the PDF renderer, not to this package.
"""

import ast
import pathlib

from docling_core.types.doc.document import DoclingDocument
import pytest

from langextract_docling import provenance
from langextract_docling import provenance_serializer
from langextract_docling import word_layout

DATA_DIR = pathlib.Path(__file__).parent / "data"

# A phrase inside a paragraph that docling boxed as three full-width
# lines, and one that wraps from the end of a line onto the next.
PHRASE = "Ada Lovelace"
WRAPPING_PHRASE = "Charles Babbage during the year 1843"


@pytest.fixture(scope="module")
def report(report_pdf_path):
  """The serialized report PDF as (text, provenance_map)."""
  doc = DoclingDocument.load_from_json(DATA_DIR / "report_pdf.docling.json")
  serializer = provenance_serializer.ProvenanceMarkdownSerializer(doc=doc)
  return serializer.serialize_with_provenance()


@pytest.fixture
def layout(report_pdf_path):
  with word_layout.PdfCharLayout.from_path(report_pdf_path) as open_layout:
    yield open_layout


def _rectangle(bbox):
  """Returns a docling (l, t, r, b) box as (left, low, right, high)."""
  left, top, right, bottom = bbox
  return (
      min(left, right),
      min(top, bottom),
      max(left, right),
      max(top, bottom),
  )


def _contains(outer, inner, slack=1.0):
  """True when `inner` sits inside `outer`, allowing a point of slack."""
  outer_box, inner_box = _rectangle(outer), _rectangle(inner)
  return (
      inner_box[0] >= outer_box[0] - slack
      and inner_box[1] >= outer_box[1] - slack
      and inner_box[2] <= outer_box[2] + slack
      and inner_box[3] <= outer_box[3] + slack
  )


def _area(bbox):
  left, low, right, high = _rectangle(bbox)
  return (right - left) * (high - low)


def _narrow(report, phrase, layout=None):
  text, pmap = report
  start = text.index(phrase)
  return pmap.narrow(start, start + len(phrase), layout)


def _item_locations(report, phrase):
  text, pmap = report
  start = text.index(phrase)
  return [
      loc
      for span in pmap.lookup(start, start + len(phrase))
      for loc in span.locations
  ]


class TestNarrowedBoxes:

  def test_phrase_is_boxed_inside_its_item(self, report, layout):
    (sub,) = _narrow(report, PHRASE, layout)
    (item_location,) = _item_locations(report, PHRASE)
    assert sub.exact
    for location in sub.locations:
      assert _contains(item_location.bbox, location.bbox)

  def test_phrase_box_is_a_fraction_of_the_item_box(self, report, layout):
    (sub,) = _narrow(report, PHRASE, layout)
    (item_location,) = _item_locations(report, PHRASE)
    narrowed = sum(_area(location.bbox) for location in sub.locations)
    assert 0 < narrowed < 0.25 * _area(item_location.bbox)

  def test_page_and_coordinate_origin_are_preserved(self, report, layout):
    (sub,) = _narrow(report, PHRASE, layout)
    (item_location,) = _item_locations(report, PHRASE)
    for location in sub.locations:
      assert location.page_no == item_location.page_no
      assert location.coord_origin == item_location.coord_origin

  def test_charspans_stay_within_the_narrowed_range(self, report, layout):
    (sub,) = _narrow(report, PHRASE, layout)
    for location in sub.locations:
      assert sub.charspan[0] <= location.charspan[0]
      assert location.charspan[1] <= sub.charspan[1]

  def test_a_heading_narrows_too(self, report, layout):
    (sub,) = _narrow(report, "Introduction", layout)
    (item_location,) = _item_locations(report, "Introduction")
    assert sub.exact
    for location in sub.locations:
      assert _contains(item_location.bbox, location.bbox)

  def test_a_bullet_narrows_within_its_list_item(self, report, layout):
    (sub,) = _narrow(report, "Bernoulli numbers", layout)
    assert sub.exact
    assert sub.text == "Bernoulli numbers"
    assert len(sub.locations) == 1


class TestWrappedText:
  """Text crossing a line break is boxed once per line, not once in total."""

  def test_one_location_per_line(self, report, layout):
    (sub,) = _narrow(report, WRAPPING_PHRASE, layout)
    assert len(sub.locations) == 2

  def test_lines_are_vertically_separated(self, report, layout):
    (sub,) = _narrow(report, WRAPPING_PHRASE, layout)
    first, second = (_rectangle(loc.bbox) for loc in sub.locations)
    assert first[1] > second[3] or second[1] > first[3]

  def test_charspans_partition_the_phrase_in_reading_order(
      self, report, layout
  ):
    (sub,) = _narrow(report, WRAPPING_PHRASE, layout)
    first, second = (loc.charspan for loc in sub.locations)
    assert first[0] == sub.charspan[0]
    assert second[1] == sub.charspan[1]
    assert first[1] <= second[0], "line charspans must not overlap"

  def test_every_line_stays_inside_the_item(self, report, layout):
    (sub,) = _narrow(report, WRAPPING_PHRASE, layout)
    (item_location,) = _item_locations(report, WRAPPING_PHRASE)
    for location in sub.locations:
      assert _contains(item_location.bbox, location.bbox)


class TestSources:

  def test_bytes_and_path_layouts_agree(self, report, report_pdf_path):
    from_path = word_layout.PdfCharLayout.from_path(report_pdf_path)
    from_bytes = word_layout.PdfCharLayout.from_bytes(
        report_pdf_path.read_bytes()
    )
    try:
      assert _narrow(report, PHRASE, from_path) == _narrow(
          report, PHRASE, from_bytes
      )
    finally:
      from_path.close()
      from_bytes.close()

  def test_closing_twice_is_harmless(self, report_pdf_path):
    closed = word_layout.PdfCharLayout.from_path(report_pdf_path)
    closed.close()
    closed.close()


class TestDegradation:
  """Every failure keeps the item-level box rather than inventing one."""

  def test_missing_pdf_falls_back_to_the_item(self, report, tmp_path):
    with word_layout.PdfCharLayout.from_path(tmp_path / "absent.pdf") as gone:
      (sub,) = _narrow(report, PHRASE, gone)
    assert not sub.exact
    assert list(sub.locations) == _item_locations(report, PHRASE)

  def test_unreadable_bytes_fall_back_to_the_item(self, report):
    with word_layout.PdfCharLayout.from_bytes(b"not a pdf") as broken:
      (sub,) = _narrow(report, PHRASE, broken)
    assert not sub.exact

  def test_page_the_pdf_does_not_have_is_not_located(self, layout):
    location = provenance.SourceLocation(
        page_no=99,
        bbox=(0.0, 100.0, 200.0, 80.0),
        coord_origin="BOTTOMLEFT",
        charspan=(0, 5),
    )
    assert layout.locate(location, "Hello", 0, 5) == ()

  def test_box_holding_other_text_is_not_located(self, report, layout):
    (item_location,) = _item_locations(report, PHRASE)
    assert layout.locate(item_location, "wholly unrelated wording", 0, 24) == ()

  def test_empty_range_is_not_located(self, report, layout):
    (item_location,) = _item_locations(report, PHRASE)
    text, _ = report
    assert layout.locate(item_location, text, 5, 5) == ()


class TestImportLightness:
  """The layout reads PDFs, so it needs neither docling nor eager pdfium."""

  def _imports(self, top_level_only):
    tree = ast.parse(pathlib.Path(word_layout.__file__).read_text())
    nodes = tree.body if top_level_only else ast.walk(tree)
    imported = set()
    for node in nodes:
      if isinstance(node, ast.Import):
        imported.update(alias.name for alias in node.names)
      elif isinstance(node, ast.ImportFrom):
        imported.add(node.module or "")
    return imported

  def test_docling_is_not_imported(self):
    offenders = {
        module
        for module in self._imports(top_level_only=False)
        if module.startswith("docling")
    }
    assert not offenders, f"docling imported: {offenders}"

  def test_pypdfium2_is_imported_lazily(self):
    # Importing the package must not require the PDF reader, which only
    # matters once an extraction is actually narrowed.
    assert "pypdfium2" not in self._imports(top_level_only=True)


class TestCoordinateOrigins:
  """Boxes come back in whichever origin the item-level location used."""

  def _page_height(self, report_pdf_path):
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(report_pdf_path))
    try:
      return pdf[0].get_size()[1]
    finally:
      pdf.close()

  def _flip(self, bbox, height):
    """Swaps a box between the two origins by mirroring its y values."""
    left, top, right, bottom = bbox
    return (left, height - top, right, height - bottom)

  def test_topleft_location_yields_the_same_box_topleft(
      self, report, layout, report_pdf_path
  ):
    height = self._page_height(report_pdf_path)
    text, pmap = report
    start = text.index(PHRASE)
    (span,) = pmap.lookup(start, start + len(PHRASE))
    covered = span.item_charspan(start, start + len(PHRASE))
    (bottom_left,) = span.locations
    top_left = provenance.SourceLocation(
        page_no=bottom_left.page_no,
        bbox=self._flip(bottom_left.bbox, height),
        coord_origin="TOPLEFT",
        charspan=bottom_left.charspan,
    )

    from_bottom = layout.locate(bottom_left, span.item_text, *covered)
    from_top = layout.locate(top_left, span.item_text, *covered)

    assert from_bottom, "the phrase must be located to compare origins"
    assert len(from_top) == len(from_bottom)
    for bottom_box, top_box in zip(from_bottom, from_top):
      assert top_box.coord_origin == "TOPLEFT"
      assert self._flip(top_box.bbox, height) == pytest.approx(bottom_box.bbox)
