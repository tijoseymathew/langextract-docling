"""Wrapper for langextract library.

This module wraps the langextract.extract method while passing through all other exports unchanged.
"""

import importlib
import os
from pathlib import Path
import sys
import tempfile
import typing
from typing import Any, Dict

from langextract import extract as _original_extract
from langextract import prompt_validation as pv
from langextract.core import data
import requests

# Cache for lazy-loaded modules
_CACHE: Dict[str, Any] = {}

# Define the same lazy modules as the original langextract
_LAZY_MODULES = {
    "annotation": "langextract.annotation",
    "chunking": "langextract.chunking",
    "data": "langextract.data",
    "data_lib": "langextract.data_lib",
    "debug_utils": "langextract.core.debug_utils",
    "exceptions": "langextract.exceptions",
    "factory": "langextract.factory",
    "inference": "langextract.inference",
    "io": "langextract.io",
    "progress": "langextract.progress",
    "prompting": "langextract.prompting",
    "providers": "langextract.providers",
    "resolver": "langextract.resolver",
    "schema": "langextract.schema",
    "tokenizer": "langextract.tokenizer",
    "visualization": "langextract.visualization",
    "core": "langextract.core",
    "plugins": "langextract.plugins",
    "registry": "langextract.registry",  # Backward compat - will emit warning
}


