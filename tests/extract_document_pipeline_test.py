"""Upstream extract() scenarios, re-run over a generated document.

`tests/langextract/` is a byte-for-byte mirror of upstream langextract's
suite at the pinned version and is never edited here — that is what makes
an upgrade a delete-and-recopy and what keeps an upstream behaviour change
visible instead of absorbed into a local patch. Its extract() tests drive
the wrapper (conftest redirects `lx.extract`) but always with short literal
strings, so the branch this project actually adds — PDF in, docling
markdown out, provenance back on the extractions — never runs.

This module re-runs the upstream scenarios whose outcome can genuinely
change when the input is a document, against the generated two-page
`tests/data/report.pdf`:

- `init_test.InitTest.test_lang_extract_as_lx_extract` — the real
  pipeline (chunking, resolver, alignment) end to end behind a stubbed
  model, here over the converted markdown rather than one sentence.
- `chunking_test` — chunking, here over generated markdown with its
  headings, bullets, and a table.
- `extract_precedence_test` — an explicitly supplied `model` still wins,
  and still sees the converted document.

Everything is offline and deterministic: `factory.create_model` is
replaced by a stub that "extracts" whichever known entities appear in the
chunk it is shown, so alignment does real work on real text.
"""

import json
import pathlib
from unittest import mock

from langextract.core import data
from langextract.core import types
import pytest

from langextract_docling import provenance
import langextract_docling as lx

DATA_DIR = pathlib.Path(__file__).parent / "data"
PDF_PATH = DATA_DIR / "report.pdf"
GOLDEN_MD = DATA_DIR / "report_pdf.golden.md"
PAGE_COUNT = 2  # report.pdf is built as a two-page document

# Named on page 1 in prose and again on page 2 inside the table, which is
# what makes them useful probes: the same string must resolve to whichever
# occurrence the aligner picked.
ADA = "Ada Lovelace"
BABBAGE = "Charles Babbage"

EXAMPLES = [
    data.ExampleData(
        text="The study was carried out by Marie Curie in Paris.",
        extractions=[
            data.Extraction(
                extraction_class="person", extraction_text="Marie Curie"
            )
        ],
    )
]


@pytest.fixture(autouse=True, scope="module")
def _convert_generated_pdf_once(report_pdf_path):
  """Converts the generated (gitignored) report.pdf once for the module.

  Every case below runs the wrapper against the same PDF, and docling's
  layout pass dominates their runtime. The conversion is real and its
  output is used verbatim; only the repeat trips are elided, so the
  serializer, chunker, resolver, and provenance lookup still work on a
  genuinely converted document. That docling itself yields this document
  is asserted in tests/test_pdf_functionality.py.
  """
  from docling.document_converter import DocumentConverter

  document = DocumentConverter().convert(report_pdf_path).document
  stub = mock.MagicMock()
  stub.return_value.convert.return_value.document = document
  with mock.patch("docling.document_converter.DocumentConverter", stub):
    yield


def _chunk_of(prompt: str) -> str:
  """Returns the source chunk a rendered QA prompt is asking about."""
  return prompt.rsplit("Q: ", 1)[1].rsplit("\nA:", 1)[0]


def _oracle_model(entities):
  """Stubs a language model that reports known entities it is shown.

  Answering per chunk (rather than replaying one canned response) keeps
  the resolver honest: an entity is only claimed where it really occurs,
  so every alignment the pipeline reports has to be earned from the
  converted markdown.
  """
  model = mock.MagicMock()
  model.requires_fence_output = True

  def infer(batch_prompts, **unused_kwargs):
    responses = []
    for prompt in batch_prompts:
      chunk = _chunk_of(prompt)
      payload = json.dumps(
          {"extractions": [{"person": e} for e in entities if e in chunk]}
      )
      responses.append(
          [types.ScoredOutput(output=f"```json\n{payload}\n```", score=0.9)]
      )
    return responses

  model.infer.side_effect = infer
  return model


def _run(entities, **extract_kwargs):
  """Runs the real pipeline over the generated PDF behind a stub model."""
  model = _oracle_model(entities)
  kwargs = {
      "fence_output": True,
      "use_schema_constraints": False,
      "max_char_buffer": 200,
      "show_progress": False,
      **extract_kwargs,
  }
  with mock.patch(
      "langextract.extraction.factory.create_model", return_value=model
  ):
    result = lx.extract(
        text_or_documents=str(PDF_PATH),
        prompt_description="Extract the names of all people mentioned.",
        examples=EXAMPLES,
        **kwargs,
    )
  return result, model


