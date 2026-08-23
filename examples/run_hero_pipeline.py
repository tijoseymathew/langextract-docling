"""Runs the hero PDF through the whole pipeline against a live model API.

    python examples/run_hero_pipeline.py

PDF -> docling conversion -> markdown serialization (with the offset map)
-> LLM extraction -> alignment -> item provenance -> sub-item provenance
-> animated HTML. Credentials come from the nearest `.env` walking up from
this file. `OPENROUTER_API_KEY` (with optional `OPENROUTER_MODEL`) wins if
set and routes through OpenRouter's OpenAI-compatible endpoint; otherwise
`GEMINI_API_KEY` and optional `GEMINI_MODEL` are used, where litellm-style
ids like "gemini/gemini-3.1-flash-lite" have the prefix stripped.

Outputs next to this script: `hero_report.pdf` (built if missing),
`hero_report.md` (what the model actually saw) and `hero_report.html` (the
visualization). Every assertion the demo makes about provenance is printed
as a PASS/FAIL check, so a broken stage is visible without reading the HTML.
"""

import collections
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
PDF_PATH = HERE / "hero_report.pdf"
MD_PATH = HERE / "hero_report.md"
HTML_PATH = HERE / "hero_report.html"

# Run against the checkout this script lives in, not the editable install.
sys.path.insert(0, str(HERE.parent))


def load_env() -> None:
  """Loads the nearest .env found walking up from this file."""
  for directory in [HERE, *HERE.parents]:
    candidate = directory / ".env"
    if not candidate.is_file():
      continue
    from dotenv import load_dotenv

    load_dotenv(candidate)
    print(f"env      : {candidate}")
    return
  print("env      : no .env found; relying on the ambient environment")


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def model_kwargs() -> dict | None:
  """The `lx.extract` model arguments, or None if no credentials are set.

  OpenRouter is preferred when its key is present. Its model ids carry a
  vendor prefix ("deepseek/...") that collides with langextract's Ollama
  routing patterns, so the provider is named explicitly rather than
  inferred from the id.
  """
  if key := os.environ.get("OPENROUTER_API_KEY"):
    from langextract import factory

    model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    print(f"model    : {model} (openrouter)")
    return {
        "config": factory.ModelConfig(
            model_id=model,
            provider="OpenAILanguageModel",
            provider_kwargs={"api_key": key, "base_url": OPENROUTER_BASE_URL},
        )
    }

  if key := os.environ.get("GEMINI_API_KEY"):
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    model = model.split("/", 1)[1] if model.startswith("gemini/") else model
    print(f"model    : {model} (gemini)")
    return {"model_id": model, "api_key": key}

  return None


def examples(lx):
  return [
      lx.data.ExampleData(
          text=(
              "The Aurora line was run by Nils Haugen of Fjord Systems in"
              " Bergen, reaching a yield of 89.4%."
          ),
          extractions=[
              lx.data.Extraction(
                  extraction_class="person",
                  extraction_text="Nils Haugen",
                  attributes={"affiliation": "Fjord Systems"},
              ),
              lx.data.Extraction(
                  extraction_class="organization",
                  extraction_text="Fjord Systems",
              ),
              lx.data.Extraction(
                  extraction_class="site", extraction_text="Bergen"
              ),
              lx.data.Extraction(
                  extraction_class="measurement",
                  extraction_text="89.4%",
                  attributes={"quantity": "yield"},
              ),
          ],
      )
  ]


def summarize(extraction) -> str:
  """One line per extraction: text, class, page(s), narrowed box, item."""
  subs = getattr(extraction, "sub_provenance", None) or []
  spans = getattr(extraction, "provenance", None) or []
  locations = [loc for sub in subs for loc in sub.locations]
  pages = sorted({loc.page_no for loc in locations})
  labels = sorted({span.doc_item_label for span in spans})
  exact = all(sub.exact for sub in subs) if subs else False
  box = ""
  if locations:
    left, top, right, bottom = locations[0].bbox
    box = f"[{left:.0f},{top:.0f},{right:.0f},{bottom:.0f}]"
  columns = [
      f"{extraction.extraction_class:<13}",
      f"{extraction.extraction_text[:34]:<34}",
      f"p{','.join(map(str, pages)) or '-':<5}",
      f"{'exact' if exact else 'item':<5}",
      f"{','.join(labels):<13}",
      f"{len(locations)} box {box}",
  ]
  return "  " + " ".join(columns)


def _area(bbox) -> float:
  """The area of a (left, top, right, bottom) box, whatever its origin."""
  left, top, right, bottom = bbox
  return abs(right - left) * abs(top - bottom)


def check(label: str, ok: bool, detail: str = "") -> bool:
  print(
      f"  [{'PASS' if ok else 'FAIL'}]"
      f" {label}{f' — {detail}' if detail else ''}"
  )
  return ok


