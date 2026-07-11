"""Offset-shift cases: serialized text differs from stored text (§5.2).

The markdown serializer may escape or normalize item text, so serialized
spans can have different lengths than the stored DocItem.text. Offsets must
track the output; markers are ASCII-alphanumeric, hence escape-proof, and
placed after the specials so any length drift misplaces their span.
"""

from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel

from tests.corpus import builders


@builders.builder("map-md-specials")
def map_md_specials() -> builders.BuiltCase:
  """Literal markdown special characters ahead of each marker."""
  doc = DoclingDocument(name="map-md-specials")
  paragraphs = [
      "Stars *emphasis* and **strong** precede LXM001 here.",
      "Under_scores _wrap_ this__ text before LXM002 arrives.",
      "Hash # signs and ## double hashes sit before LXM003 now.",
      "Pipes | split | cells | before LXM004 in this line.",
      "Backticks `code` and ``double`` come before LXM005 too.",
      "A link [x](y) and image ![a](b) precede LXM006 finally.",
  ]
  probes = []
  for index, text in enumerate(paragraphs, start=1):
    item = doc.add_text(label=DocItemLabel.TEXT, text=text)
    probes.append(builders.span_probe(f"LXM00{index}", item))
  return builders.BuiltCase(doc=doc, probes=probes)


@builders.builder("map-fake-syntax")
def map_fake_syntax() -> builders.BuiltCase:
  """Plain paragraphs whose text merely looks like markdown structure."""
  doc = DoclingDocument(name="map-fake-syntax")
  paragraphs = [
      "1. Not an ordered list, just prose with LXM001 inside.",
      "- Not a bullet either, only a dash before LXM002 here.",
      "## Not a heading, a paragraph that carries LXM003 along.",
      "> Not a quote, simply an angle bracket before LXM004.",
  ]
  probes = []
  for index, text in enumerate(paragraphs, start=1):
    item = doc.add_text(label=DocItemLabel.TEXT, text=text)
    probes.append(builders.span_probe(f"LXM00{index}", item))
  return builders.BuiltCase(doc=doc, probes=probes)


@builders.builder("map-unicode")
def map_unicode() -> builders.BuiltCase:
  """Mixed-width neighbors: offsets count code points, never bytes."""
  doc = DoclingDocument(name="map-unicode")
  paragraphs = [
      "汉字文本环绕着 LXM001 这个标记继续。",
      "نص عربي يحيط بالعلامة LXM002 قبل النهاية.",
      "Family emoji 👨‍👩‍👧‍👦 and flags 🏳️‍🌈 precede LXM003 here.",
      # NFD sequences: base letters followed by combining accents.
      "Combining diacritics e\u0301a\u0308o\u0302 surround LXM004 closely.",
  ]
  items = []
  probes = []
  for index, text in enumerate(paragraphs, start=1):
    item = doc.add_text(label=DocItemLabel.TEXT, text=text)
    items.append(item)
    probes.append(builders.span_probe(f"LXM00{index}", item))
  # Straddling wide-char items catches any byte/grapheme counting drift.
  probes.append(builders.straddle_probe("LXM001", "LXM002", items[:2]))
  probes.append(builders.straddle_probe("LXM003", "LXM004", items[2:]))
  return builders.BuiltCase(doc=doc, probes=probes)
