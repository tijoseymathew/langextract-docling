"""Multi-item spans and groups (test-spec §5.4).

Items serialized as one unit (list groups, inline groups, tables with
captions, pictures with captions) emit one SpanProvenance per contributing
DocItem, all sharing an identical [start, end) range.
"""

from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.document import TableCell
from docling_core.types.doc.document import TableData
from docling_core.types.doc.labels import DocItemLabel

from tests.corpus import builders


def _table_data(rows: list[list[str]]) -> TableData:
  cells = [
      TableCell(
          text=text,
          start_row_offset_idx=row_index,
          end_row_offset_idx=row_index + 1,
          start_col_offset_idx=col_index,
          end_col_offset_idx=col_index + 1,
      )
      for row_index, row in enumerate(rows)
      for col_index, text in enumerate(row)
  ]
  return TableData(num_rows=len(rows), num_cols=len(rows[0]), table_cells=cells)


@builders.builder("map-list-group")
def map_list_group() -> builders.BuiltCase:
  """Flat ListGroup: identical range, three distinct refs."""
  doc = DoclingDocument(name="map-list-group")
  group = doc.add_list_group()
  items = [
      doc.add_list_item(
          text=f"List entry number {n} holds LXM00{n} today.", parent=group
      )
      for n in (1, 2, 3)
  ]
  probes = [
      builders.group_probe(["LXM001", "LXM002", "LXM003"], items),
  ]
  return builders.BuiltCase(doc=doc, probes=probes)


@builders.builder("map-list-nested")
def map_list_nested() -> builders.BuiltCase:
  """3-deep nesting: all descendants share the outer group's range."""
  doc = DoclingDocument(name="map-list-nested")
  outer = doc.add_list_group()
  first = doc.add_list_item(
      text="Outer level holds LXM001 up top.", parent=outer
  )
  middle = doc.add_list_group(parent=first)
  second = doc.add_list_item(
      text="Middle level keeps LXM002 nested.", parent=middle
  )
  inner = doc.add_list_group(parent=second)
  third = doc.add_list_item(text="Deep level hides LXM003 below.", parent=inner)
  probes = [
      builders.group_probe(
          ["LXM001", "LXM002", "LXM003"], [first, second, third]
      ),
  ]
  return builders.BuiltCase(doc=doc, probes=probes)


@builders.builder("map-inline-group")
def map_inline_group() -> builders.BuiltCase:
  """InlineGroup children serialize joined into one shared range."""
  doc = DoclingDocument(name="map-inline-group")
  group = doc.add_inline_group()
  items = [
      doc.add_text(
          label=DocItemLabel.TEXT,
          text=f"inline piece {n} carrying LXM00{n}",
          parent=group,
      )
      for n in (1, 2)
  ]
  probes = [builders.group_probe(["LXM001", "LXM002"], items)]
  return builders.BuiltCase(doc=doc, probes=probes)


@builders.builder("map-two-lists")
def map_two_lists() -> builders.BuiltCase:
  """List, paragraph, list: two separate shared ranges around a solo span."""
  doc = DoclingDocument(name="map-two-lists")
  first_group = doc.add_list_group()
  first_items = [
      doc.add_list_item(
          text=f"First list entry {n} has LXM00{n} inside.", parent=first_group
      )
      for n in (1, 2)
  ]
  paragraph = doc.add_text(
      label=DocItemLabel.TEXT,
      text="A lone paragraph between the lists carries LXM003.",
  )
  second_group = doc.add_list_group()
  second_items = [
      doc.add_list_item(
          text=f"Second list entry {n} has LXM00{n} inside.",
          parent=second_group,
      )
      for n in (4, 5)
  ]
  probes = [
      builders.group_probe(["LXM001", "LXM002"], first_items),
      builders.span_probe("LXM003", paragraph),
      builders.group_probe(["LXM004", "LXM005"], second_items),
      # From inside the first list into the paragraph: the list's shared
      # range contributes every list item, plus the paragraph itself.
      builders.straddle_probe("LXM002", "LXM003", first_items + [paragraph]),
  ]
  return builders.BuiltCase(doc=doc, probes=probes)


@builders.builder("map-table")
def map_table() -> builders.BuiltCase:
  """3x3 table: every cell marker resolves to the single TableItem ref."""
  doc = DoclingDocument(name="map-table")
  markers = [[f"LXM{r}{c}1" for c in range(3)] for r in range(3)]
  rows = [[f"cell {r}{c} {markers[r][c]}" for c in range(3)] for r in range(3)]
  table = doc.add_table(data=_table_data(rows))
  probes = [
      builders.span_probe(marker, table) for row in markers for marker in row
  ]
  return builders.BuiltCase(doc=doc, probes=probes)


@builders.builder("map-table-caption")
def map_table_caption() -> builders.BuiltCase:
  """Caption and table serialize as one shared range with both refs."""
  doc = DoclingDocument(name="map-table-caption")
  caption = doc.add_text(
      label=DocItemLabel.CAPTION, text="A captioned table shows LXM001 here."
  )
  rows = [["head LXM002", "head LXM003"], ["body LXM004", "body LXM005"]]
  table = doc.add_table(data=_table_data(rows), caption=caption)
  probes = [
      # docling-core serializes caption + table as one result, so every
      # marker (caption or cell) resolves to the same range with both refs.
      builders.group_probe(["LXM001", "LXM002", "LXM004"], [caption, table]),
  ]
  return builders.BuiltCase(doc=doc, probes=probes)


@builders.builder("map-picture-caption")
def map_picture_caption() -> builders.BuiltCase:
  """Picture placeholder and caption share one range with both refs."""
  doc = DoclingDocument(name="map-picture-caption")
  caption = doc.add_text(
      label=DocItemLabel.CAPTION, text="A captioned picture shows LXM001."
  )
  picture = doc.add_picture(caption=caption)
  after = doc.add_text(
      label=DocItemLabel.TEXT,
      text="A paragraph after the picture holds LXM002 safely.",
  )
  probes = [
      builders.group_probe(["LXM001"], [caption, picture]),
      builders.span_probe("LXM002", after),
  ]
  return builders.BuiltCase(doc=doc, probes=probes)


@builders.builder("map-code-formula")
def map_code_formula() -> builders.BuiltCase:
  """Code blocks (with backtick runs) and formula items."""
  doc = DoclingDocument(name="map-code-formula")
  code = doc.add_code(text="print('LXM001')  # ``` fenced backticks inside")
  formula = doc.add_formula(text="E = mc^2 + LXM002")
  probes = [
      builders.span_probe("LXM001", code),
      builders.span_probe("LXM002", formula),
  ]
  return builders.BuiltCase(doc=doc, probes=probes)
