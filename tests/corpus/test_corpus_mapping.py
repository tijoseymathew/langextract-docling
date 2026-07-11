"""Corpus-driven tests of the provenance mapping (test-spec §4, §9).

Every case runs the structural checks (three-way text invariant, span
integrity, gap probes) plus its manifest probes; span and straddle probes
also run as enrichment probes through _attach_provenance with injected
char_intervals.
"""

from langextract.core import data
import pytest

from langextract_docling import provenance_serializer
import langextract_docling as lx
from tests import corpus
from tests.corpus import reference_chunker

DELIM = "\n\n"

CASE_IDS = corpus.case_ids()
_PROBES = [
    (case_id, index, probe)
    for case_id in CASE_IDS
    for index, probe in enumerate(corpus.load_case(case_id).probes)
]


def _probe_params(*kinds):
  return [
      pytest.param(case_id, probe, id=f"{case_id}-p{index}-{probe['kind']}")
      for case_id, index, probe in _PROBES
      if probe["kind"] in kinds
  ]


_SERIALIZED_CACHE: dict[str, tuple[corpus.Case, str, object]] = {}


def _serialized(case_id: str):
  """Serializes a case once; returns (case, text, provenance_map)."""
  if case_id not in _SERIALIZED_CACHE:
    case = corpus.load_case(case_id)
    serializer = provenance_serializer.ProvenanceMarkdownSerializer(
        doc=case.doc
    )
    text, pmap = serializer.serialize_with_provenance(**case.serializer_kwargs)
    _SERIALIZED_CACHE[case_id] = (case, text, pmap)
  return _SERIALIZED_CACHE[case_id]


def _gaps(text: str, pmap) -> list[tuple[int, int]]:
  """Maximal runs of text offsets covered by no span, as intervals."""
  covered = set()
  for span in pmap.spans:
    covered.update(range(span.start, span.end))
  gaps: list[list[int]] = []
  for pos in sorted(set(range(len(text))) - covered):
    if gaps and gaps[-1][-1] == pos - 1:
      gaps[-1][-1] = pos
    else:
      gaps.append([pos, pos])
  return [(lo, hi + 1) for lo, hi in gaps]


@pytest.fixture(params=CASE_IDS)
def case_id(request):
  return request.param


class TestTextInvariant:
  """spec §11.1: new serializer text == snapshot == reference chunker."""

  def test_three_way_invariant(self, case_id):
    case, text, _ = _serialized(case_id)
    chunks = reference_chunker.HierarchicalMarkdownChunker().chunk(
        case.doc, **case.serializer_kwargs
    )
    reference = DELIM.join(chunk.text for chunk in chunks)
    assert text == case.snapshot, "serializer diverged from snapshot"
    assert reference == case.snapshot, "reference chunker != snapshot"


class TestSpanIntegrity:
  """spec §11.2: spans are sorted, in-bounds, and never partially overlap."""

  def test_spans_sorted_and_within_text(self, case_id):
    _, text, pmap = _serialized(case_id)
    assert [s.start for s in pmap.spans] == sorted(s.start for s in pmap.spans)
    for span in pmap.spans:
      assert 0 <= span.start < span.end <= len(text)

  def test_spans_disjoint_or_identical(self, case_id):
    _, _, pmap = _serialized(case_id)
    for a, b in zip(pmap.spans, pmap.spans[1:]):
      assert (a.start, a.end) == (b.start, b.end) or a.end <= b.start


class TestGapProbes:
  """Implicit for every case: gaps are exactly the delimiter, unmapped."""

  def test_gaps_are_delimiters_and_lookup_empty(self, case_id):
    _, text, pmap = _serialized(case_id)
    for start, end in _gaps(text, pmap):
      assert text[start:end] == DELIM
      assert pmap.lookup(start, end) == []

  def test_lookup_outside_text_is_empty(self, case_id):
    _, text, pmap = _serialized(case_id)
    assert pmap.lookup(len(text), len(text) + 10) == []
    assert pmap.lookup(0, 0) == []


class TestSpanProbes:
  """spec §4: the marker's span maps to exactly the recorded item."""

  @pytest.mark.parametrize("case_id_, probe", _probe_params("span"))
  def test_marker_maps_to_expected_item(self, case_id_, probe):
    _, text, pmap = _serialized(case_id_)
    start, end = corpus.resolve_probe(probe, text)
    (span,) = pmap.lookup(start, end)
    expect = probe["expect"]
    assert span.doc_item_ref == expect["doc_item_ref"]
    assert span.doc_item_label == expect["label"]
    assert [loc.to_dict() for loc in span.locations] == expect["locations"]
    assert span.start <= start and end <= span.end


class TestStraddleProbes:
  """spec §4: intervals across items return exactly the straddled refs."""

  @pytest.mark.parametrize("case_id_, probe", _probe_params("straddle"))
  def test_straddle_returns_expected_refs(self, case_id_, probe):
    _, text, pmap = _serialized(case_id_)
    start, end = corpus.resolve_probe(probe, text)
    refs = {span.doc_item_ref for span in pmap.lookup(start, end)}
    assert refs == set(probe["expect_refs"])


class TestEnrichmentProbes:
  """spec §11.4: _attach_provenance mirrors lookup() for char_intervals."""

  def _enrich(self, text, pmap, char_interval):
    extraction = data.Extraction(
        extraction_class="probe",
        extraction_text="probe",
        char_interval=char_interval,
    )
    doc = data.AnnotatedDocument(text=text, extractions=[extraction])
    lx._attach_provenance(doc, pmap)
    return extraction

  @pytest.mark.parametrize("case_id_, probe", _probe_params("span", "straddle"))
  def test_extraction_provenance_equals_lookup(self, case_id_, probe):
    _, text, pmap = _serialized(case_id_)
    start, end = corpus.resolve_probe(probe, text)
    interval = data.CharInterval(start_pos=start, end_pos=end)
    extraction = self._enrich(text, pmap, interval)
    assert extraction.provenance == pmap.lookup(start, end)
    assert extraction.provenance, "probe interval must map to >=1 span"

  def test_unaligned_extraction_gets_none(self, case_id):
    _, text, pmap = _serialized(case_id)
    extraction = self._enrich(text, pmap, None)
    assert extraction.provenance is None

  def test_zero_length_interval_maps_to_nothing(self, case_id):
    _, text, pmap = _serialized(case_id)
    interval = data.CharInterval(start_pos=0, end_pos=0)
    extraction = self._enrich(text, pmap, interval)
    assert extraction.provenance == []
