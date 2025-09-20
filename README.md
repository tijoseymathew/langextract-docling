# LangExtract Docling

A [Docling](https://github.com/docling-project/docling) wrapper of [LangExtract](https://github.com/google/langextract) that supports based parsing of PDF documents.

## Installation

```bash
pip install -e .
```

## Usage

```python
import langextract as lx

result = lx.extract(
    text="Your document here",
    model_id="docling-model",
    prompt_description="Extract entities",
    examples=[...]
)
```

## Development

1. Install in development mode: `pip install -e .`
2. Run tests: `python test_plugin.py`
3. Build package: `python -m build`
4. Publish to PyPI: `twine upload dist/*`

## License

MIT License
