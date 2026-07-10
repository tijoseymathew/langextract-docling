"""Provenance data types mapping serialized markdown back to source items.

These types are plain dataclasses flattened to primitives so extraction
results can be serialized and consumed without a docling dependency.
"""

import bisect
import dataclasses
import typing


@dataclasses.dataclass(frozen=True)
class SourceLocation:
  """One physical location in the source document.

  Mirrors docling's ProvenanceItem (page_no, bbox, charspan) flattened to
  primitives.

  Attributes:
      page_no: 1-based page number in the source document.
      bbox: Bounding box as (left, top, right, bottom) page coordinates.
      coord_origin: Coordinate origin of bbox, "TOPLEFT" or "BOTTOMLEFT".
      charspan: Character span within the source item's own text.
  """

  page_no: int
  bbox: tuple[float, float, float, float]
  coord_origin: str
  charspan: tuple[int, int]

  def to_dict(self) -> dict:
    """Returns a JSON-serializable dict representation."""
    return {
        "page_no": self.page_no,
        "bbox": list(self.bbox),
        "coord_origin": self.coord_origin,
        "charspan": list(self.charspan),
    }


@dataclasses.dataclass(frozen=True)
class SpanProvenance:
  """Provenance for one contiguous span of the serialized markdown.

  Attributes:
      start: Character offset in the markdown text (inclusive).
      end: Character offset in the markdown text (exclusive).
      doc_item_ref: The DocItem.self_ref, e.g. "#/texts/12".
      doc_item_label: The DocItem.label, e.g. "text", "table".
      locations: Physical locations from DocItem.prov; empty for items from
        non-paginated sources.
  """

  start: int
  end: int
  doc_item_ref: str
  doc_item_label: str
  locations: tuple[SourceLocation, ...] = ()

  def to_dict(self) -> dict:
    """Returns a JSON-serializable dict representation."""
    return {
        "start": self.start,
        "end": self.end,
        "doc_item_ref": self.doc_item_ref,
        "doc_item_label": self.doc_item_label,
        "locations": [loc.to_dict() for loc in self.locations],
    }


class ProvenanceMap:
  """Ordered spans over the serialized markdown text.

  Spans from distinct document items never overlap, but items serialized as
  one group (e.g. list items in a ListGroup) share an identical [start, end)
  range. Gaps between spans (the "\\n\\n" delimiters) belong to no span.
  """

  def __init__(
      self,
      spans: typing.Iterable[SpanProvenance],
      source: str | None = None,
  ):
    """Initializes the map.

    Args:
        spans: Spans over the serialized text, in any order.
        source: Optional origin of the document (file path or URL), for
          consumers rendering citations.
    """
    self.spans: list[SpanProvenance] = sorted(spans, key=lambda s: s.start)
    self.source = source
    self._starts = [s.start for s in self.spans]

  def lookup(self, start: int, end: int) -> list[SpanProvenance]:
    """Returns all spans overlapping the half-open interval [start, end).

    A zero-length interval overlaps nothing. Runs in O(log n + k) for k
    overlapping spans, via bisect on span starts.

    Args:
        start: Interval start (inclusive) in the serialized text.
        end: Interval end (exclusive) in the serialized text.

    Returns:
        Overlapping spans, ordered as in self.spans.
    """
    if start >= end:
      return []
    # Spans at index >= hi start at or after `end` and cannot overlap. Ends
    # are non-decreasing (spans are disjoint or share identical ranges), so
    # scanning left stops at the first span ending at or before `start`.
    hi = bisect.bisect_left(self._starts, end)
    result = []
    for i in range(hi - 1, -1, -1):
      if self.spans[i].end <= start:
        break
      result.append(self.spans[i])
    result.reverse()
    return result

  def to_dicts(self) -> list[dict]:
    """Returns the span table as JSON-serializable dicts."""
    return [span.to_dict() for span in self.spans]


def provenance_to_dict(annotated_doc: typing.Any) -> dict:
  """Returns a JSON-serializable snapshot of a document's provenance.

  Dynamic attributes are invisible to langextract's own JSONL serializer, so
  this provides a sidecar representation users can persist alongside it.

  Args:
      annotated_doc: An AnnotatedDocument, typically enriched by extract()
        with .provenance_map and per-extraction .provenance attributes.

  Returns:
      A dict with the document "source", the full "spans" table, and
      "extractions" mapping each extraction's index to its span dicts (None
      for extractions without provenance).
  """
  pmap = getattr(annotated_doc, "provenance_map", None)
  extractions = {}
  for index, extraction in enumerate(annotated_doc.extractions or []):
    spans = getattr(extraction, "provenance", None)
    extractions[index] = (
        None if spans is None else [span.to_dict() for span in spans]
    )
  return {
      "source": pmap.source if pmap is not None else None,
      "spans": pmap.to_dicts() if pmap is not None else [],
      "extractions": extractions,
  }
