"""Regenerates the provenance-mapping corpus fixtures.

Run from the repository root:

    python -m tests.corpus.generate --out tests/data/corpus

Output is deterministic (fixed markers and phrases, no timestamps, sorted
JSON keys), so regeneration in an unchanged environment is byte-identical.
The manifest records the exact docling versions because snapshot text is
version-sensitive; after a docling upgrade, regenerate and commit the diff.
"""

import argparse
import importlib.metadata
import json
import pathlib

from tests import corpus
from tests.corpus import builders
from tests.corpus import reference_chunker

_DELIM = "\n\n"


def _snapshot(built: builders.BuiltCase) -> str:
  """The reference-chunker text: the committed side of the text invariant."""
  chunker = reference_chunker.HierarchicalMarkdownChunker()
  kwargs = corpus.decode_serializer_kwargs(built.serializer_kwargs)
  return _DELIM.join(c.text for c in chunker.chunk(built.doc, **kwargs))


def _dumps(payload) -> bytes:
  return (
      json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
  ).encode("utf-8")


def generate() -> dict[str, bytes]:
  """Builds every case; returns {relative filename: file bytes}."""
  files: dict[str, bytes] = {}
  manifest_cases = []
  for case_id, built in builders.all_cases().items():
    doc_json = _dumps(built.doc.export_to_dict())
    files[f"{case_id}.docling.json"] = doc_json
    files[f"{case_id}.expected.md.txt"] = _snapshot(built).encode("utf-8")
    entry = {
        "case_id": case_id,
        "builder": built.builder,
        "probes": built.probes,
    }
    if built.serializer_kwargs:
      entry["serializer_kwargs"] = built.serializer_kwargs
    manifest_cases.append(entry)
  files["manifest.json"] = _dumps({
      "generated_with": {
          "docling": importlib.metadata.version("docling"),
          "docling-core": importlib.metadata.version("docling-core"),
      },
      "cases": manifest_cases,
  })
  return files


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
      "--out",
      type=pathlib.Path,
      default=corpus.CORPUS_DIR,
      help="output directory (default: tests/data/corpus)",
  )
  args = parser.parse_args(argv)
  args.out.mkdir(parents=True, exist_ok=True)
  files = generate()
  stale = {p.name for p in args.out.iterdir() if p.is_file()} - files.keys()
  for name, content in sorted(files.items()):
    (args.out / name).write_bytes(content)
    print(f"wrote {args.out / name} ({len(content)} bytes)")
  for name in sorted(stale):
    print(f"WARNING: stale file not regenerated: {args.out / name}")


if __name__ == "__main__":
  main()
