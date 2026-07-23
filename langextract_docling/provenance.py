"""Provenance data types mapping serialized markdown back to source items.

These types are plain dataclasses flattened to primitives so extraction
results can be serialized and consumed without a docling dependency.
"""

import bisect
import dataclasses
import typing

from langextract_docling import text_alignment


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
class TextSegment:
  """A run of characters shared by a markdown span and its source item.

  Markdown serialization inserts characters the source item never had
  (escape backslashes, "## " and "- " prefixes, bold markers) and drops
  others, so the two texts correspond only in runs. Segments record those
  runs, which is what lets a markdown offset be narrowed to an offset in
  the item's own text — the coordinate ProvenanceItem.charspan uses.

  Attributes:
      start: Offset of the run in the serialized markdown text.
      item_start: Offset of the same run in the source item's own text.
      length: Length of the run, in characters.
  """

  start: int
  item_start: int
  length: int


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
      item_text: The source item's own text, the coordinate system of both
        text_segments and every locations[i].charspan. Empty for items
        that carry no text of their own (tables, pictures).
      text_segments: Runs shared by the markdown [start, end) and
        item_text, in order. Empty when the item's text could not be
        located in its serialization, which disables sub-item narrowing
        for this span but leaves item-level provenance intact.
  """

  start: int
  end: int
  doc_item_ref: str
  doc_item_label: str
  locations: tuple[SourceLocation, ...] = ()
  item_text: str = ""
  text_segments: tuple[TextSegment, ...] = ()

  def item_charspan(self, start: int, end: int) -> tuple[int, int] | None:
    """Narrows a markdown interval to a range of the item's own text.

    Args:
        start: Interval start (inclusive) in the serialized markdown.
        end: Interval end (exclusive) in the serialized markdown.

    Returns:
        The tightest (start, end) range of item_text the interval covers,
        or None when the interval and the item's text share no character
        — an unaligned span, or an interval covering only markdown syntax.
    """
    return text_alignment.map_range(
        [(seg.start, seg.item_start, seg.length) for seg in self.text_segments],
        start,
        end,
    )

  def to_dict(self) -> dict:
    """Returns a JSON-serializable dict representation.

    item_text and text_segments are omitted: they are the join machinery
    behind sub-item narrowing, and would duplicate the whole document in
    the span table. Persist narrowed results (SubItemProvenance) instead.
    """
    return {
        "start": self.start,
        "end": self.end,
        "doc_item_ref": self.doc_item_ref,
        "doc_item_label": self.doc_item_label,
        "locations": [loc.to_dict() for loc in self.locations],
    }


@dataclasses.dataclass(frozen=True)
class SubItemProvenance:
  """Provenance narrowed from a whole document item to some of its text.

  Where SpanProvenance answers "which item did this come from", this
  answers "which words of that item, and where exactly do they sit on the
  page" — the item's bounding box shrunk to the characters actually
  extracted, one location per line of the source they occupy.

  Attributes:
      doc_item_ref: The DocItem.self_ref the text belongs to.
      doc_item_label: The DocItem.label, e.g. "text", "list_item".
      charspan: The (start, end) range of the item's own text covered.
      text: That range of the item's text, verbatim from the source
        document (not markdown-escaped).
      locations: Physical locations covering `text`; empty for items from
        non-paginated sources.
      exact: True when every location was narrowed to `charspan`. False
        when at least one location is the whole item's box, because no
        page layout was available or the text could not be found in it.
  """

  doc_item_ref: str
  doc_item_label: str
  charspan: tuple[int, int]
  text: str
  locations: tuple[SourceLocation, ...] = ()
  exact: bool = True

  def to_dict(self) -> dict:
    """Returns a JSON-serializable dict representation."""
    return {
        "doc_item_ref": self.doc_item_ref,
        "doc_item_label": self.doc_item_label,
        "charspan": list(self.charspan),
        "text": self.text,
        "locations": [loc.to_dict() for loc in self.locations],
        "exact": self.exact,
    }


class CharLayout(typing.Protocol):
  """A source of character geometry for a page of the original document.

  Implemented by word_layout.PdfCharLayout; injected rather than imported
  so this module stays free of PDF dependencies.
  """

  def locate(
      self, location: SourceLocation, item_text: str, start: int, end: int
  ) -> tuple[SourceLocation, ...]:
    """Returns locations covering item_text[start:end] within `location`.

    Args:
        location: The item-level location to narrow. Its charspan says
          which slice of item_text the box holds.
        item_text: The source item's own text.
        start: Start of the range to narrow (inclusive), in item_text.
        end: End of the range to narrow (exclusive), in item_text.

    Returns:
        One location per line the range occupies, or () when the layout
        cannot place the text (unreadable page, scanned image, mismatch).
    """


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

  def narrow(
      self,
      start: int,
      end: int,
      layout: CharLayout | None = None,
  ) -> list[SubItemProvenance]:
    """Resolves a markdown interval down to the source text it covers.

    Each span the interval overlaps contributes one SubItemProvenance
    describing just the characters of that item the interval reaches, and
    — when a layout is supplied — the boxes those characters occupy
    rather than the whole item's box. Narrowing degrades rather than
    fails: a span whose text cannot be aligned, or whose page cannot be
    read, still reports the item with exact=False.

    Items serialized as a group share one range, so lookup() reports the
    whole list for an interval inside a single bullet. Narrowing knows
    where each item's text sits and drops the ones the interval never
    reaches, which is the main reason to prefer it for highlighting.

    Args:
        start: Interval start (inclusive) in the serialized text.
        end: Interval end (exclusive) in the serialized text.
        layout: Optional page geometry used to shrink bounding boxes to
          the covered characters. Without it, boxes stay item-level.

    Returns:
        One entry per span the interval genuinely covers, ordered as in
        self.spans.
    """
    narrowed = (
        _narrow_span(span, start, end, layout)
        for span in self.lookup(start, end)
    )
    return [span for span in narrowed if span is not None]

  def to_dicts(self) -> list[dict]:
    """Returns the span table as JSON-serializable dicts."""
    return [span.to_dict() for span in self.spans]


def _narrow_span(
    span: SpanProvenance,
    start: int,
    end: int,
    layout: CharLayout | None,
) -> SubItemProvenance | None:
  """Narrows one span to the item text an interval covers.

  Args:
      span: The overlapping span to narrow.
      start: Interval start (inclusive) in the serialized markdown.
      end: Interval end (exclusive) in the serialized markdown.
      layout: Optional page geometry; None keeps boxes item-level.

  Returns:
      The narrowed provenance; the whole item with exact=False when the
      span carries no alignment to narrow by; or None when the span is
      aligned and the interval demonstrably misses this item's text.
  """
  charspan = span.item_charspan(start, end)
  if charspan is None:
    if span.text_segments:
      # The item's text is placed, and the interval falls outside it:
      # a neighbour in the same serialized group, not a match.
      return None
    # No alignment to stand on: report the item as a whole, honestly
    # labelled, so callers can still cite and highlight it.
    return SubItemProvenance(
        doc_item_ref=span.doc_item_ref,
        doc_item_label=span.doc_item_label,
        charspan=(0, len(span.item_text)),
        text=span.item_text,
        locations=span.locations,
        exact=False,
    )

  lo, hi = charspan
  locations: list[SourceLocation] = []
  exact = True
  for location in span.locations:
    covered_start = max(lo, location.charspan[0])
    covered_end = min(hi, location.charspan[1])
    if covered_start >= covered_end:
      continue  # this location holds none of the covered characters
    narrowed = (
        ()
        if layout is None
        else layout.locate(location, span.item_text, covered_start, covered_end)
    )
    if narrowed:
      locations.extend(narrowed)
    else:
      locations.append(location)
      exact = False
  return SubItemProvenance(
      doc_item_ref=span.doc_item_ref,
      doc_item_label=span.doc_item_label,
      charspan=charspan,
      text=span.item_text[lo:hi],
      locations=tuple(locations),
      exact=exact,
  )


def provenance_to_dict(annotated_doc: typing.Any) -> dict:
  """Returns a JSON-serializable snapshot of a document's provenance.

  Dynamic attributes are invisible to langextract's own JSONL serializer, so
  this provides a sidecar representation users can persist alongside it.

  Args:
      annotated_doc: An AnnotatedDocument, typically enriched by extract()
        with .provenance_map and per-extraction .provenance attributes.

  Returns:
      A dict with the document "source", the full item-level "spans"
      table, "extractions" mapping each extraction's index to its span
      dicts, and "sub_provenance" mapping the same indices to the
      narrowed sub-item dicts. Both mappings hold None for extractions
      that have no provenance of that kind.
  """
  pmap = getattr(annotated_doc, "provenance_map", None)
  extractions = {}
  sub_provenance = {}
  for index, extraction in enumerate(annotated_doc.extractions or []):
    spans = getattr(extraction, "provenance", None)
    extractions[index] = (
        None if spans is None else [span.to_dict() for span in spans]
    )
    subs = getattr(extraction, "sub_provenance", None)
    sub_provenance[index] = (
        None if subs is None else [sub.to_dict() for sub in subs]
    )
  return {
      "source": pmap.source if pmap is not None else None,
      "spans": pmap.to_dicts() if pmap is not None else [],
      "extractions": extractions,
      "sub_provenance": sub_provenance,
  }
