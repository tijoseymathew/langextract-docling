"""Integrity checks for the provenance-mapping corpus (test-spec §8).

These tests validate the corpus itself — fixtures, snapshots, and the frozen
reference chunker — so a broken fixture never masquerades as a mapping bug.
"""

import pathlib

from docling_core.types.doc.document import ContentLayer
from docling_core.types.doc.document import DoclingDocument
import pytest

from langextract_docling import provenance_serializer
from tests import corpus
from tests.corpus import builders
from tests.corpus import generate
from tests.corpus import reference_chunker

DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
DELIM = "\n\n"

CASE_IDS = corpus.case_ids()

# Pre-corpus fixtures converted from real sources by tests/data/make_fixtures
# (a two-page PDF and a markdown file); they pin the freeze against documents
# whose golden markdown was produced by the original chunker pipeline.
LEGACY_FIXTURES = ["report_pdf", "notes_md"]


def _load_legacy(name: str) -> DoclingDocument:
  return DoclingDocument.load_from_json(DATA_DIR / f"{name}.docling.json")


def _reference_join(doc: DoclingDocument) -> str:
  chunks = reference_chunker.HierarchicalMarkdownChunker().chunk(doc)
  return DELIM.join(chunk.text for chunk in chunks)


class TestReferenceChunkerFreeze:
  """The frozen pre-change chunker anchors the text invariant (spec §6).

  serialize_with_provenance() promises text byte-identical to the chunker
  pipeline that existed before it; the frozen copy is that pipeline, so it
  must reproduce the legacy golden files and agree with today's serializer.
  """

  @pytest.mark.parametrize("name", LEGACY_FIXTURES)
  def test_reproduces_legacy_golden_files(self, name):
    golden = (DATA_DIR / f"{name}.golden.md").read_text()
    assert _reference_join(_load_legacy(name)) == golden

  @pytest.mark.parametrize("name", LEGACY_FIXTURES)
  def test_matches_new_serializer_text(self, name):
    doc = _load_legacy(name)
    serializer = provenance_serializer.ProvenanceMarkdownSerializer(doc=doc)
    text, _ = serializer.serialize_with_provenance()
    assert _reference_join(doc) == text


@pytest.fixture(params=CASE_IDS)
def case(request):
  return corpus.load_case(request.param)


def _item_texts(doc: DoclingDocument) -> list[str]:
  """All stored item texts markers can live in (incl. table cells)."""
  texts = [item.text for item in doc.texts]
  for table in doc.tables:
    texts.extend(cell.text for cell in table.data.table_cells)
  return texts


def _probe_markers(probe: dict) -> list[str]:
  """The unique-marker tokens a probe relies on (not occurrence texts)."""
  if probe["kind"] == "span":
    return [probe["marker"]] if "marker" in probe else []
  if probe["kind"] == "straddle":
    return [probe["from_marker"], probe["to_marker"]]
  if probe["kind"] == "group":
    return list(probe["markers"])
  if probe["kind"] == "absent":
    return []  # asserted separately: present in items, absent in snapshot
  raise ValueError(f"unknown probe kind: {probe['kind']!r}")


class TestManifestParity:
  """spec §8.1: manifest, files, and builder registry agree."""

  def test_case_ids_unique(self):
    assert len(CASE_IDS) == len(set(CASE_IDS))

  def test_manifest_matches_committed_files(self):
    files = {p.name for p in corpus.CORPUS_DIR.iterdir() if p.is_file()}
    expected = {"manifest.json"}
    for case_id in CASE_IDS:
      expected.add(f"{case_id}.docling.json")
      expected.add(f"{case_id}.expected.md.txt")
    assert files == expected

  def test_manifest_matches_builder_registry(self):
    built = builders.all_cases()
    assert set(built) == set(CASE_IDS)
    for entry in corpus.load_manifest()["cases"]:
      assert entry["builder"] == built[entry["case_id"]].builder


class TestFixtureValidity:
  """spec §8.2: fixtures load under the pinned docling-core, round-trip."""

  def test_load_dump_load_idempotent(self, case):
    dumped = case.doc.export_to_dict()
    reloaded = DoclingDocument.model_validate(dumped)
    assert reloaded.export_to_dict() == dumped


class TestMarkerDiscipline:
  """spec §8.3: markers occur exactly once in items and in the snapshot."""

  def test_probe_markers_unique_in_items_and_snapshot(self, case):
    for probe in case.probes:
      for marker in _probe_markers(probe):
        in_items = sum(t.count(marker) for t in _item_texts(case.doc))
        assert in_items == 1, f"{marker} occurs {in_items}x in item texts"
        in_snapshot = case.snapshot.count(marker)
        assert in_snapshot == 1, f"{marker} occurs {in_snapshot}x in snapshot"

  def test_absent_markers_in_items_but_not_snapshot(self, case):
    for probe in case.probes:
      if probe["kind"] != "absent":
        continue
      marker = probe["marker"]
      assert any(marker in t for t in _item_texts(case.doc))
      assert marker not in case.snapshot

  def test_occurrence_probes_have_declared_counts(self, case):
    by_text: dict[str, list[int]] = {}
    for probe in case.probes:
      if probe["kind"] == "span" and "occurrence" in probe:
        by_text.setdefault(probe["text"], []).append(probe["occurrence"])
    for text, occurrences in by_text.items():
      assert case.snapshot.count(text) == max(occurrences)


class TestGroundTruthSelfConsistency:
  """spec §8.4: manifest expectations resolve against the fixture itself."""

  def test_expected_refs_and_locations_match_document(self, case):
    items = {
        item.self_ref: item
        for item, _ in case.doc.iterate_items(
            with_groups=True,
            # Absent probes may point at furniture items.
            included_content_layers=set(ContentLayer),
        )
    }
    for probe in case.probes:
      expects = [probe["expect"]] if "expect" in probe else []
      for expect in expects:
        item = items[expect["doc_item_ref"]]  # KeyError = dangling ref
        assert expect["label"] == str(item.label)
        assert expect["locations"] == builders.expected_locations(item)
      refs = list(probe.get("expect_refs", []))
      if "ref" in probe:  # absent probes record the excluded item's ref
        refs.append(probe["ref"])
      for ref in refs:
        assert ref in items, f"dangling ref {ref}"


class TestDeterminism:
  """spec §8.5-§8.6: regeneration is byte-identical, snapshots fresh."""

  def test_regenerating_is_byte_identical(self):
    regenerated = generate.generate()
    committed = {
        p.name: p.read_bytes()
        for p in corpus.CORPUS_DIR.iterdir()
        if p.is_file()
    }
    assert regenerated.keys() == committed.keys()
    for name in regenerated:
      assert regenerated[name] == committed[name], f"{name} is stale"

  def test_snapshots_fresh_against_committed_fixtures(self, case):
    chunker = reference_chunker.HierarchicalMarkdownChunker()
    chunks = chunker.chunk(case.doc, **case.serializer_kwargs)
    assert DELIM.join(c.text for c in chunks) == case.snapshot
