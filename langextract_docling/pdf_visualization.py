"""Animated, interactive HTML visualization of extractions on PDF pages.

The PDF counterpart of langextract.visualization: given an AnnotatedDocument
enriched by extract() with per-extraction provenance, builds a self-contained
HTML widget in the same spirit as lx.visualize() — rendered page images with
the provenance bounding boxes overlaid, play/pause/previous/next controls and
a progress slider stepping through the extractions, an attributes panel, and
a class color legend.

Page rasterization needs pillow and pypdfium2, both installed with docling;
they are imported lazily so this module stays importable without them.
"""

import base64
import html as html_lib
import io
import json
import pathlib
import textwrap
import typing

# Fallback if IPython is not present, as in langextract.visualization.
try:
  from IPython import get_ipython  # type: ignore[import-not-found]
  from IPython.display import HTML  # type: ignore[import-not-found]
except ImportError:

  def get_ipython():  # type: ignore[no-redef]
    return None

  HTML = None  # pytype: disable=annotation-type-mismatch

# Mirrors langextract.visualization._PALETTE (cycled over sorted extraction
# classes) so a class gets the same color here as in the text visualization.
_PALETTE: tuple[str, ...] = (
    "#D2E3FC",  # Light Blue
    "#C8E6C9",  # Light Green
    "#FEF0C3",  # Light Yellow
    "#F9DEDC",  # Light Red
    "#FFDDBE",  # Light Orange
    "#EADDFF",  # Light Purple
    "#C4E9E4",  # Light Teal
    "#FCE4EC",  # Light Pink
    "#E8EAED",  # Very Light Grey
    "#DDE8E8",  # Pale Cyan
)

_FILL_ALPHA = 0.35
_OUTLINE_DARKEN = 0.55

_VISUALIZATION_CSS = textwrap.dedent("""\
    <style>
    .lx-pdf-wrapper { max-width: 100%; font-family: Arial, sans-serif; }
    .lx-pdf-window {
      border: 1px solid #90caf9; max-height: 620px; overflow-y: auto;
      margin-bottom: 12px; background: #eceff1; padding: 12px;
    }
    .lx-pdf-page {
      position: relative; margin: 0 auto 12px auto; max-width: 100%;
      box-shadow: 0 1px 4px rgba(0,0,0,0.3);
    }
    .lx-pdf-page:last-child { margin-bottom: 0; }
    .lx-pdf-page.lx-pdf-page-hidden { display: none; }
    .lx-pdf-page img { display: block; width: 100%; height: auto; }
    .lx-pdf-page-label {
      position: absolute; top: 4px; right: 4px; background: rgba(0,0,0,0.55);
      color: #fff; font-size: 11px; padding: 2px 6px; border-radius: 3px;
    }
    .lx-pdf-box {
      position: absolute; box-sizing: border-box; border: 2px solid;
      border-radius: 2px; cursor: pointer; opacity: 0.35;
      transition: opacity 0.2s ease-in-out;
    }
    .lx-pdf-box:hover { opacity: 0.7; }
    .lx-pdf-box.lx-current-highlight {
      opacity: 1;
      border-color: #ff4444 !important;
      box-shadow: 0 0 0 3px rgba(255,68,68,0.35);
      animation: lx-pdf-pulse 1s ease-in-out;
      z-index: 10;
    }
    @keyframes lx-pdf-pulse {
      0% { box-shadow: 0 0 0 3px rgba(255,68,68,0.35); }
      50% { box-shadow: 0 0 0 6px rgba(255,0,0,0.45); }
      100% { box-shadow: 0 0 0 3px rgba(255,68,68,0.35); }
    }
    .lx-controls {
      background: #fafafa; border: 1px solid #90caf9; border-radius: 8px;
      padding: 12px; margin-bottom: 16px;
    }
    .lx-button-row {
      display: flex; justify-content: center; gap: 8px; margin-bottom: 12px;
    }
    .lx-control-btn {
      background: #4285f4; color: white; border: none; border-radius: 4px;
      padding: 8px 16px; cursor: pointer; font-size: 13px; font-weight: 500;
      transition: background-color 0.2s;
    }
    .lx-control-btn:hover { background: #3367d6; }
    .lx-progress-container { margin-bottom: 8px; }
    .lx-progress-slider {
      width: 100%; margin: 0; appearance: none; height: 6px;
      background: #ddd; border-radius: 3px; outline: none;
    }
    .lx-progress-slider::-webkit-slider-thumb {
      appearance: none; width: 18px; height: 18px; background: #4285f4;
      border-radius: 50%; cursor: pointer;
    }
    .lx-progress-slider::-moz-range-thumb {
      width: 18px; height: 18px; background: #4285f4; border-radius: 50%;
      cursor: pointer; border: none;
    }
    .lx-status-text {
      text-align: center; font-size: 12px; color: #666; margin-top: 4px;
    }
    .lx-attributes-panel {
      background: #fafafa; border: 1px solid #90caf9; border-radius: 6px;
      padding: 8px 10px; margin-bottom: 8px; font-size: 13px;
    }
    .lx-legend {
      font-size: 12px; margin-bottom: 8px;
      padding-bottom: 8px; border-bottom: 1px solid #e0e0e0;
    }
    .lx-label {
      display: inline-block; padding: 2px 4px; border-radius: 3px;
      margin-right: 4px; color: #000;
    }
    .lx-attr-key { font-weight: 600; color: #1565c0; letter-spacing: 0.3px; }
    .lx-attr-value { font-weight: 400; opacity: 0.85; letter-spacing: 0.2px; }
    </style>""")