def main() -> int:
  load_env()
  if not PDF_PATH.exists():
    from examples.make_hero_pdf import build_hero_pdf

    build_hero_pdf(PDF_PATH)
  print(f"pdf      : {PDF_PATH} ({PDF_PATH.stat().st_size:,} bytes)")

  model = model_kwargs()
  if model is None:
    print(
        "no credentials: set OPENROUTER_API_KEY or GEMINI_API_KEY"
        " (checked .env and the environment)"
    )
    return 2

  from langextract_docling import provenance
  import langextract_docling as lx

  print(f"package  : {lx.__file__}")

  result = lx.extract(
      text_or_documents=str(PDF_PATH),
      prompt_description=(
          "Extract the people, the organizations they belong to, the site"
          " names, and the reported yield and drift measurements. Use the"
          " exact text of the document for each extraction."
      ),
      examples=examples(lx),
      extraction_passes=2,
      show_progress=False,
      **model,
  )

  MD_PATH.write_text(result.text)
  print(f"markdown : {MD_PATH} ({len(result.text):,} chars)")

  aligned = [e for e in result.extractions or [] if e.char_interval is not None]
  print(
      f"\nextractions: {len(result.extractions or [])} returned,"
      f" {len(aligned)} aligned to the markdown\n"
  )
  for extraction in sorted(aligned, key=lambda e: e.char_interval.start_pos):
    print(summarize(extraction))

  print("\nchecks")
  ok = True
  ok &= check(
      "document carries a provenance map",
      isinstance(result.provenance_map, provenance.ProvenanceMap),
  )
  ok &= check("at least one aligned extraction", bool(aligned))

  no_prov = [e for e in aligned if not getattr(e, "provenance", None)]
  ok &= check(
      "every aligned extraction has item provenance",
      not no_prov,
      ", ".join(e.extraction_text for e in no_prov[:3]),
  )

  no_sub = [e for e in aligned if not getattr(e, "sub_provenance", None)]
  ok &= check(
      "every aligned extraction has sub-item provenance",
      not no_sub,
      ", ".join(e.extraction_text for e in no_sub[:3]),
  )

  subs = [sub for e in aligned for sub in getattr(e, "sub_provenance", [])]
  blunt = [sub for sub in subs if not sub.exact]
  ok &= check(
      "every extraction narrows to the words or the cell holding them",
      not blunt,
      f"{len(subs) - len(blunt)}/{len(subs)} narrowed"
      + (f"; blunt: {[s.text for s in blunt[:3]]}" if blunt else ""),
  )

  wrapped = [
      sub
      for sub in subs
      if sub.doc_item_label != "table" and len(sub.locations) > 1
  ]
  ok &= check(
      "text wrapping across lines gets one box per line",
      bool(wrapped),
      ", ".join(f"{sub.text!r}×{len(sub.locations)}" for sub in wrapped[:3]),
  )

  # A cell box must be a small fraction of the table it belongs to.
  table_area = {
      span.doc_item_ref: _area(span.locations[0].bbox)
      for e in aligned
      for span in getattr(e, "provenance", [])
      if span.doc_item_label == "table" and span.locations
  }
  cells = [sub for sub in subs if sub.doc_item_label == "table"]
  roomy = [
      sub
      for sub in cells
      for loc in sub.locations
      if _area(loc.bbox) > table_area.get(sub.doc_item_ref, 0) / 4
  ]
  ok &= check(
      "table extractions box their own cell, not the whole table",
      bool(cells) and not roomy,
      f"{len(cells)} cell extraction(s)"
      + (f"; whole-table: {[s.text for s in roomy[:3]]}" if roomy else ""),
  )

  # A narrowed box must sit inside the item box it was cut from.
  def inside(inner, outer, slack=2.0):
    return (
        inner[0] >= outer[0] - slack
        and inner[2] <= outer[2] + slack
        and min(inner[1], inner[3]) >= min(outer[1], outer[3]) - slack
        and max(inner[1], inner[3]) <= max(outer[1], outer[3]) + slack
    )

  escapes = []
  for extraction in aligned:
    item_boxes = collections.defaultdict(list)
    for span in getattr(extraction, "provenance", []):
      for loc in span.locations:
        item_boxes[span.doc_item_ref].append(loc)
    for sub in getattr(extraction, "sub_provenance", []):
      if not sub.exact:
        continue
      for loc in sub.locations:
        outer = [
            o
            for o in item_boxes.get(sub.doc_item_ref, [])
            if o.page_no == loc.page_no
        ]
        if outer and not any(inside(loc.bbox, o.bbox) for o in outer):
          escapes.append((extraction.extraction_text, sub.doc_item_ref))
  ok &= check(
      "narrowed boxes stay inside their item's box",
      not escapes,
      str(escapes[:2]),
  )

  pages = {loc.page_no for sub in subs for loc in sub.locations}
  ok &= check(
      "provenance spans both pages",
      pages == {1, 2},
      f"pages hit: {sorted(pages)}",
  )

  labels = {
      span.doc_item_label
      for e in aligned
      for span in getattr(e, "provenance", [])
  }
  ok &= check(
      "extractions resolve into table cells",
      "table" in labels,
      f"labels: {sorted(labels)}",
  )
  ok &= check(
      "extractions resolve into list items",
      bool({"list_item"} & labels),
      f"labels: {sorted(labels)}",
  )

  # Repeated names: the same text extracted more than once must land on
  # distinct places — this is the occurrence pinning the offset map buys.
  by_text = collections.defaultdict(set)
  for extraction in aligned:
    for sub in getattr(extraction, "sub_provenance", []):
      for loc in sub.locations:
        by_text[extraction.extraction_text.lower()].add(
            (loc.page_no, tuple(round(v, 1) for v in loc.bbox))
        )
  repeated = {text: boxes for text, boxes in by_text.items() if len(boxes) > 1}
  ok &= check(
      "repeated mentions map to distinct boxes",
      bool(repeated),
      ", ".join(f"{t}×{len(b)}" for t, b in sorted(repeated.items())[:4]),
  )

  html = lx.visualize_pdf(result, PDF_PATH)
  HTML_PATH.write_text(html if isinstance(html, str) else html.data)
  print(f"\nhtml     : {HTML_PATH} ({HTML_PATH.stat().st_size:,} bytes)")
  return 0 if ok else 1


if __name__ == "__main__":
  raise SystemExit(main())
