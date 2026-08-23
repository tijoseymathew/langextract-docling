"""Repetition cases: the mapping must be positional, not text-search (§5.3).

Repeated strings are probed by occurrence index; each occurrence must map
to its own item, so any implementation that searches the text instead of
tracking offsets collapses the occurrences onto one item.
"""

from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.document import TableCell
from docling_core.types.doc.document import TableData
from docling_core.types.doc.labels import DocItemLabel

from tests.corpus import builders


@builders.builder("map-repeat-identical")
def map_repeat_identical() -> builders.BuiltCase:
  """The exact same sentence as two items under different headings."""
  doc = DoclingDocument(name="map-repeat-identical")
  sentence = "This sentence appears twice, verbatim, in the document."
  head_a = doc.add_heading(text="First home LXM001 of the sentence", level=1)
  item_a = doc.add_text(label=DocItemLabel.TEXT, text=sentence)
  head_b = doc.add_heading(text="Second home LXM002 of the sentence", level=1)
  item_b = doc.add_text(label=DocItemLabel.TEXT, text=sentence)
  probes = [
      builders.span_probe("LXM001", head_a),
      builders.span_probe("LXM002", head_b),
      builders.occurrence_probe(sentence, 1, item_a),
      builders.occurrence_probe(sentence, 2, item_b),
  ]
  return builders.BuiltCase(doc=doc, probes=probes)


@builders.builder("map-repeat-substring")
def map_repeat_substring() -> builders.BuiltCase:
  """Item B's text is a strict substring of item A's text."""
  doc = DoclingDocument(name="map-repeat-substring")
  shared = "the engine computes numbers"
  item_a = doc.add_text(
      label=DocItemLabel.TEXT,
      text=f"Everyone knows LXM001 that {shared} without any error.",
  )
  item_b = doc.add_text(label=DocItemLabel.TEXT, text=shared)
  probes = [
      builders.span_probe("LXM001", item_a),
      builders.occurrence_probe(shared, 1, item_a),
      builders.occurrence_probe(shared, 2, item_b),
  ]
  return builders.BuiltCase(doc=doc, probes=probes)


@builders.builder("map-repeat-cross-type")
def map_repeat_cross_type() -> builders.BuiltCase:
  """Same string as heading, list item, and table cell."""
  doc = DoclingDocument(name="map-repeat-cross-type")
  phrase = "Bernoulli numbers everywhere"
  heading = doc.add_heading(text=phrase, level=1)
  group = doc.add_list_group()
  list_item = doc.add_list_item(text=phrase, parent=group)
  table = doc.add_table(
      data=TableData(
          num_rows=1,
          num_cols=1,
          table_cells=[
              TableCell(
                  text=phrase,
                  start_row_offset_idx=0,
                  end_row_offset_idx=1,
                  start_col_offset_idx=0,
                  end_col_offset_idx=1,
              )
          ],
      )
  )
  probes = [
      builders.occurrence_probe(phrase, 1, heading),
      builders.occurrence_probe(phrase, 2, list_item),
      builders.occurrence_probe(phrase, 3, table),
  ]
  return builders.BuiltCase(doc=doc, probes=probes)