def visualize_pdf(
    annotated_doc: typing.Any,
    pdf_path: str | pathlib.Path | None = None,
    *,
    animation_speed: float = 1.0,
    show_legend: bool = True,
    scale: float = 2.0,
) -> "HTML | str":
  """Visualizes extractions on their PDF pages as animated HTML.

  The PDF counterpart of lx.visualize(): the widget shows the rendered
  source pages with every extraction's provenance bounding boxes overlaid,
  colored per extraction class (same colors the text visualization assigns),
  and steps through the extractions with play/pause/previous/next controls,
  a progress slider, and an attributes panel. Pages are embedded as base64
  PNGs, so the HTML is fully self-contained.

  Args:
      annotated_doc: An AnnotatedDocument enriched by extract() with
        per-extraction `provenance` and a document `provenance_map`.
      pdf_path: Path to the source PDF. Defaults to the provenance map's
        recorded source; required explicitly when the document came from a
        URL or the recorded path no longer exists.
      animation_speed: Animation speed in seconds between extractions.
      show_legend: If True, prepends a color legend mapping extraction
        classes to colors.
      scale: Page rasterization scale; 1.0 renders at 72 dpi. Higher values
        sharpen zoomed-in pages at the cost of a larger HTML file.

  Returns:
      An IPython.display.HTML object if running in a notebook, otherwise the
      generated HTML string.

  Raises:
      ValueError: If no PDF path can be resolved, or the provenance
        references a page the PDF does not have (wrong pdf_path).
  """
  extractions = _filter_locatable_extractions(annotated_doc)
  if not extractions:
    empty_html = _VISUALIZATION_CSS + (
        '<div class="lx-pdf-wrapper"><p>No extractions with PDF provenance'
        " to animate.</p></div>"
    )
    return _maybe_ipython_html(empty_html)

  color_map = _assign_colors(e.extraction_class for e in extractions)
  boxes_per_extraction = [_boxes_of(e) for e in extractions]
  page_numbers = sorted(
      {box["page"] for boxes in boxes_per_extraction for box in boxes}
  )
  resolved_path = _resolve_pdf_path(annotated_doc, pdf_path)
  pages = _render_pages(resolved_path, page_numbers, scale)

  full_html = _VISUALIZATION_CSS + _build_visualization_html(
      extractions,
      boxes_per_extraction,
      pages,
      color_map,
      animation_speed,
      show_legend,
  )
  return _maybe_ipython_html(full_html)


def _is_jupyter() -> bool:
  """Checks for a Jupyter/IPython environment that can display HTML."""
  try:
    ip = get_ipython() if get_ipython is not None else None
    return (
        ip is not None and ip.__class__.__name__ != "TerminalInteractiveShell"
    )
  except Exception:  # pylint: disable=broad-except
    return False


def _maybe_ipython_html(full_html: str) -> "HTML | str":
  if HTML is not None and _is_jupyter():
    return HTML(full_html)
  return full_html


def _filter_locatable_extractions(annotated_doc: typing.Any) -> list:
  """Returns extractions with at least one provenance location, in text order."""
  locatable = [
      e
      for e in annotated_doc.extractions or []
      if any(span.locations for span in getattr(e, "provenance", None) or [])
  ]

  def sort_key(extraction):
    interval = extraction.char_interval
    if interval is None or interval.start_pos is None:
      return (1, 0)
    return (0, interval.start_pos)

  return sorted(locatable, key=sort_key)


