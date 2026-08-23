"""Builds the hero PDF used to demo the end-to-end pipeline.

    python examples/make_hero_pdf.py [path]

The document is deliberately built to exercise every part of the pipeline
that provenance has to survive:

  * three heading levels, so the chunker emits real section context;
  * inline markdown (bold, italic) inside otherwise plain paragraphs;
  * bullet and numbered lists, which docling groups into ListGroups whose
    items share a text range;
  * two tables with captions, so extractions can resolve into table cells;
  * text carrying markdown-significant characters (`_`, `*`, `#`, `[`, `>`)
    that the serializer has to escape without shifting the offset map;
  * entity names repeated across prose, list items and table cells, so a
    mention can only be placed by pinning the right occurrence;
  * two pages, so provenance has to carry a page number that is not 1.

reportlab lays out deterministically, so the PDF is reproducible and is
never committed.
"""

import pathlib
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import ListFlowable
from reportlab.platypus import ListItem
from reportlab.platypus import PageBreak
from reportlab.platypus import Paragraph
from reportlab.platypus import SimpleDocTemplate
from reportlab.platypus import Spacer
from reportlab.platypus import Table
from reportlab.platypus import TableStyle

DEFAULT_PATH = pathlib.Path(__file__).parent / "hero_report.pdf"

_MEASUREMENTS = [
    ["Site", "Lead", "Sample", "Yield", "Drift"],
    ["Reykjavik", "Amara Osei", "HX_204", "94.2%", "+0.8%"],
    ["Reykjavik", "Amara Osei", "HX_205", "91.7%", "-1.4%"],
    ["Trondheim", "Ines Alvarado", "HX_311", "88.0%", "+2.1%"],
    ["Valparaiso", "Ines Alvarado", "HX_418", "96.5%", "+0.2%"],
]

_PERSONNEL = [
    ["Name", "Role", "Affiliation"],
    ["Amara Osei", "Principal investigator", "Kestrel Dynamics"],
    ["Ines Alvarado", "Field engineer", "Kestrel Dynamics"],
    ["Tomas Berg", "Instrumentation lead", "Nordvik Institute"],
]

_TABLE_STYLE = TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#607d8b")),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#cfd8dc")),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 9),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
])


def _styles():
  sheet = getSampleStyleSheet()
  sheet.add(
      ParagraphStyle(
          "HeroBody",
          parent=sheet["BodyText"],
          alignment=TA_JUSTIFY,
          spaceAfter=8,
          leading=14,
      )
  )
  sheet.add(
      ParagraphStyle(
          "HeroCaption",
          parent=sheet["BodyText"],
          fontSize=9,
          textColor=colors.HexColor("#455a64"),
          spaceBefore=4,
          spaceAfter=12,
      )
  )
  sheet.add(
      ParagraphStyle(
          "HeroQuote",
          parent=sheet["BodyText"],
          leftIndent=18,
          rightIndent=18,
          fontName="Helvetica-Oblique",
          textColor=colors.HexColor("#37474f"),
          spaceAfter=10,
      )
  )
  return sheet


