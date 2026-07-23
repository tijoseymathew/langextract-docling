"""Character geometry read back from the source PDF.

A DoclingDocument stores one bounding box per item, so the box for a
paragraph is the whole paragraph — several lines tall and the full column
wide. Narrowing an extraction to the words it actually names needs the
per-character layout, which only the PDF itself has. This module reads it
with pypdfium2 (already required to rasterize pages for visualize_pdf),
locates an item's text among the characters inside the item's own box,
and returns one tight box per line the requested characters occupy.

Everything here degrades to (): a scanned page with no text layer, an
encrypted document, a page docling numbered differently — all end with
the caller keeping its item-level box rather than a wrong one.
"""

import pathlib
import typing

from langextract_docling import text_alignment
from langextract_docling.provenance import SourceLocation

Box = tuple[float, float, float, float]

# Character boxes can sit marginally outside the item box docling derived
# from them, so membership is tested on the character's center with a
# point of slack rather than on strict containment.
_CLIP_SLACK = 1.0

# Two characters belong to the same line when their boxes overlap
# vertically by more than this fraction of the shorter one's height.
_LINE_OVERLAP = 0.5


class PdfCharLayout:
  """Lazily-read character boxes for the pages of one PDF.

  Pages are parsed on first use and cached, so a document whose
  extractions all land on page 3 never touches the other pages.

  Use as a context manager, or call close(), to release the underlying
  document.
  """

  def __init__(self, source: pathlib.Path | bytes):
    """Initializes the layout over a PDF path or its raw bytes.

    Args:
        source: Path to the PDF, or the PDF's bytes when no file will
          outlive the extraction (a downloaded URL, say).
    """
    self._source = source
    self._pdf: typing.Any = None
    self._opened = False
    self._pages: dict[int, _Page | None] = {}

  @classmethod
  def from_path(cls, path: str | pathlib.Path) -> "PdfCharLayout":
    """Returns a layout reading the PDF at `path` on demand."""
    return cls(pathlib.Path(path))

  @classmethod
  def from_bytes(cls, data: bytes) -> "PdfCharLayout":
    """Returns a layout over an in-memory PDF."""
    return cls(data)

  def __enter__(self) -> "PdfCharLayout":
    return self

  def __exit__(self, *exc_info) -> None:
    self.close()

  def close(self) -> None:
    """Releases the underlying PDF document."""
    if self._pdf is not None:
      try:
        self._pdf.close()
      except Exception:  # pylint: disable=broad-except
        pass
      self._pdf = None
    self._pages.clear()

  def locate(
      self,
      location: SourceLocation,
      item_text: str,
      start: int,
      end: int,
  ) -> tuple[SourceLocation, ...]:
    """Narrows one item-level location to item_text[start:end].

    Implements the provenance.CharLayout protocol.

    Args:
        location: The item-level location to narrow; its charspan says
          which slice of item_text its box holds.
        item_text: The source item's own text.
        start: Start of the range to narrow (inclusive), in item_text.
        end: End of the range to narrow (exclusive), in item_text.

    Returns:
        One location per line the range occupies, boxes given in the same
        coordinate origin as `location`. Empty when the page cannot be
        read or the text cannot be found inside the item's box.
    """
    page = self._page(location.page_no)
    if page is None or start >= end:
      return ()

    indices = page.clip(_to_bottom_left(location, page.height))
    if not indices:
      return ()

    span_start, span_end = location.charspan
    blocks = text_alignment.trusted_blocks(
        item_text[span_start:span_end],
        "".join(page.text[i] for i in indices),
    )
    if not blocks:
      return ()

    covered = text_alignment.map_range(
        blocks, start - span_start, end - span_start
    )
    if covered is None:
      return ()

    first_covered, past_covered = covered
    reverse = text_alignment.invert(blocks)
    return tuple(
        _line_location(
            location,
            page,
            indices,
            first_covered + line_start,
            first_covered + line_end,
            reverse,
            span_start,
        )
        for line_start, line_end in page.lines(
            indices[first_covered:past_covered]
        )
    )

  def _page(self, page_no: int) -> "_Page | None":
    """Returns the cached geometry of a 1-based page, or None."""
    if page_no not in self._pages:
      self._pages[page_no] = self._read_page(page_no)
    return self._pages[page_no]

  def _read_page(self, page_no: int) -> "_Page | None":
    """Extracts one page's characters and boxes; None if unreadable."""
    pdf = self._document()
    if pdf is None or not 1 <= page_no <= len(pdf):
      return None
    try:
      page = pdf[page_no - 1]
      height = page.get_size()[1]
      text_page = page.get_textpage()
      count = text_page.count_chars()
      return _Page(
          text=text_page.get_text_range(),
          boxes=[_normalize(text_page.get_charbox(i)) for i in range(count)],
          height=height,
      )
    except Exception:  # pylint: disable=broad-except
      return None

  def _document(self) -> typing.Any:
    """Opens the PDF once; None when it cannot be read at all."""
    if not self._opened:
      self._opened = True
      try:
        import pypdfium2 as pdfium  # pylint: disable=import-outside-toplevel

        self._pdf = pdfium.PdfDocument(self._source)
      except Exception:  # pylint: disable=broad-except
        self._pdf = None
    return self._pdf


