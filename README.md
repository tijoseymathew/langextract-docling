# LangExtract Docling

**LangExtract Docling** is a lightweight wrapper around [LangExtract](https://github.com/google/langextract) that adds native support for processing **PDF files** via [Docling](https://github.com/docling-project/docling).

## Installation

```bash
pip install langextract-docling
````

## Usage

```python
import langextract_docling as lx

# Extract from plain text (same as LangExtract)
result = lx.extract(
    text_or_documents="Your document text here.",
    prompt_description="Extract entities",
    examples=[...]
)

# Extract from a local PDF
result = lx.extract(
    text_or_documents="path/to/document.pdf",
    prompt_description="Extract entities",
    examples=[...]
)

# Extract from a PDF URL (requires fetch_urls=True; see below)
result = lx.extract(
    text_or_documents="https://example.com/document.pdf",
    prompt_description="Extract entities",
    examples=[...],
    fetch_urls=True,
)
```

## Breaking changes in 1.1.0

Following the upgrade to LangExtract 1.6.0, the wrapper mirrors upstream's
new defaults:

- `fetch_urls` now defaults to `False`: URL strings (including PDF URLs) are
  treated as literal text unless you pass `fetch_urls=True`. Local PDF paths
  are unaffected.
- The default `model_id` is now `gemini-3.5-flash`.

## License

MIT License
