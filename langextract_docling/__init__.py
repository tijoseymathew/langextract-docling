"""Wrapper for langextract library.

This module wraps the langextract.extract method while passing through all other exports unchanged.
"""

from langextract import *

from langextract import extract as _original_extract
from pathlib import Path
import os


def extract(text_or_documents, *args, **kwargs):
    """Wrapper around langextract.extract that adds PDF processing capability.

    If text_or_documents is a path to a PDF file, it will be processed using
    the markdown chunker before extraction. Otherwise, it passes through to
    the original extract method.

    Args:
        text_or_documents: The source text to extract information from, a path to
            a PDF file, a URL to download text from, or an iterable of Document objects.
        *args: Positional arguments to pass to the original extract method.
        **kwargs: Keyword arguments to pass to the original extract method.

    Returns:
        The result of the extraction process.
    """
    # Check if text_or_documents is a path to a PDF file using the new coding style
    if (
        isinstance(text_or_documents, str)
        and _is_pdf_path(text_or_documents)
    ):
        # Import docling components here to avoid dependency issues
        # when not processing PDF files
        from docling.document_converter import DocumentConverter
        from langextract_docling.markdown_chunker import HierarchicalMarkdownChunker

        filepath = Path(text_or_documents).expanduser()
        converter = DocumentConverter()
        document = converter.convert(filepath)
        chunks = [x for x in HierarchicalMarkdownChunker().chunk(document.document)]

        # Concatenate all chunks into a single text
        text_or_documents = "\n\n".join([chunk.text for chunk in chunks])

    return _original_extract(text_or_documents, *args, **kwargs)


def _is_pdf_path(path):
    """Check if the given path is to a PDF file using pathlib with expanduser.

    Args:
        path: The path to check.

    Returns:
        True if the path is to a PDF file, False otherwise.
    """
    try:
        path_obj = Path(path).expanduser()
        return path_obj.is_file() and path_obj.suffix.lower() == '.pdf'
    except Exception:
        return False
