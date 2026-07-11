"""Tests for the animated PDF-highlight HTML (pdf_visualization)."""

import base64
import pathlib
import re
from unittest import mock

from langextract.core import data
import pytest

from langextract_docling import pdf_visualization
from langextract_docling import provenance
import langextract_docling as lx

DATA_DIR = pathlib.Path(__file__).parent / "data"
PDF_PATH = DATA_DIR / "report.pdf"

# A box near the top of report.pdf's A4 page, in BOTTOMLEFT coordinates.
BBOX = (72.0, 780.0, 300.0, 730.0)


def _extraction_with_provenance(
    cls="finding",
    text="Bernoulli numbers",
    page_no=1,
    bbox=BBOX,
    start_pos=0,
    attributes=None,
):
  extraction = data.Extraction(
      extraction_class=cls,
      extraction_text=text,
      char_interval=data.CharInterval(
          start_pos=start_pos, end_pos=start_pos + len(text)
      ),
      attributes=attributes,
  )
  extraction.provenance = [
      provenance.SpanProvenance(
          start=start_pos,
          end=start_pos + len(text),
          doc_item_ref="#/texts/0",
          doc_item_label="text",
          locations=(
              provenance.SourceLocation(
                  page_no=page_no,
                  bbox=bbox,
                  coord_origin="BOTTOMLEFT",
                  charspan=(0, len(text)),
              ),
          ),
      )
  ]
  return extraction


def _highlighted_doc(source=str(PDF_PATH), extractions=None):
  if extractions is None:
    extractions = [_extraction_with_provenance()]
  doc = data.AnnotatedDocument(
      text="Bernoulli numbers", extractions=extractions
  )
  spans = [span for e in extractions for span in (e.provenance or [])]
  doc.provenance_map = provenance.ProvenanceMap(spans, source=source)
  return doc


class TestBboxToPercent:

  def test_bottomleft_origin_flips_vertically(self):
    percent = pdf_visualization._bbox_to_percent(
        (10, 100, 30, 80), "BOTTOMLEFT", page_width=100, page_height=200
    )
    assert percent == (10.0, 50.0, 20.0, 10.0)

  def test_topleft_origin_maps_directly(self):
    percent = pdf_visualization._bbox_to_percent(
        (10, 80, 30, 100), "TOPLEFT", page_width=100, page_height=200
    )
    assert percent == (10.0, 40.0, 20.0, 10.0)

  def test_inverted_coordinates_are_normalized(self):
    percent = pdf_visualization._bbox_to_percent(
        (30, 100, 10, 80), "TOPLEFT", page_width=100, page_height=200
    )
    assert percent == (10.0, 40.0, 20.0, 10.0)


