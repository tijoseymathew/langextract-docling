"""Offset-bookkeeping cases: the serializer walk arithmetic (test-spec §5.1).

Every case here stresses the `start = len(assembled) + len(delim)` logic of
serialize_with_provenance() — first-item offset, steady state, empty-item
skips, and the degenerate single-item and empty documents.
"""

from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel

from tests.corpus import builders


@builders.builder("map-baseline")
def map_baseline() -> builders.BuiltCase:
  """Title, two sections of paragraphs; steady-state offset arithmetic."""
  doc = DoclingDocument(name="map-baseline")
  title = doc.add_title(text="Corpus baseline LXM001 report")
  head_a = doc.add_heading(text="First section LXM002 heading", level=1)
  para_1 = doc.add_text(
      label=DocItemLabel.TEXT,
      text="The opening paragraph carries LXM003 in its middle.",
  )
  para_2 = doc.add_text(
      label=DocItemLabel.TEXT,
      text="A second paragraph mentions LXM004 before ending.",
  )
  head_b = doc.add_heading(text="Second section LXM005 heading", level=1)
  para_3 = doc.add_text(
      label=DocItemLabel.TEXT,
      text="The third paragraph hides LXM006 mid-sentence.",
  )
  para_4 = doc.add_text(
      label=DocItemLabel.TEXT,
      text="A closing paragraph keeps LXM007 near the end.",
  )
  probes = [
      builders.span_probe("LXM001", title),
      builders.span_probe("LXM002", head_a),
      builders.span_probe("LXM003", para_1),
      builders.span_probe("LXM004", para_2),
      builders.span_probe("LXM005", head_b),
      builders.span_probe("LXM006", para_3),
      builders.span_probe("LXM007", para_4),
      builders.straddle_probe("LXM003", "LXM004", [para_1, para_2]),
      builders.straddle_probe("LXM006", "LXM007", [para_3, para_4]),
  ]
  return builders.BuiltCase(doc=doc, probes=probes)


@builders.builder("map-heading-prefix")
def map_heading_prefix() -> builders.BuiltCase:
  """Serializer-added '## ' prefixes shift spans past the stored text."""
  doc = DoclingDocument(name="map-heading-prefix")
  probes = []
  for level, marker in [(1, "LXM001"), (2, "LXM002"), (3, "LXM003")]:
    heading = doc.add_heading(
        text=f"Level {level} heading {marker} text", level=level
    )
    probes.append(builders.span_probe(marker, heading))
  tail = doc.add_text(
      label=DocItemLabel.TEXT,
      text="A plain paragraph with LXM004 after the headings.",
  )
  probes.append(builders.span_probe("LXM004", tail))
  return builders.BuiltCase(doc=doc, probes=probes)


@builders.builder("map-empty-text-item")
def map_empty_text_item() -> builders.BuiltCase:
  """An item serializing to '' must consume neither a span nor a delimiter."""
  doc = DoclingDocument(name="map-empty-text-item")
  before = doc.add_text(
      label=DocItemLabel.TEXT,
      text="The paragraph before the gap holds LXM001 safely.",
  )
  doc.add_text(label=DocItemLabel.TEXT, text="")
  after = doc.add_text(
      label=DocItemLabel.TEXT,
      text="The paragraph after the gap holds LXM002 safely.",
  )
  probes = [
      builders.span_probe("LXM001", before),
      builders.span_probe("LXM002", after),
      # Exactly these two refs: the empty item left no phantom span.
      builders.straddle_probe("LXM001", "LXM002", [before, after]),
  ]
  return builders.BuiltCase(doc=doc, probes=probes)


@builders.builder("map-single-item")
def map_single_item() -> builders.BuiltCase:
  """One paragraph: span is [0, len(text)) and there are no gaps."""
  doc = DoclingDocument(name="map-single-item")
  only = doc.add_text(
      label=DocItemLabel.TEXT,
      text="A single paragraph containing LXM001 and nothing else.",
  )
  return builders.BuiltCase(
      doc=doc, probes=[builders.span_probe("LXM001", only)]
  )


@builders.builder("map-empty-doc")
def map_empty_doc() -> builders.BuiltCase:
  """No body items: serialization is '' and every lookup is empty."""
  return builders.BuiltCase(
      doc=DoclingDocument(name="map-empty-doc"), probes=[]
  )