def extract(
    text_or_documents: typing.Any,
    prompt_description: str | None = None,
    examples: typing.Sequence[typing.Any] | None = None,
    model_id: str = "gemini-2.5-flash",
    api_key: str | None = None,
    language_model_type: typing.Type[typing.Any] | None = None,
    format_type: typing.Any = None,
    max_char_buffer: int = 1000,
    temperature: float | None = None,
    fence_output: bool | None = None,
    use_schema_constraints: bool = True,
    batch_length: int = 10,
    max_workers: int = 10,
    additional_context: str | None = None,
    resolver_params: dict | None = None,
    language_model_params: dict | None = None,
    debug: bool = False,
    model_url: str | None = None,
    extraction_passes: int = 1,
    config: typing.Any = None,
    model: typing.Any = None,
    *,
    fetch_urls: bool = True,
    prompt_validation_level: pv.PromptValidationLevel = pv.PromptValidationLevel.WARNING,
    prompt_validation_strict: bool = False,
) -> typing.Any:
  """Extracts structured information from text.

  Retrieves structured information from the provided text or documents using a
  language model based on the instructions in prompt_description and guided by
  examples. Supports sequential extraction passes to improve recall at the cost
  of additional API calls.

  Args:
      text_or_documents: The source text to extract information from, a path to
        a PDF file, a URL to download text or PDF from (starting with http:// or https:// when fetch_urls
        is True), or an iterable of Document objects.
      prompt_description: Instructions for what to extract from the text.
      examples: List of ExampleData objects to guide the extraction.
      api_key: API key for Gemini or other LLM services (can also use
        environment variable LANGEXTRACT_API_KEY). Cost considerations: Most
        APIs charge by token volume. Smaller max_char_buffer values increase the
        number of API calls, while extraction_passes > 1 reprocesses tokens
        multiple times. Note that max_workers improves processing speed without
        additional token costs. Refer to your API provider's pricing details and
        monitor usage with small test runs to estimate costs.
      model_id: The model ID to use for extraction (e.g., 'gemini-2.5-flash').
        If your model ID is not recognized or you need to use a custom provider,
        use the 'config' parameter with factory.ModelConfig to specify the
        provider explicitly.
      language_model_type: [DEPRECATED] The type of language model to use for
        inference. Warning triggers when value differs from the legacy default
        (GeminiLanguageModel). This parameter will be removed in v2.0.0. Use
        the model, config, or model_id parameters instead.
      format_type: The format type for the output (JSON or YAML).
      max_char_buffer: Max number of characters for inference.
      temperature: The sampling temperature for generation. When None (default),
        uses the model's default temperature. Set to 0.0 for deterministic output
        or higher values for more variation.
      fence_output: Whether to expect/generate fenced output (```json or
        ```yaml). When True, the model is prompted to generate fenced output and
        the resolver expects it. When False, raw JSON/YAML is expected. When None,
        automatically determined based on provider schema capabilities: if a schema
        is applied and supports_strict_mode is True, defaults to False; otherwise
        True. If your model utilizes schema constraints, this can generally be set
        to False unless the constraint also accounts for code fence delimiters.
      use_schema_constraints: Whether to generate schema constraints for models.
        For supported models, this enables structured outputs. Defaults to True.
      batch_length: Number of text chunks processed per batch. Higher values
        enable greater parallelization when batch_length >= max_workers.
        Defaults to 10.
      max_workers: Maximum parallel workers for concurrent processing. Effective
        parallelization is limited by min(batch_length, max_workers). Supported
        by Gemini models. Defaults to 10.
      additional_context: Additional context to be added to the prompt during
        inference.
      resolver_params: Parameters for the `resolver.Resolver`, which parses the
        raw language model output string (e.g., extracting JSON from ```json ...
        ``` blocks) into structured `data.Extraction` objects. This dictionary
        overrides default settings. Keys include: - 'fence_output' (bool):
        Whether to expect fenced output. - 'extraction_index_suffix' (str |
        None): Suffix for keys indicating extraction order. Default is None
        (order by appearance). - 'extraction_attributes_suffix' (str | None):
        Suffix for keys containing extraction attributes. Default is
        "_attributes".
      language_model_params: Additional parameters for the language model.
      debug: Whether to enable debug logging. When True, enables detailed logging
        of function calls, arguments, return values, and timing for the langextract
        namespace. Note: Debug logging remains enabled for the process once activated.
      model_url: Endpoint URL for self-hosted or on-prem models. Only forwarded
        when the selected `language_model_type` accepts this argument.
      extraction_passes: Number of sequential extraction attempts to improve
        recall and find additional entities. Defaults to 1 (standard single
        extraction). When > 1, the system performs multiple independent
        extractions and merges non-overlapping results (first extraction wins
        for overlaps). WARNING: Each additional pass reprocesses tokens,
        potentially increasing API costs. For example, extraction_passes=3
        reprocesses tokens 3x.
      config: Model configuration to use for extraction. Takes precedence over
        model_id, api_key, and language_model_type parameters. When both model
        and config are provided, model takes precedence.
      model: Pre-configured language model to use for extraction. Takes
        precedence over all other parameters including config.
      fetch_urls: Whether to automatically download content when the input is a
        URL string. When True (default), strings starting with http:// or
        https:// are fetched. When False, all strings are treated as literal
        text to analyze. This is a keyword-only parameter.
      prompt_validation_level: Controls pre-flight alignment checks on few-shot
        examples. OFF skips validation, WARNING logs issues but continues, ERROR
        raises on failures. Defaults to WARNING.
      prompt_validation_strict: When True and prompt_validation_level is ERROR,
        raises on non-exact matches (MATCH_FUZZY, MATCH_LESSER). Defaults to False.

  Returns:
        An AnnotatedDocument with the extracted information when input is a
        string or URL, or an iterable of AnnotatedDocuments when input is an
        iterable of Documents.

  Raises:
    ValueError: If examples is None or empty.
    ValueError: If no API key is provided or found in environment variables.
    requests.RequestException: If URL download fails.
    pv.PromptAlignmentError: If validation fails in ERROR mode.
  """
  # Check if text_or_documents is a path to a PDF file or a URL to a PDF file
  if isinstance(text_or_documents, str):
    if _is_pdf_path(text_or_documents):
      # Import docling components here to avoid dependency issues
      # when not processing PDF files
      from docling.document_converter import DocumentConverter

      from langextract_docling.markdown_chunker import HierarchicalMarkdownChunker

      filepath = Path(text_or_documents).expanduser()
      converter = DocumentConverter()
      document = converter.convert(filepath)
      chunks = [
          x for x in HierarchicalMarkdownChunker().chunk(document.document)
      ]

      # Concatenate all chunks into a single text
      text_or_documents = "\n\n".join([chunk.text for chunk in chunks])
    elif fetch_urls and _is_pdf_url(text_or_documents):
      # Handle PDF URL download
      from docling.document_converter import DocumentConverter

      from langextract_docling.markdown_chunker import HierarchicalMarkdownChunker

      # Download PDF to a temporary file
      with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
        response = requests.get(text_or_documents, timeout=30)
        response.raise_for_status()
        tmp_file.write(response.content)
        tmp_file_path = tmp_file.name

      try:
        # Process the downloaded PDF
        converter = DocumentConverter()
        document = converter.convert(tmp_file_path)
        chunks = [
            x for x in HierarchicalMarkdownChunker().chunk(document.document)
        ]

        # Concatenate all chunks into a single text
        text_or_documents = "\n\n".join([chunk.text for chunk in chunks])
      finally:
        # Clean up the temporary file
        os.unlink(tmp_file_path)

  return _original_extract(
      text_or_documents=text_or_documents,
      prompt_description=prompt_description,
      examples=examples,
      model_id=model_id,
      api_key=api_key,
      language_model_type=language_model_type,
      format_type=format_type,
      max_char_buffer=max_char_buffer,
      temperature=temperature,
      fence_output=fence_output,
      use_schema_constraints=use_schema_constraints,
      batch_length=batch_length,
      max_workers=max_workers,
      additional_context=additional_context,
      resolver_params=resolver_params,
      language_model_params=language_model_params,
      debug=debug,
      model_url=model_url,
      extraction_passes=extraction_passes,
      config=config,
      model=model,
      fetch_urls=fetch_urls,
      prompt_validation_level=prompt_validation_level,
      prompt_validation_strict=prompt_validation_strict,
  )