def _prompts(model):
  return model.infer.call_args.kwargs["batch_prompts"]


class TestDocumentReachesThePipeline:
  """The converted markdown, not the path, is what gets extracted from."""

  def test_annotated_document_text_is_the_generated_markdown(self):
    result, _ = _run([ADA])
    assert result.text == GOLDEN_MD.read_text()

  def test_every_prompt_asks_about_a_slice_of_that_markdown(self):
    golden = GOLDEN_MD.read_text()
    _, model = _run([ADA])

    prompts = _prompts(model)
    assert len(prompts) > 1, "expected the document to chunk"
    for prompt in prompts:
      assert _chunk_of(prompt) in golden
      assert str(PDF_PATH) not in prompt


class TestAlignmentOverGeneratedMarkdown:
  """Upstream's alignment guarantees, restated over document text."""

  def test_char_intervals_index_back_into_the_document(self):
    result, _ = _run([ADA, BABBAGE])
    assert result.extractions

    for extraction in result.extractions:
      assert extraction.alignment_status == data.AlignmentStatus.MATCH_EXACT
      interval = extraction.char_interval
      sliced = result.text[interval.start_pos : interval.end_pos]
      assert sliced == extraction.extraction_text

  def test_repeated_name_resolves_to_the_page_it_was_found_on(self):
    result, _ = _run([ADA])

    hits = [e for e in result.extractions if e.extraction_text == ADA]
    assert len(hits) == 2, "Ada Lovelace appears in the prose and the table"

    starts = {e.char_interval.start_pos for e in hits}
    assert len(starts) == 2, "repeats must not collapse onto one offset"

    pages = {
        loc.page_no
        for e in hits
        for span in e.provenance
        for loc in span.locations
    }
    assert pages == {1, 2}, f"expected one hit per page, got {pages}"

  def test_entity_absent_from_the_document_never_aligns(self):
    result, _ = _run(["Grace Hopper"])
    assert not result.extractions


class TestProvenanceFromTheRealPipeline:
  """The offline counterpart of the live_api end-to-end assertions."""

  def test_document_carries_a_provenance_map_for_the_pdf(self):
    result, _ = _run([ADA])
    assert isinstance(result.provenance_map, provenance.ProvenanceMap)
    assert result.provenance_map.source == str(PDF_PATH)

  def test_aligned_extractions_carry_page_and_bbox(self):
    result, _ = _run([ADA, BABBAGE])
    assert result.extractions

    for extraction in result.extractions:
      assert extraction.provenance, (
          f"aligned extraction {extraction.extraction_text!r} has no"
          " provenance spans"
      )
      locations = [
          loc for span in extraction.provenance for loc in span.locations
      ]
      assert locations, "PDF-derived spans must carry physical locations"
      for loc in locations:
        assert 1 <= loc.page_no <= PAGE_COUNT
        assert len(loc.bbox) == 4

  def test_include_provenance_false_leaves_the_pipeline_identical(self):
    enriched, _ = _run([ADA, BABBAGE])
    plain, _ = _run([ADA, BABBAGE], include_provenance=False)

    assert plain.text == enriched.text
    assert [
        (e.extraction_text, e.char_interval) for e in plain.extractions
    ] == [(e.extraction_text, e.char_interval) for e in enriched.extractions]

    assert not hasattr(plain, "provenance_map")
    for extraction in plain.extractions:
      assert not hasattr(extraction, "provenance")


class TestPrecedenceWithDocumentInput:
  """A supplied model still wins, and still sees the converted document."""

  def test_supplied_model_bypasses_the_factory_and_gets_the_markdown(self):
    model = _oracle_model([ADA])
    golden = GOLDEN_MD.read_text()

    with mock.patch(
        "langextract.extraction.factory.create_model"
    ) as mock_create_model:
      result = lx.extract(
          text_or_documents=str(PDF_PATH),
          prompt_description="Extract the names of all people mentioned.",
          examples=EXAMPLES,
          model=model,
          model_id="ignored-model",
          fence_output=True,
          use_schema_constraints=False,
          max_char_buffer=200,
          show_progress=False,
      )

    mock_create_model.assert_not_called()
    assert result.text == golden
    for prompt in _prompts(model):
      assert _chunk_of(prompt) in golden
    assert result.extractions