class TestVisualizePdfHtml:

  def test_widget_structure(self):
    html = pdf_visualization.visualize_pdf(_highlighted_doc())
    assert isinstance(html, str)  # not running under IPython
    # In the spirit of lx.visualize: CSS + panel + window + controls + script
    assert "<style>" in html
    assert 'id="lxPdfAttributes"' in html
    assert 'class="lx-pdf-window"' in html
    # Control glyphs are encoding-independent HTML entities, not raw emoji,
    # so a file saved without a UTF-8 charset does not mojibake them.
    assert "&#9654; Play" in html
    assert "&#9198; Previous" in html and "&#9197; Next" in html
    assert 'class="lx-progress-slider"' in html
    assert "<script>" in html and "setInterval" in html

  def test_page_image_is_valid_embedded_png(self):
    html = pdf_visualization.visualize_pdf(_highlighted_doc())
    match = re.search(r'src="data:image/png;base64,([^"]+)"', html)
    assert match, "expected an embedded page image"
    assert base64.b64decode(match.group(1)).startswith(b"\x89PNG")
    # Only the highlighted page is embedded (report.pdf has two pages).
    assert html.count("data:image/png;base64,") == 1
    assert 'data-page="1"' in html

  def test_box_geometry_matches_bbox(self):
    html = pdf_visualization.visualize_pdf(_highlighted_doc())
    match = re.search(
        r'class="lx-pdf-box[^"]*" data-idx="0"[^>]*style="'
        r"left:([\d.]+)%;top:([\d.]+)%;width:([\d.]+)%;height:([\d.]+)%",
        html,
    )
    assert match, "expected a positioned highlight box"
    left, top, width, height = (float(g) for g in match.groups())
    # A4 page: 595.28 x 841.89 pt; BBOX = (72, 780, 300, 730) BOTTOMLEFT.
    assert left == pytest.approx(100 * 72 / 595.28, abs=0.01)
    assert top == pytest.approx(100 * (841.89 - 780) / 841.89, abs=0.01)
    assert width == pytest.approx(100 * (300 - 72) / 595.28, abs=0.01)
    assert height == pytest.approx(100 * 50 / 841.89, abs=0.01)

  def test_extractions_ordered_by_char_position(self):
    second = _extraction_with_provenance(
        cls="person", text="Ada Lovelace", start_pos=100
    )
    first = _extraction_with_provenance(start_pos=5)
    doc = _highlighted_doc(extractions=[second, first])
    html = pdf_visualization.visualize_pdf(doc)
    # "finding" (pos 5) must animate before "person" (pos 100).
    finding_box = html.index('title="finding:')
    person_box = html.index('title="person:')
    assert finding_box < person_box
    assert 'id="lxPdfEntityInfo">1/2</span>' in html  # starts at entity 1

  def test_legend_lists_classes_with_palette_colors(self):
    doc = _highlighted_doc(
        extractions=[
            _extraction_with_provenance(cls="b_class"),
            _extraction_with_provenance(cls="a_class"),
        ]
    )
    html = pdf_visualization.visualize_pdf(doc)
    assert "Highlights Legend:" in html
    a_pos = html.index(
        f'style="background-color:{pdf_visualization._PALETTE[0]};">a_class'
    )
    b_pos = html.index(
        f'style="background-color:{pdf_visualization._PALETTE[1]};">b_class'
    )
    assert a_pos < b_pos

    without = pdf_visualization.visualize_pdf(doc, show_legend=False)
    assert "Highlights Legend:" not in without

  def test_animation_speed_is_embedded(self):
    html = pdf_visualization.visualize_pdf(
        _highlighted_doc(), animation_speed=2.5
    )
    assert "const animationSpeed = 2.5;" in html

  def test_extraction_text_is_escaped(self):
    doc = _highlighted_doc(
        extractions=[_extraction_with_provenance(text='<b>"evil" & text</b>')]
    )
    html = pdf_visualization.visualize_pdf(doc)
    assert '<b>"evil"' not in html
    assert "&lt;b&gt;" in html

  def test_no_locatable_provenance_returns_empty_widget(self):
    bare = data.Extraction(
        extraction_class="finding", extraction_text="x", char_interval=None
    )
    doc = data.AnnotatedDocument(text="x", extractions=[bare])
    html = pdf_visualization.visualize_pdf(doc, pdf_path=PDF_PATH)
    assert "No extractions with PDF provenance" in html

  def test_url_source_requires_explicit_pdf_path(self):
    doc = _highlighted_doc(source="https://example.com/report.pdf")
    with pytest.raises(ValueError, match="pass pdf_path"):
      pdf_visualization.visualize_pdf(doc)
    html = pdf_visualization.visualize_pdf(doc, pdf_path=PDF_PATH)
    assert "lx-pdf-window" in html

  def test_page_beyond_pdf_raises(self):
    doc = _highlighted_doc(
        extractions=[_extraction_with_provenance(page_no=99)]
    )
    with pytest.raises(ValueError, match="page 99"):
      pdf_visualization.visualize_pdf(doc)

  def test_attributes_rendered_in_panel_data(self):
    doc = _highlighted_doc(
        extractions=[_extraction_with_provenance(attributes={"year": "1843"})]
    )
    html = pdf_visualization.visualize_pdf(doc)
    assert "lx-attr-key" in html and "1843" in html

  def test_top_level_alias(self):
    html = lx.visualize_pdf(_highlighted_doc())
    assert "lx-pdf-window" in html


