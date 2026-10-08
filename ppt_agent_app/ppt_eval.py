"""PPT Evaluation — text-only implementation adapted from icip-cas/PPTAgent's
ppteval module.

Original PPTAgent evaluates 4 dimensions (content / style / logic / constraint)
via VLM (vision) + LLM. This adaptation drops the vision-dependent 'style'
dimension (requires libreoffice pptx→PNG rendering) and evaluates 3 dimensions
via LLM-on-text only:

  1. content_text — per-slide text content quality (5-point scale)
  2. logic       — whole-deck narrative coherence (5-point scale)
  3. constraint  — hard rules (slide_count range, language, aspect ratio hint)

Adds a 4th 'style' dimension placeholder (defaults to null) — will be filled
when libreoffice becomes available.

Reads:
  - <deck>.pptx  (final rendered PPT)
  - question-state.json (for constraint spec)

Writes:
  - eval-report.json  (per-slide + aggregate scores)
  - eval-summary.md   (human-readable)
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from pptx import Presentation

from .models import ROOT, now, project_dir, read_json, write_json


# ──────────────────────────────────────────────────────────────────────────
# Prompt loading (from skills/eval/*.md, copied from PPTAgent)
# ──────────────────────────────────────────────────────────────────────────

_PROMPT_DIR = ROOT / "skills" / "eval"


def _load_prompt(name: str) -> str:
    p = _PROMPT_DIR / name
    if not p.exists():
        raise FileNotFoundError(f"prompt {p} missing (expected in skills/eval/)")
    return p.read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────
# Text extraction
# ──────────────────────────────────────────────────────────────────────────

def extract_slide_texts(pptx_path: str | Path) -> list[dict]:
    """Extract text content per slide.

    Returns list of {slide_index, title, body, notes, all_text} for each slide.
    Uses python-pptx directly (no external converter).
    """
    prs = Presentation(str(pptx_path))
    result = []
    for idx, slide in enumerate(prs.slides, start=1):
        title = ""
        body_lines = []
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            texts = []
            for para in shape.text_frame.paragraphs:
                t = para.text.strip()
                if t:
                    texts.append(t)
            if not texts:
                continue
            joined = "\n".join(texts)
            # heuristic: first text-shape at top of slide is title
            if not title:
                try:
                    if shape.top is not None and shape.top < prs.slide_height * 0.2:
                        title = texts[0]
                        body_lines.extend(texts[1:])
                        continue
                except Exception:
                    pass
            body_lines.extend(texts)
        # speaker notes
        notes = ""
        try:
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                notes = slide.notes_slide.notes_text_frame.text.strip()
        except Exception:
            pass
        all_text = (title + "\n" + "\n".join(body_lines) + ("\n[notes] " + notes if notes else "")).strip()
        result.append({
            "slide_index": idx,
            "title": title,
            "body": body_lines,
            "notes": notes,
            "all_text": all_text,
        })
    return result


def format_deck_for_extract(slides: list[dict]) -> str:
    """Serialize slides as text passed into the extract prompt."""
    parts = []
    for s in slides:
        parts.append(f"## Slide {s['slide_index']}")
        if s.get("title"):
            parts.append(f"Title: {s['title']}")
        for line in s.get("body", []):
            parts.append(f"- {line}")
        if s.get("notes"):
            parts.append(f"[speaker notes] {s['notes']}")
        parts.append("")
    return "\n".join(parts)


def format_slide_text_desc(s: dict) -> str:
    """Format one slide's text as the 'descr' passed into content prompt."""
    parts = [f"Slide {s['slide_index']}"]
    if s.get("title"):
        parts.append(f"Title: {s['title']}")
    if s.get("body"):
        parts.append("Body:")
        for line in s["body"]:
            parts.append(f"  - {line}")
    if s.get("notes"):
        parts.append(f"Speaker notes: {s['notes']}")
    if not s.get("title") and not s.get("body"):
        parts.append("(empty slide)")
    return "\n".join(parts)


# ──────────────────────────────────────────────────────────────────────────
# LLM scoring (via claude_cli)
# ──────────────────────────────────────────────────────────────────────────

