"""Tests for provenance enrichment in the wrapper extract() pipeline."""

import json
import pathlib
from unittest import mock

from langextract.core import data
import pytest

from langextract_docling import provenance
import langextract_docling as lx

DATA_DIR = pathlib.Path(__file__).parent / "data"
PDF_PATH = DATA_DIR / "report.pdf"
PDF_URL = "https://example.com/fake/report.pdf"


@pytest.fixture(autouse=True)
def _needs_generated_pdf(report_pdf_path):
  """All tests here read the generated (gitignored) report.pdf."""


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
    assert extraction.sub_provenance is None

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
    assert not hasattr(extraction, "sub_provenance")

  def test_include_provenance_not_forwarded_to_langextract(self):
    _, fake = _run_extract([], include_provenance=True)
    assert "include_provenance" not in fake.call_args.kwargs


class TestPdfPathSubItemProvenance:
  """The PDF is read back so boxes outline the extracted words."""

  def _extraction_for(self, phrase):
    """Runs extract() pretending the model returned `phrase`."""
    probe, _ = _run_extract([])
    start = probe.text.index(phrase)
    interval = data.CharInterval(start_pos=start, end_pos=start + len(phrase))
    extraction = data.Extraction(
        extraction_class="finding",
        extraction_text=phrase,
        char_interval=interval,
    )
    result, _ = _run_extract([extraction])
    (returned,) = result.extractions
    return returned

  def test_sub_provenance_narrows_to_the_extracted_words(self):
    extraction = self._extraction_for("Ada Lovelace")
    (sub,) = extraction.sub_provenance
    assert sub.text == "Ada Lovelace"
    assert sub.exact, "the source PDF should have been read back"
    assert sub.locations

  def test_sub_boxes_are_smaller_than_the_item_boxes(self):
    extraction = self._extraction_for("Ada Lovelace")

    def area(bbox):
      left, top, right, bottom = bbox
      return abs(right - left) * abs(top - bottom)

    narrowed = sum(
        area(loc.bbox)
        for sub in extraction.sub_provenance
        for loc in sub.locations
    )
    item_level = sum(
        area(loc.bbox)
        for span in extraction.provenance
        for loc in span.locations
    )
    assert 0 < narrowed < item_level

  def test_sub_provenance_drops_untouched_list_items(self):
    extraction = self._extraction_for("Bernoulli numbers")
    # The three bullets serialize as one range, so item-level provenance
    # reports all of them; narrowing keeps only the one extracted from.
    assert len(extraction.provenance) == 3
    assert [sub.text for sub in extraction.sub_provenance] == [
        "Bernoulli numbers"
    ]

  def test_table_extraction_boxes_the_cell_not_the_table(self):
    # "Mathematician" is a cell of the table on page 2 and appears nowhere
    # else in the report.
    extraction = self._extraction_for("Mathematician")
    (sub,) = extraction.sub_provenance
    assert sub.doc_item_label == "table"
    assert sub.text == "Mathematician"
    assert sub.exact

    def area(bbox):
      left, top, right, bottom = bbox
      return abs(right - left) * abs(top - bottom)

    (cell,) = sub.locations
    (table,) = [
        loc
        for span in extraction.provenance
        if span.doc_item_label == "table"
        for loc in span.locations
    ]
    assert cell.page_no == table.page_no
    assert 0 < area(cell.bbox) < area(table.bbox) / 4

  def test_pages_are_reported_for_the_second_page_too(self):
    extraction = self._extraction_for("analytical engine")
    pages = {
        loc.page_no
        for sub in extraction.sub_provenance
        for loc in sub.locations
    }
    assert pages == {2}


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

  def test_downloaded_bytes_still_narrow_after_the_file_is_gone(self):
    # The temporary file is deleted before extraction returns, so
    # narrowing has to work from the bytes that were downloaded.
    pdf_bytes = PDF_PATH.read_bytes()
    probe, _ = _run_extract([])
    start = probe.text.index("Ada Lovelace")
    extraction = data.Extraction(
        extraction_class="person",
        extraction_text="Ada Lovelace",
        char_interval=data.CharInterval(
            start_pos=start, end_pos=start + len("Ada Lovelace")
        ),
    )
    fake = _fake_extract_returning([extraction])
    with (
        mock.patch("langextract_docling._original_extract", fake),
        mock.patch(
            "langextract_docling.requests.get",
            return_value=mock.MagicMock(content=pdf_bytes),
        ),
    ):
      result = lx.extract(
          text_or_documents=PDF_URL,
          prompt_description="Test",
          examples=[],
          fetch_urls=True,
      )
    (returned,) = result.extractions
    (sub,) = returned.sub_provenance
    assert sub.exact
    assert sub.text == "Ada Lovelace"


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
    assert not hasattr(returned, "sub_provenance")


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
    assert sidecar["sub_provenance"][0] == [
        sub.to_dict() for sub in result.extractions[0].sub_provenance
    ]
    assert sidecar["sub_provenance"][1] is None
    json.dumps(sidecar)  # the sidecar must be persistable as-is
