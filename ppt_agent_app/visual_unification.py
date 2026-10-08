"""Visual Unification — normalize fonts, sizes, and colors across all slides
by voting on the draft's own dominant style.

Runs between CHARACTER_REVISION (text/term unification) and TEMPLATE_UNIFICATION
(master/footer/logo). No LLM — pure python-pptx XML scan + rewrite.

Design (2026-07-28):
  - Profile source: draft self-vote (NOT external template). Rationale: draft is
    already ~70% consistent (most slides come from one source deck); minority
    outliers should be pulled to the majority, not to an external "correct" style.
  - Three tiers: title / body / note (by original size range)
  - Colors: keep palette + semantic whitelist; map unknown to nearest palette
  - Fonts: force latin/east_asian to the majority winners

Public API:
  extract_style_profile(pptx_path) -> dict
  scan_deck(pptx_path) -> dict
  apply_profile(pptx_path, profile, out_path) -> audit
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.util import Pt
from pptx.dml.color import RGBColor


# ──────────────────────────────────────────────────────────────────────────
# Scan
# ──────────────────────────────────────────────────────────────────────────

def _iter_runs(prs):
    for slide in prs.slides:
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    yield slide, shape, para, run


def _run_rgb_hex(run) -> str | None:
    """Return uppercase 6-char hex string if run has an explicit RGB color, else None."""
    try:
        if run.font.color.type is None:
            return None
        rgb = run.font.color.rgb
        if rgb is None:
            return None
        return str(rgb).upper()
    except Exception:
        return None


def _is_cjk(ch: str) -> bool:
    return "一" <= ch <= "鿿" or "㐀" <= ch <= "䶿"


def _run_script(run) -> str:
    """Classify a run as 'east_asian' if it contains any CJK char, else 'latin'.
    Used to bucket font names correctly (east_asian.name vs latin.name)."""
    text = run.text or ""
    for ch in text:
        if _is_cjk(ch):
            return "east_asian"
    return "latin"


def scan_deck(pptx_path: str | Path) -> dict:
    """Scan a deck and return distributions. Pure statistical, no changes."""
    prs = Presentation(str(pptx_path))
    fonts_latin: Counter = Counter()
    fonts_ea: Counter = Counter()
    sizes: Counter = Counter()
    colors: Counter = Counter()
    per_slide: list[dict] = []

    for slide_idx, slide in enumerate(prs.slides, start=1):
        slide_fonts: Counter = Counter()
        slide_sizes: Counter = Counter()
        slide_colors: Counter = Counter()
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    name = run.font.name
                    if name:
                        if _run_script(run) == "east_asian":
                            fonts_ea[name] += 1
                        else:
                            fonts_latin[name] += 1
                        slide_fonts[name] += 1
                    if run.font.size:
                        s = run.font.size.pt
                        sizes[s] += 1
                        slide_sizes[s] += 1
                    hexc = _run_rgb_hex(run)
                    if hexc:
                        colors[hexc] += 1
                        slide_colors[hexc] += 1
        per_slide.append({
            "slide_index": slide_idx,
            "dominant_font": slide_fonts.most_common(1)[0][0] if slide_fonts else None,
            "dominant_size": slide_sizes.most_common(1)[0][0] if slide_sizes else None,
            "dominant_color": slide_colors.most_common(1)[0][0] if slide_colors else None,
        })

    return {
        "slide_count": len(prs.slides),
        "fonts_latin": dict(fonts_latin.most_common(20)),
        "fonts_east_asian": dict(fonts_ea.most_common(20)),
        "sizes": {str(k): v for k, v in sizes.most_common(20)},
        "colors": dict(colors.most_common(30)),
        "per_slide": per_slide,
    }


# ──────────────────────────────────────────────────────────────────────────
# Profile extraction (draft self-vote)
# ──────────────────────────────────────────────────────────────────────────

# Fallbacks when the draft is basically empty
_FALLBACK_LATIN = "Calibri"
_FALLBACK_EA = "微软雅黑"
_FALLBACK_SIZES = {"title": 24.0, "body": 16.0, "note": 10.0}
_FALLBACK_TEXT_COLOR = "000000"

# Colors considered "neutral" (text/background) — separated from theme accents
_NEUTRAL_HEXES = {"000000", "FFFFFF", "F2F2F2", "D9D9D9", "BFBFBF", "A6A6A6",
                  "808080", "595959", "404040", "262626"}


def _is_grey(hex_str: str) -> bool:
    """RGB where R==G==B (or close), we consider grey/neutral."""
    if len(hex_str) != 6:
        return False
    try:
        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
    except Exception:
        return False
    return max(abs(r - g), abs(g - b), abs(r - b)) <= 8


def _pick_three_size_tiers(sizes_counter: Counter) -> dict:
    """Split the top sizes into title (largest bucket) / body (middle) / note (smallest).
    If < 3 distinct sizes, fall back."""
    if not sizes_counter:
        return dict(_FALLBACK_SIZES)
    unique = sorted(sizes_counter.keys())
    if len(unique) == 1:
        s = unique[0]
        return {"title": s, "body": s, "note": s}
    if len(unique) == 2:
        return {"title": unique[-1], "body": unique[0], "note": unique[0]}
    # ≥3 distinct: partition by tercile of the sorted list weighted by frequency
    ordered = sorted(sizes_counter.items(), key=lambda kv: kv[0])
    total = sum(c for _, c in ordered)
    cum = 0
    thirds = []
    for size, cnt in ordered:
        cum += cnt
        thirds.append((size, cum / total))
    # note = median of bottom third; body = median of middle; title = median of top
    note_sizes = [s for s, p in thirds if p <= 1/3]
    title_sizes = [s for s, p in thirds if p > 2/3]
    body_sizes = [s for s, p in thirds if 1/3 < p <= 2/3]
    return {
        "title": (title_sizes or [ordered[-1][0]])[len(title_sizes)//2 if title_sizes else 0],
        "body":  (body_sizes  or [ordered[len(ordered)//2][0]])[len(body_sizes)//2 if body_sizes else 0],
        "note":  (note_sizes  or [ordered[0][0]])[len(note_sizes)//2 if note_sizes else 0],
    }


def extract_style_profile(pptx_path: str | Path) -> dict:
    """Vote on the draft's own dominant style. No external template involved."""
    scan = scan_deck(pptx_path)
    fl = Counter(scan.get("fonts_latin") or {})
    fe = Counter(scan.get("fonts_east_asian") or {})
    colors = Counter(scan.get("colors") or {})
    sizes = Counter({float(k): v for k, v in (scan.get("sizes") or {}).items()})

    # Primary fonts: majority winner or fallback
    primary_latin = fl.most_common(1)[0][0] if fl else _FALLBACK_LATIN
    primary_ea = fe.most_common(1)[0][0] if fe else _FALLBACK_EA

    # Palette: text color = majority neutral/black; primary/accent = top non-neutral
    text_color = _FALLBACK_TEXT_COLOR
    for hexc, _ in colors.most_common():
        if hexc.upper() in _NEUTRAL_HEXES or _is_grey(hexc):
            text_color = hexc.upper()
            break

    # v2 (2026-07-29): expand palette to top-8 accent colors instead of just
    # primary/secondary. Prior version mapped everything outside top-2 to nearest
    # palette color, which killed blue titles in decks with red-dominant color.
    accent_colors = [hexc for hexc, _ in colors.most_common()
                     if hexc.upper() not in _NEUTRAL_HEXES and not _is_grey(hexc)]
    top_accents = accent_colors[:8]  # keep top-8 (was 2)
    primary = top_accents[0] if top_accents else "1F4E79"
    secondary = top_accents[1] if len(top_accents) >= 2 else primary
    muted = None
    for hexc, _ in colors.most_common():
        if _is_grey(hexc) and hexc.upper() != text_color.upper():
            muted = hexc.upper()
            break
    muted = muted or "A6A6A6"

    palette = {
        "text": text_color,
        "primary": primary,
        "secondary": secondary,
        "muted": muted,
        "bg": "FFFFFF",
    }
    # accent_extra: top-3..top-8 accents kept alongside palette (won't be remapped)
    palette["accent_extra"] = ",".join(top_accents[2:8])
    palette_set = {v.upper() for v in palette.values() if v}
    palette_set.update(c.upper() for c in top_accents)

    # Semantic whitelist: colors with usage >= 20 that are NOT already in palette
    semantic = []
    for hexc, cnt in colors.most_common(30):
        if hexc.upper() in palette_set:
            continue
        if cnt >= 20:
            semantic.append(hexc.upper())
    # Common semantic colors always kept even if not seen (safety)
    for stock in ("C00000", "00B050", "FFC000", "FFFF00", "FF0000"):
        if stock not in semantic:
            semantic.append(stock)

    tiers = _pick_three_size_tiers(sizes)

    return {
        "source": "draft_self_vote",
        "primary_font_latin": primary_latin,
        "primary_font_east_asian": primary_ea,
        "palette": palette,
        "semantic_colors_keep": semantic,
        "size_tiers": {k: float(v) for k, v in tiers.items()},
        "scan_summary": {
            "slide_count": scan.get("slide_count"),
            "top_fonts_latin": dict(fl.most_common(3)),
            "top_fonts_east_asian": dict(fe.most_common(3)),
            "top_colors": dict(colors.most_common(5)),
        },
    }