_CONTENT_PROMPT_TPL = None
_COHERENCE_PROMPT_TPL = None
_EXTRACT_PROMPT_TPL = None


def _lazy_prompts():
    global _CONTENT_PROMPT_TPL, _COHERENCE_PROMPT_TPL, _EXTRACT_PROMPT_TPL
    if _CONTENT_PROMPT_TPL is None:
        _CONTENT_PROMPT_TPL = _load_prompt("ppteval_content.md")
        _COHERENCE_PROMPT_TPL = _load_prompt("ppteval_coherence.md")
        _EXTRACT_PROMPT_TPL = _load_prompt("ppteval_extract.md")
    return _CONTENT_PROMPT_TPL, _COHERENCE_PROMPT_TPL, _EXTRACT_PROMPT_TPL


def _render_prompt(tpl: str, var_name: str, value: str) -> str:
    """Minimal jinja2 {{var}} replacement (avoids adding jinja2 dep)."""
    return tpl.replace("{{" + var_name + "}}", value)


def score_content(slide_text_desc: str, claude_cli) -> dict:
    """Send content descr to Claude with content-scoring prompt. Returns {score, reason}."""
    tpl, _, _ = _lazy_prompts()
    prompt = _render_prompt(tpl, "descr", slide_text_desc)
    outcome = claude_cli.call_claude_json(prompt, timeout=120)
    if not outcome.get("ok"):
        return {"score": None, "reason": f"claude_error: {outcome.get('error','')[:200]}"}
    d = outcome["data"]
    try:
        score = float(d.get("score", 0))
    except Exception:
        score = None
    return {"score": score, "reason": (d.get("reason") or "")[:400]}


def score_coherence(deck_summary: str, claude_cli) -> dict:
    """Send deck summary (extracted) to coherence-scoring prompt. Returns {score, reason}."""
    _, tpl, _ = _lazy_prompts()
    prompt = _render_prompt(tpl, "presentation", deck_summary)
    outcome = claude_cli.call_claude_json(prompt, timeout=180)
    if not outcome.get("ok"):
        return {"score": None, "reason": f"claude_error: {outcome.get('error','')[:200]}"}
    d = outcome["data"]
    try:
        score = float(d.get("score", 0))
    except Exception:
        score = None
    return {"score": score, "reason": (d.get("reason") or "")[:400]}


def extract_presentation_summary(deck_text_serialized: str, claude_cli) -> dict:
    """Ask Claude to produce {slide_descriptions, background} from raw text."""
    _, _, tpl = _lazy_prompts()
    prompt = _render_prompt(tpl, "presentation", deck_text_serialized)
    outcome = claude_cli.call_claude_json(prompt, timeout=180)
    if not outcome.get("ok"):
        return {"slide_descriptions": [], "background": {}, "error": outcome.get("error")}
    return outcome["data"]


# ──────────────────────────────────────────────────────────────────────────
# PPTX → PNG rendering (for vision-based style scoring)
# ──────────────────────────────────────────────────────────────────────────

def _soffice_available() -> str | None:
    """Return path to soffice binary if installed, else None."""
    import shutil
    return shutil.which("soffice") or shutil.which("libreoffice")