# PEP 562 lazy loading - same as original langextract
def __getattr__(name: str) -> Any:
  if name in _CACHE:
    return _CACHE[name]
  modpath = _LAZY_MODULES.get(name)
  if modpath is None:
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
  module = importlib.import_module(modpath)
  # ensure future 'import langextract_docling.<name>' returns the same module
  sys.modules[f"{__name__}.{name}"] = module
  setattr(sys.modules[__name__], name, module)
  _CACHE[name] = module
  return module


def __dir__():
  # Return the same attributes as the original langextract, plus our wrapped extract
  original_attrs = ["extract"]  # Include our wrapped extract function
  lazy_attrs = list(_LAZY_MODULES.keys())
  return sorted(original_attrs + lazy_attrs)


def _is_pdf_path(path):
  """Check if the given path is to a PDF file using pathlib with expanduser.

  Args:
      path: The path to check.

  Returns:
      True if the path is to a PDF file, False otherwise.
  """
  try:
    path_obj = Path(path).expanduser()
    return path_obj.is_file() and path_obj.suffix.lower() == ".pdf"
  except Exception:
    return False


def _is_pdf_url(url):
  """Check if the given URL points to a PDF file.

  Args:
      url: The URL to check.

  Returns:
      True if the URL points to a PDF file, False otherwise.
  """
  if not _is_text_url(url):
    return False

  try:
    # Check if URL ends with .pdf
    if url.lower().endswith(".pdf"):
      return True

    # Check Content-Type header
    response = requests.head(url, timeout=10)
    content_type = response.headers.get("Content-Type", "").lower()
    return "application/pdf" in content_type
  except Exception:
    return False


def _is_text_url(text):
  """Check if the given text is a valid URL using the langextract.io.is_url function.

  Args:
      text: The string to check.

  Returns:
      True if the text is a valid URL, False otherwise.
  """
  try:
    from langextract import io

    return io.is_url(text)
  except Exception:
    return False
