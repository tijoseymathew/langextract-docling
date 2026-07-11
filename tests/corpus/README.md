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

## Layout

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
