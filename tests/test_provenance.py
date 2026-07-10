"""Tests for langextract_docling.provenance data types."""

import json

from langextract.core import data
import pytest

from langextract_docling import provenance


def _span(start, end, ref="#/texts/0", label="text", locations=()):
  return provenance.SpanProvenance(
      start=start,
      end=end,
      doc_item_ref=ref,
      doc_item_label=label,
      locations=tuple(locations),
  )


def _location(page_no=1):
  return provenance.SourceLocation(
      page_no=page_no,
      bbox=(1.0, 2.0, 3.0, 4.0),
      coord_origin="BOTTOMLEFT",
      charspan=(0, 10),
  )


class TestDataTypes:

  def test_source_location_is_frozen(self):
    loc = _location()
    with pytest.raises(Exception):
      loc.page_no = 2

  def test_span_provenance_is_frozen(self):
    span = _span(0, 5)
    with pytest.raises(Exception):
      span.start = 1

  def test_source_location_to_dict_is_json_serializable(self):
    loc = _location()
    as_dict = loc.to_dict()
    assert json.loads(json.dumps(as_dict)) == {
        "page_no": 1,
        "bbox": [1.0, 2.0, 3.0, 4.0],
        "coord_origin": "BOTTOMLEFT",
        "charspan": [0, 10],
    }

  def test_span_provenance_to_dict_includes_locations(self):
    span = _span(3, 9, locations=[_location(page_no=7)])
    as_dict = span.to_dict()
    assert as_dict["start"] == 3
    assert as_dict["end"] == 9
    assert as_dict["doc_item_ref"] == "#/texts/0"
    assert as_dict["doc_item_label"] == "text"
    assert as_dict["locations"][0]["page_no"] == 7
    json.dumps(as_dict)  # must not raise


class TestProvenanceMap:

  def test_spans_are_sorted_by_start(self):
    spans = [_span(10, 15), _span(0, 5)]
    pmap = provenance.ProvenanceMap(spans)
    assert [s.start for s in pmap.spans] == [0, 10]

  def test_lookup_inside_one_span(self):
    pmap = provenance.ProvenanceMap([_span(0, 5), _span(7, 12)])
    assert pmap.lookup(8, 10) == [pmap.spans[1]]

  def test_lookup_straddling_two_spans(self):
    pmap = provenance.ProvenanceMap([_span(0, 5), _span(7, 12)])
    assert pmap.lookup(4, 8) == [pmap.spans[0], pmap.spans[1]]

  def test_lookup_in_delimiter_gap_returns_empty(self):
    pmap = provenance.ProvenanceMap([_span(0, 5), _span(7, 12)])
    assert pmap.lookup(5, 7) == []

  def test_lookup_zero_length_interval_returns_empty(self):
    pmap = provenance.ProvenanceMap([_span(0, 5)])
    assert pmap.lookup(3, 3) == []

  def test_lookup_boundaries_are_half_open(self):
    pmap = provenance.ProvenanceMap([_span(0, 5), _span(7, 12)])
    # [5, 7) touches only the exclusive end of the first span and the gap
    assert pmap.lookup(5, 7) == []
    # [4, 5) still overlaps the first span
    assert pmap.lookup(4, 5) == [pmap.spans[0]]
    # [7, 8) overlaps the second span at its inclusive start
    assert pmap.lookup(7, 8) == [pmap.spans[1]]

  def test_lookup_group_spans_sharing_one_range(self):
    # A serialized ListGroup emits one SpanProvenance per contributing
    # DocItem, all sharing the same [start, end) range.
    group = [
        _span(0, 20, ref="#/texts/1"),
        _span(0, 20, ref="#/texts/2"),
        _span(0, 20, ref="#/texts/3"),
    ]
    pmap = provenance.ProvenanceMap(group + [_span(22, 30)])
    assert pmap.lookup(5, 10) == group

  def test_lookup_range_covering_everything(self):
    spans = [_span(0, 5), _span(7, 12), _span(14, 20)]
    pmap = provenance.ProvenanceMap(spans)
    assert pmap.lookup(0, 100) == spans

  def test_empty_map_lookup(self):
    pmap = provenance.ProvenanceMap([])
    assert pmap.lookup(0, 10) == []

  def test_to_dicts(self):
    pmap = provenance.ProvenanceMap([_span(0, 5)])
    dicts = pmap.to_dicts()
    assert dicts == [pmap.spans[0].to_dict()]
    json.dumps(dicts)  # must not raise

  def test_source_defaults_to_none(self):
    assert provenance.ProvenanceMap([]).source is None

  def test_source_is_stored(self):
    pmap = provenance.ProvenanceMap([], source="/path/to/paper.pdf")
    assert pmap.source == "/path/to/paper.pdf"


class TestProvenanceToDict:

  def _annotated_doc(self):
    extraction_with_prov = data.Extraction(
        extraction_class="person",
        extraction_text="Ada",
        char_interval=data.CharInterval(start_pos=1, end_pos=4),
    )
    extraction_without_prov = data.Extraction(
        extraction_class="person",
        extraction_text="Bob",
    )
    doc = data.AnnotatedDocument(
        text="0123456789",
        extractions=[extraction_with_prov, extraction_without_prov],
    )
    pmap = provenance.ProvenanceMap([_span(0, 5)], source="paper.pdf")
    extraction_with_prov.provenance = pmap.lookup(1, 4)
    extraction_without_prov.provenance = None
    doc.provenance_map = pmap
    return doc, pmap

  def test_round_trips_through_json(self):
    doc, pmap = self._annotated_doc()
    result = provenance.provenance_to_dict(doc)
    assert json.loads(json.dumps(result)) is not None

  def test_contains_span_table_and_source(self):
    doc, pmap = self._annotated_doc()
    result = provenance.provenance_to_dict(doc)
    assert result["source"] == "paper.pdf"
    assert result["spans"] == pmap.to_dicts()

  def test_maps_extraction_indices_to_span_dicts(self):
    doc, pmap = self._annotated_doc()
    result = provenance.provenance_to_dict(doc)
    assert result["extractions"][0] == [pmap.spans[0].to_dict()]
    assert result["extractions"][1] is None

  def test_document_without_provenance_map(self):
    doc = data.AnnotatedDocument(text="abc", extractions=[])
    result = provenance.provenance_to_dict(doc)
    assert result == {"source": None, "spans": [], "extractions": {}}
