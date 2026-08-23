"""Tests for langextract_docling.text_alignment."""

from langextract_docling import text_alignment

# "a\_b" as markdown escapes it, against the item's own "a_b": the two
# share the leading "a" and the trailing "_b", but not the backslash.
ESCAPED = text_alignment.matching_blocks(r"a\_b", "a_b")


class TestMatchingBlocks:

  def test_identical_strings_are_one_block(self):
    assert text_alignment.matching_blocks("abc", "abc") == [(0, 0, 3)]

  def test_strings_with_nothing_in_common_share_no_block(self):
    assert text_alignment.matching_blocks("abc", "xyz") == []

  def test_empty_string_shares_no_block(self):
    assert text_alignment.matching_blocks("", "abc") == []
    assert text_alignment.matching_blocks("abc", "") == []

  def test_escape_character_splits_the_run(self):
    assert ESCAPED == [(0, 0, 1), (2, 1, 2)]

  def test_heading_prefix_shifts_the_block(self):
    assert text_alignment.matching_blocks("## Heading", "Heading") == [
        (3, 0, 7)
    ]

  def test_blocks_are_never_empty(self):
    blocks = text_alignment.matching_blocks("a-b-c", "abc")
    assert blocks
    assert all(length > 0 for _, _, length in blocks)

  def test_blocks_advance_in_both_strings(self):
    blocks = text_alignment.matching_blocks("one two three", "one. two! three")
    for (start, target, length), (next_start, next_target, _) in zip(
        blocks, blocks[1:]
    ):
      assert start + length <= next_start
      assert target + length <= next_target


class TestTrustedBlocks:
  """The stronger question: is one string a rendering of the other?"""

  def test_line_break_instead_of_a_space_is_still_the_same_text(self):
    item = "conducted by Ada Lovelace and Charles Babbage"
    on_page = "conducted by Ada Lovelace and\r\nCharles Babbage"
    blocks = text_alignment.trusted_blocks(item, on_page)
    assert text_alignment.map_range(blocks, 13, 25) == (13, 25)

  def test_unrelated_prose_is_refused(self):
    assert (
        text_alignment.trusted_blocks(
            "wholly unrelated wording",
            "This report summarizes the research conducted by Ada Lovelace",
        )
        == []
    )

  def test_empty_strings_are_refused(self):
    assert text_alignment.trusted_blocks("", "anything") == []
    assert text_alignment.trusted_blocks("anything", "") == []

  def test_a_string_present_in_full_is_accepted(self):
    assert text_alignment.trusted_blocks("Ada", "by Ada Lovelace") == [
        (0, 3, 3)
    ]

  def test_a_string_barely_present_is_refused(self):
    assert text_alignment.trusted_blocks("Ada Lovelace wrote", "Ada") == []


class TestInvert:

  def test_reads_the_alignment_from_the_other_side(self):
    assert text_alignment.invert([(0, 5, 2), (4, 9, 3)]) == [
        (5, 0, 2),
        (9, 4, 3),
    ]

  def test_inverting_twice_restores_the_alignment(self):
    blocks = text_alignment.matching_blocks("## Heading", "Heading")
    assert text_alignment.invert(text_alignment.invert(blocks)) == blocks


class TestMapRange:

  def test_range_inside_one_block(self):
    assert text_alignment.map_range(ESCAPED, 2, 4) == (1, 3)

  def test_range_spanning_blocks_covers_both(self):
    assert text_alignment.map_range(ESCAPED, 0, 4) == (0, 3)

  def test_range_of_unmatched_characters_maps_to_nothing(self):
    assert text_alignment.map_range(ESCAPED, 1, 2) is None

  def test_zero_length_range_maps_to_nothing(self):
    assert text_alignment.map_range(ESCAPED, 2, 2) is None

  def test_inverted_range_maps_to_nothing(self):
    assert text_alignment.map_range(ESCAPED, 4, 2) is None

  def test_without_blocks_nothing_maps(self):
    assert text_alignment.map_range([], 0, 5) is None

  def test_range_is_clipped_to_the_block_it_overlaps(self):
    assert text_alignment.map_range([(5, 100, 5)], 3, 8) == (100, 103)

  def test_range_before_every_block_maps_to_nothing(self):
    assert text_alignment.map_range([(5, 100, 5)], 0, 5) is None

  def test_range_after_every_block_maps_to_nothing(self):
    assert text_alignment.map_range([(5, 100, 5)], 10, 20) is None

  def test_range_covering_a_gap_spans_the_blocks_around_it(self):
    # Characters between two blocks exist in only one string, so the
    # result is the tightest range enclosing what both share.
    blocks = [(0, 0, 2), (10, 5, 2)]
    assert text_alignment.map_range(blocks, 1, 11) == (1, 6)
