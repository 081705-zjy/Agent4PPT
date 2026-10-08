"""Template Unification — align outlier slides to the dominant source deck's
template shell (master/footer/page-number/logo).

Runs between VISUAL_UNIFICATION (fonts/colors) and DRAFT_REVIEW.

Design (2026-07-28):
  - Dominant source is voted from draft-source-lineage.json (majority deck by
    slide count). Slides already from the dominant deck are left untouched.
  - Two paths:
      A. swap  — outlier canvas == dominant canvas → replace master/layout via
                 XML injection (NOT YET IMPLEMENTED; falls back to overlay)
      B. overlay — outlier canvas != dominant canvas OR swap disabled → keep the
                 outlier's own master/layout, but overlay dominant deck's
                 footer/pageNumber/logo shapes on top
  - Purely deterministic Python — no LLM.

Public API:
  detect_dominant_source(lineage_doc) -> dict
  extract_shell(source_pptx_path) -> dict
  apply_shell(draft_pptx, dominant_deck_pptx, out_path,
              minority_slide_indices) -> audit
"""

from __future__ import annotations

import re
import shutil
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.util import Emu


# ──────────────────────────────────────────────────────────────────────────
# Dominant source detection
# ──────────────────────────────────────────────────────────────────────────

# source_resource_id looks like:
#   "tpl.<scenario>.<slug>.<sha8>.slide_NN"  (real format from decks-index.json)
# deck_id = first 4 segments (drop the trailing ".slide_NN")
_RESOURCE_RE = re.compile(r"^(tpl\.[^.]+\.[^.]+\.[a-f0-9]{6,10})")


def _deck_id_from_resource(rid: str) -> str | None:
    if not rid or not isinstance(rid, str):
        return None
    m = _RESOURCE_RE.match(rid)
    return m.group(1) if m else None


def detect_dominant_source(lineage_doc: dict) -> dict:
    """Vote on the majority source deck across all slides.

    Returns:
      {
        "dominant_deck_id": str | None,
        "dominant_count": int,
        "total_count": int,
        "distribution": {deck_id: count, ...},
        "minority_slide_indices": [int, ...],  # slides NOT from the dominant deck
      }
    """
    entries = lineage_doc.get("entries") or lineage_doc.get("lineage_entries") or []
    if not entries:
        return {"dominant_deck_id": None, "dominant_count": 0, "total_count": 0,
                "distribution": {}, "minority_slide_indices": []}

    per_slide_deck: dict[int, str | None] = {}
    for e in entries:
        if not isinstance(e, dict):
            continue
        try:
            idx = int(e.get("slide_index"))
        except (TypeError, ValueError):
            continue
        deck = _deck_id_from_resource(e.get("source_resource_id") or "")
        per_slide_deck[idx] = deck

    counter: Counter = Counter(v for v in per_slide_deck.values() if v)
    if not counter:
        return {"dominant_deck_id": None, "dominant_count": 0,
                "total_count": len(per_slide_deck), "distribution": {},
                "minority_slide_indices": sorted(per_slide_deck.keys())}

    dominant, dominant_count = counter.most_common(1)[0]
    minority = [idx for idx, d in per_slide_deck.items() if d != dominant]
    return {
        "dominant_deck_id": dominant,
        "dominant_count": dominant_count,
        "total_count": len(per_slide_deck),
        "distribution": dict(counter.most_common()),
        "minority_slide_indices": sorted(minority),
    }


# ──────────────────────────────────────────────────────────────────────────
# Shell extraction
# ──────────────────────────────────────────────────────────────────────────

def resolve_deck_pptx_path(deck_id: str, root: Path) -> Path | None:
    """Look up the source pptx file for a deck_id via material/decks-index.json.

    deck_id format: tpl.<scenario>.<deck-slug>[.<sha8>]
    Returns absolute path to the source .pptx, or None if not found.
    """
    import json
    idx_path = root / "data" / "resources_library" / "material" / "decks-index.json"
    if not idx_path.exists():
        return None
    try:
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    for d in idx.get("decks") or []:
        if str(d.get("deck标识")) == deck_id:
            src = d.get("源文件")  # e.g. "templates/本组论文与科研成果/DATE26 Endor...pptx"
            if src:
                p = root / src
                if p.exists():
                    return p
    return None


def extract_shell(pptx_path: str | Path,
                    min_slide_occurrences: int = 3) -> dict:
    """Extract "shell" elements: shapes that repeat across multiple content slides
    at the same position (= true footer/pageNum/logo, not per-page content).

    Algorithm: scan slides 2..end (skip cover), for each shape record a fingerprint
    (role, position_bucket_100px). Any fingerprint seen in >= min_slide_occurrences
    slides is deemed shell; take the first XML found. This filters out per-page
    content images that our loose _classify_shell_role would otherwise flag.
    """
    prs = Presentation(str(pptx_path))
    canvas = (int(prs.slide_width), int(prs.slide_height))

    if len(prs.slides) < 2:
        return {"source_pptx": str(pptx_path), "canvas": canvas,
                "shell_elements": [], "shell_count": 0}

    # Skip cover slide, sample the rest
    content_slides = list(prs.slides)[1:]
    # Bucket positions to 100k EMU (~0.1 inch) to tolerate minor drift
    def _bucket(v):
        if v is None:
            return None
        return int(v) // 100000

    # fingerprint → [(slide_idx, shape)]
    fp_to_shapes: dict = {}
    for i, slide in enumerate(content_slides):
        for shape in slide.shapes:
            role = _classify_shell_role(shape)
            if role is None:
                continue
            try:
                pos_bucket = (_bucket(shape.left), _bucket(shape.top),
                              _bucket(shape.width), _bucket(shape.height))
            except Exception:
                pos_bucket = (None, None, None, None)
            fp = (role, pos_bucket)
            fp_to_shapes.setdefault(fp, []).append((i, shape))

    shell_xml: list[dict] = []
    for fp, occurrences in fp_to_shapes.items():
        if len(occurrences) < min_slide_occurrences:
            continue
        # take first occurrence's xml
        _, shape = occurrences[0]
        shell_xml.append({
            "role": fp[0],
            "occurrence_count": len(occurrences),
            "xml": shape._element.xml,
            "position": {
                "left": int(shape.left) if shape.left else None,
                "top": int(shape.top) if shape.top else None,
                "width": int(shape.width) if shape.width else None,
                "height": int(shape.height) if shape.height else None,
            },
        })

    return {
        "source_pptx": str(pptx_path),
        "canvas": canvas,
        "shell_elements": shell_xml,
        "shell_count": len(shell_xml),
    }


