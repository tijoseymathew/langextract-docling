"""Builder registry for the provenance-mapping corpus (test-spec §5).

Each builder module constructs DoclingDocuments and records their expected
mapping answers (probes) at build time: refs are read back from the
constructed items (item.self_ref, never assumed indices) and expected
locations from the ProvenanceItems the builder itself attached.
"""

import dataclasses
import importlib
import typing

from docling_core.types.doc.base import BoundingBox
from docling_core.types.doc.base import CoordOrigin
from docling_core.types.doc.document import DocItem
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.document import ProvenanceItem

# Catalog-area modules (test-spec §5.1-§5.6); imported by all_cases().
_MODULES = [
    "offsets",
    "escaping",
    "repetition",
    "groups",
]

_REGISTRY: dict[str, typing.Callable[[], "BuiltCase"]] = {}


@dataclasses.dataclass
class BuiltCase:
  """A constructed corpus case with its executable ground truth."""

  doc: DoclingDocument
  probes: list[dict]
  serializer_kwargs: dict = dataclasses.field(default_factory=dict)
  builder: str = ""


def builder(case_id: str):
  """Registers a zero-arg builder function under a case id."""

  def register(fn):
    if case_id in _REGISTRY:
      raise ValueError(f"duplicate case id: {case_id}")
    _REGISTRY[case_id] = fn
    return fn

  return register


def all_cases() -> dict[str, BuiltCase]:
  """Builds every registered case, in stable registration order."""
  for module in _MODULES:
    importlib.import_module(f"{__name__}.{module}")
  cases = {}
  for case_id, fn in _REGISTRY.items():
    built = fn()
    built.builder = fn.__module__.rsplit(".", 1)[-1]
    cases[case_id] = built
  return cases


def prov_item(
    page_no: int,
    bbox: tuple[float, float, float, float],
    coord_origin: str = "TOPLEFT",
    charspan: tuple[int, int] = (0, 0),
) -> ProvenanceItem:
  """Synthesizes a ProvenanceItem from primitive ground-truth values."""
  left, top, right, bottom = bbox
  return ProvenanceItem(
      page_no=page_no,
      bbox=BoundingBox(
          l=left,
          t=top,
          r=right,
          b=bottom,
          coord_origin=CoordOrigin(coord_origin),
      ),
      charspan=charspan,
  )


def expected_locations(item: DocItem) -> list[dict]:
  """The SourceLocation dicts the serializer must copy from item.prov."""
  return [
      {
          "page_no": prov.page_no,
          "bbox": [prov.bbox.l, prov.bbox.t, prov.bbox.r, prov.bbox.b],
          "coord_origin": str(prov.bbox.coord_origin.value),
          "charspan": list(prov.charspan),
      }
      for prov in getattr(item, "prov", None) or ()
  ]


def span_probe(marker: str, item: DocItem) -> dict:
  """A span probe recording the item the builder put the marker into."""
  return {
      "kind": "span",
      "marker": marker,
      "expect": {
          "doc_item_ref": item.self_ref,
          "label": str(item.label),
          "locations": expected_locations(item),
      },
  }


def occurrence_probe(text: str, occurrence: int, item: DocItem) -> dict:
  """A span probe for the Nth occurrence of a deliberately repeated text."""
  return {
      "kind": "span",
      "text": text,
      "occurrence": occurrence,
      "expect": {
          "doc_item_ref": item.self_ref,
          "label": str(item.label),
          "locations": expected_locations(item),
      },
  }


def straddle_probe(from_marker: str, to_marker: str, items) -> dict:
  """A straddle probe over the refs of the items it must return."""
  return {
      "kind": "straddle",
      "from_marker": from_marker,
      "to_marker": to_marker,
      "expect_refs": [item.self_ref for item in items],
  }


def group_probe(markers, items) -> dict:
  """A group probe: markers resolve into one shared range, these refs.

  Looking up any of the markers must return exactly one span per listed
  item, all with the identical [start, end) range (items serialized as one
  group emit one SpanProvenance per contributing DocItem).
  """
  return {
      "kind": "group",
      "markers": list(markers),
      "expect_refs": [item.self_ref for item in items],
  }
