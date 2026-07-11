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

## PDF provenance

Extractions from PDF inputs can be traced back to the page and bounding box
they came from. Each aligned extraction carries a `provenance` attribute — a
list of `SpanProvenance` objects linking the extraction's character range to
the docling document items it overlaps — and the returned document carries a
`provenance_map` covering the full text:

```python
import langextract_docling as lx

result = lx.extract(
    text_or_documents="paper.pdf",
    prompt_description="Extract author names",
    examples=[...],
)

for e in result.extractions:
    for span in (e.provenance or []):
        for loc in span.locations:
            print(f"{e.extraction_text!r}: page {loc.page_no}, bbox {loc.bbox}")
```

Notes:

- Provenance granularity is the docling document item (paragraph, heading,
  table, list group). `span.doc_item_ref` (e.g. `#/texts/12`) points back
  into the docling document; `span.locations` holds page number, bounding
  box, and coordinate origin (empty for non-paginated sources).
- Extractions that langextract could not align (`char_interval is None`)
  have `provenance = None`.
- Non-PDF inputs (plain text, text URLs, Document iterables) bypass docling
  and get no `provenance` attribute — read it with
  `getattr(extraction, "provenance", None)`.
- Pass `include_provenance=False` to convert PDFs to the identical markdown
  without enrichment.
- `provenance` and `provenance_map` are dynamic attributes, invisible to
  langextract's JSONL serialization. To persist them, save a sidecar:

```python
import json
from langextract_docling.provenance import provenance_to_dict

with open("results.provenance.json", "w") as f:
    json.dump(provenance_to_dict(result), f)
```

## PDF highlight visualization

`visualize_pdf()` is the PDF counterpart of `lx.visualize()`: an animated,
interactive HTML widget showing the rendered source pages with every
extraction's bounding boxes overlaid, colored per extraction class (same
colors `lx.visualize()` assigns). Play/pause, previous/next, and a progress
slider step through the extractions. The viewer pages to whichever page the
current extraction lives on (one page at a time, so multi-page documents stay
focused), spotlights its box while dimming the rest, and shows its class,
text, and attributes. Click any box to jump straight to that extraction:

```python
import langextract_docling as lx

result = lx.extract(
    text_or_documents="paper.pdf",
    prompt_description="Extract author names",
    examples=[...],
)

lx.visualize_pdf(result)  # displays inline in a notebook

html = lx.visualize_pdf(result)  # plain HTML string outside notebooks
with open("highlights.html", "w") as f:
    f.write(html.data if hasattr(html, "data") else html)
```

The HTML is fully self-contained (pages are embedded as base64 PNGs); only
pages with at least one highlight are included. The source PDF path is taken
from the provenance map; pass `pdf_path=...` when the document came from a
URL. Optional keywords: `animation_speed` (seconds between extractions),
`show_legend`, and `scale` (rasterization scale, 1.0 = 72 dpi). Because
provenance granularity is the document item, a highlight covers the whole
item the extraction came from, and every item of a list group is boxed when
an extraction lands in one of them.

## Breaking changes in 1.1.0

Following the upgrade to LangExtract 1.6.0, the wrapper mirrors upstream's
new defaults:

- `fetch_urls` now defaults to `False`: URL strings (including PDF URLs) are
  treated as literal text unless you pass `fetch_urls=True`. Local PDF paths
  are unaffected.
- The default `model_id` is now `gemini-3.5-flash`.

## License

MIT License
