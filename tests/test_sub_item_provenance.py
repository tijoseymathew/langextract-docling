"""Tests for narrowing provenance below the document-item level.

Geometry is out of scope here: layouts are stubbed so the offset
arithmetic — markdown offsets to item text, item text to the right
ProvenanceItem, and the fallbacks when either cannot be established — is
tested on its own. tests/test_word_layout.py covers the real thing.
"""

import json
import pathlib

from docling_core.types.doc.document import DoclingDocument
import pytest

from langextract_docling import provenance
from langextract_docling import provenance_serializer

DATA_DIR = pathlib.Path(__file__).parent / "data"

ITEM_TEXT = "Ada Lovelace wrote the first algorithm for the engine."


def _location(
    page_no=1, charspan=(0, len(ITEM_TEXT)), bbox=(10.0, 90.0, 200.0, 70.0)
):
  return provenance.SourceLocation(
      page_no=page_no,
      bbox=bbox,
      coord_origin="BOTTOMLEFT",
      charspan=charspan,
  )


def _verbatim_span(start=0, locations=(_location(),), item_text=ITEM_TEXT):
  """A span whose markdown is the item's text, unescaped and unprefixed."""
  return provenance.SpanProvenance(
      start=start,
      end=start + len(item_text),
      doc_item_ref="#/texts/0",
      doc_item_label="text",
      locations=tuple(locations),
      item_text=item_text,
      text_segments=(
          provenance.TextSegment(
              start=start, item_start=0, length=len(item_text)
          ),
      ),
  )


def _serialize_fixture(name):
  doc = DoclingDocument.load_from_json(DATA_DIR / f"{name}.docling.json")
  serializer = provenance_serializer.ProvenanceMarkdownSerializer(doc=doc)
  return serializer.serialize_with_provenance()


@pytest.fixture(scope="module")
def report():
  """The PDF-derived fixture: items carry pages, bboxes and charspans."""
  return _serialize_fixture("report_pdf")


@pytest.fixture(scope="module")
def notes():
  """The markdown-derived fixture: items have no physical location."""
  return _serialize_fixture("notes_md")


class _StubLayout:
  """A layout that reports one box per call and records its arguments."""

  def __init__(self, locations=None):
    self._locations = locations
    self.calls = []

  def locate(self, location, item_text, start, end):
    self.calls.append((location, item_text, start, end))
    if self._locations is None:
      return (
          provenance.SourceLocation(
              page_no=location.page_no,
              bbox=(1.0, 2.0, 3.0, 4.0),
              coord_origin=location.coord_origin,
              charspan=(start, end),
          ),
      )
    return self._locations


class TestItemCharspan:
  """Markdown offsets narrow to offsets in the item's own text."""

  def test_verbatim_span_maps_offsets_unchanged(self):
    span = _verbatim_span(start=100)
    assert span.item_charspan(104, 112) == (4, 12)

  def test_span_without_segments_maps_to_nothing(self):
    span = provenance.SpanProvenance(
        start=0, end=10, doc_item_ref="#/tables/0", doc_item_label="table"
    )
    assert span.item_charspan(0, 10) is None

  def test_interval_outside_the_segments_maps_to_nothing(self):
    span = _verbatim_span(start=10)
    assert span.item_charspan(0, 5) is None

  def test_to_dict_omits_the_join_machinery(self):
    span = _verbatim_span()
    assert "item_text" not in span.to_dict()
    assert "text_segments" not in span.to_dict()


