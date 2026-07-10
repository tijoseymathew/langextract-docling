"""Live end-to-end test: real PDF through docling + Gemini + provenance.

Requires GEMINI_API_KEY (and optionally GEMINI_MODEL) in the environment.
Run with: pytest tests/test_provenance_live.py -m live_api
"""

import os
import pathlib

import pytest

from langextract_docling import provenance
import langextract_docling as lx

PDF_PATH = pathlib.Path(__file__).parent / "data" / "report.pdf"


def _model_id() -> str:
  model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
  # Accept litellm-style ids like "gemini/gemini-3.1-flash-lite"
  return model.split("/", 1)[1] if model.startswith("gemini/") else model


@pytest.mark.live_api
@pytest.mark.integration
def test_pdf_extraction_end_to_end_with_provenance():
  api_key = os.environ.get("GEMINI_API_KEY")
  if not api_key:
    pytest.skip("GEMINI_API_KEY not set")

  examples = [
      lx.data.ExampleData(
          text=(
              "The study was carried out by Marie Curie and Pierre Curie"
              " in Paris."
          ),
          extractions=[
              lx.data.Extraction(
                  extraction_class="person", extraction_text="Marie Curie"
              ),
              lx.data.Extraction(
                  extraction_class="person", extraction_text="Pierre Curie"
              ),
          ],
      )
  ]

  result = lx.extract(
      text_or_documents=str(PDF_PATH),
      prompt_description="Extract the names of all people mentioned.",
      examples=examples,
      model_id=_model_id(),
      api_key=api_key,
      show_progress=False,
  )

  assert isinstance(result.provenance_map, provenance.ProvenanceMap)
  assert result.extractions, "expected the model to extract someone"

  page_count = 2  # report.pdf is a two-page document
  aligned = [e for e in result.extractions if e.char_interval is not None]
  assert aligned, "expected at least one aligned extraction"
  for extraction in aligned:
    assert extraction.provenance, (
        f"aligned extraction {extraction.extraction_text!r} has no"
        " provenance spans"
    )
    locations = [
        loc for span in extraction.provenance for loc in span.locations
    ]
    assert locations, "PDF-derived spans must carry physical locations"
    for loc in locations:
      assert 1 <= loc.page_no <= page_count
      assert len(loc.bbox) == 4
