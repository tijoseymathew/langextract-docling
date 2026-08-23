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


def _overlaps(first: tuple[int, int], second: tuple[int, int]) -> bool:
  """True when two half-open char ranges share a character."""
  return first[0] < second[1] and second[0] < first[1]


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


class TestGroupProbes:
  """spec §5 note: one SpanProvenance per contributing DocItem.

  Every listed marker resolves into the same [start, end) range, which
  carries exactly one span per expected ref.
  """

  @pytest.mark.parametrize("case_id_, probe", _probe_params("group"))
  def test_shared_range_with_one_span_per_ref(self, case_id_, probe):
    _, text, pmap = _serialized(case_id_)
    intervals = corpus.resolve_probe(probe, text)
    shared_ranges = set()
    for marker, (start, end) in intervals.items():
      spans = pmap.lookup(start, end)
      refs = [span.doc_item_ref for span in spans]
      assert sorted(refs) == sorted(probe["expect_refs"]), marker
      assert len({(s.start, s.end) for s in spans}) == 1, marker
      shared_ranges.add((spans[0].start, spans[0].end))
    assert len(shared_ranges) == 1, "markers resolved to different ranges"


class TestSubItemProbes:
  """Narrowing every probe below item level, with no fixture of its own.

  A span probe's interval is exactly its marker, so the marker is also
  the ground truth for the text narrow() must report — no new manifest
  entries needed. Items with no text of their own (tables, pictures)
  cannot be narrowed and must say so instead of guessing.
  """

  def _narrowed(self, case_id_, start, end):
    _, _, pmap = _serialized(case_id_)
    return pmap.lookup(start, end), pmap.narrow(start, end)

  @pytest.mark.parametrize("case_id_, probe", _probe_params("span"))
  def test_marker_narrows_to_itself(self, case_id_, probe):
    _, text, pmap = _serialized(case_id_)
    start, end = corpus.resolve_probe(probe, text)
    needle = probe.get("marker") or probe["text"]
    (span,), (sub,) = self._narrowed(case_id_, start, end)

    assert sub.doc_item_ref == span.doc_item_ref
    assert sub.doc_item_label == span.doc_item_label
    if span.item_text:
      assert sub.text == needle
      assert span.item_text[sub.charspan[0] : sub.charspan[1]] == sub.text
    else:
      assert not sub.exact, "an item with no text cannot be narrowed"
      assert sub.locations == span.locations

  @pytest.mark.parametrize("case_id_, probe", _probe_params("span"))
  def test_only_locations_holding_the_narrowed_text_survive(
      self, case_id_, probe
  ):
    _, text, pmap = _serialized(case_id_)
    start, end = corpus.resolve_probe(probe, text)
    (span,), (sub,) = self._narrowed(case_id_, start, end)
    if not span.item_text:
      assert sub.locations == span.locations
      return
    assert sub.locations == tuple(
        location
        for location in span.locations
        if _overlaps(location.charspan, sub.charspan)
    )

  @pytest.mark.parametrize("case_id_, probe", _probe_params("span"))
  def test_geometry_is_never_narrowed_without_a_layout(self, case_id_, probe):
    _, text, pmap = _serialized(case_id_)
    start, end = corpus.resolve_probe(probe, text)
    (span,), (sub,) = self._narrowed(case_id_, start, end)
    assert set(sub.locations) <= set(span.locations), "invented geometry"
    # exact means nothing was left at item granularity: true only when no
    # box survived at all, and the text itself did narrow.
    assert sub.exact == (not sub.locations and bool(span.item_text))

  @pytest.mark.parametrize("case_id_, probe", _probe_params("group"))
  def test_marker_narrows_within_its_group(self, case_id_, probe):
    _, text, pmap = _serialized(case_id_)
    intervals = corpus.resolve_probe(probe, text)
    for marker, (start, end) in intervals.items():
      spans, subs = self._narrowed(case_id_, start, end)
      assert len(spans) == len(probe["expect_refs"]), marker
      assert subs, marker
      assert {sub.doc_item_ref for sub in subs} <= set(
          probe["expect_refs"]
      ), marker
      matched = [sub for sub in subs if sub.text == marker]
      if matched:
        # The marker sits in an item with text of its own: that item
        # alone is reported, and its siblings in the group drop out.
        assert len(matched) == 1, marker
        for other in subs:
          if other is not matched[0]:
            assert other.text == "" and not other.exact, marker
      else:
        # The marker is inside a table cell: docling gives the table no
        # text to narrow by, so the whole table is reported instead.
        assert all(not sub.text and not sub.exact for sub in subs), marker

  @pytest.mark.parametrize("case_id_, probe", _probe_params("straddle"))
  def test_straddle_narrows_to_the_straddled_items(self, case_id_, probe):
    _, text, pmap = _serialized(case_id_)
    start, end = corpus.resolve_probe(probe, text)
    _, subs = self._narrowed(case_id_, start, end)
    assert {sub.doc_item_ref for sub in subs} <= set(probe["expect_refs"])
    assert subs, "a straddling interval must reach at least one item"

  def test_gaps_narrow_to_nothing(self, case_id):
    _, text, pmap = _serialized(case_id)
    for start, end in _gaps(text, pmap):
      assert pmap.narrow(start, end) == []

  def test_zero_length_interval_narrows_to_nothing(self, case_id):
    _, _, pmap = _serialized(case_id)
    assert pmap.narrow(0, 0) == []


class TestAbsentProbes:
  """spec §4: excluded/furniture markers never reach the output."""

  @pytest.mark.parametrize("case_id_, probe", _probe_params("absent"))
  def test_marker_not_in_serialized_text(self, case_id_, probe):
    _, text, pmap = _serialized(case_id_)
    assert probe["marker"] not in text
    refs = {span.doc_item_ref for span in pmap.spans}
    assert probe.get("ref") not in refs


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

  @pytest.mark.parametrize("case_id_, probe", _probe_params("span", "straddle"))
  def test_extraction_sub_provenance_equals_narrow(self, case_id_, probe):
    _, text, pmap = _serialized(case_id_)
    start, end = corpus.resolve_probe(probe, text)
    interval = data.CharInterval(start_pos=start, end_pos=end)
    extraction = self._enrich(text, pmap, interval)
    assert extraction.sub_provenance == pmap.narrow(start, end)
    assert extraction.sub_provenance, "probe interval must reach >=1 item"

  def test_unaligned_extraction_gets_none(self, case_id):
    _, text, pmap = _serialized(case_id)
    extraction = self._enrich(text, pmap, None)
    assert extraction.provenance is None
    assert extraction.sub_provenance is None

  def test_zero_length_interval_maps_to_nothing(self, case_id):
    _, text, pmap = _serialized(case_id)
    interval = data.CharInterval(start_pos=0, end_pos=0)
    extraction = self._enrich(text, pmap, interval)
    assert extraction.provenance == []
    assert extraction.sub_provenance == []
