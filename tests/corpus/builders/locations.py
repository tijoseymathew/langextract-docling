"""Location passthrough: DocItem.prov -> SourceLocation (test-spec §5.5).

All cases share an identical two-section text; only the synthesized
ProvenanceItems vary. With docling's extraction assumed correct, faithful
order-preserving copying of page_no/bbox/coord_origin/charspan is the
entire "provenance" half of the mapping. Bboxes are distinct per item so
cross-wiring between items is detectable.
"""

from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel

from tests.corpus import builders

_SECTIONS = [
    ("heading", "Opening section LXM001 heading"),
    ("text", "The first paragraph carries LXM002 within it."),
    ("heading", "Closing section LXM003 heading"),
    ("text", "The final paragraph carries LXM004 within it."),
]
_MARKERS = ["LXM001", "LXM002", "LXM003", "LXM004"]


def _two_section_case(name: str, provs: list) -> builders.BuiltCase:
  """Builds the shared skeleton; provs[i] is None or a ProvenanceItem list."""
  doc = DoclingDocument(name=name)
  probes = []
  for (kind, text), marker, prov in zip(_SECTIONS, _MARKERS, provs):
    prov_list = prov or []
    first = prov_list[0] if prov_list else None
    if kind == "heading":
      item = doc.add_heading(text=text, level=1, prov=first)
    else:
      item = doc.add_text(label=DocItemLabel.TEXT, text=text, prov=first)
    item.prov.extend(prov_list[1:])
    probes.append(builders.span_probe(marker, item))
  return builders.BuiltCase(doc=doc, probes=probes)


@builders.builder("prov-none")
def prov_none() -> builders.BuiltCase:
  """No ProvenanceItems: locations == (), doc_item_ref still set."""
  return _two_section_case("prov-none", [None, None, None, None])


@builders.builder("prov-single")
def prov_single() -> builders.BuiltCase:
  """One location per item; every page/bbox pair unique."""
  provs = [
      [builders.prov_item(1, (10.0, 20.0, 210.0, 40.0), "TOPLEFT", (0, 30))],
      [builders.prov_item(1, (10.0, 60.0, 350.0, 80.0), "TOPLEFT", (0, 46))],
      [builders.prov_item(2, (15.0, 25.0, 215.0, 45.0), "TOPLEFT", (0, 30))],
      [builders.prov_item(3, (15.0, 65.0, 355.0, 85.0), "TOPLEFT", (0, 46))],
  ]
  return _two_section_case("prov-single", provs)


@builders.builder("prov-multi-location")
def prov_multi_location() -> builders.BuiltCase:
  """An item split across pages keeps both locations, in order."""
  provs = [
      [builders.prov_item(1, (10.0, 20.0, 210.0, 40.0), "TOPLEFT", (0, 30))],
      [
          builders.prov_item(
              1, (10.0, 700.0, 350.0, 780.0), "TOPLEFT", (0, 20)
          ),
          builders.prov_item(2, (10.0, 30.0, 350.0, 60.0), "TOPLEFT", (20, 46)),
      ],
      [builders.prov_item(2, (15.0, 25.0, 215.0, 45.0), "TOPLEFT", (0, 30))],
      None,
  ]
  return _two_section_case("prov-multi-location", provs)


@builders.builder("prov-partial-charspan")
def prov_partial_charspan() -> builders.BuiltCase:
  """Partial and zero-width charspans are copied verbatim."""
  provs = [
      [builders.prov_item(1, (10.0, 20.0, 210.0, 40.0), "TOPLEFT", (4, 19))],
      [builders.prov_item(1, (10.0, 60.0, 350.0, 80.0), "TOPLEFT", (0, 0))],
      None,
      None,
  ]
  return _two_section_case("prov-partial-charspan", provs)


@builders.builder("prov-coord-origins")
def prov_coord_origins() -> builders.BuiltCase:
  """TOPLEFT and BOTTOMLEFT copied as strings, never converted."""
  provs = [
      [builders.prov_item(1, (10.0, 20.0, 210.0, 40.0), "TOPLEFT", (0, 30))],
      [
          builders.prov_item(
              1, (10.0, 780.0, 350.0, 760.0), "BOTTOMLEFT", (0, 46)
          )
      ],
      [
          builders.prov_item(
              2, (15.0, 800.0, 215.0, 770.0), "BOTTOMLEFT", (0, 30)
          )
      ],
      [builders.prov_item(2, (15.0, 65.0, 355.0, 85.0), "TOPLEFT", (0, 46))],
  ]
  return _two_section_case("prov-coord-origins", provs)


@builders.builder("prov-mixed")
def prov_mixed() -> builders.BuiltCase:
  """Alternating items with and without provenance in one document."""
  provs = [
      [builders.prov_item(1, (10.0, 20.0, 210.0, 40.0), "TOPLEFT", (0, 30))],
      None,
      [builders.prov_item(2, (15.0, 25.0, 215.0, 45.0), "TOPLEFT", (0, 30))],
      None,
  ]
  return _two_section_case("prov-mixed", provs)