def build_hero_pdf(path: pathlib.Path) -> pathlib.Path:
  """Writes the two-page hero report to `path` and returns it."""
  s = _styles()
  body, caption, quote = s["HeroBody"], s["HeroCaption"], s["HeroQuote"]

  story = [
      Paragraph("Helios Deposition Program", s["Title"]),
      Paragraph(
          "Quarterly Field Report &mdash; prepared by Kestrel Dynamics",
          caption,
      ),
      Paragraph("1. Executive Summary", s["Heading1"]),
      Paragraph(
          "Across the third quarter the deposition program held a mean yield"
          " of <b>92.6%</b> over four sites. <b>Amara Osei</b> led the"
          " Reykjavik campaign, where the reworked feed line lifted yield"
          " above the 90% floor for the first time since commissioning."
          " Kestrel Dynamics now recommends promoting the Reykjavik"
          " configuration to the remaining sites.",
          body,
      ),
      Paragraph(
          "Two risks remain open. The drift term <i>delta_peak</i> still"
          " exceeds the [draft] tolerance of 2%, and the spare-parts budget"
          " for the #3 chamber runs out before the next quarter closes.",
          body,
      ),
      Paragraph("1.1 Scope", s["Heading2"]),
      ListFlowable(
          [
              ListItem(
                  Paragraph(
                      "Four production sites: Reykjavik, Trondheim,"
                      " Valparaiso and the Nordvik pilot line.",
                      body,
                  )
              ),
              ListItem(
                  Paragraph(
                      "Sample families HX_204 through HX_418, excluding the"
                      " recalled HX_309 batch.",
                      body,
                  )
              ),
              ListItem(
                  Paragraph(
                      "Instrumentation signed off by <b>Tomas Berg</b> of the"
                      " Nordvik Institute.",
                      body,
                  )
              ),
          ],
          bulletType="bullet",
      ),
      Spacer(1, 10),
      Paragraph("2. Site Measurements", s["Heading1"]),
      Paragraph(
          "Yield is reported per sample and averaged over three runs; drift"
          " is the deviation of <i>delta_peak</i> from its calibration"
          " value. Reykjavik reports two samples because the second chamber"
          " came back online mid-quarter.",
          body,
      ),
      Table(_MEASUREMENTS, style=_TABLE_STYLE, hAlign="LEFT"),
      Paragraph("Table 1: Yield and drift by site, quarter three.", caption),
      Paragraph("2.1 Method", s["Heading3"]),
      ListFlowable(
          [
              ListItem(
                  Paragraph(
                      "Purge the chamber and hold vacuum for 30 minutes.",
                      body,
                  )
              ),
              ListItem(
                  Paragraph(
                      "Deposit at 640 &deg;C, ramping at 12 &deg;C * min^-1.",
                      body,
                  )
              ),
              ListItem(
                  Paragraph(
                      "Measure yield > 90% against the reference coupon.",
                      body,
                  )
              ),
          ],
          bulletType="1",
      ),
      PageBreak(),
      Paragraph("3. Personnel", s["Heading1"]),
      Paragraph(
          "The quarter was staffed by three engineers across two"
          " organizations.",
          body,
      ),
      Table(
          _PERSONNEL,
          style=_TABLE_STYLE,
          hAlign="LEFT",
          colWidths=[
              4.5 * cm,
              5.5 * cm,
              5.0 * cm,
          ],
      ),
      Paragraph("Table 2: Personnel and affiliations.", caption),
      Paragraph("4. Observations", s["Heading1"]),
      ListFlowable(
          [
              ListItem(
                  Paragraph(
                      "Amara Osei observed that the Reykjavik feed line"
                      " stabilized within two runs of the rework.",
                      body,
                  )
              ),
              ListItem(
                  Paragraph(
                      "Ines Alvarado traced the Trondheim shortfall to a"
                      " miscalibrated coupon rather than the deposition"
                      " chamber itself.",
                      body,
                  )
              ),
              ListItem(
                  Paragraph(
                      "Tomas Berg flagged that the Nordvik Institute logger"
                      " drops samples above 20 Hz.",
                      body,
                  )
              ),
          ],
          bulletType="bullet",
      ),
      Spacer(1, 6),
      Paragraph(
          "&ldquo;The Reykjavik result is the first evidence that the"
          " feed-line geometry, not the thermal profile, sets the ceiling on"
          " yield.&rdquo; &mdash; Amara Osei, review meeting notes.",
          quote,
      ),
      Paragraph("5. Conclusion", s["Heading1"]),
      Paragraph(
          "Kestrel Dynamics will roll the Reykjavik configuration out to"
          " Trondheim in the coming quarter, with Ines Alvarado leading the"
          " transfer and Tomas Berg supplying instrumentation from the"
          " Nordvik Institute. A follow-up review is scheduled once"
          " <i>delta_peak</i> drift has been measured on the migrated line.",
          body,
      ),
  ]
  SimpleDocTemplate(
      str(path),
      pagesize=A4,
      title="Helios Deposition Program - Quarterly Field Report",
      author="Kestrel Dynamics",
  ).build(story)
  return path


def main() -> None:
  path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
  path.parent.mkdir(parents=True, exist_ok=True)
  build_hero_pdf(path)
  print(f"wrote {path} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
  main()
