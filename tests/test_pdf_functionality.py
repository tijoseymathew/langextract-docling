"""Simplified tests for PDF functionality in langextract_docling."""

import os
from pathlib import Path
import tempfile
import textwrap
from unittest import mock

from absl.testing import absltest
from langextract.core import data
from langextract.core import types
import requests

import langextract_docling as lx

# PDF URL and expected content constants
PDF_URL = "https://raw.githubusercontent.com/py-pdf/sample-files/main/001-trivial/minimal-document.pdf"
EXPECTED_PDF_CONTENT = (
    "Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy"
    " eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam"
    " voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet"
    " clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit"
    " amet. Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam"
    " nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat,"
    " sed diam voluptua. At vero eos et accusam et justo duo dolores et ea"
    " rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum"
    " dolor sit amet."
)


class TestPDFFunctionality(absltest.TestCase):
  """Tests for PDF processing functionality in langextract_docling."""

  def test_pdf_file_processing(self):
    """Test that PDF files are converted to text and sent to langextract."""
    # Download the minimal-document.pdf file from the GitHub repository to a temporary file

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
      response = requests.get(PDF_URL)
      response.raise_for_status()
      temp_pdf.write(response.content)
      pdf_path = temp_pdf.name

    try:
      # Store the original extract function to check what text it receives
      with mock.patch("langextract_docling._original_extract") as mock_extract:
        # Call the extract function with the PDF path
        result = lx.extract(
            text_or_documents=pdf_path,
            prompt_description="Test description",
            examples=[],
        )

        # Verify that the original extract was called with the text from the PDF
        mock_extract.assert_called_once()
        call_args = mock_extract.call_args
        actual_text_sent = call_args[1]["text_or_documents"]

        # Check that the expected text is same as actual text
        self.assertEqual(EXPECTED_PDF_CONTENT, actual_text_sent)
    finally:
      # Clean up temporary file
      if os.path.exists(pdf_path):
        os.unlink(pdf_path)

  def test_pdf_url_processing(self):
    """Test that PDF URLs are downloaded, converted to text, and sent to langextract."""
    # Mock the _is_pdf_url function to return True for our test URL
    # This will ensure the URL is processed as a PDF
    with mock.patch("langextract_docling._original_extract") as mock_extract:
      # Call the extract function with PDF URL
      result = lx.extract(
          text_or_documents=PDF_URL,
          prompt_description="Test description",
          examples=[],
      )

      # The original extract should be called with the text extracted from the PDF
      mock_extract.assert_called_once()
      call_args = mock_extract.call_args
      actual_text_sent = call_args[1]["text_or_documents"]

      # Check that the expected text is same as actual text
      self.assertEqual(EXPECTED_PDF_CONTENT, actual_text_sent)

  def test_non_pdf_file_processing(self):
    """Test that non-PDF files are processed normally (not through PDF path)."""
    # Create a non-PDF file to test
    input_text = "Regular text content"

    # Mock only the original extract function to check the input text
    with mock.patch("langextract_docling._original_extract") as mock_extract:

      # Mock the original extract function to return a known result
      expected_result = data.AnnotatedDocument(
          text="", extractions=[], document_id=None
      )
      mock_extract.return_value = expected_result

      # Call the extract function with regular text
      result = lx.extract(
          text_or_documents=input_text,
          prompt_description="Test description",
          examples=[],
      )

      # Verify that the original extract was called directly with the input text
      mock_extract.assert_called_once()
      call_args = mock_extract.call_args
      self.assertEqual(call_args[1]["text_or_documents"], input_text)

      # Verify the result
      self.assertEqual(result, expected_result)


if __name__ == "__main__":
  absltest.main()