class TestNarrowToItemText:
  """narrow() reports the characters an interval actually covers."""

  def test_reports_the_covered_text_and_charspan(self):
    pmap = provenance.ProvenanceMap([_verbatim_span()])
    (sub,) = pmap.narrow(0, 12)
    assert sub.charspan == (0, 12)
    assert sub.text == "Ada Lovelace"
    assert sub.doc_item_ref == "#/texts/0"
    assert sub.doc_item_label == "text"

  def test_text_is_the_source_not_the_markdown(self):
    # The markdown escaped the underscore; the source text never had one.
    span = provenance.SpanProvenance(
        start=0,
        end=4,
        doc_item_ref="#/texts/0",
        doc_item_label="text",
        item_text="a_b",
        text_segments=(
            provenance.TextSegment(start=0, item_start=0, length=1),
            provenance.TextSegment(start=2, item_start=1, length=2),
        ),
    )
    (sub,) = provenance.ProvenanceMap([span]).narrow(0, 4)
    assert sub.text == "a_b"

  def test_zero_length_interval_narrows_to_nothing(self):
    pmap = provenance.ProvenanceMap([_verbatim_span()])
    assert pmap.narrow(5, 5) == []

  def test_to_dict_round_trips_through_json(self):
    pmap = provenance.ProvenanceMap([_verbatim_span()])
    (sub,) = pmap.narrow(0, 12)
    as_dict = sub.to_dict()
    assert json.loads(json.dumps(as_dict)) == {
        "doc_item_ref": "#/texts/0",
        "doc_item_label": "text",
        "charspan": [0, 12],
        "text": "Ada Lovelace",
        "locations": [_location().to_dict()],
        "exact": False,
    }


class TestNarrowSelectsLocations:
  """Only the ProvenanceItems holding the covered characters are kept."""

  def test_location_whose_charspan_misses_the_range_is_dropped(self):
    first_line = _location(page_no=1, charspan=(0, 20))
    second_line = _location(page_no=2, charspan=(20, len(ITEM_TEXT)))
    span = _verbatim_span(locations=(first_line, second_line))
    (sub,) = provenance.ProvenanceMap([span]).narrow(0, 12)
    assert [loc.page_no for loc in sub.locations] == [1]

  def test_range_across_two_locations_keeps_both(self):
    first_line = _location(page_no=1, charspan=(0, 20))
    second_line = _location(page_no=2, charspan=(20, len(ITEM_TEXT)))
    span = _verbatim_span(locations=(first_line, second_line))
    (sub,) = provenance.ProvenanceMap([span]).narrow(15, 25)
    assert [loc.page_no for loc in sub.locations] == [1, 2]

  def test_item_without_locations_still_narrows_its_text(self):
    span = _verbatim_span(locations=())
    (sub,) = provenance.ProvenanceMap([span]).narrow(0, 12)
    assert sub.locations == ()
    assert sub.text == "Ada Lovelace"
    assert sub.exact, "nothing was left un-narrowed"


class TestNarrowWithLayout:
  """A layout replaces item-level boxes with the covered characters'."""

  def test_layout_boxes_replace_the_item_box(self):
    layout = _StubLayout()
    pmap = provenance.ProvenanceMap([_verbatim_span()])
    (sub,) = pmap.narrow(4, 12, layout)
    assert sub.exact
    assert [loc.bbox for loc in sub.locations] == [(1.0, 2.0, 3.0, 4.0)]

  def test_layout_is_asked_for_exactly_the_covered_characters(self):
    layout = _StubLayout()
    provenance.ProvenanceMap([_verbatim_span()]).narrow(4, 12, layout)
    (location, item_text, start, end) = layout.calls[0]
    assert (start, end) == (4, 12)
    assert item_text == ITEM_TEXT
    assert location.page_no == 1

  def test_layout_that_cannot_place_the_text_falls_back_to_the_item(self):
    layout = _StubLayout(locations=())
    span = _verbatim_span()
    (sub,) = provenance.ProvenanceMap([span]).narrow(4, 12, layout)
    assert not sub.exact
    assert sub.locations == span.locations
    assert sub.charspan == (4, 12), "the text still narrows without geometry"

  def test_without_a_layout_boxes_stay_item_level(self):
    span = _verbatim_span()
    (sub,) = provenance.ProvenanceMap([span]).narrow(4, 12)
    assert not sub.exact
    assert sub.locations == span.locations


