"""Tests for provenance enrichment in the wrapper extract() pipeline."""

import pathlib
from unittest import mock

from langextract.core import data
import pytest

from langextract_docling import provenance
import langextract_docling as lx

DATA_DIR = pathlib.Path(__file__).parent / "data"
PDF_PATH = DATA_DIR / "report.pdf"
PDF_URL = "https://example.com/fake/report.pdf"


def _fake_extract_returning(extractions):
  """Returns a mock _original_extract echoing the text it received."""

  def fake(**kwargs):
    return data.AnnotatedDocument(
        text=kwargs["text_or_documents"], extractions=extractions
    )

  return mock.MagicMock(side_effect=fake)


def _extraction(char_interval=None):
  return data.Extraction(
      extraction_class="finding",
      extraction_text="Bernoulli numbers",
      char_interval=char_interval,
  )


def _run_extract(extractions, **extract_kwargs):
  fake = _fake_extract_returning(extractions)
  with mock.patch("langextract_docling._original_extract", fake):
    result = lx.extract(
        text_or_documents=str(PDF_PATH),
        prompt_description="Test",
        examples=[],
        **extract_kwargs,
    )
  return result, fake


class TestPdfPathProvenance:

  def test_document_gains_provenance_map_with_source_path(self):
    result, _ = _run_extract([])
    assert isinstance(result.provenance_map, provenance.ProvenanceMap)
    assert result.provenance_map.source == str(PDF_PATH.expanduser())
    assert result.provenance_map.spans

  def test_aligned_extraction_gains_matching_provenance(self):
    # Locate a known phrase in the exact text the model receives, then
    # pretend the model extracted it.
    probe, _ = _run_extract([])
    start = probe.text.index("Bernoulli")
    interval = data.CharInterval(
        start_pos=start, end_pos=start + len("Bernoulli numbers")
    )

    result, _ = _run_extract([_extraction(interval)])
    (extraction,) = result.extractions
    assert extraction.provenance == result.provenance_map.lookup(
        interval.start_pos, interval.end_pos
    )
    assert extraction.provenance, "expected at least one overlapping span"
    for span in extraction.provenance:
      assert span.locations, "PDF-derived spans must carry locations"

  def test_unaligned_extraction_gets_none(self):
    result, _ = _run_extract([_extraction(char_interval=None)])
    (extraction,) = result.extractions
    assert extraction.provenance is None

  def test_include_provenance_false_restores_plain_pipeline(self):
    enriched, enriched_call = _run_extract([_extraction()])
    plain, plain_call = _run_extract([_extraction()], include_provenance=False)

    # Byte-for-byte identical text reaches langextract either way
    sent_enriched = enriched_call.call_args.kwargs["text_or_documents"]
    sent_plain = plain_call.call_args.kwargs["text_or_documents"]
    assert sent_plain == sent_enriched

    assert not hasattr(plain, "provenance_map")
    (extraction,) = plain.extractions
    assert not hasattr(extraction, "provenance")

  def test_include_provenance_not_forwarded_to_langextract(self):
    _, fake = _run_extract([], include_provenance=True)
    assert "include_provenance" not in fake.call_args.kwargs


class TestPdfUrlProvenance:

  def test_source_records_the_url(self):
    fake = _fake_extract_returning([])
    pdf_bytes = PDF_PATH.read_bytes()
    fake_response = mock.MagicMock(content=pdf_bytes)
    with (
        mock.patch("langextract_docling._original_extract", fake),
        mock.patch(
            "langextract_docling.requests.get", return_value=fake_response
        ),
    ):
      result = lx.extract(
          text_or_documents=PDF_URL,
          prompt_description="Test",
          examples=[],
          fetch_urls=True,
      )
    assert result.provenance_map.source == PDF_URL
    assert result.provenance_map.spans


class TestNonPdfInputs:

  def test_plain_text_extractions_are_untouched(self):
    extraction = _extraction(data.CharInterval(start_pos=0, end_pos=4))
    fake = _fake_extract_returning([extraction])
    with mock.patch("langextract_docling._original_extract", fake):
      result = lx.extract(
          text_or_documents="Just some plain text.",
          prompt_description="Test",
          examples=[],
          include_provenance=True,
      )
    assert not hasattr(result, "provenance_map")
    (returned,) = result.extractions
    assert not hasattr(returned, "provenance")


class TestSidecarRoundTrip:

  def test_provenance_to_dict_over_enriched_document(self):
    probe, _ = _run_extract([])
    start = probe.text.index("Bernoulli")
    interval = data.CharInterval(
        start_pos=start, end_pos=start + len("Bernoulli numbers")
    )
    result, _ = _run_extract([_extraction(interval), _extraction(None)])

    sidecar = provenance.provenance_to_dict(result)
    assert sidecar["source"] == str(PDF_PATH.expanduser())
    assert sidecar["spans"] == result.provenance_map.to_dicts()
    assert sidecar["extractions"][0]
    assert sidecar["extractions"][1] is None