def _boxes_of(extraction: typing.Any) -> list[dict]:
  """Returns one {page, left, top, width, height} dict per unique location.

  Coordinates are percentages of the page size so the boxes track the page
  image at any display width. Several spans can carry identical locations
  (list items share their group's range), so duplicates collapse.
  """
  boxes: dict[tuple, dict] = {}
  for span in extraction.provenance or []:
    for loc in span.locations:
      key = (loc.page_no, tuple(loc.bbox), loc.coord_origin)
      boxes.setdefault(
          key,
          {
              "page": loc.page_no,
              "bbox": tuple(loc.bbox),
              "coord_origin": loc.coord_origin,
          },
      )
  return list(boxes.values())


def _assign_colors(classes: typing.Iterable[str]) -> dict[str, str]:
  """Maps sorted classes onto the cycled palette, as langextract does."""
  unique = sorted(set(classes))
  return {cls: _PALETTE[i % len(_PALETTE)] for i, cls in enumerate(unique)}


def _resolve_pdf_path(
    annotated_doc: typing.Any, pdf_path: str | pathlib.Path | None
) -> pathlib.Path:
  """Returns the PDF to render, defaulting to the provenance map's source."""
  if pdf_path is None:
    provenance_map = getattr(annotated_doc, "provenance_map", None)
    pdf_path = getattr(provenance_map, "source", None)
    if pdf_path is None:
      raise ValueError(
          "annotated_doc has no provenance_map with a recorded source; pass"
          " pdf_path explicitly"
      )
  path = pathlib.Path(pdf_path).expanduser()
  if not path.is_file():
    raise ValueError(
        f"no PDF file at {str(path)!r}; pass pdf_path explicitly (required"
        " when the document was extracted from a URL)"
    )
  return path


def _render_pages(
    pdf_path: pathlib.Path, page_numbers: list[int], scale: float
) -> dict[int, dict]:
  """Rasterizes pages to base64 PNG data URIs with their point sizes.

  Returns:
      {page_no: {"data_uri": str, "width": float, "height": float}} with
      width/height in PDF points, for percent-coordinate conversion.
  """
  import pypdfium2 as pdfium

  pages: dict[int, dict] = {}
  pdf = pdfium.PdfDocument(str(pdf_path))
  try:
    for page_no in page_numbers:
      if not 1 <= page_no <= len(pdf):
        raise ValueError(
            f"provenance references page {page_no} but {pdf_path} has"
            f" {len(pdf)} page(s); is pdf_path the document that was"
            " extracted?"
        )
      page = pdf[page_no - 1]
      width, height = page.get_size()
      image = page.render(scale=scale).to_pil()
      buffer = io.BytesIO()
      image.save(buffer, format="PNG")
      encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
      pages[page_no] = {
          "data_uri": f"data:image/png;base64,{encoded}",
          "width": width,
          "height": height,
      }
  finally:
    pdf.close()
  return pages


def _bbox_to_percent(
    bbox: tuple[float, float, float, float],
    coord_origin: str,
    page_width: float,
    page_height: float,
) -> tuple[float, float, float, float]:
  """Converts a docling bbox (l, t, r, b) to a percent (left, top, w, h).

  Args:
      bbox: Box in page points, (left, top, right, bottom).
      coord_origin: "TOPLEFT" or "BOTTOMLEFT" (docling's CoordOrigin values).
      page_width: Page width in points.
      page_height: Page height in points.

  Returns:
      (left, top, width, height) as percentages of the page size, measured
      from the page's top-left corner.
  """
  left, top, right, bottom = bbox
  if coord_origin.upper() == "BOTTOMLEFT":
    top, bottom = page_height - top, page_height - bottom
  x0, x1 = sorted((left, right))
  y0, y1 = sorted((top, bottom))
  return (
      100 * x0 / page_width,
      100 * y0 / page_height,
      100 * (x1 - x0) / page_width,
      100 * (y1 - y0) / page_height,
  )


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
  return tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))


def _box_style(color: str) -> str:
  """Returns inline fill/border colors for a highlight box."""
  red, green, blue = _hex_to_rgb(color)
  dark = tuple(int(channel * _OUTLINE_DARKEN) for channel in (red, green, blue))
  return (
      f"background: rgba({red},{green},{blue},{_FILL_ALPHA});"
      f" border-color: rgb({dark[0]},{dark[1]},{dark[2]});"
  )