class TestNarrowWithoutAlignment:
  """Spans carrying no text (tables, pictures) degrade to the whole item."""

  def _table_span(self):
    return provenance.SpanProvenance(
        start=0,
        end=40,
        doc_item_ref="#/tables/0",
        doc_item_label="table",
        locations=(_location(charspan=(0, 0)),),
    )

  def test_reports_the_item_as_a_whole(self):
    span = self._table_span()
    (sub,) = provenance.ProvenanceMap([span]).narrow(5, 20)
    assert sub.doc_item_ref == "#/tables/0"
    assert sub.charspan == (0, 0)
    assert sub.text == ""
    assert not sub.exact

  def test_keeps_every_location_of_the_item(self):
    span = self._table_span()
    (sub,) = provenance.ProvenanceMap([span]).narrow(5, 20)
    assert sub.locations == span.locations


class TestNarrowDropsUntouchedGroupMembers:
  """Items sharing a serialized range are separated by their own text."""

  def _list_group(self):
    """Two list items serialized as "- alpha one\n- beta two"."""
    markdown = "- alpha one\n- beta two"
    return provenance.ProvenanceMap([
        provenance.SpanProvenance(
            start=0,
            end=len(markdown),
            doc_item_ref="#/texts/0",
            doc_item_label="list_item",
            locations=(_location(charspan=(0, 9)),),
            item_text="alpha one",
            text_segments=(
                provenance.TextSegment(start=2, item_start=0, length=9),
            ),
        ),
        provenance.SpanProvenance(
            start=0,
            end=len(markdown),
            doc_item_ref="#/texts/1",
            doc_item_label="list_item",
            locations=(_location(page_no=2, charspan=(0, 8)),),
            item_text="beta two",
            text_segments=(
                provenance.TextSegment(start=14, item_start=0, length=8),
            ),
        ),
    ])

  def test_lookup_returns_the_whole_group(self):
    pmap = self._list_group()
    assert len(pmap.lookup(2, 7)) == 2

  def test_narrow_returns_only_the_item_the_interval_reaches(self):
    pmap = self._list_group()
    (sub,) = pmap.narrow(2, 7)
    assert sub.doc_item_ref == "#/texts/0"
    assert sub.text == "alpha"

  def test_interval_across_both_items_keeps_both(self):
    pmap = self._list_group()
    assert [sub.doc_item_ref for sub in pmap.narrow(2, 20)] == [
        "#/texts/0",
        "#/texts/1",
    ]

  def test_interval_on_bullet_syntax_alone_reaches_no_item(self):
    pmap = self._list_group()
    assert pmap.narrow(12, 14) == []


class TestNarrowOverRealDocuments:
  """The same narrowing over documents docling actually produced."""

  def _narrow(self, serialized, phrase):
    text, pmap = serialized
    start = text.index(phrase)
    return pmap.narrow(start, start + len(phrase))

  def test_heading_prefix_does_not_shift_the_charspan(self, report):
    (sub,) = self._narrow(report, "Introduction")
    assert sub.charspan == (0, 12)
    assert sub.text == "Introduction"

  def test_phrase_inside_a_paragraph_narrows_to_itself(self, report):
    (sub,) = self._narrow(report, "Ada Lovelace")
    assert sub.text == "Ada Lovelace"
    assert sub.doc_item_label == "text"
    assert sub.charspan[1] - sub.charspan[0] == len("Ada Lovelace")

  def test_bullet_narrows_to_its_own_list_item(self, report):
    subs = self._narrow(report, "Bernoulli numbers")
    assert [sub.text for sub in subs] == ["Bernoulli numbers"]
    assert subs[0].doc_item_label == "list_item"

  def test_markdown_source_narrows_without_any_location(self, notes):
    (sub,) = self._narrow(notes, "Map the offsets")
    assert sub.text == "Map the offsets"
    assert sub.locations == ()

  def test_table_falls_back_to_the_whole_table(self, report):
    (sub,) = self._narrow(report, "Mathematician")
    assert sub.doc_item_ref.startswith("#/tables/")
    assert not sub.exact
    assert sub.locations, "the table's own box is still reported"
