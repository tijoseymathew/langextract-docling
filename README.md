# LangExtract Docling

A wrapper for [LangExtract](https://github.com/google/langextract) that adds PDF processing capability using [Docling](https://github.com/docling-project/docling).

## Installation

```bash
pip install -e .
```

## Usage

```python
import langextract_docling as lx

# Use with regular text
result = lx.extract(
    text_or_documents="Your document here",
    prompt_description="Extract entities",
    examples=[...]
)

# Use with PDF files
result = lx.extract(
    text_or_documents="path/to/document.pdf",
    prompt_description="Extract entities",
    examples=[...]
)
```

## License

MIT License
