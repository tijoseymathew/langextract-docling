"""Integrity checks for the provenance-mapping corpus (test-spec §8).

These tests validate the corpus itself — fixtures, snapshots, and the frozen
reference chunker — so a broken fixture never masquerades as a mapping bug.
"""

import pathlib

from docling_core.types.doc.document import DoclingDocument
import pytest

from langextract_docling import provenance_serializer
from tests.corpus import reference_chunker

DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
DELIM = "\n\n"

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