# ──────────────────────────────────────────────────────────────────────────
# Color mapping
# ──────────────────────────────────────────────────────────────────────────

def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    return (int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16))


def _color_distance(a: str, b: str) -> float:
    ra, ga, ba = _hex_to_rgb(a)
    rb, gb, bb = _hex_to_rgb(b)
    return ((ra - rb) ** 2 + (ga - gb) ** 2 + (ba - bb) ** 2) ** 0.5


def _map_to_palette(hex_str: str, palette: dict) -> str:
    """Return the palette color closest to hex_str."""
    candidates = [(v.upper(), _color_distance(hex_str, v)) for v in palette.values()]
    candidates.sort(key=lambda x: x[1])
    return candidates[0][0]


def _classify_size_tier(pt: float, tiers: dict) -> str:
    """Return 'title'|'body'|'note' by picking the closest tier size."""
    scored = sorted(tiers.items(), key=lambda kv: abs(kv[1] - pt))
    return scored[0][0]


# ──────────────────────────────────────────────────────────────────────────
# Apply
# ──────────────────────────────────────────────────────────────────────────

def apply_profile(pptx_path: str | Path, profile: dict,
                   out_path: str | Path | None = None,
                   *,
                   apply_font: bool = False,
                   apply_size: bool = False,
                   apply_color: bool = True) -> dict:
    """Rewrite the deck to conform to the profile. Returns audit dict.

    v2 (2026-07-29) defaults changed: apply_font=False and apply_size=False.
    Prior version aggressively changed source fonts and sizes which caused
    text overflow (title too wide) and destroyed original design.  Only
    color normalization stays on by default, and even that only re-maps
    colors that are neither in the palette nor in the semantic whitelist.

    Rules:
      - font.name: only touched if apply_font=True
      - font.size: only touched if apply_size=True
      - font.color.rgb: if apply_color=True and color not in palette/semantic
        -> map to nearest palette color; else keep
      - italic/bold/underline/highlight left untouched
    """
    prs = Presentation(str(pptx_path))
    palette = profile.get("palette") or {}
    palette_set = {v.upper() for v in palette.values()}
    semantic_set = {c.upper() for c in (profile.get("semantic_colors_keep") or [])}
    tiers = profile.get("size_tiers") or _FALLBACK_SIZES
    latin_name = profile.get("primary_font_latin") or _FALLBACK_LATIN
    ea_name = profile.get("primary_font_east_asian") or _FALLBACK_EA

    changes_per_slide: list[dict] = []
    total_font_changes = 0
    total_size_changes = 0
    total_color_changes = 0
    total_color_kept_semantic = 0

    for slide_idx, slide in enumerate(prs.slides, start=1):
        slide_changes = {"slide_index": slide_idx, "font": 0, "size": 0,
                         "color": 0, "color_kept": 0}
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    if not (run.text or "").strip():
                        continue
                    script = _run_script(run)
                    target_name = ea_name if script == "east_asian" else latin_name

                    # Font (only if apply_font)
                    if apply_font:
                        if run.font.name and run.font.name != target_name:
                            run.font.name = target_name
                            slide_changes["font"] += 1
                            total_font_changes += 1
                        elif not run.font.name:
                            run.font.name = target_name
                            slide_changes["font"] += 1
                            total_font_changes += 1

                    # Size (only if apply_size)
                    if apply_size and run.font.size:
                        cur_pt = run.font.size.pt
                        if cur_pt >= 6:
                            tier_name = _classify_size_tier(cur_pt, tiers)
                            target_pt = tiers[tier_name]
                            if abs(cur_pt - target_pt) > 0.5:
                                run.font.size = Pt(target_pt)
                                slide_changes["size"] += 1
                                total_size_changes += 1

                    # Color (only if apply_color)
                    if not apply_color:
                        continue
                    hexc = _run_rgb_hex(run)
                    if hexc:
                        hex_u = hexc.upper()
                        if hex_u in palette_set or hex_u in semantic_set:
                            slide_changes["color_kept"] += 1
                            total_color_kept_semantic += 1
                        else:
                            mapped = _map_to_palette(hex_u, palette)
                            if mapped != hex_u:
                                try:
                                    run.font.color.rgb = RGBColor(*_hex_to_rgb(mapped))
                                    slide_changes["color"] += 1
                                    total_color_changes += 1
                                except Exception:
                                    pass
        changes_per_slide.append(slide_changes)

    out = Path(out_path) if out_path else Path(pptx_path)
    prs.save(str(out))

    return {
        "ok": True,
        "input_pptx": str(pptx_path),
        "output_pptx": str(out),
        "apply_flags": {"font": apply_font, "size": apply_size, "color": apply_color},
        "profile_used": {
            "primary_font_latin": latin_name,
            "primary_font_east_asian": ea_name,
            "size_tiers": tiers,
            "palette": palette,
            "semantic_colors_keep": sorted(semantic_set),
        },
        "summary": {
            "slide_count": len(prs.slides),
            "font_changes": total_font_changes,
            "size_changes": total_size_changes,
            "color_changes": total_color_changes,
            "color_kept_semantic": total_color_kept_semantic,
        },
        "per_slide": changes_per_slide,
    }