def _format_attributes(attributes: dict | None) -> str:
  """Formats attributes as a single-line string, as lx.visualize does."""
  valid_attrs = {
      key: value
      for key, value in (attributes or {}).items()
      if value not in (None, "", "null")
  }
  if not valid_attrs:
    return "{}"
  attrs_parts = []
  for key, value in valid_attrs.items():
    value_str = (
        ", ".join(str(v) for v in value)
        if isinstance(value, list)
        else str(value)
    )
    attrs_parts.append(
        f'<span class="lx-attr-key">{html_lib.escape(str(key))}</span>: <span'
        f' class="lx-attr-value">{html_lib.escape(value_str)}</span>'
    )
  return "{" + ", ".join(attrs_parts) + "}"


def _prepare_extraction_data(
    extractions: list, boxes_per_extraction: list[list[dict]]
) -> list[dict]:
  """Prepares the JavaScript data driving the animation."""
  extraction_data = []
  for index, (extraction, boxes) in enumerate(
      zip(extractions, boxes_per_extraction)
  ):
    pages = sorted({box["page"] for box in boxes})
    attributes_html = (
        "<div><strong>class:</strong>"
        f" {html_lib.escape(extraction.extraction_class)}</div>"
        "<div><strong>text:</strong>"
        f" {html_lib.escape(extraction.extraction_text or '')}</div>"
        "<div><strong>attributes:</strong>"
        f" {_format_attributes(extraction.attributes)}</div>"
    )
    extraction_data.append({
        "index": index,
        "pages": pages,
        "attributesHtml": attributes_html,
    })
  return extraction_data


def _build_page_window_html(
    extractions: list,
    boxes_per_extraction: list[list[dict]],
    pages: dict[int, dict],
    color_map: dict[str, str],
) -> str:
  """Builds the scrollable window of page images with overlaid boxes."""
  boxes_by_page: dict[int, list[str]] = {page_no: [] for page_no in pages}
  for index, (extraction, boxes) in enumerate(
      zip(extractions, boxes_per_extraction)
  ):
    color = color_map.get(extraction.extraction_class, "#ffff8d")
    for box in boxes:
      page = pages[box["page"]]
      left, top, width, height = _bbox_to_percent(
          box["bbox"], box["coord_origin"], page["width"], page["height"]
      )
      current = " lx-current-highlight" if index == 0 else ""
      title = html_lib.escape(
          f"{extraction.extraction_class}: {extraction.extraction_text or ''}",
          quote=True,
      )
      boxes_by_page[box["page"]].append(
          f'<div class="lx-pdf-box{current}" data-idx="{index}"'
          f' title="{title}" style="left:{left:.3f}%;top:{top:.3f}%;'
          f'width:{width:.3f}%;height:{height:.3f}%;{_box_style(color)}">'
          "</div>"
      )

  # Only the first extraction's page(s) are visible initially; the animation
  # pages the viewer to whichever page(s) the current extraction lives on.
  first_pages = {box["page"] for box in boxes_per_extraction[0]}

  page_parts = []
  for page_no in sorted(pages):
    hidden = "" if page_no in first_pages else " lx-pdf-page-hidden"
    page_parts.append(
        f'<div class="lx-pdf-page{hidden}" data-page="{page_no}">'
        f'<img src="{pages[page_no]["data_uri"]}" alt="Page {page_no}">'
        f'{"".join(boxes_by_page[page_no])}'
        f'<div class="lx-pdf-page-label">Page {page_no}</div>'
        "</div>"
    )
  return (
      f'<div class="lx-pdf-window" id="lxPdfWindow">{"".join(page_parts)}</div>'
  )


def _build_legend_html(color_map: dict[str, str]) -> str:
  """Builds legend HTML showing extraction classes and their colors."""
  legend_items = [
      f'<span class="lx-label" style="background-color:{color};">'
      f"{html_lib.escape(extraction_class)}</span>"
      for extraction_class, color in color_map.items()
  ]
  return (
      '<div class="lx-legend">Highlights Legend:'
      f' {" ".join(legend_items)}</div>'
  )


