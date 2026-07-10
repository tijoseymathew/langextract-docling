"""Tests for langextract_docling.provenance_serializer."""

import ast
import pathlib

from docling_core.types.doc.document import DoclingDocument
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
