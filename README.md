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

- `provenance` granularity is the docling document item (paragraph, heading,
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

### Sub-item provenance

An item-level box is the whole paragraph. `sub_provenance` narrows it to the
words the extraction actually names, one box per line they occupy:

```python
for e in result.extractions:
    for sub in (e.sub_provenance or []):
        for loc in sub.locations:
            print(f"{sub.text!r}: page {loc.page_no}, bbox {loc.bbox}")
```

Each `SubItemProvenance` carries the source item it belongs to
(`doc_item_ref`, `doc_item_label`), the `charspan` of that item's own text
the extraction covers, that `text` verbatim (unescaped, as the document has
it), and the `locations` covering it.

It is computed for PDF inputs whenever `include_provenance` is on, by
reading the character geometry back out of the source PDF with pypdfium2.
Two things follow:

- Narrowing is what separates items that share a serialized range. An
  extraction inside one bullet reports every item of the list in
  `provenance`, but only that bullet in `sub_provenance`.
- Tables have no text of their own, so they are narrowed through their
  cells: an extraction from a table reports the cell it came from, boxed on
  its own. A table whose cells docling did not place on the page reports its
  whole box instead, as does a cell the markdown rewrites rather than
  spelling out (a `|` inside a cell, say) — that cell alone gets no
  `sub_provenance`, so read it as `sub_provenance or provenance`, which is
  what `visualize_pdf()` does.
- `sub.exact` says whether the boxes hold nothing but the extracted text. It
  is `False` when the page had no readable text layer (a scan), when the PDF
  is no longer available, or for items with no geometry below the item — a
  picture, or a table that fell back to its whole box. The charspan and text
  still narrow in every case where the item has text; only the geometry
  falls back.

## PDF highlight visualization

`visualize_pdf()` is the PDF counterpart of `lx.visualize()`: an animated,
interactive HTML widget showing the rendered source pages with every
extraction's bounding boxes overlaid, colored per extraction class (same
colors `lx.visualize()` assigns). Play/pause, previous/next, and a progress
slider step through the extractions. The viewer pages to whichever page the
current extraction lives on (one page at a time, so multi-page documents stay
focused), spotlights its box while dimming the rest, and shows its class,
text, and attributes. Click any box to jump straight to that extraction, and
zoom the canvas with the toolbar (or Ctrl/⌘ + scroll) to inspect fine detail:

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
`show_legend`, and `scale` (rasterization scale, 1.0 = 72 dpi). Highlights
come from `sub_provenance` when it is available, so they outline the
extracted words themselves; they fall back to the whole document item when
the source PDF has no readable text layer.

## Breaking changes in 1.1.0

Following the upgrade to LangExtract 1.6.0, the wrapper mirrors upstream's
new defaults:

- `fetch_urls` now defaults to `False`: URL strings (including PDF URLs) are
  treated as literal text unless you pass `fetch_urls=True`. Local PDF paths
  are unaffected.
- The default `model_id` is now `gemini-3.5-flash`.

## Development

Install with the test extra and run the suite (live-API tests are opt-in):

```bash
pip install -e ".[test]"
pytest -m "not live_api and not requires_pip"
```

Test PDFs are generated on demand with reportlab and are not committed:
`tests/data/report.pdf` is gitignored and rebuilt automatically by a
session fixture when missing.

The provenance mapping (markdown offsets → `SpanProvenance` →
`extraction.provenance`, and its narrowing to `extraction.sub_provenance`)
is verified by a deterministic synthetic corpus under `tests/corpus/` —
constructed `DoclingDocument`s with marker-based ground truth, regenerated
via `python -m tests.corpus.generate`. See `tests/corpus/README.md` for the
probe schema and the docling-upgrade regeneration flow. Page geometry, which
the corpus synthesizes rather than measures, is tested separately in
`tests/test_word_layout.py` against the generated PDF.

`tests/langextract/` is a byte-for-byte copy of upstream langextract's
test suite at the pinned version, run against this wrapper (conftest
redirects `langextract.extract`). It is never edited locally: upgrading
means deleting the directory and recopying it from the new tag, which is
also what keeps an upstream behaviour change visible instead of quietly
absorbed into a local patch. Upstream scenarios worth re-running over a
real document live in `tests/extract_document_pipeline_test.py`, which
drives the full pipeline over the generated PDF behind a stubbed model —
the offline counterpart of the `live_api` end-to-end test.

## License

MIT License
