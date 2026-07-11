"""Synthetic corpus verifying the provenance mapping (see test spec).

The corpus pins the chain
serialized markdown char offsets -> SpanProvenance -> Extraction.provenance
with constructed DoclingDocuments whose ground truth is known exactly.

load_case() returns a committed fixture with its manifest entry and
snapshot; resolve_probe() turns a manifest probe into concrete character
intervals against the actual serializer output, so no expected offset is
ever hardcoded.
"""

import dataclasses
import functools
import json
import pathlib
import typing

from docling_core.types.doc.document import DoclingDocument

CORPUS_DIR = pathlib.Path(__file__).parent.parent / "data" / "corpus"


@dataclasses.dataclass(frozen=True)
class Case:
  """One corpus case: fixture document, manifest entry, snapshot text."""

  case_id: str
  doc: DoclingDocument
  entry: dict
  snapshot: str

  @property
  def probes(self) -> list[dict]:
    return self.entry["probes"]

  @property
  def serializer_kwargs(self) -> dict:
    return decode_serializer_kwargs(self.entry.get("serializer_kwargs", {}))


@functools.cache
def load_manifest() -> dict:
  return json.loads((CORPUS_DIR / "manifest.json").read_text())


def case_ids() -> list[str]:
  return [entry["case_id"] for entry in load_manifest()["cases"]]


def load_case(case_id: str) -> Case:
  """Loads a committed corpus case by id."""
  entries = {e["case_id"]: e for e in load_manifest()["cases"]}
  doc = DoclingDocument.model_validate_json(
      (CORPUS_DIR / f"{case_id}.docling.json").read_bytes()
  )
  snapshot = (CORPUS_DIR / f"{case_id}.expected.md.txt").read_text()
  return Case(
      case_id=case_id, doc=doc, entry=entries[case_id], snapshot=snapshot
  )


def decode_serializer_kwargs(kwargs: dict) -> dict:
  """Decodes JSON-encoded serializer kwargs (e.g. pages list -> set)."""
  return {k: set(v) if k == "pages" else v for k, v in kwargs.items()}


def find_occurrence(text: str, needle: str, occurrence: int = 1) -> int:
  """Returns the start of the Nth (1-based) occurrence of needle in text."""
  pos = -1
  for _ in range(occurrence):
    pos = text.index(needle, pos + 1)
  return pos


def resolve_probe(
    probe: dict, text: str
) -> typing.Union[tuple[int, int], dict[str, tuple[int, int]], None]:
  """Resolves a manifest probe against actual serializer output.

  Returns a (start, end) interval for span and straddle probes, a
  {marker: (start, end)} dict for group probes, and None for absent probes
  (their assertion is pure non-presence).
  """
  kind = probe["kind"]
  if kind == "span":
    needle = probe.get("marker") or probe["text"]
    start = find_occurrence(text, needle, probe.get("occurrence", 1))
    return (start, start + len(needle))
  if kind == "straddle":
    # From inside one marker to inside another: midpoints guarantee the
    # interval starts and ends strictly within the two items' spans.
    from_start = find_occurrence(text, probe["from_marker"])
    to_start = find_occurrence(text, probe["to_marker"])
    start = from_start + len(probe["from_marker"]) // 2
    end = to_start + len(probe["to_marker"]) // 2
    if start >= end:
      raise ValueError(f"straddle probe resolves to empty interval: {probe}")
    return (start, end)
  if kind == "group":
    intervals = {}
    for marker in probe["markers"]:
      start = find_occurrence(text, marker)
      intervals[marker] = (start, start + len(marker))
    return intervals
  if kind == "absent":
    return None
  raise ValueError(f"unknown probe kind: {kind!r}")