def render_pptx_to_pngs(pptx_path: str | Path, out_dir: str | Path,
                          *, dpi: int = 100) -> list[Path]:
    """Convert pptx to per-slide PNGs.

    Uses `soffice --headless --convert-to pdf` then PyMuPDF (fitz) for PDF→PNG.
    Returns list of PNG paths (empty on failure).
    """
    import subprocess
    import tempfile
    soffice = _soffice_available()
    if soffice is None:
        return []
    pptx_path = Path(pptx_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_pdf_dir, tempfile.TemporaryDirectory() as profile_dir:
        # Step 1: pptx → pdf via soffice
        profile_uri = Path(profile_dir).as_uri()
        cmd = [
            soffice,
            f"-env:UserInstallation={profile_uri}",
            "--headless", "--convert-to", "pdf",
            str(pptx_path),
            "--outdir", str(tmp_pdf_dir),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            return []
        if proc.returncode != 0:
            return []
        pdfs = list(Path(tmp_pdf_dir).glob("*.pdf"))
        if not pdfs:
            return []
        pdf_path = pdfs[0]

        # Step 2: pdf → per-page png via PyMuPDF (fitz)
        try:
            import fitz
        except ImportError:
            return []
        pngs: list[Path] = []
        doc = fitz.open(str(pdf_path))
        try:
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            for i, page in enumerate(doc, start=1):
                pix = page.get_pixmap(matrix=mat, alpha=False)
                png_out = out_dir / f"slide_{i:02d}.png"
                pix.save(str(png_out))
                pngs.append(png_out)
        finally:
            doc.close()
        return pngs


# ──────────────────────────────────────────────────────────────────────────
# Style scoring (vision-based, requires rendered PNGs)
# ──────────────────────────────────────────────────────────────────────────

_STYLE_DESCRIBE_TPL = None
_STYLE_SCORE_TPL = None


def _lazy_style_prompts():
    global _STYLE_DESCRIBE_TPL, _STYLE_SCORE_TPL
    if _STYLE_DESCRIBE_TPL is None:
        _STYLE_DESCRIBE_TPL = _load_prompt("ppteval_describe_style.md")
        _STYLE_SCORE_TPL = _load_prompt("ppteval_style.md")
    return _STYLE_DESCRIBE_TPL, _STYLE_SCORE_TPL


def describe_style_from_image(png_path: str | Path, claude_cli) -> str:
    """Use Claude vision (via Read tool on PNG) to describe visual style.
    Returns a text description or empty string on failure.
    """
    describe_tpl, _ = _lazy_style_prompts()
    png_path = Path(png_path).resolve()
    # Embed the actual PNG path so Claude Read-tool call knows what to open
    prompt = (
        describe_tpl.rstrip()
        + f"\n\nPlease Read the file at `{png_path}` and describe its style."
    )
    outcome = claude_cli.call_claude_text(
        prompt, timeout=180,
        add_dirs=[str(png_path.parent)],
        allowed_tools=["Read"],
    ) if hasattr(claude_cli, "call_claude_text") else claude_cli.call_claude_json(
        prompt, timeout=180,
        add_dirs=[str(png_path.parent)],
        allowed_tools=["Read"],
    )
    if not outcome.get("ok"):
        return ""
    # call_claude_text returns .text; call_claude_json returns .data (may be str)
    return outcome.get("text") or (outcome.get("data") if isinstance(outcome.get("data"), str) else "")


def score_style(style_descr: str, claude_cli) -> dict:
    """Score a slide's style descr with the style prompt (5pt scale)."""
    _, tpl = _lazy_style_prompts()
    prompt = _render_prompt(tpl, "descr", style_descr)
    outcome = claude_cli.call_claude_json(prompt, timeout=120)
    if not outcome.get("ok"):
        return {"score": None, "reason": f"claude_error: {outcome.get('error','')[:200]}"}
    d = outcome["data"]
    try:
        score = float(d.get("score", 0))
    except Exception:
        score = None
    return {"score": score, "reason": (d.get("reason") or "")[:400]}


# ──────────────────────────────────────────────────────────────────────────
# Constraint verification (deterministic; no LLM)
# ──────────────────────────────────────────────────────────────────────────

def verify_constraints(pptx_path: str | Path, project_config: dict) -> dict:
    """Check hard rules from question-state.answers against actual deck.

    Returns {items: [{constraint, actual, expected, pass, note}], score: 0-1}.
    """
    prs = Presentation(str(pptx_path))
    items = []

    # 1. slide_count within ±20% of expected
    expected_count = project_config.get("slide_count")
    if expected_count:
        try:
            expected_count = int(expected_count)
        except Exception:
            expected_count = None
    actual_count = len(prs.slides)
    if expected_count:
        low = int(expected_count * 0.8)
        high = int(expected_count * 1.2)
        ok = low <= actual_count <= high
        items.append({
            "constraint": "slide_count",
            "expected": f"{low}-{high} (target {expected_count})",
            "actual": actual_count,
            "pass": ok,
            "note": "within ±20% of user-specified slide_count",
        })

    # 2. aspect ratio
    canvas_w = prs.slide_width / 914400.0  # EMU → inches
    canvas_h = prs.slide_height / 914400.0
    ar = canvas_w / canvas_h if canvas_h else 0
    if abs(ar - 16 / 9) < 0.1:
        detected = "16:9"
    elif abs(ar - 4 / 3) < 0.1:
        detected = "4:3"
    else:
        detected = f"{canvas_w:.2f}:{canvas_h:.2f}"
    items.append({
        "constraint": "aspect_ratio",
        "expected": "16:9 or 4:3 (standard)",
        "actual": detected,
        "pass": detected in ("16:9", "4:3"),
        "note": None,
    })

    # 3. language: expected from project_config, detect from all-text
    all_text = ""
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    all_text += (para.text or "") + " "
    expected_lang = (project_config.get("language") or "zh").lower()
    # heuristic: compare CJK vs latin alphabet count (ignore whitespace, digits, punctuation).
    # zh deck typically has CJK > latin (even if a lot of English tech terms sprinkled).
    # A 30% CJK-of-alpha-only threshold catches Chinese decks that also contain
    # significant English terms.
    cjk_count = sum(1 for c in all_text if "一" <= c <= "鿿")
    latin_count = sum(1 for c in all_text if c.isalpha() and not ("一" <= c <= "鿿"))
    total_alpha = cjk_count + latin_count
    if total_alpha == 0:
        detected_lang = expected_lang  # empty deck: assume match
    else:
        detected_lang = "zh" if cjk_count / total_alpha > 0.2 else "en"
    items.append({
        "constraint": "language",
        "expected": expected_lang,
        "actual": detected_lang,
        "pass": expected_lang == detected_lang,
        "note": f"heuristic based on alpha count (CJK {cjk_count} vs latin {latin_count})",
    })

    n_pass = sum(1 for i in items if i["pass"])
    score = n_pass / len(items) if items else 1.0
    return {"items": items, "score": round(score, 3), "n_pass": n_pass, "n_total": len(items)}


# ──────────────────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────────────────

def evaluate_deck(pptx_path: str | Path, project_config: dict, claude_cli,
                  *, max_slides: int | None = None) -> dict:
    """Full 3-dimension evaluation. Returns report dict.

    Args:
      pptx_path: final rendered .pptx
      project_config: dict with keys slide_count, language, ...
        (usually derived from question-state.answers or idea-intake-light)
      claude_cli: module (ppt_agent_app.claude_cli) with call_claude_json
      max_slides: optional cap for content eval (dev testing)
    """
    pptx_path = Path(pptx_path)
    slides = extract_slide_texts(pptx_path)
    if not slides:
        return {"ok": False, "error": "no slides in pptx"}

    # 0. Optional: render pptx → PNG for style scoring (needs soffice)
    render_dir = pptx_path.with_suffix("") / "eval_images"
    slide_pngs: dict[int, Path] = {}
    if _soffice_available():
        try:
            pngs = render_pptx_to_pngs(pptx_path, render_dir)
            slide_pngs = {i + 1: p for i, p in enumerate(pngs)}
            print(f"[ppt_eval] rendered {len(pngs)} PNGs for style scoring",
                  flush=True)
        except Exception as exc:
            print(f"[ppt_eval] render failed ({exc}); style dim will be null",
                  flush=True)
    else:
        print("[ppt_eval] soffice not on PATH; style dim will be null",
              flush=True)

    # 1. content (+ style if PNGs available) per slide
    to_score = slides[:max_slides] if max_slides else slides
    per_slide = []
    for s in to_score:
        desc = format_slide_text_desc(s)
        content_score = score_content(desc, claude_cli)
        style_score = {"score": None,
                       "reason": "vision unavailable (libreoffice/pngs missing)"}
        png = slide_pngs.get(s["slide_index"])
        if png and png.exists():
            style_descr = describe_style_from_image(png, claude_cli)
            if style_descr:
                style_score = score_style(style_descr, claude_cli)
        per_slide.append({
            "slide_index": s["slide_index"],
            "title": s["title"],
            "content": content_score,
            "style": style_score,
        })

    # 2. coherence: extract summary, then score
    deck_serial = format_deck_for_extract(slides)
    summary_obj = extract_presentation_summary(deck_serial, claude_cli)
    summary_json = json.dumps(summary_obj, ensure_ascii=False, indent=2)
    coherence = score_coherence(summary_json, claude_cli)

    # 3. constraint
    constraint = verify_constraints(pptx_path, project_config)

    # Aggregate
    content_scores = [p["content"]["score"] for p in per_slide
                      if p["content"].get("score") is not None]
    avg_content = sum(content_scores) / len(content_scores) if content_scores else None
    style_scores = [p["style"]["score"] for p in per_slide
                    if p["style"].get("score") is not None]
    avg_style = sum(style_scores) / len(style_scores) if style_scores else None

    return {
        "schema_version": "1.0",
        "generated_at": now(),
        "input_pptx": str(pptx_path),
        "slide_count": len(slides),
        "slides_evaluated_for_content": len(per_slide),
        "aggregate": {
            "content_avg": round(avg_content, 2) if avg_content is not None else None,
            "style_avg": round(avg_style, 2) if avg_style is not None else None,
            "logic_score": coherence.get("score"),
            "constraint_score": constraint.get("score"),
            "overall": _overall(avg_content, avg_style, coherence.get("score"), constraint.get("score")),
        },
        "content": per_slide,
        "logic": coherence,
        "constraint": constraint,
        "presentation_summary": summary_obj,
    }


def _overall(content, style, logic, constraint) -> float | None:
    """Simple weighted average (equal weights across available dimensions)."""
    parts = []
    if content is not None:
        parts.append(content / 5.0)   # normalize 5-point to 0-1
    if style is not None:
        parts.append(style / 5.0)
    if logic is not None:
        parts.append(logic / 5.0)
    if constraint is not None:
        parts.append(constraint)
    if not parts:
        return None
    return round(sum(parts) / len(parts), 3)


def render_summary_md(report: dict) -> str:
    """Human-readable eval report."""
    agg = report.get("aggregate", {})
    lines = [
        "# PPT Evaluation Report",
        f"Generated: {report.get('generated_at')}",
        f"Input: {report.get('input_pptx')}",
        f"Slide count: {report.get('slide_count')}",
        "",
        "## Aggregate Scores",
        f"- **Overall**: {agg.get('overall')}" if agg.get('overall') is not None else "- Overall: N/A",
        f"- **Content (avg 5pt)**: {agg.get('content_avg')}"
        if agg.get('content_avg') is not None else "- Content: N/A",
        f"- **Style (avg 5pt)**: {agg.get('style_avg')}" if agg.get('style_avg') is not None
        else "- **Style**: N/A (soffice / libreoffice not installed for pptx→PNG)",
        f"- **Logic (5pt)**: {agg.get('logic_score')}"
        if agg.get('logic_score') is not None else "- Logic: N/A",
        f"- **Constraint (0-1)**: {agg.get('constraint_score')}"
        if agg.get('constraint_score') is not None else "- Constraint: N/A",
        "",
        "## Constraints",
    ]
    for c in (report.get("constraint") or {}).get("items", []):
        mark = "✅" if c["pass"] else "❌"
        lines.append(f"- {mark} **{c['constraint']}**: expected `{c['expected']}`, actual `{c['actual']}`")
    lines.append("")
    lines.append("## Logic")
    logic = report.get("logic", {})
    lines.append(f"Score: {logic.get('score')}/5")
    lines.append(f"Reason: {logic.get('reason','')}")
    lines.append("")
    lines.append("## Content (per slide)")
    for p in report.get("content", []):
        score = p["content"].get("score")
        lines.append(f"- Slide {p['slide_index']}: **{score}/5** — {(p.get('title') or '')[:60]}")
    return "\n".join(lines)
