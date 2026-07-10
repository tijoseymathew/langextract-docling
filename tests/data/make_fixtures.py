"""Regenerates the DoclingDocument JSON fixtures and golden markdown files.

Run from the repository root (requires reportlab in addition to the package
dependencies):

    python tests/data/make_fixtures.py

report_pdf: a two-page PDF (headings, paragraphs, bullet list, table) built
with reportlab and converted with docling, so spans carry page/bbox
locations. notes_md: a markdown source converted with docling, so items have
no physical locations and lists form a ListGroup.

The .golden.md files hold the markdown produced by the chunker pipeline at
generation time; the serializer's text-invariant tests compare against them.
"""

from pathlib import Path
import tempfile

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import ListFlowable
from reportlab.platypus import ListItem
from reportlab.platypus import PageBreak
from reportlab.platypus import Paragraph
from reportlab.platypus import SimpleDocTemplate
from reportlab.platypus import Spacer
from reportlab.platypus import Table
from reportlab.platypus import TableStyle

DATA_DIR = Path(__file__).parent

LOREM = (
    "Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam "
    "nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam."
)

MARKDOWN_SOURCE = """# Project Notes

Some introductory prose about the project.

## Tasks

- Write the serializer
- Map the offsets
- Ship version 1.1.0

Final remarks after the list.
"""


def build_pdf(path: Path):
  styles = getSampleStyleSheet()
  body = styles["BodyText"]
  story = [
      Paragraph("Annual Research Report", styles["Title"]),
      Paragraph("Introduction", styles["Heading1"]),
      Paragraph(
          "This report summarizes the research conducted by Ada Lovelace "
          "and Charles Babbage during the year 1843.",
          body,
      ),
      Paragraph(LOREM, body),
      Paragraph("Key Findings", styles["Heading1"]),
      ListFlowable(
          [
              ListItem(
                  Paragraph("The engine computes Bernoulli numbers.", body)
              ),
              ListItem(
                  Paragraph(
                      "Punched cards store both programs and data.", body
                  )
              ),
              ListItem(Paragraph("Conditional branching is supported.", body)),
          ],
          bulletType="bullet",
      ),
      PageBreak(),
      Paragraph("Results", styles["Heading1"]),
      Paragraph(
          "The table below lists the collaborators and their roles.", body
      ),
      Table(
          [
              ["Name", "Role"],
              ["Ada Lovelace", "Mathematician"],
              ["Charles Babbage", "Engineer"],
          ],
          style=TableStyle([
              ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
              ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
          ]),
      ),
      Spacer(1, 12),
      Paragraph(
          "In conclusion, the analytical engine anticipated modern "
          "computing by more than a century.",
          body,
      ),
  ]
  SimpleDocTemplate(str(path), pagesize=A4).build(story)


def main():
  from docling.document_converter import DocumentConverter

  from langextract_docling.markdown_chunker import HierarchicalMarkdownChunker

  with tempfile.TemporaryDirectory() as tmp:
    pdf_path = Path(tmp) / "report.pdf"
    build_pdf(pdf_path)
    md_path = Path(tmp) / "notes.md"
    md_path.write_text(MARKDOWN_SOURCE)

    converter = DocumentConverter()
    for name, src in [("report_pdf", pdf_path), ("notes_md", md_path)]:
      doc = converter.convert(src).document
      doc.save_as_json(DATA_DIR / f"{name}.docling.json")
      chunks = HierarchicalMarkdownChunker().chunk(doc)
      golden = "\n\n".join(chunk.text for chunk in chunks)
      (DATA_DIR / f"{name}.golden.md").write_text(golden)
      print(f"wrote {name}: {len(golden)} golden chars")


if __name__ == "__main__":
  main()