def _build_visualization_html(
    extractions: list,
    boxes_per_extraction: list[list[dict]],
    pages: dict[int, dict],
    color_map: dict[str, str],
    animation_speed: float,
    show_legend: bool,
) -> str:
  """Assembles the widget: panel, page window, controls, and script."""
  page_window_html = _build_page_window_html(
      extractions, boxes_per_extraction, pages, color_map
  )
  legend_html = _build_legend_html(color_map) if show_legend else ""
  js_data = json.dumps(
      _prepare_extraction_data(extractions, boxes_per_extraction)
  )
  first_pages = sorted({box["page"] for box in boxes_per_extraction[0]})
  total_pages = len(pages)

  return textwrap.dedent(f"""
    <div class="lx-pdf-wrapper">
      <div class="lx-attributes-panel">
        {legend_html}
        <div id="lxPdfAttributes"></div>
      </div>
      {page_window_html}
      <div class="lx-controls">
        <div class="lx-button-row">
          <button class="lx-control-btn" id="lxPdfPlayBtn">▶️ Play</button>
          <button class="lx-control-btn" id="lxPdfPrevBtn">⏮ Previous</button>
          <button class="lx-control-btn" id="lxPdfNextBtn">⏭ Next</button>
        </div>
        <div class="lx-progress-container">
          <input type="range" id="lxPdfSlider" class="lx-progress-slider"
                 min="0" max="{len(extractions) - 1}" value="0">
        </div>
        <div class="lx-status-text">
          Entity <span id="lxPdfEntityInfo">1/{len(extractions)}</span> |
          Page <span id="lxPdfPageInfo">{", ".join(map(str, first_pages))}</span>
          of {total_pages}
        </div>
      </div>
    </div>

    <script>
      (function() {{
        const extractions = {js_data};
        let currentIndex = 0;
        let isPlaying = false;
        let animationInterval = null;
        const animationSpeed = {animation_speed};

        const playBtn = document.getElementById('lxPdfPlayBtn');
        const slider = document.getElementById('lxPdfSlider');

        function updateDisplay() {{
          const extraction = extractions[currentIndex];
          if (!extraction) return;

          document.getElementById('lxPdfAttributes').innerHTML = extraction.attributesHtml;
          document.getElementById('lxPdfEntityInfo').textContent = (currentIndex + 1) + '/' + extractions.length;
          document.getElementById('lxPdfPageInfo').textContent = extraction.pages.join(', ');
          slider.value = currentIndex;
          playBtn.textContent = isPlaying ? '⏸ Pause' : '▶️ Play';

          // Page the viewer to the current extraction's page(s), hiding others
          // so a multi-page document stays focused instead of scrolling a stack.
          const activePages = new Set(extraction.pages);
          document.querySelectorAll('#lxPdfWindow .lx-pdf-page').forEach((pageEl) => {{
            const pageNo = parseInt(pageEl.getAttribute('data-page'), 10);
            pageEl.classList.toggle('lx-pdf-page-hidden', !activePages.has(pageNo));
          }});

          document.querySelectorAll('#lxPdfWindow .lx-current-highlight').forEach(
            (box) => box.classList.remove('lx-current-highlight'));
          const boxes = document.querySelectorAll(
            '#lxPdfWindow .lx-pdf-box[data-idx="' + currentIndex + '"]');
          boxes.forEach((box) => box.classList.add('lx-current-highlight'));
          if (boxes.length) {{
            boxes[0].scrollIntoView({{block: 'center', behavior: 'smooth'}});
          }}
        }}

        function nextExtraction() {{
          currentIndex = (currentIndex + 1) % extractions.length;
          updateDisplay();
        }}

        function prevExtraction() {{
          currentIndex = (currentIndex - 1 + extractions.length) % extractions.length;
          updateDisplay();
        }}

        function playPause() {{
          if (isPlaying) {{
            clearInterval(animationInterval);
            isPlaying = false;
          }} else {{
            animationInterval = setInterval(nextExtraction, animationSpeed * 1000);
            isPlaying = true;
          }}
          updateDisplay();
        }}

        playBtn.addEventListener('click', playPause);
        document.getElementById('lxPdfPrevBtn').addEventListener('click', prevExtraction);
        document.getElementById('lxPdfNextBtn').addEventListener('click', nextExtraction);
        slider.addEventListener('input', () => {{
          currentIndex = parseInt(slider.value, 10);
          updateDisplay();
        }});

        // Click any box to jump to its extraction.
        document.getElementById('lxPdfWindow').addEventListener('click', (event) => {{
          const box = event.target.closest('.lx-pdf-box');
          if (!box) return;
          currentIndex = parseInt(box.getAttribute('data-idx'), 10);
          updateDisplay();
        }});

        updateDisplay();
      }})();
    </script>""")
