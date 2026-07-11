"""Exclusion cases: skipped items leave no trace in the map (§5.6).

Furniture (page headers/footers) never enters the body walk; items filtered
by serializer params land in get_excluded_refs and take the excluded-refs
skip branch of the walk (spec §6.3 step 1). Either way, their markers must
be absent from the output and the surviving offsets unaffected.
"""

from docling_core.types.doc.document import ContentLayer
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel

from tests.corpus import builders


@builders.builder("map-furniture")
def map_furniture() -> builders.BuiltCase:
  """Page header/footer items are skipped; body offsets are unaffected."""
  doc = DoclingDocument(name="map-furniture")
  header = doc.add_text(
      label=DocItemLabel.PAGE_HEADER,
      text="Running header with LXM101 never serialized.",
      content_layer=ContentLayer.FURNITURE,
  )
  first = doc.add_text(
      label=DocItemLabel.TEXT,
      text="The first body paragraph keeps LXM001 visible.",
  )
  footer = doc.add_text(
      label=DocItemLabel.PAGE_FOOTER,
      text="Running footer with LXM102 never serialized.",
      content_layer=ContentLayer.FURNITURE,
  )
  second = doc.add_text(
      label=DocItemLabel.TEXT,
      text="The second body paragraph keeps LXM002 visible.",
  )
  probes = [
      builders.absent_probe("LXM101", header),
      builders.absent_probe("LXM102", footer),
      builders.span_probe("LXM001", first),
      builders.span_probe("LXM002", second),
      # Adjacent in the output despite the furniture between them.
      builders.straddle_probe("LXM001", "LXM002", [first, second]),
  ]
  return builders.BuiltCase(doc=doc, probes=probes)


@builders.builder("map-excluded-refs")
def map_excluded_refs() -> builders.BuiltCase:
  """A pages filter routes body items through the excluded_refs branch."""
  doc = DoclingDocument(name="map-excluded-refs")
  page_bbox = (10.0, 20.0, 400.0, 40.0)
  first = doc.add_text(
      label=DocItemLabel.TEXT,
      text="A page-one paragraph carries LXM001 along.",
      prov=builders.prov_item(1, page_bbox, "TOPLEFT", (0, 42)),
  )
  excluded = doc.add_text(
      label=DocItemLabel.TEXT,
      text="A page-two paragraph carries LXM201 along.",
      prov=builders.prov_item(2, page_bbox, "TOPLEFT", (0, 42)),
  )
  last = doc.add_text(
      label=DocItemLabel.TEXT,
      text="Another page-one paragraph carries LXM002 along.",
      prov=builders.prov_item(1, (10.0, 60.0, 400.0, 80.0), "TOPLEFT", (0, 48)),
  )
  probes = [
      builders.span_probe("LXM001", first),
      builders.absent_probe("LXM201", excluded),
      builders.span_probe("LXM002", last),
      builders.straddle_probe("LXM001", "LXM002", [first, last]),
  ]
  return builders.BuiltCase(
      doc=doc, probes=probes, serializer_kwargs={"pages": [1]}
  )
