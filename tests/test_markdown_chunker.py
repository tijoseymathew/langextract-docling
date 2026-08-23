"""Characterization tests for HierarchicalMarkdownChunker.

These pin the chunker's public behavior (which the provenance serializer's
text invariant depends on) across the reimplementation over the shared
serializer walk.
"""

import pathlib

from docling.chunking import DocChunk
from docling_core.types.doc.document import DoclingDocument
import pytest

from langextract_docling.markdown_chunker import HierarchicalMarkdownChunker
from langextract_docling.provenance_serializer import ProvenanceMarkdownSerializer

DATA_DIR = pathlib.Path(__file__).parent / "data"
FIXTURES = ["report_pdf", "notes_md"]


def _load(name: str) -> DoclingDocument:
  return DoclingDocument.load_from_json(DATA_DIR / f"{name}.docling.json")


@pytest.fixture(params=FIXTURES)
def doc(request):
  return _load(request.param)


@pytest.mark.parametrize("name", FIXTURES)
def test_join_matches_golden_file(name):
  chunks = list(HierarchicalMarkdownChunker().chunk(_load(name)))
  golden = (DATA_DIR / f"{name}.golden.md").read_text()
  assert "\n\n".join(c.text for c in chunks) == golden


def test_yields_doc_chunks_with_items_and_origin(doc):
  chunks = list(HierarchicalMarkdownChunker().chunk(doc))
  assert chunks
  for chunk in chunks:
    assert isinstance(chunk, DocChunk)
    assert chunk.text
    assert chunk.meta.doc_items
    assert chunk.meta.origin == doc.origin


def test_headings_metadata_is_always_none(doc):
  # The pre-provenance implementation never populated heading_by_level, so
  # headings must stay None to keep chunk output stable.
  for chunk in HierarchicalMarkdownChunker().chunk(doc):
    assert chunk.meta.headings is None


def test_chunk_items_match_serializer_span_refs(doc):
  chunks = list(HierarchicalMarkdownChunker().chunk(doc))
  _, pmap = ProvenanceMarkdownSerializer(doc=doc).serialize_with_provenance()

  chunk_refs = [
      [item.self_ref for item in chunk.meta.doc_items] for chunk in chunks
  ]
  span_refs_by_range: dict[tuple[int, int], list[str]] = {}
  for span in pmap.spans:
    span_refs_by_range.setdefault((span.start, span.end), []).append(
        span.doc_item_ref
    )
  assert chunk_refs == list(span_refs_by_range.values())