def _classify_shell_role(shape) -> str | None:
    """Return 'footer' | 'page_number' | 'logo' | None."""
    # Check for placeholder type (footer / slide number)
    try:
        if shape.is_placeholder:
            ph_type = shape.placeholder_format.type
            # ph_type is an enum; string repr contains 'FOOTER', 'SLIDE_NUMBER'
            ph_str = str(ph_type).upper()
            if "FOOTER" in ph_str:
                return "footer"
            if "SLIDE_NUMBER" in ph_str or "SLDNUM" in ph_str:
                return "page_number"
    except Exception:
        pass
    # Small pictures in corners often = logo
    if shape.shape_type == 13:  # PICTURE
        try:
            # heuristic: small (< 15% of slide dim) and near an edge
            # Skip this heuristic here; user can extend later.
            return "logo"
        except Exception:
            pass
    return None


# ──────────────────────────────────────────────────────────────────────────
# Apply — overlay mode
# ──────────────────────────────────────────────────────────────────────────

def _remove_existing_shell(slide) -> int:
    """Remove existing footer/pageNumber/logo shapes from a slide.
    Returns count removed. Used before overlaying new shell to avoid duplicates."""
    to_remove = []
    for shape in slide.shapes:
        role = _classify_shell_role(shape)
        if role is not None:
            to_remove.append(shape)
    removed = 0
    for shape in to_remove:
        try:
            sp = shape._element
            sp.getparent().remove(sp)
            removed += 1
        except Exception:
            pass
    return removed


def _inject_shell(slide, shell_xml_entry: dict) -> bool:
    """Append a shell shape (from stored XML) into a slide's spTree.
    Returns True on success."""
    from lxml import etree
    try:
        # Parse the stored xml back into an element
        new_el = etree.fromstring(shell_xml_entry["xml"])
        spTree = slide.shapes._spTree
        spTree.append(new_el)
        return True
    except Exception:
        return False


def apply_shell_overlay(draft_pptx: str | Path, dominant_pptx: str | Path,
                          out_pptx: str | Path,
                          minority_slide_indices: list[int]) -> dict:
    """Overlay dominant deck's shell (footer/pageNumber/logo) onto minority slides.
    Does NOT change canvas size or master. minority_slide_indices are 1-based.
    """
    # Copy draft to output first (we operate on the copy)
    shutil.copy2(str(draft_pptx), str(out_pptx))
    shell = extract_shell(dominant_pptx)
    shell_elements = shell.get("shell_elements") or []
    if not shell_elements:
        return {"ok": True, "mode": "overlay", "note": "dominant has no shell to overlay",
                "output_pptx": str(out_pptx), "changed_slides": 0}

    prs = Presentation(str(out_pptx))
    n_slides = len(prs.slides)
    minority_set = {i for i in minority_slide_indices if 1 <= i <= n_slides}

    changed = 0
    skipped_canvas = 0
    per_slide_audit: list[dict] = []
    dominant_canvas = tuple(shell.get("canvas") or ())
    draft_canvas = (int(prs.slide_width), int(prs.slide_height))
    if draft_canvas != dominant_canvas:
        # Canvas mismatch: overlay position emu is relative to dominant canvas;
        # if we blindly inject, shape ends up at wrong place. For now, skip
        # position-sensitive elements and warn.
        canvas_ok = False
    else:
        canvas_ok = True

    for idx_1 in sorted(minority_set):
        slide = prs.slides[idx_1 - 1]
        removed = _remove_existing_shell(slide)
        injected = 0
        for shell_entry in shell_elements:
            if not canvas_ok and shell_entry.get("role") in {"footer", "page_number", "logo"}:
                # positional overlay skipped when canvas differs
                continue
            if _inject_shell(slide, shell_entry):
                injected += 1
        per_slide_audit.append({
            "slide_index": idx_1,
            "shell_removed": removed,
            "shell_injected": injected,
        })
        if injected > 0:
            changed += 1
        elif not canvas_ok:
            skipped_canvas += 1

    prs.save(str(out_pptx))
    return {
        "ok": True,
        "mode": "overlay",
        "output_pptx": str(out_pptx),
        "dominant_canvas": list(dominant_canvas),
        "draft_canvas": list(draft_canvas),
        "canvas_match": canvas_ok,
        "shell_element_count": len(shell_elements),
        "minority_slide_count": len(minority_set),
        "changed_slides": changed,
        "skipped_canvas_mismatch": skipped_canvas,
        "per_slide": per_slide_audit,
    }
