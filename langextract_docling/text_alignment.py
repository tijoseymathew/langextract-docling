"""Monotonic character alignment between two renderings of one text.

Sub-item provenance joins three views of the same words: the serialized
markdown langextract aligns against, the source item's own text that
ProvenanceItem.charspan indexes into, and the characters the PDF page
actually carries. Each pair differs only by insertions and deletions —
markdown escapes and heading/list prefixes on one side, line breaks and
soft hyphens on the other — so the runs the two strings share are enough
to map an offset from either onto the other, and to refuse where they
share nothing.

Pure stdlib: this module is imported by provenance.py, which stays free of
docling and PDF dependencies.
"""

import difflib
import typing

Block = tuple[int, int, int]
"""A run present in both strings: (source_start, target_start, length)."""

# Any two prose strings share scattered single characters, so only runs
# this long count as evidence that they are renderings of one text.
_MIN_TRUSTED_RUN = 4

# And those runs must account for this much of the string being placed.
_MIN_TRUSTED_FRACTION = 0.5


def matching_blocks(source: str, target: str) -> list[Block]:
  """Returns the runs of characters that source and target share.

  Blocks are non-overlapping and strictly increasing in both strings, so
  they define a monotonic partial mapping between the two: characters
  inside a block correspond one-to-one, characters outside one exist in
  only one of the strings.

  Args:
      source: The string whose offsets are being mapped.
      target: The string to map them onto.

  Returns:
      Non-empty (source_start, target_start, length) blocks, in order.
  """
  matcher = difflib.SequenceMatcher(None, source, target, autojunk=False)
  return [
      (source_start, target_start, length)
      for source_start, target_start, length in matcher.get_matching_blocks()
      if length
  ]


def trusted_blocks(source: str, target: str) -> list[Block]:
  """Aligns two strings, refusing alignments that are coincidence.

  Every pair of English strings has characters in common, so a bare
  alignment always produces something. This asks the stronger question —
  is `target` a rendering of `source`? — and answers no unless whole
  runs of `source` are present in it.

  Args:
      source: The string being placed, e.g. a document item's own text.
      target: The string to place it in, e.g. the characters found inside
        that item's bounding box.

  Returns:
      Blocks as matching_blocks() returns them, or [] when the two
      strings share no substantial run.
  """
  if not source or not target:
    return []
  blocks = matching_blocks(source, target)
  minimum_run = min(_MIN_TRUSTED_RUN, len(source))
  substantial = sum(length for _, _, length in blocks if length >= minimum_run)
  if substantial < _MIN_TRUSTED_FRACTION * len(source):
    return []
  return blocks


def invert(blocks: typing.Sequence[Block]) -> list[Block]:
  """Returns the same alignment read from the target's side."""
  return [
      (target_start, source_start, length)
      for source_start, target_start, length in blocks
  ]


def map_range(
    blocks: typing.Sequence[Block], start: int, end: int
) -> tuple[int, int] | None:
  """Maps a source range onto the tightest target range covering it.

  Only characters inside a matching block carry over; source characters
  with no counterpart (an escape backslash, a "## " prefix) contribute
  nothing, so a range consisting solely of those maps to None rather than
  to a guessed position.

  Args:
      blocks: Blocks from matching_blocks(), in order.
      start: Start of the source range (inclusive).
      end: End of the source range (exclusive).

  Returns:
      A (target_start, target_end) half-open range, or None when the
      source range shares no character with the target.
  """
  if start >= end:
    return None
  lo = hi = None
  for source_start, target_start, length in blocks:
    if source_start >= end:
      break
    overlap_start = max(start, source_start)
    overlap_end = min(end, source_start + length)
    if overlap_start >= overlap_end:
      continue
    offset = target_start - source_start
    if lo is None:
      lo = overlap_start + offset
    hi = overlap_end + offset
  return None if lo is None else (lo, hi)
