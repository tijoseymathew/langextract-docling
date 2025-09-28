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

# Extract from a PDF URL
result = lx.extract(
    text_or_documents="https://example.com/document.pdf",
    prompt_description="Extract entities",
    examples=[...]
)
```

## License

MIT License