class TestPagePagingAndFocus:
  """The PDF-specific UX: one page at a time, current box spotlighted."""

  def _two_page_doc(self):
    # "finding" (pos 0) on page 1, "table" (pos 100) on page 2.
    page1 = _extraction_with_provenance(start_pos=0, page_no=1)
    page2 = _extraction_with_provenance(
        cls="artifact", text="Results table", start_pos=100, page_no=2
    )
    return _highlighted_doc(extractions=[page1, page2])

  def test_pages_after_the_first_start_hidden(self):
    html = pdf_visualization.visualize_pdf(self._two_page_doc())
    # Page 1 (holds the first extraction) is visible; page 2 starts hidden.
    assert re.search(r'class="lx-pdf-page" data-page="1"', html)
    assert re.search(
        r'class="lx-pdf-page lx-pdf-page-hidden" data-page="2"', html
    )

  def test_animation_pages_between_pages(self):
    html = pdf_visualization.visualize_pdf(self._two_page_doc())
    # The script toggles page visibility from the current extraction's pages.
    assert "activePages" in html
    assert "lx-pdf-page-hidden" in html and "classList.toggle" in html

  def test_non_current_boxes_are_dimmed(self):
    html = pdf_visualization.visualize_pdf(self._two_page_doc())
    # Boxes default to reduced opacity; the current one is brought to full.
    assert re.search(r"\.lx-pdf-box\s*\{[^}]*opacity:\s*0\.35", html)
    assert re.search(r"\.lx-current-highlight\s*\{[^}]*opacity:\s*1", html)

  def test_boxes_are_clickable_to_jump(self):
    html = pdf_visualization.visualize_pdf(self._two_page_doc())
    assert "cursor: pointer" in html
    assert "windowEl.addEventListener('click'" in html

  def test_status_shows_total_page_count(self):
    html = pdf_visualization.visualize_pdf(self._two_page_doc())
    assert re.search(r"lxPdfPageInfo\">1</span>\s*of 2", html)


class TestZoom:
  """The canvas zoom controls."""

  def test_zoom_toolbar_is_present(self):
    html = pdf_visualization.visualize_pdf(_highlighted_doc())
    assert 'class="lx-pdf-toolbar"' in html
    assert 'id="lxPdfZoomIn"' in html
    assert 'id="lxPdfZoomOut"' in html
    assert 'id="lxPdfZoomFit"' in html
    # Starts at 100%.
    assert 'id="lxPdfZoomLevel">100%' in html

  def test_zoom_scales_page_width_and_scrolls_both_axes(self):
    html = pdf_visualization.visualize_pdf(_highlighted_doc())
    # The page width is driven by a CSS variable the script updates, and the
    # window scrolls on both axes so a zoomed page is fully reachable.
    assert "width: var(--lx-zoom-width, 100%)" in html
    assert re.search(r"\.lx-pdf-window\s*\{[^}]*overflow:\s*auto", html)
    assert "setProperty('--lx-zoom-width'" in html

  def test_zoom_is_clamped(self):
    html = pdf_visualization.visualize_pdf(_highlighted_doc())
    assert "MIN_ZOOM = 0.5" in html and "MAX_ZOOM = 4.0" in html
    assert "Math.min(MAX_ZOOM, Math.max(MIN_ZOOM" in html

  def test_ctrl_wheel_zoom(self):
    html = pdf_visualization.visualize_pdf(_highlighted_doc())
    assert "addEventListener('wheel'" in html
    assert "event.ctrlKey" in html and "event.metaKey" in html


class TestEndToEndPipeline:

  def test_extract_then_visualize_real_pdf(self):
    """Real docling provenance renders to HTML without live model access."""

    def fake(**kwargs):
      text = kwargs["text_or_documents"]
      start = text.index("Bernoulli")
      extraction = data.Extraction(
          extraction_class="finding",
          extraction_text="Bernoulli numbers",
          char_interval=data.CharInterval(
              start_pos=start, end_pos=start + len("Bernoulli numbers")
          ),
      )
      return data.AnnotatedDocument(text=text, extractions=[extraction])

    with mock.patch(
        "langextract_docling._original_extract",
        mock.MagicMock(side_effect=fake),
    ):
      result = lx.extract(
          text_or_documents=str(PDF_PATH),
          prompt_description="Test",
          examples=[],
      )

    html = pdf_visualization.visualize_pdf(result)
    assert "data:image/png;base64," in html
    assert 'data-idx="0"' in html
    assert "Entity" in html and "1/1" in html
