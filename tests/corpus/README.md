# Provenance-mapping corpus

A deterministic corpus of constructed `DoclingDocument` fixtures, with
executable ground truth, verifying the mapping

```
serialized markdown char offsets ──▶ SpanProvenance ──▶ Extraction.provenance
```

i.e. `ProvenanceMarkdownSerializer.serialize_with_provenance()`,
`ProvenanceMap.lookup()`, and `_attach_provenance`. Docling's own
page/bbox extraction and langextract's alignment are assumed correct: all
provenance here is synthesized onto constructed documents, and enrichment
inputs are injected.

## How ground truth works (marker probes)

Expected char offsets are never hardcoded. Every constructed `DocItem`
embeds a unique ASCII marker (`LXM007`) mid-sentence; the builder records,
per marker, the item ref and synthesized locations it must map to
(`manifest.json` probes). At test time `resolve_probe()` locates the marker
in the *actual* serializer output, `ProvenanceMap.lookup()` answers, and
the answer is compared against the manifest — no offset prediction, no
circularity. Refs are read back from constructed items (`item.self_ref`),
never assumed by index.

### Probe kinds

- `span` — the marker's (or the Nth `occurrence` of a repeated `text`'s)
  enclosing span maps to exactly the recorded item, label, and locations.
- `straddle` — an interval from inside one marker's item to inside
  another's returns exactly `expect_refs`.
- `group` — every listed marker resolves into one shared `[start, end)`
  range carrying one span per ref in `expect_refs` (lists, inline groups,
  captioned tables/pictures).
- `absent` — the marker (furniture or param-excluded item) never reaches
  the serialized output; `ref` records the excluded item.

Two probe families are implicit for every case: **gap probes** (every
uncovered run of text is exactly the `"\n\n"` delimiter and `lookup()`
over it is empty) and **enrichment probes** (each span/straddle interval
is injected as an `Extraction.char_interval` through `_attach_provenance`
and must yield the `lookup()` answer, plus `char_interval=None` → `None`
and zero-length-interval → `[]`).

Cases needing serializer parameters (e.g. the `pages` filter exercising
the excluded-refs branch) carry `serializer_kwargs` in their manifest
entry, applied symmetrically at generation and test time.

## Layout

- `__init__.py` — `load_case()` / `resolve_probe()` helpers.
- `builders/` — one module per catalog area of the test spec (§5); each
  builder returns a document plus its probes.
- `generate.py` — regenerates `tests/data/corpus/` (see below).
- `test_corpus_mapping.py` — corpus-driven mapping tests: three-way text
  invariant, span integrity, gap probes, manifest probes, and enrichment
  probes through `_attach_provenance` with injected `char_interval`s.
- `reference_chunker.py` — **frozen** verbatim copy of
  `langextract_docling/markdown_chunker.py` at commit `7e53403`, the last
  iteration before the chunker was reimplemented over the provenance
  serializer. It is the ground-truth side of the text invariant: the new
  serializer's text must equal this chunker's chunks joined with `"\n\n"`.
- `test_corpus_integrity.py` — validates the corpus itself (fixtures,
  snapshots, marker discipline), so a broken fixture never masquerades as a
  mapping bug.

Run with:

```bash
pytest tests/corpus
```

No network, no API keys, no `DocumentConverter` import.

## Real-PDF fixture (end-to-end test)

The end-to-end `live_api` test (`tests/test_provenance_live.py`) runs a
real PDF through docling + Gemini + provenance. Its fixture is the
generated two-page `tests/data/report.pdf` — built on demand with
reportlab by a session fixture in `tests/conftest.py`, gitignored, never
committed. Its ground truth is deliberately weak (every aligned
extraction maps to ≥1 location with an in-range page number): docling's
extraction quality is out of scope here.

## Regenerating fixtures

```bash
python -m tests.corpus.generate --out tests/data/corpus
```

Generation is deterministic (fixed markers and phrases, no timestamps,
sorted JSON keys): rerunning in an unchanged environment must be
byte-identical. The manifest records the exact docling versions because
`MarkdownDocSerializer` output is version-sensitive.

**Docling upgrade flow:** after bumping the docling pins, integrity tests
fail loudly (snapshots and manifest no longer reproduce). Regenerate with
the command above **in the upgrade commit** and review the snapshot diff:
"reference chunker != snapshot" distinguishes an upstream serializer change
(expected after an upgrade, resolved by the regen) from a divergence in
`ProvenanceMarkdownSerializer` itself (a bug).

Note: `.pre-commit-config.yaml` excludes `tests/data/corpus/` from
end-of-line fixers — snapshots are byte-exact serializer output.