class _Page:
  """One page's characters, their boxes, and its height."""

  def __init__(self, text: str, boxes: list[Box], height: float):
    # pdfium can report fewer boxes than characters on damaged pages;
    # truncating keeps the two indexable in lockstep.
    usable = min(len(text), len(boxes))
    self.text = text[:usable]
    self.boxes = boxes[:usable]
    self.height = height

  def clip(self, box: Box) -> list[int]:
    """Returns the indices of characters centered inside `box`.

    Args:
        box: A (left, bottom, right, top) region in bottom-left page
          coordinates.

    Returns:
        Character indices, in reading order.
    """
    left, bottom, right, top = box
    inside = []
    for index, (char_l, char_b, char_r, char_t) in enumerate(self.boxes):
      center_x = (char_l + char_r) / 2
      center_y = (char_b + char_t) / 2
      if (
          left - _CLIP_SLACK <= center_x <= right + _CLIP_SLACK
          and bottom - _CLIP_SLACK <= center_y <= top + _CLIP_SLACK
      ):
        inside.append(index)
    return inside

  def lines(self, indices: typing.Sequence[int]) -> list[tuple[int, int]]:
    """Splits a run of characters wherever it moves to another line.

    Characters that enclose no area — the spaces a PDF places between
    words carry a zero-height box — never start or end a line, since the
    box uniting the characters around them already covers the gap.

    Args:
        indices: Character indices, in reading order.

    Returns:
        One (start, end) half-open range into `indices` per line.
    """
    runs: list[list[int]] = []
    extents: list[tuple[float, float]] = []
    for position, index in enumerate(indices):
      box = self.boxes[index]
      if not _has_area(box):
        continue
      _, bottom, _, top = box
      if runs and _same_line(extents[-1], (bottom, top)):
        runs[-1][1] = position + 1
        extents[-1] = (min(extents[-1][0], bottom), max(extents[-1][1], top))
      else:
        runs.append([position, position + 1])
        extents.append((bottom, top))
    return [(start, end) for start, end in runs]

  def union(self, indices: typing.Sequence[int]) -> Box:
    """Returns the bounding box enclosing the given characters."""
    boxes = [self.boxes[index] for index in indices]
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _line_location(
    location: SourceLocation,
    page: _Page,
    indices: typing.Sequence[int],
    start: int,
    end: int,
    reverse: list[text_alignment.Block],
    span_start: int,
) -> SourceLocation:
  """Builds the narrowed location for one line of characters.

  Args:
      location: The item-level location being narrowed.
      page: The page the characters live on.
      indices: All character indices clipped to the item's box, in
        reading order — the coordinate the alignment blocks target.
      start: Position in `indices` where this line starts (inclusive).
      end: Position in `indices` where this line ends (exclusive).
      reverse: Alignment blocks mapping clipped positions back to the
        item's own text.
      span_start: Offset of the location's charspan in the item's text.

  Returns:
      A location with the line's box and the charspan it covers.
  """
  covered = text_alignment.map_range(reverse, start, end)
  charspan = (
      location.charspan
      if covered is None
      else (span_start + covered[0], span_start + covered[1])
  )
  return SourceLocation(
      page_no=location.page_no,
      bbox=_from_bottom_left(
          page.union(indices[start:end]), location.coord_origin, page.height
      ),
      coord_origin=location.coord_origin,
      charspan=charspan,
  )


def _normalize(box: typing.Sequence[float]) -> Box:
  """Orders a pdfium char box into (left, bottom, right, top)."""
  left, bottom, right, top = box
  return (
      min(left, right),
      min(bottom, top),
      max(left, right),
      max(bottom, top),
  )


def _has_area(box: Box) -> bool:
  """True when the box encloses something worth highlighting."""
  return box[2] > box[0] and box[3] > box[1]


def _same_line(extent: tuple[float, float], other: tuple[float, float]) -> bool:
  """True when two vertical extents overlap enough to share a line."""
  overlap = min(extent[1], other[1]) - max(extent[0], other[0])
  shortest = min(extent[1] - extent[0], other[1] - other[0])
  return overlap > _LINE_OVERLAP * shortest if shortest > 0 else overlap > 0


def _to_bottom_left(location: SourceLocation, page_height: float) -> Box:
  """Converts a docling (l, t, r, b) box to pdfium's coordinate system.

  Args:
      location: The location whose bbox and coord_origin to convert.
      page_height: Page height in points.

  Returns:
      A (left, bottom, right, top) box measured from the page's bottom
      left, as pdfium reports character boxes.
  """
  left, top, right, bottom = location.bbox
  if location.coord_origin.upper() == "TOPLEFT":
    top, bottom = page_height - top, page_height - bottom
  return (
      min(left, right),
      min(top, bottom),
      max(left, right),
      max(top, bottom),
  )


def _from_bottom_left(box: Box, coord_origin: str, page_height: float) -> Box:
  """Converts a pdfium box back to a docling (l, t, r, b) box.

  Args:
      box: A (left, bottom, right, top) box in bottom-left coordinates.
      coord_origin: The origin to express the result in, "TOPLEFT" or
        "BOTTOMLEFT".
      page_height: Page height in points.

  Returns:
      A (left, top, right, bottom) box in the requested origin, matching
      the convention of the location it narrows.
  """
  left, bottom, right, top = box
  if coord_origin.upper() == "TOPLEFT":
    return (left, page_height - top, right, page_height - bottom)
  return (left, top, right, bottom)
