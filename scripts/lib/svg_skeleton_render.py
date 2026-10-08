#!/usr/bin/env python3
"""svg_skeleton_render.py — template-inheriting render path (the ppt-master way).

For each slide it inherits the user template's *layout SVG skeleton* (real background,
header band, logo, accent shapes — placeholder prompt text stripped), injects EDITABLE
title/body/table text into the template's real placeholder regions using the template's
locked colors/fonts (from template-profile.json / spec_lock.md), then exports the deck to
native DrawingML via ppt-master's `svg_to_pptx` (so every text/shape stays editable).

Entry point: render(run_dir, out_dir, blocks, smoke, backend, min_ratio, scripts_dir,
profile). Produces in out_dir: deck.pptx, slides-html/, screenshots/, render-log.md —
the same contract pptx_backend's native builder produces.
"""
from __future__ import annotations

import base64
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import speaker_notes
import presentation_effects

CJK_FONT = os.path.expanduser("~/.fonts/NotoSansCJKsc-Regular.otf")
# Font stack used in the SVG so PowerPoint and rasterizers both have a CJK option.
# Single-quoted family names so the value is valid inside a double-quoted XML attribute.
FONT_STACK = "'Microsoft YaHei', '微软雅黑', 'Noto Sans CJK SC', Arial, sans-serif"


def _now():
    return os.environ.get("PPT_FAKE_NOW") or datetime.datetime.now(
        datetime.timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def _char_w(ch: str, size: float) -> float:
    o = ord(ch)
    if o > 0x2E80:  # CJK / full-width
        return size * 1.02
    if ch in " .,:;'\"|!iltf":
        return size * 0.34
    return size * 0.56


def _wrap(text: str, size: float, max_w: float):
    lines, cur, w = [], "", 0.0
    for ch in text:
        cw = _char_w(ch, size)
        if w + cw > max_w and cur:
            lines.append(cur)
            cur, w = "", 0.0
        cur += ch
        w += cw
    if cur:
        lines.append(cur)
    tidied = []
    for line in lines:
        if tidied and re.fullmatch(r"[\)\]）】,，.。;；:：]+", line.strip()):
            tidied[-1] = tidied[-1].rstrip() + line.strip()
        else:
            tidied.append(line)
    return tidied or [""]


def _truncate_width(text: str, size: float, max_w: float) -> str:
    text = str(text or "")
    if sum(_char_w(ch, size) for ch in text) <= max_w:
        return text
    limit = max(0.0, max_w)
    out, width = "", 0.0
    for ch in text:
        cw = _char_w(ch, size)
        if width + cw > limit:
            break
        out += ch
        width += cw
    return out.rstrip()


def _fit_lines(text: str, size: float, max_w: float, max_lines: int) -> list[str]:
    lines = _wrap(str(text or ""), size, max_w)
    if len(lines) <= max_lines:
        return lines
    return lines[:max_lines]


def _short_source_label(title: str, url: str = "") -> str:
    raw = re.sub(r"\s+", " ", str(title or "")).strip()
    raw = raw.split("：", 1)[0].split(":", 1)[0]
    raw = re.sub(r"\s*\|\s*.*$", "", raw)
    raw = re.sub(r"\s*-\s*(arXiv|IEEE|ACM|Springer|ResearchGate).*$", "", raw, flags=re.I)
    raw = raw.strip(" \"'[]()")
    if not raw and url:
        m = re.search(r"https?://(?:www\.)?([^/]+)", str(url))
        raw = m.group(1) if m else str(url)
    if not raw:
        return ""
    return _truncate_width(raw, 11.5, 220)


def _citation_map(run_dir: Path) -> dict[str, str]:
    path = run_dir / "citations.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    citations = data.get("citations") if isinstance(data, dict) else []
    out = {}
    for item in citations or []:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id") or "").strip()
        label = _short_source_label(str(item.get("title") or ""), str(item.get("url") or ""))
        if cid and label:
            out[cid] = label
    return out


def _format_citations(value, citation_labels: dict[str, str] | None = None) -> str:
    citation_labels = citation_labels or {}
    if isinstance(value, str):
        tokens = [x.strip() for x in re.split(r"[,，;；]\s*", value) if x.strip()]
    elif isinstance(value, list):
        tokens = [str(x).strip() for x in value if str(x).strip()]
    else:
        tokens = []
    labels = []
    seen = set()
    for token in tokens:
        if citation_labels.get(token):
            label = _citation_marker(token)
        elif str(token).startswith("sources/"):
            label = "[local]"
        else:
            label = token
        if label and label not in seen:
            labels.append(label)
            seen.add(label)
    return "".join(labels[:3])


def _format_citation_footnotes(value, citation_labels: dict[str, str] | None = None) -> str:
    citation_labels = citation_labels or {}
    if isinstance(value, str):
        tokens = [x.strip() for x in re.split(r"[,，;；]\s*", value) if x.strip()]
    elif isinstance(value, list):
        tokens = [str(x).strip() for x in value if str(x).strip()]
    else:
        tokens = []
    items = []
    seen = set()
    for token in tokens:
        marker = _citation_marker(token)
        label = citation_labels.get(token)
        if not label:
            continue
        text = f"{marker} {label}"
        if text not in seen:
            items.append(text)
            seen.add(text)
    return "；".join(items[:3])


def _slide_citation_footnotes(block: dict, visual: dict | None, citation_labels: dict[str, str] | None = None) -> str:
    visual = visual or {}
    return _format_citation_footnotes(
        block.get("footer_citations") or visual.get("citations") or block.get("citations"),
        citation_labels,
    )


def _citation_marker(token: str) -> str:
    m = re.fullmatch(r"S(\d+)", str(token or "").strip())
    return f"[{m.group(1)}]" if m else str(token or "").strip()


def _replace_citation_tokens(text: str, citation_labels: dict[str, str] | None = None) -> str:
    citation_labels = citation_labels or {}
    if not citation_labels:
        return str(text or "")

    def repl(match: re.Match) -> str:
        token = match.group(0)
        return _citation_marker(token) if citation_labels.get(token) else token

    return re.sub(r"\bS\d+\b", repl, str(text or ""))


def _clean_visible_text(text: str, citation_labels: dict[str, str] | None = None, *, allow_marker: bool = True) -> str:
    value = str(text or "").strip()
    value = re.sub(r"依据\s*S\d+(?:\s*[,，]\s*S\d+)*[，,]\s*", "", value)
    value = re.sub(r"来源\s*S\d+(?:\s*[,，]\s*S\d+)*[，,]\s*", "", value)
    value = _replace_citation_tokens(value, citation_labels)
    value = re.sub(r"\bS(\d+)\b", r"[\1]", value)
    if not allow_marker:
        value = re.sub(r"\[\d+\]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _hex(value: str, default: str) -> str:
    raw = str(value or "").strip()
    raw = raw[1:] if raw.startswith("#") else raw
    fallback = default if str(default).startswith("#") else f"#{default}"
    return f"#{raw.upper()}" if re.fullmatch(r"[0-9A-Fa-f]{6}", raw) else fallback


def _text_el(
    x,
    y,
    s,
    size,
    fill,
    *,
    anchor="start",
    weight="normal",
    font_family: str | None = None,
    text_length: float | None = None,
    length_adjust: str = "spacingAndGlyphs",
):
    wt = f' font-weight="{weight}"' if weight != "normal" else ""
    an = f' text-anchor="{anchor}"' if anchor != "start" else ""
    fit = ""
    if text_length is not None and text_length > 0:
        fit = f' textLength="{float(text_length):.1f}" lengthAdjust="{_esc(str(length_adjust))}"'
    ff = _esc(font_family or FONT_STACK)
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{ff}" '
        f'font-size="{size:.1f}" fill="{fill}"{wt}{an}{fit}>{_esc(s)}</text>'
    )


def _strip_lab_footer(inner: str) -> str:
    # DAI lab template footer contains a concrete speaker name. Treat it as a
    # placeholder and redraw it as editable project text during render.
    patterns = [
        r'<g\b[^>]*>\s*<rect\b[^>]*>\s*</rect>\s*<text\b[^>]*>\s*(?=[\s\S]*?Guohao)(?=[\s\S]*?Shanghai)(?=[\s\S]*?University)[\s\S]*?</text>\s*</g>',
        r'<g\b[^>]*data-name="[^"]*Slide Number Placeholder[^"]*"[^>]*>[\s\S]*?</g>',
        r'<g\b[^>]*>\s*<rect\b[^>]*>\s*</rect>\s*<text\b[^>]*>\s*<tspan[^>]*>Page</tspan>[\s\S]*?</text>\s*</g>',
    ]
    for pattern in patterns:
        inner = re.sub(pattern, "", inner, flags=re.DOTALL | re.IGNORECASE)
    return inner


def _strip_placeholder_groups(inner: str) -> str:
    inner = re.sub(
        r'<g\b(?=[^>]*data-ph-type="[^"]+")[^>]*>[\s\S]*?</g>',
        "",
        inner,
        flags=re.DOTALL | re.IGNORECASE,
    )
    inner = re.sub(
        r'<g\b(?=[^>]*(?:Placeholder|占位符|Content Placeholder|Title 1))[^>]*>[\s\S]*?</g>',
        "",
        inner,
        flags=re.DOTALL | re.IGNORECASE,
    )
    inner = re.sub(
        r'<g\b[^>]*>\s*<rect\b(?=[^>]*stroke-dasharray=)[^>]*/>\s*</g>',
        "",
        inner,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return inner


def _strip_tiny_image_refs(inner: str, layout_svg_path: Path, *, min_bytes: int = 2048) -> str:
    """Remove ``<image>`` tags whose referenced asset is smaller than ``min_bytes``.

    Source PPT decks routinely embed micro-PNGs (~200B transparent dots,
    color-corner markers, font placeholders). When we paste a source slide
    verbatim those references survive into the new deck and render as tiny
    blurry squares. They carry no information for the human reader.

    Only filters file-path refs (``../assets/foo.png``); data: URIs are left
    alone since they're harder to size cheaply.
    """
    asset_root = layout_svg_path.parent
    pattern = re.compile(r'<image\b[^>]*\b(?:xlink:href|href)="([^"]+)"[^>]*/?>(?:</image>)?', re.DOTALL)
    def _drop(m: re.Match) -> str:
        ref = m.group(1)
        if ref.startswith("data:"):
            return m.group(0)
        # Resolve relative path against the SVG's own dir.
        try:
            cand = (asset_root / ref).resolve()
            if cand.exists() and cand.is_file() and cand.stat().st_size < min_bytes:
                return ""
        except Exception:
            pass
        return m.group(0)
    return pattern.sub(_drop, inner)


def _normalize_svg_viewbox(svg_text: str, target_width: float = 1280.0, target_height: float = 720.0) -> str:
    """Rewrite the outer <svg> attributes so source SVGs of any size render
    centered inside the target canvas. Preferred mode is **viewBox-only**:
    re-set width/height/viewBox to the target without wrapping inner content
    in an extra ``<g transform>`` (that wrapper sometimes conflicts with the
    source's own coordinate system / nested <svg>).

    Falls back to no-op when the source viewBox already matches target.
    """
    m = re.search(r'<svg\b([^>]*)>', svg_text)
    if not m:
        return svg_text
    attrs_text = m.group(1)
    vb_match = re.search(r'viewBox\s*=\s*"([0-9.\s-]+)"', attrs_text)
    src_w = src_h = 0.0
    if vb_match:
        try:
            parts = [float(x) for x in vb_match.group(1).split()]
            if len(parts) == 4:
                src_w, src_h = parts[2], parts[3]
        except Exception:
            pass
    if src_w <= 0 or src_h <= 0:
        wm = re.search(r'width\s*=\s*"([0-9.]+)"', attrs_text)
        hm = re.search(r'height\s*=\s*"([0-9.]+)"', attrs_text)
        src_w = float(wm.group(1)) if wm else 0.0
        src_h = float(hm.group(1)) if hm else 0.0
    if src_w <= 0 or src_h <= 0:
        return svg_text  # can't determine, leave alone
    if abs(src_w - target_width) < 1 and abs(src_h - target_height) < 1:
        return svg_text  # already at target
    # viewBox-only normalization: keep inner content untouched, just tell the
    # outer svg how to map to the target canvas with preserveAspectRatio meet.
    new_attrs = attrs_text
    new_attrs = re.sub(r'\bwidth\s*=\s*"[^"]*"', '', new_attrs)
    new_attrs = re.sub(r'\bheight\s*=\s*"[^"]*"', '', new_attrs)
    if vb_match:
        new_attrs = re.sub(r'\bviewBox\s*=\s*"[^"]*"', f'viewBox="0 0 {src_w:.0f} {src_h:.0f}"', new_attrs)
    else:
        new_attrs = new_attrs.rstrip() + f' viewBox="0 0 {src_w:.0f} {src_h:.0f}"'
    new_attrs = re.sub(r'\bpreserveAspectRatio\s*=\s*"[^"]*"', '', new_attrs)
    new_attrs = new_attrs.rstrip() + f' width="{int(target_width)}" height="{int(target_height)}" preserveAspectRatio="xMidYMid meet"'
    new_attrs = re.sub(r'\s+', ' ', new_attrs).strip()
    new_open = f'<svg {new_attrs}>'
    return svg_text[:m.start()] + new_open + svg_text[m.end():]


def _gap_warning_overlay(reuse_fit: str, gap_summary: str | None,
                          canvas_w: float = 1280, canvas_h: float = 720) -> str:
    """Return SVG snippet placed inside the outer <svg> as a top-strip warning
    when reuse_fit is partial/weak. Empty string for direct/none.
    """
    if reuse_fit not in ("partial", "weak"):
        return ""
    color = "#FFA500" if reuse_fit == "partial" else "#D32F2F"  # orange / red
    label = "⚠ 部分适配, 后续需改写" if reuse_fit == "partial" else "⚠ 弱相关, 仅作风格参考"
    if gap_summary:
        label = f"{label} — {gap_summary[:60]}"
    band_h = max(28, canvas_h * 0.05)
    return (
        f'<g class="gap-warning-overlay">'
        f'<rect x="0" y="0" width="{canvas_w}" height="{band_h}" '
        f'fill="{color}" fill-opacity="0.92"/>'
        f'<text x="{canvas_w/2}" y="{band_h*0.66}" '
        f'font-family="Microsoft YaHei,微软雅黑,Noto Sans CJK SC,Arial,sans-serif" '
        f'font-size="{int(band_h*0.55)}" font-weight="bold" fill="#FFFFFF" '
        f'text-anchor="middle">{html.escape(label)}</text>'
        f'</g>'
    )


def _gap_page_card_svg(target_title: str, target_claim: str, plan_note: str,
                        key_points: list, evidence_needed: list,
                        gap_types: list, next_action: str | None,
                        canvas_w: float = 1280, canvas_h: float = 720) -> str:
    """Return a complete SVG document for a gap-page card layout.

    Yellow header bar + 4 content blocks (claim / 缺什么 / 建议来源 / next_action).
    """
    fs_title = 36
    fs_claim = 22
    fs_label = 18
    fs_body = 16
    margin = 80
    inner_w = canvas_w - margin * 2

    def _fmt_lines(items, max_lines=3, max_chars=100):
        if not items:
            return ["—"]
        out = []
        for it in items[:max_lines]:
            t = str(it).strip()
            if not t:
                continue
            out.append(t[:max_chars])
        return out or ["—"]

    title = (target_title or "本页待补充").strip()
    claim = (target_claim or "").strip()

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(canvas_w)}" height="{int(canvas_h)}" viewBox="0 0 {int(canvas_w)} {int(canvas_h)}">']
    # White bg
    parts.append(f'<rect x="0" y="0" width="{int(canvas_w)}" height="{int(canvas_h)}" fill="#FFFFFF"/>')
    # Yellow header
    parts.append(f'<rect x="0" y="0" width="{int(canvas_w)}" height="60" fill="#FFC107"/>')
    parts.append(f'<text x="{int(canvas_w/2)}" y="42" font-family="Microsoft YaHei,微软雅黑,Arial,sans-serif" font-size="22" font-weight="bold" fill="#000000" text-anchor="middle">⚠ Gap Page · 本页暂无可直接复用 slide</text>')
    # Title
    parts.append(f'<text x="{margin}" y="130" font-family="Microsoft YaHei,微软雅黑,Arial,sans-serif" font-size="{fs_title}" font-weight="bold" fill="#0A2E5D">{html.escape(title)}</text>')
    if claim:
        parts.append(f'<text x="{margin}" y="170" font-family="Microsoft YaHei,微软雅黑,Arial,sans-serif" font-size="{fs_claim}" fill="#333333">{html.escape(claim[:80])}</text>')
    # Four content blocks (2x2 grid)
    block_y_top = 220
    block_h = (canvas_h - block_y_top - margin) / 2
    block_w = inner_w / 2 - 20
    blocks = [
        ("本页核心要点", _fmt_lines(key_points, 4, 100)),
        ("缺什么", _fmt_lines(evidence_needed, 4, 100) if evidence_needed else _fmt_lines([plan_note], 1, 200)),
        ("Gap 类型", [", ".join(gap_types) if gap_types else "—"]),
        ("Next action", [next_action or "text_rewrite"]),
    ]
    for i, (label, lines) in enumerate(blocks):
        col = i % 2
        row = i // 2
        bx = margin + col * (block_w + 40)
        by = block_y_top + row * (block_h + 20)
        parts.append(f'<rect x="{bx}" y="{by}" width="{block_w}" height="{block_h}" fill="#F8F9FA" stroke="#DEE2E6" stroke-width="1"/>')
        parts.append(f'<text x="{bx+16}" y="{by+30}" font-family="Microsoft YaHei,微软雅黑,Arial,sans-serif" font-size="{fs_label}" font-weight="bold" fill="#0A2E5D">{html.escape(label)}</text>')
        for j, ln in enumerate(lines):
            ly = by + 56 + j * (fs_body + 8)
            if ly > by + block_h - 10:
                break
            parts.append(f'<text x="{bx+16}" y="{ly}" font-family="Microsoft YaHei,微软雅黑,Arial,sans-serif" font-size="{fs_body}" fill="#333333">• {html.escape(ln)}</text>')
    parts.append('</svg>')
    return "".join(parts)



def _layout_skeleton_inner(layout_svg_path: Path, *, strip_slide_content_images: bool = False, strip_all_images: bool = False, strip_lab_footer: bool = False, strip_placeholders: bool = False, preserve_full_slide: bool = False, strip_tiny_images: bool = True) -> str:
    """Return the layout SVG's inner markup (defs + furniture) with placeholder TEXT removed.

    When ``preserve_full_slide`` is True the inner markup is returned mostly
    verbatim — text, images and placeholder groups are all kept — EXCEPT
    that micro-asset image refs (< 2KB on disk) are dropped to avoid the
    blurry-thumbnail look that comes from pasting source decks that
    embedded tiny placeholder PNGs. Pass ``strip_tiny_images=False`` to
    disable the filter.
    """
    try:
        s = layout_svg_path.read_text(encoding="utf-8")
    except Exception:
        return ""
    m = re.search(r"<svg\b[^>]*>", s)
    if not m:
        return ""
    inner = s[m.end(): s.rfind("</svg>")]
    if preserve_full_slide:
        if strip_tiny_images:
            inner = _strip_tiny_image_refs(inner, layout_svg_path)
        return inner
    inner = re.sub(r"<text\b[^>]*?/>", "", inner)
    inner = re.sub(r"<text\b.*?</text>", "", inner, flags=re.DOTALL)
    if strip_slide_content_images:
        # Flat source-slide SVGs include example content images. Those are useful
        # for slot inference, but should not be pasted into new decks as template
        # furniture. Keep master/layout images; strip slide-level picture groups.
        inner = re.sub(
            r'<g\b(?=[^>]*id="shape-[^"]+")[^>]*>\s*<svg\b[^>]*>.*?</svg>\s*</g>',
            "",
            inner,
            flags=re.DOTALL,
        )
    if strip_all_images:
        inner = re.sub(r"<image\b[^>]*/>", "", inner, flags=re.DOTALL)
        inner = re.sub(r"<image\b.*?</image>", "", inner, flags=re.DOTALL)
    if strip_lab_footer:
        inner = _strip_lab_footer(inner)
    if strip_placeholders:
        inner = _strip_placeholder_groups(inner)
    return inner


def _page_type(layout_type: str, idx: int, total: int) -> str:
    lt = (layout_type or "").lower()
    if lt in ("title",) or idx == 1:
        return "cover"
    if lt == "ending" or idx == total:
        return "ending"
    if lt == "closing":
        return "content"
    if lt in ("section", "chapter"):
        return "chapter"
    return "content"


def _visual_layouts(run_dir: Path):
    vp = run_dir / "visual-plan.json"
    out = {}
    if vp.exists():
        try:
            data = json.load(open(vp, encoding="utf-8"))
            for s in data.get("slides", []):
                out[int(s.get("slide_index", 0))] = str(s.get("layout_type", ""))
        except Exception:
            pass
    return out


def _visual_plan(run_dir: Path):
    vp = run_dir / "visual-plan.json"
    out = {}
    if vp.exists():
        try:
            data = json.load(open(vp, encoding="utf-8"))
            for s in data.get("slides", []):
                idx = int(s.get("slide_index", 0))
                if idx > 0:
                    out[idx] = {
                        "layout_type": str(s.get("layout_type", "")),
                        "visual_type": str(s.get("visual_type", "")),
                        "assets": s.get("assets", []) or [],
                        "template_svg": str(s.get("template_svg") or s.get("template_layout_svg") or ""),
                        "adaptation_policy": s.get("adaptation_policy") or {},
                        "template_source": s.get("template_source") or {},
                        "content_regions": s.get("content_regions") or {},
                        "component_id": str(s.get("component_id") or ""),
                        "component_slots": s.get("component_slots") or {},
                        "visual_spec": s.get("visual_spec") or {},
                        "layout_blueprint": s.get("layout_blueprint") or {},
                        "layout_variation": s.get("layout_variation") or "",
                        "slide_composition": s.get("slide_composition") or {},
                        "content_blocks": s.get("content_blocks") or [],
                        "asset_request": s.get("asset_request") or {},
                        "semantic_component_id": s.get("semantic_component_id") or "",
                        "layout_family": s.get("layout_family") or "",
                        "copy_limits": s.get("copy_limits") or {},
                        "quality_requirements": s.get("quality_requirements") or {},
                        "citations": s.get("citations") or [],
                        "reuse_mode": str(s.get("reuse_mode") or ""),
                        "source_slide_svg_ref": str(s.get("source_slide_svg_ref") or ""),
                        "source_asset_refs": s.get("source_asset_refs") or [],
                        # B-style fields the renderer needs for warning bands /
                        # gap pages.
                        "draft_action_kind": str(s.get("draft_action_kind") or ""),
                        "reuse_fit": str(s.get("reuse_fit") or ""),
                        "gap_types": s.get("gap_types") or [],
                        "next_action": str(s.get("next_action") or ""),
                        "fit_score": s.get("fit_score"),
                        "target_title": str(s.get("target_title") or ""),
                        "target_claim": str(s.get("target_claim") or ""),
                        "key_points": s.get("key_points") or [],
                        "evidence_needed": s.get("evidence_needed") or [],
                        "plan_note": str(s.get("plan_note") or ""),
                        "transition_note": str(s.get("transition_note") or ""),
                        "section_coherence": str(s.get("section_coherence") or ""),
                    }
        except Exception:
            pass
    return out


def _stage_visual_assets(run_dir: Path, build: Path, visuals: dict[int, dict]) -> None:
    target_dir = build / "assets" / "bound"
    target_dir.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    for slide_idx, visual in visuals.items():
        assets = visual.get("assets") if isinstance(visual.get("assets"), list) else []
        for asset_idx, asset in enumerate(assets, start=1):
            if isinstance(asset, str):
                src_rel = asset
                asset_obj = None
            elif isinstance(asset, dict):
                src_rel = str(asset.get("local_path") or asset.get("path") or "")
                asset_obj = asset
            else:
                continue
            if not src_rel:
                continue
            src = (run_dir / src_rel).resolve()
            try:
                src.relative_to(run_dir.resolve())
            except ValueError:
                continue
            if not src.exists() or not src.is_file():
                continue
            suffix = src.suffix.lower() or ".png"
            stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", src.stem)[:48] or "asset"
            name = f"slide_{slide_idx:02d}_{asset_idx:02d}_{stem}{suffix}"
            while name in used:
                name = f"slide_{slide_idx:02d}_{asset_idx:02d}_{len(used)}_{stem}{suffix}"
            used.add(name)
            shutil.copy2(src, target_dir / name)
            staged_rel = f"assets/bound/{name}"
            if asset_obj is not None:
                asset_obj["local_path"] = staged_rel
                asset_obj["path"] = staged_rel
                asset_obj["staged_from"] = src_rel
            else:
                assets[asset_idx - 1] = staged_rel


def _resolve_template_svg(import_dir: Path | None, ref: str | None, run_dir: Path | None = None) -> Path | None:
    """Resolve a template SVG reference.

    Order of resolution:
      1. project-root-relative paths (``data/resources_library/template/...``,
         ``decomposed/...``, absolute paths) are tried against ``run_dir``
         AND against the ppt-agent project root so a slide can reuse a SVG
         from the offline library (which lives at ``<ppt-agent>/data/...``,
         NOT under the per-project run_dir).
      2. paths starting with ``svg/``, ``svg-flat/`` or ``assets/`` resolve
         against ``import_dir`` (the lab template's import dir).
      3. otherwise tries ``import_dir/svg/<ref>`` and ``import_dir/<ref>``.
    """
    if not ref:
        return None
    raw = str(ref).strip()
    if not raw:
        return None
    raw = raw.lstrip("/")
    candidates: list[Path] = []
    if (raw.startswith("data/")
            or raw.startswith("decomposed/")
            or raw.startswith("templates/")
            or "template_library/imports/" in raw):
        if run_dir is not None:
            candidates.append((run_dir / raw))
        # Library paths (``data/resources_library/template/...``) are anchored at the
        # ppt-agent project root, NOT at the per-project run_dir. Try both.
        # ROOT = <ppt-agent>/ppt_agent_app/.. (set in models.py), but to keep
        # this renderer self-contained we walk up from this file: this file is
        # at <ppt-agent>/scripts/lib/svg_skeleton_render.py, so two parents up.
        ppt_root = Path(__file__).resolve().parents[2]
        candidates.append((ppt_root / raw))
    if import_dir is not None:
        if raw.startswith(("svg/", "svg-flat/", "assets/")):
            candidates.append(import_dir / raw)
        else:
            candidates.extend([import_dir / "svg" / raw, import_dir / raw])
    for path in candidates:
        if path.exists():
            return path
    return None


def _lab_reuse_skeleton(profile: dict, page_type: str) -> tuple[str, bool]:
    contract = profile.get("lab_template_contract") if isinstance(profile.get("lab_template_contract"), dict) else {}
    if not contract:
        return "", False
    key = "cover_reuse" if page_type == "cover" else "ending_reuse" if page_type == "ending" else ""
    reuse = contract.get(key) if key and isinstance(contract.get(key), dict) else {}
    return str(reuse.get("template_svg") or ""), bool(reuse.get("copy_assets"))


def _lab_reuse_allows_assets(profile: dict, page_type: str, ref: str | None) -> bool:
    if page_type not in {"cover", "ending"} or not ref:
        return False
    lab_ref, copy_assets = _lab_reuse_skeleton(profile, page_type)
    return copy_assets and str(ref).strip().lstrip("/") == lab_ref


def _rect(x, y, w, h, fill, stroke="none", sw=1, rx=0, opacity=None):
    op = f' opacity="{opacity}"' if opacity is not None else ""
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
        f'rx="{rx:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{op}/>'
    )


def _line(x1, y1, x2, y2, stroke, sw=2, marker=False):
    mk = ' marker-end="url(#arrow)"' if marker else ""
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" stroke-width="{sw}"{mk}/>'


def _circle(cx, cy, r, fill, stroke="none", sw=1, opacity=None):
    op = f' opacity="{opacity}"' if opacity is not None else ""
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{op}/>'


def _text_lines(parts, x, y, text, size, fill, max_w, *, weight="normal", anchor="start", max_lines=3, line_gap=1.22, font_family: str | None = None):
    for ln in _fit_lines(_clean_visible_text(str(text or "")), size, max_w, max_lines):
        parts.append(_text_el(x, y, ln, size, fill, weight=weight, anchor=anchor, font_family=font_family))
        y += size * line_gap
    return y


def _lab_contract(profile: dict | None) -> dict:
    if profile and isinstance(profile.get("lab_template_contract"), dict):
        return profile["lab_template_contract"]
    return {}


def _font_family(value, default: str = FONT_STACK) -> str:
    raw = str(value or "").strip()
    return raw or default


def _is_placeholder_value(value: str | None) -> bool:
    raw = re.sub(r"\s+", "", str(value or "")).strip().lower()
    return raw in {"", "x", "xx", "xxx", "xxxx", "todo", "tbd", "姓名", "汇报人", "presenter"} or raw.startswith("xxx@")


def _speaker_name(contract: dict) -> str:
    env_value = os.environ.get("PPT_SPEAKER_NAME")
    if env_value and not _is_placeholder_value(env_value):
        return env_value
    configured = str(contract.get("speaker_name") or "")
    if not _is_placeholder_value(configured):
        return configured
    return "DAI Lab"


def _speaker_email(contract: dict) -> str:
    env_value = os.environ.get("PPT_SPEAKER_EMAIL")
    if env_value and not _is_placeholder_value(env_value):
        return env_value
    configured = str(contract.get("speaker_email") or "")
    if not _is_placeholder_value(configured):
        return configured
    return ""


def _fit_size_for_text(text: str, size: float, max_w: float, max_lines: int, min_size: float) -> tuple[float, list[str]]:
    size = float(size)
    min_size = float(min_size)
    while size > min_size:
        lines = _wrap(str(text or ""), size, max_w)
        if len(lines) <= max_lines:
            return size, lines
        size -= 1.0
    return min_size, _fit_lines(str(text or ""), min_size, max_w, max_lines)


def _draw_text_box(parts, text, region: dict, style: dict, *, group_id: str, max_lines: int = 2):
    x = float(region.get("x", 60.0))
    y = float(region.get("y", 40.0))
    w = float(region.get("width", 840.0))
    h = float(region.get("height", 90.0))
    anchor = str(style.get("anchor") or "start")
    size, lines = _fit_size_for_text(
        str(text or ""),
        float(style.get("font_size", 34.0)),
        w,
        max_lines,
        float(style.get("min_font_size", 24.0)),
    )
    line_gap = 1.16
    total_h = size + max(0, len(lines) - 1) * size * line_gap
    baseline_y = y + max(size, (h - total_h) / 2.0 + size)
    text_x = x + w / 2.0 if anchor == "middle" else (x + w if anchor == "end" else x)
    parts.append(f'<g id="{_esc(group_id)}">')
    for line in lines:
        parts.append(_text_el(
            text_x,
            baseline_y,
            line,
            size,
            _hex(str(style.get("fill") or ""), "#17324D"),
            anchor=anchor,
            weight=str(style.get("weight") or "normal"),
            font_family=_font_family(style.get("font_family")),
        ))
        baseline_y += size * line_gap
    parts.append("</g>")


def _draw_lab_slide_title(parts, title: str, profile: dict | None, page_kind: str, fallback_region: dict, fallback_color: str):
    contract = _lab_contract(profile)
    styles = contract.get("title_style") if isinstance(contract.get("title_style"), dict) else {}
    style = styles.get(page_kind) if isinstance(styles.get(page_kind), dict) else {}
    if page_kind == "cover":
        style = {
            **style,
            "font_family": style.get("font_family") or "Calibri",
            "font_size": float(style.get("font_size") or 25.0),
            "min_font_size": min(float(style.get("min_font_size") or 20.0), 20.0),
        }
    if page_kind == "content" and style:
        title_rule = contract.get("title_rule") if isinstance(contract.get("title_rule"), dict) else {}
        rule_y = float(title_rule.get("line_y", 64.71)) if title_rule else 64.71
        rule_w = float(title_rule.get("line_width", 7.667)) if title_rule else 7.667
        size = min(float(style.get("font_size", 42.67)), 38.0)
        max_w = 840.0
        text = str(title or "")
        natural_w = sum(_char_w(ch, size) for ch in text)
        text_length = max_w if natural_w > max_w else None
        title_y = min(float(style.get("y", 51.26)), rule_y - rule_w - 9.0)
        parts.append('<g id="content-title">')
        parts.append(_text_el(
            float(style.get("x", 480.0)),
            title_y,
            text,
            size,
            _hex(str(style.get("fill") or ""), fallback_color),
            anchor=str(style.get("anchor") or "middle"),
            weight=str(style.get("weight") or "bold"),
            font_family=_font_family(style.get("font_family")),
            text_length=text_length,
        ))
        parts.append("</g>")
        return
    if style and isinstance(style.get("region"), dict):
        _draw_text_box(parts, title, style["region"], style, group_id=f"{page_kind}-title", max_lines=2)
        return
    size = 40.0 if page_kind in {"cover", "ending"} else 34.0
    y = float(fallback_region.get("y", 48.0)) + size
    parts.append('<g id="content-title">')
    for ln in _wrap(str(title or "Slide"), size, float(fallback_region.get("width", 840.0))):
        parts.append(_text_el(float(fallback_region.get("x", 60.0)), y, ln, size, fallback_color, weight="bold"))
        y += size * 1.22
    parts.append("</g>")


def _draw_assertion_box(parts, claim: str, profile: dict | None, canvas, *, y: float) -> float:
    claim = str(claim or "").strip()
    if not claim:
        return y
    contract = _lab_contract(profile)
    title_rule = contract.get("title_rule") if isinstance(contract.get("title_rule"), dict) else {}
    blue = _hex(str(title_rule.get("line_color") or ""), "#074BA2")
    body_style = _body_style(profile)
    cw = float(canvas.get("width_px", 1280))
    x = max(54.0, cw * 0.065)
    w = cw - x * 2
    h = 52.0
    parts.append('<g id="assertion-blue-box">')
    parts.append(_rect(x, y, w, h, "none", blue, sw=2.2, rx=0))
    lines = _wrap(claim, 19.0, w - 34)[:2]
    yy = y + 23.0 if len(lines) == 1 else y + 18.0
    for line in lines:
        parts.append(_text_el(
            x + 17.0,
            yy,
            line,
            18.5,
            blue,
            weight="bold",
            font_family=_font_family(body_style.get("font_family")),
        ))
        yy += 21.0
    parts.append("</g>")
    return y + h + 18.0


def _draw_lab_cover_metadata(parts, profile: dict | None):
    contract = _lab_contract(profile)
    meta = contract.get("cover_metadata") if isinstance(contract.get("cover_metadata"), dict) else {}
    if not meta:
        return
    speaker_name = _speaker_name(contract)
    affiliation = os.environ.get("PPT_SPEAKER_AFFILIATION") or str(contract.get("speaker_affiliation") or "Shanghai Jiao Tong University")
    date_value = _lab_date_value(contract, str(meta.get("presentation_date_format") or "%Y.%m.%d"))
    x = float(meta.get("x", 480.0))
    anchor = str(meta.get("anchor") or "middle")
    family = _font_family(meta.get("font_family"))
    size = float(meta.get("font_size", 24.0))
    parts.append('<g id="lab-cover-metadata">')
    parts.append(_text_el(x, float(meta.get("speaker_y", 318.0)), speaker_name, size, _hex(str(meta.get("fill") or ""), "#000000"), anchor=anchor, font_family=family))
    parts.append(_text_el(x, float(meta.get("affiliation_y", 356.0)), affiliation, size, _hex(str(meta.get("affiliation_fill") or ""), "#262626"), anchor=anchor, font_family=family))
    parts.append(_text_el(x, float(meta.get("date_y", 394.0)), date_value, size, _hex(str(meta.get("date_fill") or ""), "#7F7F7F"), anchor=anchor, font_family=family))
    parts.append("</g>")


def _lab_date_value(contract: dict, fmt: str = "%Y.%m.%d") -> str:
    raw_date = os.environ.get("PPT_PRESENTATION_DATE")
    if raw_date:
        return raw_date
    return datetime.datetime.now().strftime(fmt)


def _draw_lab_ending_content(parts, profile: dict | None):
    contract = _lab_contract(profile)
    ending = contract.get("ending_content") if isinstance(contract.get("ending_content"), dict) else {}
    if not ending:
        return False
    speaker_name = _speaker_name(contract)
    speaker_email = _speaker_email(contract)
    date_value = _lab_date_value(contract, "%Y.%m.%d")
    title_style = {
        "region": ending.get("title_region") or {"x": 120.0, "y": 142.0, "width": 720.0, "height": 88.0},
        "anchor": ending.get("anchor") or "middle",
        "font_family": ending.get("font_family") or "Arial, sans-serif",
        "font_size": ending.get("title_font_size") or 42.67,
        "min_font_size": 34,
        "fill": ending.get("title_fill") or "#000000",
        "weight": "bold",
    }
    _draw_text_box(parts, str(ending.get("title") or "Thanks"), title_style["region"], title_style, group_id="ending-title", max_lines=1)
    x = float(ending.get("x", 480.0))
    anchor = str(ending.get("anchor") or "middle")
    family = _font_family(ending.get("font_family"), "Arial, sans-serif")
    size = float(ending.get("metadata_font_size", 24.0))
    parts.append('<g id="lab-ending-metadata">')
    parts.append(_text_el(x, float(ending.get("name_y", 306.0)), speaker_name, size, _hex(str(ending.get("metadata_fill") or ""), "#262626"), anchor=anchor, font_family=family))
    parts.append(_text_el(x, float(ending.get("date_y", 344.0)), date_value, size, _hex(str(ending.get("date_fill") or ""), "#7F7F7F"), anchor=anchor, font_family=family))
    if speaker_email:
        parts.append(_text_el(x, float(ending.get("email_y", 382.0)), speaker_email, size, _hex(str(ending.get("email_fill") or ""), "#262626"), anchor=anchor, font_family=family))
    parts.append("</g>")
    return True


def _draw_ending_takeaway_content(parts, block, visual, palette, canvas, profile: dict | None) -> bool:
    """Ending page is owned by the base template contract."""
    return _draw_lab_ending_content(parts, profile)


def _visual_region(canvas, *, mode: str = "side", fill_target: float | None = None) -> dict[str, float]:
    override = canvas.get("_visual_region_override") if isinstance(canvas, dict) else None
    if isinstance(override, dict):
        try:
            return {
                "x": float(override.get("x")),
                "y": float(override.get("y")),
                "width": float(override.get("width")),
                "height": float(override.get("height")),
            }
        except (TypeError, ValueError):
            pass
    cw = float(canvas.get("width_px", 1280))
    ch = float(canvas.get("height_px", 720))
    margin_x = max(52.0, cw * 0.07)
    try:
        ft = float(fill_target) if fill_target is not None else 0.68
    except (TypeError, ValueError):
        ft = 0.68
    ft = max(0.45, min(0.88, ft))
    top = max(132.0, ch * (0.36 - 0.10 * ft))
    bottom = max(34.0, ch * 0.075)
    if mode == "table":
        y = max(150.0, ch * (0.48 - 0.18 * ft))
        return {
            "x": margin_x,
            "y": y,
            "width": max(360.0, cw - margin_x * 2),
            "height": max(210.0, ch - y - bottom),
        }
    left_text_w = min(390.0, max(240.0, cw * (0.48 - 0.16 * ft)))
    gap = max(28.0, cw * 0.04)
    x = margin_x + left_text_w + gap
    return {
        "x": x,
        "y": top,
        "width": max(300.0, cw - x - margin_x),
        "height": max(260.0, ch - top - bottom),
    }


def _offset_visual_start(visual: dict | None, y: float) -> dict:
    visual = dict(visual or {})
    visual["_content_start_y"] = y
    return visual


def _body_region_for_visual(body_region: dict, canvas, *, visual_kind: str, table_like: bool) -> dict:
    br = dict(body_region)
    if not visual_kind:
        return br
    cw = float(canvas.get("width_px", 1280))
    if table_like:
        br["height"] = min(float(br.get("height", 120) or 120), max(58.0, cw * 0.095))
        br["width"] = min(float(br.get("width", cw - 120) or cw - 120), cw - 120)
        return br
    vr = _visual_region(canvas)
    max_body_w = max(280.0, vr["x"] - float(br.get("x", 60)) - max(24.0, cw * 0.025))
    br["width"] = min(float(br.get("width", max_body_w) or max_body_w), max_body_w)
    br["height"] = min(float(br.get("height", 220) or 220), max(190.0, float(canvas.get("height_px", 720)) * 0.48))
    return br


def _fill_target(visual: dict | None) -> float:
    visual = visual or {}
    q = visual.get("quality_requirements") if isinstance(visual.get("quality_requirements"), dict) else {}
    raw = q.get("content_fill_target", visual.get("content_fill_target", 0.68))
    try:
        return max(0.45, min(0.88, float(raw)))
    except (TypeError, ValueError):
        return 0.68


def _nodes(block):
    paras = [p for p in (block.get("paragraphs") or []) if str(p).strip()]
    if not paras and block.get("body"):
        paras = [block["body"]]
    visual = block.get("_visual_plan") if isinstance(block.get("_visual_plan"), dict) else {}
    for cblock in visual.get("content_blocks") or []:
        if not isinstance(cblock, dict):
            continue
        heading = str(cblock.get("heading") or "").strip()
        if heading:
            paras.append(heading)
        body = cblock.get("body") or []
        if isinstance(body, str):
            body = [body]
        paras.extend(str(item).strip() for item in body if str(item).strip())
    for key in ("left_box", "right_box"):
        box = block.get(key) if isinstance(block.get(key), dict) else {}
        heading = str(box.get("heading") or "").strip()
        if heading:
            paras.append(heading)
        body = box.get("body") or []
        if isinstance(body, str):
            body = [body]
        paras.extend(str(item).strip() for item in body if str(item).strip())
    paras.extend(str(item).strip() for item in (block.get("bullets") or []) if str(item).strip())
    seen = set()
    out = []
    for item in paras:
        item = _clean_visible_text(item)
        key = re.sub(r"\s+", "", item)
        if key and key not in seen:
            out.append(item)
            seen.add(key)
    return out[:8]


def _box_nodes(block, *, include_headings: bool = False) -> list[str]:
    out = []
    for key in ("left_box", "right_box"):
        box = block.get(key) if isinstance(block.get(key), dict) else {}
        heading = str(box.get("heading") or "").strip()
        if include_headings and heading:
            out.append(heading)
        body = box.get("body") or []
        if isinstance(body, str):
            body = [body]
        out.extend(str(item).strip() for item in body if str(item).strip())
    seen = set()
    deduped = []
    for item in out:
        item = _clean_visible_text(item)
        key = re.sub(r"\s+", "", item)
        if key and key not in seen:
            deduped.append(item)
            seen.add(key)
    return deduped


def _table_from_boxes(block, layout: str = ""):
    left = block.get("left_box") if isinstance(block.get("left_box"), dict) else {}
    right = block.get("right_box") if isinstance(block.get("right_box"), dict) else {}
    left_body = left.get("body") or []
    right_body = right.get("body") or []
    if isinstance(left_body, str):
        left_body = [left_body]
    if isinstance(right_body, str):
        right_body = [right_body]
    title = str(block.get("title") or "")
    layout = str(layout or "").lower()
    if "risk" in layout or "风险" in title:
        risks = [str(x) for x in left_body + right_body][:4]
        defaults = ["量化精度风险", "算子适配风险", "I/O栈开销风险", "封装供应链风险"]
        mitigations = ["回归测试/混合精度", "roofline/trace分类", "bypass/异步预取/批量搬运", "软件优先，硬件后置"]
        rows = [["风险", "边界条件", "缓解动作"]]
        for i in range(4):
            rows.append([defaults[i], risks[i] if i < len(risks) else "需结合负载实测确认", mitigations[i]])
        return rows
    if "comparison" in layout or "matrix" in layout or "对比" in title or "选型" in title:
        rows = [["维度", str(left.get("heading") or "方案A"), str(right.get("heading") or "方案B")]]
        for i in range(max(len(left_body), len(right_body), 3)):
            rows.append([f"要点{i + 1}", str(left_body[i]) if i < len(left_body) else "", str(right_body[i]) if i < len(right_body) else ""])
        return rows[:5]
    if left_body or right_body:
        rows = [["类别", "关键信息"]]
        for heading, body in [(left.get("heading") or "要点A", left_body), (right.get("heading") or "要点B", right_body)]:
            for item in body[:3]:
                rows.append([str(heading), str(item)])
        return rows[:6]
    return []


def _defs(accent):
    return (
        "<defs>"
        f'<marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">'
        f'<path d="M0,0 L0,6 L9,3 z" fill="{accent}"/></marker>'
        "</defs>"
    )


def _draw_image_panel(parts, assets, palette, canvas):
    primary, accent, neutral, text_c = palette["primary"], palette["accent"], palette["neutral"], palette["text"]
    r = _visual_region(canvas)
    x, y, w, h = r["x"], r["y"], r["width"], r["height"]
    parts.append('<g id="visual-image-panel">')
    parts.append(_rect(x, y, w, h, neutral, "none", rx=12))
    if assets:
        href = "../" + str(assets[0]).lstrip("/")
        parts.append(
            f'<image x="{x + 18:.1f}" y="{y + 18:.1f}" width="{w - 36:.1f}" height="{h - 36:.1f}" '
            f'preserveAspectRatio="xMidYMid slice" href="{_esc(href)}" xlink:href="{_esc(href)}"/>'
        )
    parts.append("</g>")


def _draw_evidence_image_composition(parts, block, visual, palette, canvas) -> bool:
    assets = _allowed_visual_assets(visual)
    blocks = [b for b in visual.get("content_blocks") or [] if isinstance(b, dict) and (b.get("heading") or b.get("body"))]
    if not assets or not blocks:
        return False
    primary, accent, neutral, text_c = palette["primary"], palette["accent"], palette["neutral"], palette["text"]
    cw = float(canvas.get("width_px", 1280))
    ch = float(canvas.get("height_px", 720))
    top = float(visual.get("_content_start_y") or 136.0)
    footer_guard = max(54.0, ch * 0.095)
    x = max(58.0, cw * 0.065)
    w = cw - x * 2.0
    h = max(250.0, ch - top - footer_guard)
    variation = str(visual.get("layout_variation") or "").lower()
    image_first = "full-bleed" in variation or "large-visual" in variation or w < 900
    image_w = w * (0.62 if image_first else 0.56)
    panel_gap = 28.0
    panel_x = x + image_w + panel_gap
    panel_w = w - image_w - panel_gap
    if panel_w < 250:
        image_w = w * 0.55
        panel_x = x + image_w + panel_gap
        panel_w = w - image_w - panel_gap
    parts.append('<g id="blueprint-composition"><g id="content-blocks-panel"><g id="evidence-image-composition">')
    image_canvas = dict(canvas)
    image_canvas["_visual_region_override"] = {
        "x": x,
        "y": top + 8.0,
        "width": image_w,
        "height": h - 30.0,
    }
    _draw_image_panel(parts, assets, palette, image_canvas)
    caption = ""
    first_asset = (visual.get("assets") or [{}])[0]
    if isinstance(first_asset, dict):
        caption = str(first_asset.get("caption") or first_asset.get("source_deck") or "")
    if caption:
        _text_lines(parts, x + 12.0, top + h - 7.0, _clean_visible_text(caption), 10.5, "#666666", image_w - 24.0, max_lines=1)
    callout_h = min(82.0, max(62.0, (h - 34.0) / max(3, min(4, len(blocks)))))
    gap = max(10.0, (h - callout_h * min(4, len(blocks))) / max(1, min(4, len(blocks)) - 1))
    for i, cblock in enumerate(blocks[:4]):
        cy = top + 8.0 + i * (callout_h + gap)
        role = str(cblock.get("role") or "").lower()
        color = accent if role in {"evidence", "boundary", "risk"} or i == 1 else primary
        parts.append(_rect(panel_x, cy, panel_w, callout_h, "#FFFFFF", "none", rx=0))
        parts.append(_rect(panel_x, cy + 2.0, 5.0, callout_h - 4.0, color, "none", rx=0))
        _text_lines(parts, panel_x + 18.0, cy + 24.0, str(cblock.get("heading") or "Analysis"), 14.5, color, panel_w - 28.0, weight="bold", max_lines=1)
        body = cblock.get("body") or []
        if isinstance(body, str):
            body = [body]
        yy = cy + 48.0
        for item in [str(v).strip() for v in body if str(v).strip()][:2]:
            yy = _text_lines(parts, panel_x + 18.0, yy, _clean_visible_text(item), 12.3, text_c, panel_w - 28.0, max_lines=1, line_gap=1.1)
    parts.append("</g></g></g>")
    return True


def _draw_generic_cards(parts, block, palette, canvas):
    primary, accent, neutral, text_c = palette["primary"], palette["accent"], palette["neutral"], palette["text"]
    nodes = _nodes(block)[:3]
    r = _visual_region(canvas)
    x, y, w = r["x"], r["y"], r["width"]
    h = min(84.0, max(64.0, (r["height"] - 44.0) / 3.0))
    gap = max(16.0, (r["height"] - h * 3.0) / 2.0)
    parts.append('<g id="visual-insight-cards">')
    for i, n in enumerate(nodes):
        yy = y + i * (h + gap)
        parts.append(_rect(x, yy, w, h, "#FFFFFF", primary, sw=1.4, rx=8))
        parts.append(_circle(x + 34, yy + 46, 18, accent))
        _text_lines(parts, x + 68, yy + 34, n, 18, text_c, w - 92, max_lines=2)
    parts.append("</g>")


def _draw_flow(parts, block, palette, canvas):
    primary, accent, neutral, text_c = palette["primary"], palette["accent"], palette["neutral"], palette["text"]
    nodes = _nodes(block)[:4]
    r = _visual_region(canvas)
    x, y, w = r["x"], r["y"], r["width"]
    h = min(66.0, max(52.0, (r["height"] - 54.0) / max(1, len(nodes))))
    gap = min(18.0, max(10.0, (r["height"] - h * max(1, len(nodes))) / max(1, len(nodes) - 1)))
    parts.append('<g id="visual-flow">')
    for i, n in enumerate(nodes):
        yy = y + i * (h + gap)
        fill = primary if i == 0 else "#FFFFFF"
        color = "#FFFFFF" if i == 0 else text_c
        parts.append(_rect(x, yy, w, h, fill, primary, sw=1.6, rx=8))
        _text_lines(parts, x + 20, yy + 28, n, 17, color, w - 40, max_lines=2)
        if i < len(nodes) - 1:
            parts.append(_line(x + w / 2, yy + h, x + w / 2, yy + h + gap - 3, accent, 2.4, marker=True))
    parts.append("</g>")


def _draw_quadrant(parts, block, palette, canvas):
    primary, accent, neutral, text_c = palette["primary"], palette["accent"], palette["neutral"], palette["text"]
    labels = ["What", "When", "How", "Where"]
    nodes = (_nodes(block) + labels)[:4]
    r = _visual_region(canvas)
    x, y, gap = r["x"], r["y"], 14.0
    card_w = (r["width"] - gap) / 2.0
    card_h = min(118.0, (r["height"] - gap) / 2.0)
    parts.append('<g id="visual-quadrant">')
    for i in range(4):
        xx = x + (i % 2) * (card_w + gap)
        yy = y + (i // 2) * (card_h + gap)
        parts.append(_rect(xx, yy, card_w, card_h, "#FFFFFF", primary, sw=1.5, rx=8))
        parts.append(_text_el(xx + 16, yy + 34, labels[i], 21, accent, weight="bold"))
        _text_lines(parts, xx + 16, yy + 68, nodes[i], 15.5, text_c, card_w - 32, max_lines=2)
    parts.append("</g>")


def _draw_cycle(parts, block, palette, canvas):
    primary, accent, neutral, text_c = palette["primary"], palette["accent"], palette["neutral"], palette["text"]
    nodes = (_nodes(block) + ["评估反馈"])[:4]
    vr = _visual_region(canvas)
    cx, cy = vr["x"] + vr["width"] / 2.0, vr["y"] + vr["height"] / 2.0
    r = min(vr["width"], vr["height"]) * 0.31
    pts = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
    parts.append('<g id="visual-cycle">')
    parts.append(_circle(cx, cy, 62, neutral, primary, sw=2))
    _text_lines(parts, cx, cy - 8, "Loop", 24, primary, 100, weight="bold", anchor="middle", max_lines=1)
    for i, (px, py) in enumerate(pts):
        parts.append(_circle(px, py, 54, "#FFFFFF", primary, sw=2))
        _text_lines(parts, px, py - 8, nodes[i], 17, text_c, 86, anchor="middle", max_lines=2)
        nx, ny = pts[(i + 1) % len(pts)]
        parts.append(_line(px + (nx - px) * 0.38, py + (ny - py) * 0.38, px + (nx - px) * 0.62, py + (ny - py) * 0.62, accent, 3, marker=True))
    parts.append("</g>")


def _draw_architecture(parts, block, palette, canvas):
    primary, accent, neutral, text_c = palette["primary"], palette["accent"], palette["neutral"], palette["text"]
    nodes = (_nodes(block) + ["评估与监控", "经验管理", "执行服务"])[:4]
    r = _visual_region(canvas)
    x, y, w = r["x"], r["y"], r["width"]
    h = min(64.0, max(50.0, (r["height"] - 48.0) / 4.0))
    gap = max(10.0, (r["height"] - h * 4.0) / 3.0)
    parts.append('<g id="visual-architecture">')
    for i, n in enumerate(nodes[:4]):
        yy = y + i * (h + gap)
        fill = neutral if i % 2 else "#FFFFFF"
        parts.append(_rect(x, yy, w, h, fill, primary, sw=1.5, rx=8))
        parts.append(_rect(x, yy, 10, h, accent, "none", rx=5))
        _text_lines(parts, x + 24, yy + 27, n, 16.5, text_c, w - 44, max_lines=2)
        if i:
            parts.append(_line(x + w - 34, yy - gap + 3, x + w - 34, yy - 2, accent, 2.2, marker=True))
    parts.append("</g>")


def _draw_roadmap(parts, block, palette, canvas):
    primary, accent, neutral, text_c = palette["primary"], palette["accent"], palette["neutral"], palette["text"]
    stage_nodes = _box_nodes(block)
    nodes = (stage_nodes + ["热度分层缓存", "KV offload + eviction/recompute", "Attention/KV 近存卸载", "3D堆叠/端云协同"])[:4]
    r = _visual_region(canvas)
    x, y, w = r["x"], r["y"] + r["height"] * 0.42, r["width"]
    card_w = min(104.0, max(78.0, (w - 24.0) / 4.0))
    step = (w - card_w) / 3.0 if len(nodes) > 1 else 0
    parts.append('<g id="visual-roadmap">')
    parts.append(_line(x + card_w / 2, y, x + w - card_w / 2, y, accent, 4))
    for i, n in enumerate(nodes[:4]):
        px = x + card_w / 2 + i * step
        parts.append(_circle(px, y, 20, primary))
        parts.append(_text_el(px, y - 34, f"0{i + 1}", 19, accent, weight="bold", anchor="middle"))
        parts.append(_rect(px - card_w / 2, y + 30, card_w, 96, "#FFFFFF", primary, sw=1.3, rx=8))
        _text_lines(parts, px, y + 62, n, 14, text_c, card_w - 14, anchor="middle", max_lines=3)
    parts.append("</g>")


def _draw_table(parts, table, palette, canvas, x, y, w, h):
    primary, accent, neutral, text_c = palette["primary"], palette["accent"], palette["neutral"], palette["text"]
    if not table:
        return
    ncols = max(len(r) for r in table)
    rh = min(56.0, h / max(1, len(table)))
    cwid = w / max(1, ncols)
    parts.append('<g id="visual-table">')
    for r, row in enumerate(table):
        for c in range(ncols):
            x0 = x + c * cwid
            y0 = y + r * rh
            fill = primary if r == 0 else (neutral if r % 2 else "#FFFFFF")
            stroke = "#FFFFFF" if r == 0 else primary
            parts.append(_rect(x0, y0, cwid, rh, fill, stroke, sw=1))
            cell = _clean_visible_text(row[c] if c < len(row) else "")
            if cell:
                color = "#FFFFFF" if r == 0 else text_c
                if r == 0:
                    _text_lines(parts, x0 + 12, y0 + 32, cell, 16, color, cwid - 24, max_lines=1)
                else:
                    _text_lines(parts, x0 + 12, y0 + 22, cell, 14.5, color, cwid - 24, max_lines=2, line_gap=1.18)
    parts.append("</g>")


def _spec_rows(spec: dict) -> list[list[str]]:
    data = spec.get("data") if isinstance(spec.get("data"), dict) else {}
    rows = data.get("rows") or spec.get("rows") or []
    out = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, list):
            out.append([_clean_visible_text(str(cell)) for cell in row])
        elif isinstance(row, dict):
            out.append([_clean_visible_text(str(v)) for v in row.values()])
    return out


def _spec_nodes(spec: dict, fallback: list[str] | None = None) -> list[str]:
    nodes = spec.get("nodes") or []
    out = []
    for item in nodes if isinstance(nodes, list) else []:
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("text") or item.get("title") or "").strip()
        else:
            label = str(item).strip()
        if label:
            out.append(_clean_visible_text(label))
    return out or list(fallback or [])


def _draw_spec_bar_chart(parts, spec: dict, palette, canvas, fill_target: float):
    primary, accent, neutral, text_c = palette["primary"], palette["accent"], palette["neutral"], palette["text"]
    data = spec.get("data") if isinstance(spec.get("data"), dict) else {}
    labels = [_clean_visible_text(str(x)) for x in (data.get("labels") or [])][:6]
    raw_values = data.get("values") or []
    values = []
    for item in raw_values[: len(labels)] if isinstance(raw_values, list) else []:
        if isinstance(item, (int, float)):
            values.append(float(item))
        else:
            m = re.search(r"-?\d+(?:\.\d+)?", str(item))
            values.append(float(m.group(0)) if m else 0.0)
    planned = bool(data.get("placeholder")) or "planned" in str(data.get("unit") or "").lower() or (labels and values and max(abs(v) for v in values) == 0)
    if not labels or (not values and not planned):
        return False
    r = _visual_region(canvas, mode="table", fill_target=fill_target)
    x, y, w, h = r["x"], r["y"], r["width"], r["height"]
    if planned:
        parts.append('<g id="visual-spec-planned-chart">')
        title = _clean_visible_text(str(data.get("title") or spec.get("purpose") or "待验证实验框架"))
        if title:
            _text_lines(parts, x, y - 12, title, 15, primary, w, weight="bold", max_lines=1)
        cols = min(3, len(labels))
        gap = 18.0
        card_w = (w - gap * (cols - 1)) / max(1, cols)
        card_h = min(112.0, max(84.0, h * 0.42))
        for i, label in enumerate(labels[:cols]):
            bx = x + i * (card_w + gap)
            color = accent if i == 1 else primary
            parts.append(_rect(bx, y + h * 0.28, card_w, card_h, "#FFFFFF", color, sw=1.4, rx=7))
            parts.append(_rect(bx, y + h * 0.28, card_w, 8.0, color, "none", rx=4))
            _text_lines(parts, bx + card_w / 2, y + h * 0.28 + 40.0, label, 13.2, text_c, card_w - 24, anchor="middle", weight="bold", max_lines=2)
            _text_lines(parts, bx + card_w / 2, y + h * 0.28 + 82.0, "Planned", 13.0, color, card_w - 24, anchor="middle", weight="bold", max_lines=1)
        parts.append("</g>")
        return True
    max_v = max(max(values), 1.0)
    chart_h = h - 58
    bar_gap = 18.0
    bar_w = max(28.0, (w - bar_gap * (len(labels) + 1)) / len(labels))
    parts.append('<g id="visual-spec-bar-chart">')
    parts.append(_line(x, y + chart_h, x + w, y + chart_h, primary, 1.2))
    unit = _clean_visible_text(str(data.get("unit") or ""))
    for i, (label, value) in enumerate(zip(labels, values)):
        bx = x + bar_gap + i * (bar_w + bar_gap)
        bh = max(6.0, chart_h * (value / max_v))
        by = y + chart_h - bh
        parts.append(_rect(bx, by, bar_w, bh, accent if i % 2 else primary, "none", rx=4))
        _text_lines(parts, bx + bar_w / 2, by - 8, f"{value:g}{unit}", 13, text_c, bar_w + 26, anchor="middle", max_lines=1)
        _text_lines(parts, bx + bar_w / 2, y + chart_h + 24, label, 12.5, text_c, bar_w + 20, anchor="middle", max_lines=2)
    title = _clean_visible_text(str(data.get("title") or spec.get("purpose") or ""))
    if title:
        _text_lines(parts, x, y - 12, title, 15, primary, w, weight="bold", max_lines=1)
    parts.append("</g>")
    return True


def _draw_spec_flow(parts, spec: dict, block, palette, canvas, fill_target: float):
    primary, accent, neutral, text_c = palette["primary"], palette["accent"], palette["neutral"], palette["text"]
    nodes = _spec_nodes(spec, _nodes(block))[:5]
    if not nodes:
        return False
    r = _visual_region(canvas, fill_target=fill_target)
    x, y, w = r["x"], r["y"], r["width"]
    h = min(58.0, max(46.0, (r["height"] - 46.0) / max(1, len(nodes))))
    gap = max(9.0, min(16.0, (r["height"] - h * len(nodes)) / max(1, len(nodes) - 1)))
    parts.append('<g id="visual-spec-flow">')
    for i, label in enumerate(nodes):
        yy = y + i * (h + gap)
        fill = primary if i == 0 else "#FFFFFF"
        color = "#FFFFFF" if i == 0 else text_c
        parts.append(_rect(x, yy, w, h, fill, primary, sw=1.5, rx=8))
        _text_lines(parts, x + 20, yy + 25, label, 15.5, color, w - 40, max_lines=2)
        if i < len(nodes) - 1:
            parts.append(_line(x + w / 2, yy + h, x + w / 2, yy + h + gap - 2, accent, 2.2, marker=True))
    parts.append("</g>")
    return True


def _draw_spec_architecture(parts, spec: dict, block, palette, canvas, fill_target: float):
    primary, accent, neutral, text_c = palette["primary"], palette["accent"], palette["neutral"], palette["text"]
    nodes = _spec_nodes(spec, _nodes(block))[:5]
    if not nodes:
        return False
    r = _visual_region(canvas, fill_target=fill_target)
    x, y, w = r["x"], r["y"], r["width"]
    h = min(58.0, max(45.0, (r["height"] - 44.0) / max(1, len(nodes))))
    gap = max(8.0, min(14.0, (r["height"] - h * len(nodes)) / max(1, len(nodes) - 1)))
    parts.append('<g id="visual-spec-architecture">')
    for i, label in enumerate(nodes):
        yy = y + i * (h + gap)
        parts.append(_rect(x, yy, w, h, neutral if i % 2 else "#FFFFFF", primary, sw=1.4, rx=8))
        parts.append(_rect(x, yy, 12, h, accent, "none", rx=4))
        _text_lines(parts, x + 26, yy + 24, label, 15.5, text_c, w - 52, max_lines=2)
    parts.append("</g>")
    return True


def _draw_spec_cards(parts, spec: dict, block, palette, canvas, fill_target: float):
    primary, accent, neutral, text_c = palette["primary"], palette["accent"], palette["neutral"], palette["text"]
    nodes = _spec_nodes(spec, _nodes(block))[:6]
    if not nodes:
        return False
    r = _visual_region(canvas, fill_target=fill_target)
    x, y, w, h = r["x"], r["y"], r["width"], r["height"]
    n = min(len(nodes), 6)
    cols = 2 if n > 3 else 1
    rows = (n + cols - 1) // cols
    gap = 14.0
    card_w = (w - gap * (cols - 1)) / cols
    card_h = min(86.0, max(58.0, (h - gap * (rows - 1)) / max(1, rows)))
    parts.append('<g id="visual-spec-cards">')
    title = _clean_visible_text(str(spec.get("purpose") or ""))
    if title and rows <= 2:
        _text_lines(parts, x, y - 10, title, 14.5, primary, w, weight="bold", max_lines=1)
    for i, label in enumerate(nodes[:n]):
        col = i % cols
        row = i // cols
        xx = x + col * (card_w + gap)
        yy = y + row * (card_h + gap)
        fill = "#FFFFFF" if i % 2 else neutral
        parts.append(_rect(xx, yy, card_w, card_h, fill, primary, sw=1.25, rx=8))
        parts.append(_rect(xx, yy, 7, card_h, accent, "none", rx=4))
        _text_lines(parts, xx + 20, yy + 27, label, 15.0, text_c, card_w - 34, max_lines=2)
    parts.append("</g>")
    return True


def _draw_spec_roadmap(parts, spec: dict, block, palette, canvas, fill_target: float):
    primary, accent, text_c = palette["primary"], palette["accent"], palette["text"]
    stages = spec.get("stages") if isinstance(spec.get("stages"), list) else []
    nodes = []
    for item in stages:
        if isinstance(item, dict):
            nodes.append(str(item.get("text") or item.get("label") or "").strip())
        else:
            nodes.append(str(item).strip())
    nodes = [_clean_visible_text(n) for n in nodes if _clean_visible_text(n)] or _box_nodes(block)[:4]
    if not nodes:
        return False
    nodes = nodes[:4]
    r = _visual_region(canvas, fill_target=fill_target)
    x, y, w = r["x"], r["y"] + r["height"] * 0.38, r["width"]
    card_w = min(118.0, max(82.0, (w - 28.0) / max(1, len(nodes))))
    step = (w - card_w) / max(1, len(nodes) - 1)
    parts.append('<g id="visual-spec-roadmap">')
    parts.append(_line(x + card_w / 2, y, x + w - card_w / 2, y, accent, 4))
    for i, label in enumerate(nodes):
        px = x + card_w / 2 + i * step
        parts.append(_circle(px, y, 20, primary))
        parts.append(_text_el(px, y + 7, str(i + 1), 17, "#FFFFFF", weight="bold", anchor="middle"))
        parts.append(_rect(px - card_w / 2, y + 30, card_w, 96, "#FFFFFF", primary, sw=1.3, rx=8))
        _text_lines(parts, px, y + 60, label, 13.5, text_c, card_w - 14, anchor="middle", max_lines=3)
    parts.append("</g>")
    return True


def _draw_from_visual_spec(parts, block, visual, palette, canvas) -> bool:
    spec = visual.get("visual_spec") if isinstance(visual.get("visual_spec"), dict) else {}
    kind = str(spec.get("kind") or "").strip().lower()
    fill_target = _fill_target(visual)
    if not kind:
        return False
    if kind in {"table", "matrix", "risk_table"}:
        rows = _spec_rows(spec)
        if not rows:
            return False
        r = _visual_region(canvas, mode="table", fill_target=_fill_target(visual))
        _draw_table(parts, rows, palette, canvas, r["x"], r["y"], r["width"], r["height"])
        return True
    if kind in {"bar_chart", "line_chart"}:
        return _draw_spec_bar_chart(parts, spec, palette, canvas, fill_target)
    if kind == "roadmap":
        return _draw_spec_roadmap(parts, spec, block, palette, canvas, fill_target)
    if kind in {"flow", "timeline"}:
        return _draw_spec_flow(parts, spec, block, palette, canvas, fill_target)
    if kind == "architecture":
        return _draw_spec_architecture(parts, spec, block, palette, canvas, fill_target)
    if kind == "cards":
        return _draw_spec_cards(parts, spec, block, palette, canvas, fill_target)
    return False


def _draw_content_blocks_panel(parts, block, visual, palette, canvas) -> bool:
    blocks = visual.get("content_blocks") if isinstance(visual.get("content_blocks"), list) else []
    blocks = [b for b in blocks if isinstance(b, dict) and (b.get("heading") or b.get("body"))]
    if not blocks:
        return False
    primary, accent, neutral, text_c = palette["primary"], palette["accent"], palette["neutral"], palette["text"]
    cw = float(canvas.get("width_px", 1280))
    ch = float(canvas.get("height_px", 720))
    region = visual.get("_content_blocks_region") if isinstance(visual.get("_content_blocks_region"), dict) else {}
    variant = str(visual.get("_content_blocks_variant") or "").lower()
    if region:
        x = float(region.get("x", 72.0))
        top = float(region.get("y", 180.0))
        w = float(region.get("width", cw - 144.0))
        h = float(region.get("height", ch - top - 74.0))
    else:
        top = 472.0 if cw >= 1000 else ch * 0.64
        h = max(112.0, ch - top - 74.0)
        x = 72.0
        w = cw - 144.0
    if variant == "right_stack":
        cols = 1
    elif variant == "bottom_band":
        cols = min(4, max(1, len(blocks)))
    else:
        cols = min(3, max(1, len(blocks)))
    gap = 14.0 if variant == "right_stack" else 18.0
    card_w = (w - gap * (cols - 1)) / cols
    visible_count = min(4, len(blocks)) if variant == "right_stack" else cols
    parts.append('<g id="content-blocks-panel">')
    for i, cblock in enumerate(blocks[:visible_count]):
        if variant == "right_stack":
            card_h = max(64.0, (h - gap * (visible_count - 1)) / max(1, visible_count))
            cx = x
            cy = top + i * (card_h + gap)
        else:
            card_h = h
            cx = x + i * (card_w + gap)
            cy = top
        role = str(cblock.get("role") or "").lower()
        color = accent if role in {"evidence", "boundary"} else primary
        parts.append(_rect(cx, cy, card_w, card_h, "#FFFFFF", color, sw=1.2, rx=6))
        header_h = 28.0 if variant == "right_stack" else 32.0
        parts.append(_rect(cx, cy, card_w, header_h, color, "none", rx=6))
        heading = str(cblock.get("heading") or {"mechanism": "机制", "evidence": "证据", "implication": "含义", "boundary": "边界"}.get(role, "分析"))
        _text_lines(parts, cx + 12, cy + 20, heading, 13.5 if variant == "right_stack" else 14.5, "#FFFFFF", card_w - 24, weight="bold", max_lines=1)
        body = cblock.get("body") or []
        if isinstance(body, str):
            body = [body]
        yy = cy + header_h + 22
        max_items = 2 if variant == "right_stack" and card_h < 86 else 3
        font_size = 11.8 if variant == "right_stack" else 12.8
        for item in [str(v).strip() for v in body if str(v).strip()][:max_items]:
            if yy > cy + card_h - 10:
                break
            parts.append(_circle(cx + 16, yy - 5, 3.2, color))
            yy = _text_lines(parts, cx + 28, yy, _clean_visible_text(item), font_size, text_c, card_w - 38, max_lines=2, line_gap=1.12)
            yy += 7
    parts.append("</g>")
    return True


def _draw_semantic_full_width_band(parts, block, visual, palette, canvas) -> bool:
    """Render semantic research pages as richer full-width compositions.

    The base template still owns the title, rule, footer, and typography. This
    layer only changes the inner evidence composition so fallback pages do not
    collapse back to the same two fixed boxes.
    """
    cid = str(visual.get("semantic_component_id") or "").strip()
    spec = visual.get("visual_spec") if isinstance(visual.get("visual_spec"), dict) else {}
    blocks = [b for b in visual.get("content_blocks") or [] if isinstance(b, dict) and (b.get("heading") or b.get("body"))]
    allowed_assets = _allowed_visual_assets(visual)
    if not cid or not blocks:
        return False
    primary, accent, neutral, text_c = palette["primary"], palette["accent"], palette["neutral"], palette["text"]
    cw = float(canvas.get("width_px", 1280))
    ch = float(canvas.get("height_px", 720))
    x, top = 66.0, max(92.0, float(visual.get("_content_start_y") or 152.0))
    w, h = cw - 132.0, max(260.0, ch - top - 80.0)

    def block_text(cblock, limit=2):
        body = cblock.get("body") or []
        if isinstance(body, str):
            body = [body]
        return [_clean_visible_text(str(v)) for v in body if str(v).strip()][:limit]

    if allowed_assets and cid in {"key_insight_mechanism.v1", "method_overview.v1", "technique_detail.v1"}:
        parts.append('<g id="blueprint-composition"><g id="content-blocks-panel"><g id="semantic-image-analysis-composition">')
        image_w = w * 0.54
        image_canvas = dict(canvas)
        image_canvas["_visual_region_override"] = {"x": x, "y": top + 28.0, "width": image_w, "height": h - 72.0}
        _draw_image_panel(parts, allowed_assets, palette, image_canvas)
        panel_x = x + image_w + 28.0
        panel_w = w - image_w - 28.0
        for i, cblock in enumerate(blocks[:3]):
            cy = top + 30.0 + i * ((h - 78.0) / 3.0)
            card_h = (h - 104.0) / 3.0
            color = accent if str(cblock.get("role") or "").lower() in {"evidence", "boundary"} else primary
            parts.append(_rect(panel_x, cy, panel_w, card_h, "#FFFFFF", color, sw=1.2, rx=6))
            _text_lines(parts, panel_x + 18.0, cy + 25.0, str(cblock.get("heading") or ""), 14.5, primary, panel_w - 36.0, weight="bold", max_lines=1)
            yy = cy + 54.0
            for item in block_text(cblock, 2):
                yy = _text_lines(parts, panel_x + 18.0, yy, item, 12.5, text_c, panel_w - 36.0, max_lines=2, line_gap=1.12)
                yy += 6.0
        parts.append("</g></g></g>")
        return True

    if cid in {"key_insight_mechanism.v1", "technique_detail.v1"}:
        center_w = w * 0.42
        side_w = (w - center_w - 56.0) / 2.0
        parts.append('<g id="blueprint-composition"><g id="content-blocks-panel"><g id="semantic-mechanism-composition">')
        for side, cblock in enumerate(blocks[:2]):
            bx = x if side == 0 else x + side_w + center_w + 56.0
            parts.append(_rect(bx, top + 34.0, side_w, h - 68.0, "#FFFFFF", primary, sw=1.1, rx=6))
            parts.append(_rect(bx, top + 34.0, 8.0, h - 68.0, accent if side else primary, "none", rx=4))
            _text_lines(parts, bx + 24.0, top + 66.0, str(cblock.get("heading") or ""), 16.0, primary, side_w - 40.0, weight="bold", max_lines=1)
            yy = top + 104.0
            for item in block_text(cblock, 3):
                parts.append(_circle(bx + 28.0, yy - 6.0, 3.4, accent if side else primary))
                yy = _text_lines(parts, bx + 42.0, yy, item, 13.2, text_c, side_w - 58.0, max_lines=2, line_gap=1.15)
                yy += 13.0
        cx = x + side_w + 28.0
        cy = top + 38.0
        parts.append(_rect(cx, cy, center_w, h - 76.0, neutral, primary, sw=1.4, rx=8))
        nodes = _spec_nodes(spec, _nodes(block))[:4]
        if len(nodes) < 4:
            nodes = (nodes + ["状态识别", "访问分层", "调度执行", "反馈更新"])[:4]
        node_h = 50.0
        gap = max(18.0, ((h - 116.0) - node_h * len(nodes)) / max(1, len(nodes) - 1))
        for i, label in enumerate(nodes):
            ny = cy + 30.0 + i * (node_h + gap)
            fill = primary if i == 0 else "#FFFFFF"
            color = "#FFFFFF" if i == 0 else text_c
            parts.append(_rect(cx + 34.0, ny, center_w - 68.0, node_h, fill, primary, sw=1.2, rx=7))
            _text_lines(parts, cx + center_w / 2.0, ny + 30.0, label, 14.0, color, center_w - 90.0, anchor="middle", weight="bold" if i == 0 else "normal", max_lines=1)
            if i < len(nodes) - 1:
                parts.append(_line(cx + center_w / 2.0, ny + node_h, cx + center_w / 2.0, ny + node_h + gap - 2.0, accent, 2.2, marker=True))
        parts.append("</g></g></g>")
        return True

    kind = str(spec.get("kind") or "").strip().lower()
    if cid in {"related_work_matrix.v1", "ablation_comparison.v1", "risk_boundary.v1"} or (kind in {"matrix", "risk_table"} and cid in {"challenge_quantification.v1", "technique_detail.v1"}):
        parts.append('<g id="blueprint-composition"><g id="content-blocks-panel"><g id="semantic-matrix-composition">')
        matrix_h = h * 0.64
        table_visual = dict(visual)
        table_canvas = dict(canvas)
        table_canvas["_visual_region_override"] = {"x": x, "y": top, "width": w, "height": matrix_h}
        if not _draw_from_visual_spec(parts, block, table_visual, palette, table_canvas):
            rows = _spec_rows(spec)
            if rows:
                _draw_table(parts, rows, palette, canvas, x, top, w, matrix_h)
        band_y = top + matrix_h + 24.0
        cols = min(3, len(blocks))
        gap = 18.0
        card_w = (w - gap * (cols - 1)) / max(1, cols)
        for i, cblock in enumerate(blocks[:cols]):
            bx = x + i * (card_w + gap)
            role = str(cblock.get("role") or "").lower()
            color = accent if role in {"gap", "boundary", "risk", "evidence"} or i == cols - 1 else primary
            parts.append(_rect(bx, band_y, card_w, h - matrix_h - 24.0, "#FFFFFF", color, sw=1.2, rx=6))
            parts.append(_rect(bx, band_y, 6.0, h - matrix_h - 24.0, color, "none", rx=3))
            _text_lines(parts, bx + 18.0, band_y + 27.0, str(cblock.get("heading") or ""), 14.5, primary, card_w - 34.0, weight="bold", max_lines=1)
            yy = band_y + 57.0
            for item in block_text(cblock, 1):
                yy = _text_lines(parts, bx + 18.0, yy, item, 11.7, text_c, card_w - 34.0, max_lines=2, line_gap=1.08)
                yy += 5.0
        parts.append("</g></g></g>")
        return True

    if cid in {"method_overview.v1"}:
        parts.append('<g id="blueprint-composition"><g id="content-blocks-panel"><g id="semantic-method-overview-composition">')
        arch_w = w * 0.68
        arch_canvas = dict(canvas)
        arch_canvas["_visual_region_override"] = {"x": x, "y": top + 16.0, "width": arch_w, "height": h - 32.0}
        if not _draw_from_visual_spec(parts, block, visual, palette, arch_canvas):
            _draw_spec_architecture(parts, spec, block, palette, arch_canvas, 1.0)
        side_x = x + arch_w + 28.0
        side_w = w - arch_w - 28.0
        for i, cblock in enumerate(blocks[:3]):
            cy = top + 18.0 + i * ((h - 36.0) / 3.0)
            card_h = (h - 64.0) / 3.0
            color = accent if i == 1 else primary
            parts.append(_rect(side_x, cy, side_w, card_h, "#FFFFFF", color, sw=1.2, rx=6))
            parts.append(_rect(side_x, cy, 7.0, card_h, color, "none", rx=4))
            _text_lines(parts, side_x + 22.0, cy + 25.0, str(cblock.get("heading") or ""), 14.5, primary, side_w - 36.0, weight="bold", max_lines=1)
            yy = cy + 54.0
            for item in block_text(cblock, 2):
                yy = _text_lines(parts, side_x + 22.0, yy, item, 12.4, text_c, side_w - 36.0, max_lines=2, line_gap=1.12)
                yy += 6.0
        parts.append("</g></g></g>")
        return True

    if cid in {"background_trend.v1", "challenge_quantification.v1", "experiment_result.v1"}:
        parts.append('<g id="blueprint-composition"><g id="content-blocks-panel"><g id="semantic-evidence-result-composition">')
        chart_w = w * 0.58
        metric_x = x + chart_w + 30.0
        metric_w = w - chart_w - 30.0
        chart_canvas = dict(canvas)
        chart_canvas["_visual_region_override"] = {"x": x, "y": top + 34.0, "width": chart_w, "height": h - 92.0}
        if allowed_assets and cid == "background_trend.v1":
            image_visual = dict(visual)
            image_visual["assets"] = allowed_assets
            _draw_image_panel(parts, allowed_assets, palette, chart_canvas)
        elif not _draw_from_visual_spec(parts, block, visual, palette, chart_canvas):
            _draw_spec_bar_chart(parts, spec, palette, chart_canvas, 1.0)
        callout = blocks[0] if blocks else {}
        parts.append(_rect(metric_x, top + 34.0, metric_w, 86.0, neutral, "none", rx=6))
        parts.append(_rect(metric_x, top + 34.0, 8.0, 86.0, accent, "none", rx=4))
        _text_lines(parts, metric_x + 24.0, top + 65.0, str(callout.get("heading") or "关键读数"), 15.0, primary, metric_w - 44.0, weight="bold", max_lines=1)
        first = (block_text(callout, 1) or [_clean_visible_text(str(block.get("claim") or ""))])[0]
        _text_lines(parts, metric_x + 24.0, top + 96.0, first, 12.6, text_c, metric_w - 44.0, max_lines=2, line_gap=1.08)
        lower_top = top + 144.0
        lower_blocks = blocks[1:4]
        lower_available = max(86.0, top + h - lower_top)
        card_gap = 16.0
        card_h = min(72.0, max(58.0, (lower_available - card_gap * max(0, len(lower_blocks) - 1)) / max(1, len(lower_blocks))))
        for i, cblock in enumerate(lower_blocks):
            cy = lower_top + i * (card_h + card_gap)
            color = primary if i % 2 == 0 else accent
            parts.append(_rect(metric_x, cy, metric_w, card_h, "#FFFFFF", color, sw=1.1, rx=6))
            _text_lines(parts, metric_x + 18.0, cy + 25.0, str(cblock.get("heading") or ""), 13.8, primary, metric_w - 36.0, weight="bold", max_lines=1)
            txt = (block_text(cblock, 1) or [""])[0]
            _text_lines(parts, metric_x + 18.0, cy + 52.0, txt, 11.2, text_c, metric_w - 36.0, max_lines=2, line_gap=1.08)
        parts.append("</g></g></g>")
        return True

    if cid in {"summary_takeaway.v1"}:
        parts.append('<g id="blueprint-composition"><g id="content-blocks-panel"><g id="semantic-summary-composition">')
        cols = min(3, len(blocks))
        gap = 22.0
        card_w = (w - gap * (cols - 1)) / max(1, cols)
        for i, cblock in enumerate(blocks[:cols]):
            bx = x + i * (card_w + gap)
            role = str(cblock.get("role") or "").lower()
            color = accent if role in {"boundary", "risk"} else primary
            parts.append(_rect(bx, top + 22.0, card_w, h - 44.0, "#FFFFFF", color, sw=1.4, rx=7))
            parts.append(_rect(bx, top + 22.0, card_w, 42.0, color, "none", rx=7))
            _text_lines(parts, bx + 18.0, top + 49.0, str(cblock.get("heading") or ""), 16.0, "#FFFFFF", card_w - 36.0, weight="bold", max_lines=1)
            yy = top + 96.0
            for item in block_text(cblock, 3):
                parts.append(_circle(bx + 24.0, yy - 6.0, 3.4, color))
                yy = _text_lines(parts, bx + 40.0, yy, item, 13.0, text_c, card_w - 56.0, max_lines=3, line_gap=1.12)
                yy += 12.0
        parts.append("</g></g></g>")
        return True

    return False


def _draw_agenda_page(parts, block, visual, palette, canvas) -> bool:
    primary, accent, neutral, text_c = palette["primary"], palette["accent"], palette["neutral"], palette["text"]
    cw = float(canvas.get("width_px", 1280))
    ch = float(canvas.get("height_px", 720))
    items = []
    active_idx = None
    meta = visual.get("agenda_state") if isinstance(visual.get("agenda_state"), dict) else {}
    if str(meta.get("active_index") or "").isdigit():
        active_idx = int(meta.get("active_index")) - 1
    for cblock in visual.get("content_blocks") or []:
        if not isinstance(cblock, dict):
            continue
        body = cblock.get("body") or []
        if isinstance(body, str):
            body = [body]
        for item in body:
            for piece in re.split(r"\s*→\s*", str(item)):
                piece = _clean_visible_text(piece)
                if piece and len(piece) <= 18 and piece not in items:
                    items.append(piece)
    if len(items) < 4:
        items = ["背景与趋势", "关键瓶颈", "问题重定义", "核心洞察", "技术路线", "验证计划与风险"]
    items = items[:6]
    x, y = 118.0, 138.0
    w = cw - 236.0
    row_h = 58.0
    gap_y = 13.0
    parts.append('<g id="blueprint-composition"><g id="dai-agenda-page">')
    parts.append(_rect(x, y - 26.0, w, 2.4, primary, "none"))
    for i, item in enumerate(items):
        cy = y + i * (row_h + gap_y)
        is_active = active_idx == i
        color = primary if is_active or active_idx is None else "#9A9A9A"
        number_color = accent if is_active else color
        parts.append(_rect(x, cy, w, row_h, "#FFFFFF", "none", rx=0))
        parts.append(_line(x, cy + row_h, x + w, cy + row_h, "#D9D9D9", 1.0))
        parts.append(_text_el(x + 8.0, cy + 38.0, f"{i + 1:02d}", 24.0, number_color, weight="bold"))
        _text_lines(parts, x + 86.0, cy + 38.0, item, 24.0 if is_active else 22.0, color, w - 120.0, weight="bold" if is_active else "normal", max_lines=1)
    summary = _clean_visible_text(str(block.get("claim") or ""))
    if summary:
        box_y = min(y + len(items) * (row_h + gap_y) + 24.0, ch - 155.0)
        parts.append(_rect(x, box_y, w, 54.0, "none", primary, sw=2.0, rx=0))
        _text_lines(parts, x + 20.0, box_y + 33.0, summary, 18.0, primary, w - 40.0, weight="bold", max_lines=1)
    parts.append("</g></g>")
    return True


def _with_split_regions(visual: dict, canvas, *, left_ratio: float = 0.64, top: float = 154.0, bottom: float = 64.0, gap: float = 24.0) -> tuple[dict, dict]:
    cw = float(canvas.get("width_px", 1280))
    ch = float(canvas.get("height_px", 720))
    x = 66.0
    total_w = cw - 132.0
    h = max(210.0, ch - top - bottom)
    left_w = total_w * left_ratio
    right_w = total_w - left_w - gap
    v2 = dict(visual or {})
    v2["_content_blocks_variant"] = "right_stack"
    v2["_content_blocks_region"] = {"x": x + left_w + gap, "y": top, "width": right_w, "height": h}
    c2 = dict(canvas)
    c2["_visual_region_override"] = {"x": x, "y": top, "width": left_w, "height": h}
    return v2, c2


def _semantic_split_ratio(semantic_component_id: str, kind: str) -> float:
    cid = str(semantic_component_id or "").strip()
    if cid in {"experiment_result.v1", "challenge_quantification.v1", "background_trend.v1"}:
        return 0.66
    if cid in {"method_overview.v1", "key_insight_mechanism.v1", "technique_detail.v1"}:
        return 0.56
    if cid in {"related_work_matrix.v1", "ablation_comparison.v1", "risk_boundary.v1"}:
        return 0.62
    if kind in {"table", "matrix", "risk_table"}:
        return 0.62
    if kind in {"flow", "timeline", "architecture"}:
        return 0.58
    return 0.64


def _blueprint_split_ratio(visual: dict, kind: str) -> float:
    blueprint = visual.get("layout_blueprint") if isinstance(visual.get("layout_blueprint"), dict) else {}
    variation = str(visual.get("layout_variation") or "").lower()
    primary = str(blueprint.get("primary_visual") or "").lower()
    analysis = str(blueprint.get("analysis_panel") or "").lower()
    callouts = str(blueprint.get("evidence_callouts") or "").lower()
    if "dense-matrix" in variation or kind in {"table", "matrix", "risk_table"}:
        return 0.66
    if "left-visual-right-claim" in variation or "right" in analysis:
        return 0.58
    if "split-evidence" in variation or callouts:
        return 0.62
    if "architecture-map" in variation or kind == "architecture":
        return 0.60
    if "top-claim-large-visual" in variation or "large" in primary or "主证据" in primary:
        return 0.70
    return _semantic_split_ratio(str(visual.get("semantic_component_id") or ""), kind)


def _draw_blueprint_composition(parts, block, visual, palette, canvas) -> bool:
    blueprint = visual.get("layout_blueprint") if isinstance(visual.get("layout_blueprint"), dict) else {}
    blocks = [b for b in visual.get("content_blocks") or [] if isinstance(b, dict) and (b.get("heading") or b.get("body"))]
    spec = visual.get("visual_spec") if isinstance(visual.get("visual_spec"), dict) else {}
    kind = str(spec.get("kind") or "").strip().lower()
    if not blueprint or not blocks or not kind:
        return False
    variation = str(visual.get("layout_variation") or "").lower()
    parts.append('<g id="blueprint-composition">')
    if "full-bleed-visual" in variation or "top-claim-large-visual" in variation:
        cw = float(canvas.get("width_px", 1280))
        ch = float(canvas.get("height_px", 720))
        x, top = 66.0, max(92.0, float(visual.get("_content_start_y") or 148.0))
        w = cw - 132.0
        visual_h = max(260.0, (ch - top - 82.0) * 0.68)
        visual_canvas = dict(canvas)
        visual_canvas["_visual_region_override"] = {"x": x, "y": top, "width": w, "height": visual_h}
        if not _draw_from_visual_spec(parts, block, visual, palette, visual_canvas):
            return False
        panel_visual = dict(visual)
        panel_visual["_content_blocks_variant"] = "bottom_band"
        panel_visual["_content_blocks_region"] = {"x": x, "y": top + visual_h + 18.0, "width": w, "height": max(90.0, ch - top - visual_h - 86.0)}
        _draw_content_blocks_panel(parts, block, panel_visual, palette, canvas)
        parts.append("</g>")
        return True
    ratio = _blueprint_split_ratio(visual, kind)
    split_visual, split_canvas = _with_split_regions(visual, canvas, left_ratio=ratio)
    if _draw_from_visual_spec(parts, block, split_visual, palette, split_canvas):
        _draw_content_blocks_panel(parts, block, split_visual, palette, canvas)
        parts.append("</g>")
        return True
    parts.append("</g>")
    return False


def _draw_semantic_header_band(parts, visual, palette, canvas) -> None:
    # The base template owns the top-of-slide furniture. Extra semantic labels
    # created a stray blue strip on content slides, so keep this marker disabled.
    return
    cid = str(visual.get("semantic_component_id") or "").strip()
    family = str(visual.get("layout_family") or "").strip()
    if not cid and not family:
        return
    primary, accent, neutral = palette["primary"], palette["accent"], palette["neutral"]
    label_map = {
        "research_agenda.v1": "Agenda",
        "background_trend.v1": "Background",
        "challenge_quantification.v1": "Bottleneck",
        "related_work_matrix.v1": "Gap",
        "key_insight_mechanism.v1": "Insight",
        "method_overview.v1": "Method",
        "technique_detail.v1": "Technique",
        "experiment_result.v1": "Result",
        "ablation_comparison.v1": "Ablation",
        "risk_boundary.v1": "Risk",
        "summary_takeaway.v1": "Takeaway",
    }
    label = label_map.get(cid, family.replace("_", " ").title()[:18])
    if not label:
        return
    cw = float(canvas.get("width_px", 1280))
    parts.append('<g id="semantic-component-marker">')
    parts.append(_rect(cw - 168.0, 82.0, 104.0, 24.0, neutral, primary, sw=1.0, rx=4))
    parts.append(_rect(cw - 168.0, 82.0, 6.0, 24.0, accent, "none", rx=3))
    _text_lines(parts, cw - 154.0, 99.0, label, 11.5, primary, 84.0, weight="bold", max_lines=1)
    parts.append("</g>")


def _draw_evidence_two_box(parts, block, visual, palette, canvas, page_no: int | None = None, citation_labels: dict[str, str] | None = None):
    primary, accent, neutral, text_c = palette["primary"], palette["accent"], palette["neutral"], palette["text"]
    cw = float(canvas.get("width_px", 1280))
    ch = float(canvas.get("height_px", 720))
    slots = visual.get("component_slots") if isinstance(visual.get("component_slots"), dict) else {}
    paras = block.get("paragraphs") or []
    claim = block.get("claim") or (paras[0] if len(paras) >= 1 else "")
    evidence = block.get("evidence_sentence") or (paras[1] if len(paras) >= 2 else "")
    claim_slot = slots.get("claim") or {"x": 60, "y": 138, "width": cw - 120, "height": 76}
    claim_slot = {**claim_slot, "height": max(float(claim_slot.get("height", 0) or 0), 72.0)}
    default_box_y = float(claim_slot["y"]) + float(claim_slot["height"]) + 32
    default_box_h = max(250.0, ch - default_box_y - 112)
    left_slot = slots.get("left_box") or {"x": 78, "y": default_box_y, "width": (cw - 190) / 2, "height": default_box_h}
    right_slot = slots.get("right_box") or {"x": 78 + (cw - 190) / 2 + 34, "y": default_box_y, "width": (cw - 190) / 2, "height": default_box_h}
    parts.append('<g id="component-evidence-two-box">')
    parts.append(_rect(claim_slot["x"], claim_slot["y"], claim_slot["width"], claim_slot["height"], neutral, "none", rx=8))
    parts.append(_rect(claim_slot["x"], claim_slot["y"], 8, claim_slot["height"], accent, "none", rx=4))
    claim = _replace_citation_tokens(claim, citation_labels)
    evidence = _replace_citation_tokens(evidence, citation_labels)
    y = _text_lines(parts, claim_slot["x"] + 24, claim_slot["y"] + 31, claim, 22, text_c, claim_slot["width"] - 48, weight="bold", max_lines=1)
    if evidence and evidence != claim:
        _text_lines(parts, claim_slot["x"] + 24, y + 6, f"依据：{evidence}", 14, primary, claim_slot["width"] - 48, max_lines=1)

    def box(slot, box, label):
        heading = str((box or {}).get("heading") or label)
        body = (box or {}).get("body") or []
        if isinstance(body, str):
            body = [body]
        x, y0, w, h = slot["x"], slot["y"], slot["width"], slot["height"]
        parts.append(_rect(x, y0, w, h, "#FFFFFF", primary, sw=1.2, rx=8))
        parts.append(_rect(x, y0, w, 44, primary, "none", rx=8))
        _text_lines(parts, x + 18, y0 + 29, heading, 18, "#FFFFFF", w - 36, weight="bold", max_lines=1)
        yy = y0 + 74
        max_items = min(3, max(1, int((h - 92) // 76)))
        for item in body[:max_items]:
            parts.append(_circle(x + 24, yy - 7, 4, accent))
            yy = _text_lines(parts, x + 42, yy, _replace_citation_tokens(str(item), citation_labels), 15.5, text_c, w - 66, max_lines=2, line_gap=1.18)
            yy += 18

    box(left_slot, block.get("left_box"), "依据分析")
    box(right_slot, block.get("right_box"), "方案含义")
    lx = float(left_slot["x"]) + float(left_slot["width"])
    rx = float(right_slot["x"])
    mid_y = float(left_slot["y"]) + float(left_slot["height"]) * 0.5
    if rx - lx > 20:
        parts.append(_line(lx + 8, mid_y, rx - 8, mid_y, accent, 2.4, marker=True))
    parts.append("</g>")


def _draw_lab_footer(parts, profile: dict, canvas, page_no: int | None = None):
    contract = profile.get("lab_template_contract") if isinstance(profile.get("lab_template_contract"), dict) else {}
    if not contract:
        return
    footer = contract.get("footer_region") if isinstance(contract.get("footer_region"), dict) else {}
    pager = contract.get("page_number_region") if isinstance(contract.get("page_number_region"), dict) else {}
    speaker_name = _speaker_name(contract)
    affiliation = os.environ.get("PPT_SPEAKER_AFFILIATION") or str(contract.get("speaker_affiliation") or "Shanghai Jiao Tong University")
    text_value = str(contract.get("footer_text_template") or "{speaker_name} @ {speaker_affiliation}").format(
        speaker_name=speaker_name,
        speaker_affiliation=affiliation,
    )
    parts.append('<g id="lab-template-footer">')
    ch = float(canvas.get("height_px", 540))
    cw = float(canvas.get("width_px", 960))
    band_y = ch - 28.0
    band_fill = str(contract.get("footer_band_fill") or "#F2F2F2")
    if footer:
        try:
            band_y = min(band_y, float(footer.get("text_y", ch - 8.0)) - 18.0)
        except (TypeError, ValueError):
            pass
    parts.append(_rect(0.0, band_y, cw, ch - band_y, _hex(band_fill, "#F2F2F2"), "none", rx=0))
    if footer:
        parts.append(_text_el(
            float(footer.get("text_x", 480.0)),
            float(footer.get("text_y", 533.27)),
            text_value,
            float(footer.get("font_size", 16)),
            _hex(str(footer.get("fill") or ""), "#A6A6A6"),
            anchor=str(footer.get("anchor") or "middle"),
            font_family=_font_family(footer.get("font_family")),
        ))
    if pager and page_no is not None:
        prefix = str(pager.get("prefix") or "Page ")
        parts.append(_text_el(
            float(pager.get("text_x", float(canvas.get("width_px", 960)) - 152.0)),
            float(pager.get("text_y", float(canvas.get("height_px", 540)) - 6.0)),
            f"{prefix}{page_no}",
            float(pager.get("font_size", 12)),
            _hex(str(pager.get("fill") or ""), "#808080"),
            anchor=str(pager.get("anchor") or "start"),
            font_family=_font_family(pager.get("font_family")),
        ))
    parts.append("</g>")


def _draw_slide_citation_footer(parts, block: dict, visual: dict, citation_labels: dict[str, str] | None, canvas, profile: dict | None = None):
    cites = _slide_citation_footnotes(block, visual, citation_labels)
    if not cites:
        return
    contract = _lab_contract(profile)
    footer = contract.get("footer_region") if isinstance(contract.get("footer_region"), dict) else {}
    pager = contract.get("page_number_region") if isinstance(contract.get("page_number_region"), dict) else {}
    x = 60.0
    y = float(canvas.get("height_px", 720)) - 42.0
    width = float(canvas.get("width_px", 1280)) - 250.0
    if footer:
        y = max(18.0, float(footer.get("text_y", y)) - 22.0)
    if pager:
        pager_x = float(pager.get("text_x", float(canvas.get("width_px", 1280)) - 170.0))
        width = max(220.0, pager_x - x - 24.0)
    parts.append('<g id="slide-citation-footer">')
    _text_lines(parts, x, y, cites, 10.5, "#808080", width, max_lines=1)
    parts.append("</g>")


def _body_style(profile: dict | None) -> dict:
    contract = _lab_contract(profile)
    style = contract.get("body_style") if isinstance(contract.get("body_style"), dict) else {}
    return {
        "font_family": _font_family(style.get("font_family")),
        "font_size": float(style.get("font_size", 22.0)),
        "fill": _hex(str(style.get("fill") or ""), "#000000"),
        "line_gap": float(style.get("line_gap", 1.28)),
        "visual_font_size": float(style.get("visual_font_size", 17.0)),
        "table_font_size": float(style.get("table_font_size", 14.5)),
    }


def _allowed_visual_assets(visual: dict) -> list[str]:
    assets = visual.get("assets") or []
    allowed = []
    for item in assets:
        if isinstance(item, str):
            allowed.append(item)
            continue
        if not isinstance(item, dict):
            continue
        role = str(item.get("usage_role") or item.get("role") or "").lower()
        atype = str(item.get("asset_type") or "").lower()
        approved = item.get("approved") is True or item.get("user_confirmed") is True
        if approved or role in {"evidence_image", "source_ppt_page", "user_provided", "retrieved_evidence", "data_chart"} or atype in {"source_figure", "source_slide_svg", "data_chart", "diagram", "table"}:
            path = item.get("local_path") or item.get("path")
            if path:
                allowed.append(str(path))
    return allowed


def _draw_visual(parts, block, visual, palette, canvas, page_no: int | None = None, citation_labels: dict[str, str] | None = None):
    vt = str(visual.get("visual_type") or visual.get("layout_type") or "").lower()
    layout = str(visual.get("layout_type") or "").lower()
    title = str(block.get("title") or "")
    assets = visual.get("assets") or []
    component_id = str(visual.get("component_id") or "")
    spec = visual.get("visual_spec") if isinstance(visual.get("visual_spec"), dict) else {}
    legacy_fixed = os.environ.get("PPT_RENDER_LEGACY_FIXED_LAYOUT", "").lower() in {"1", "true", "yes"}
    fixed_style = str(visual.get("fixed_page_style") or "").lower()
    _draw_semantic_header_band(parts, visual, palette, canvas)
    if not legacy_fixed and ("agenda" in fixed_style or str(block.get("title") or "").strip() == "目录"):
        if _draw_agenda_page(parts, block, visual, palette, canvas):
            return
    if not legacy_fixed and _allowed_visual_assets(visual):
        if _draw_evidence_image_composition(parts, block, visual, palette, canvas):
            return
    if not legacy_fixed and _draw_semantic_full_width_band(parts, block, visual, palette, canvas):
        return
    if not legacy_fixed and _draw_blueprint_composition(parts, block, visual, palette, canvas):
        return
    kind = str(spec.get("kind") or "").strip().lower()
    blocks = visual.get("content_blocks") if isinstance(visual.get("content_blocks"), list) else []
    can_split = bool(blocks) and kind in {"bar_chart", "line_chart", "flow", "timeline", "architecture", "table", "matrix", "risk_table", "cards"}
    if can_split and not legacy_fixed:
        ratio = _blueprint_split_ratio(visual, kind)
        split_visual, split_canvas = _with_split_regions(visual, canvas, left_ratio=ratio)
        if _draw_from_visual_spec(parts, block, split_visual, palette, split_canvas):
            _draw_content_blocks_panel(parts, block, split_visual, palette, canvas)
            return
    if spec.get("generated_by_model") and _draw_from_visual_spec(parts, block, visual, palette, canvas):
        _draw_content_blocks_panel(parts, block, visual, palette, canvas)
        return
    if vt == "evidence-two-box" or layout == "evidence-two-box" or component_id == "evidence_two_box.v1":
        _draw_evidence_two_box(parts, block, visual, palette, canvas, page_no=page_no, citation_labels=citation_labels)
        return
    if _draw_from_visual_spec(parts, block, visual, palette, canvas):
        _draw_content_blocks_panel(parts, block, visual, palette, canvas)
        return
    if block.get("table") or vt == "table" or layout == "table" or layout in {"evidence-matrix", "comparison-matrix", "risk-boundary-table"}:
        table = block.get("table")
        if not table:
            table = _table_from_boxes(block, layout)
        if not table:
            nodes = _nodes(block)
            table = [["维度", "当前判断", "演进方向"], ["问题", nodes[0] if nodes else "现状", nodes[1] if len(nodes) > 1 else "优化"], ["行动", nodes[-1] if nodes else "落地", "持续验证"]]
        r = _visual_region(canvas, mode="table")
        _draw_table(parts, table, palette, canvas, r["x"], r["y"], r["width"], r["height"])
        return
    assets = _allowed_visual_assets(visual)
    if assets:
        _draw_image_panel(parts, assets, palette, canvas)
        return
    if "路线" in title or "阶段" in title or "roadmap" in vt or layout == "roadmap":
        _draw_roadmap(parts, block, palette, canvas)
    elif "四" in title or "全景" in title or "问题" in title and "核心" in title:
        _draw_quadrant(parts, block, palette, canvas)
    elif "循环" in title or "闭环" in title or "cycle" in vt:
        _draw_cycle(parts, block, palette, canvas)
    elif "架构" in title or "数据流" in title or "服务" in title or layout == "layered-architecture":
        _draw_architecture(parts, block, palette, canvas)
    elif vt == "diagram" or layout in {"diagram", "process-flow"}:
        _draw_flow(parts, block, palette, canvas)
    else:
        _draw_generic_cards(parts, block, palette, canvas)


def build_slide_svg(block, page_layout, palette, canvas, *, is_cover, total_idx, visual=None, citation_labels: dict[str, str] | None = None, profile: dict | None = None, page_kind: str | None = None) -> str:
    cw = float(canvas.get("width_px", 1280))
    ch = float(canvas.get("height_px", 720))
    tr = page_layout["title_region"]
    br = page_layout["body_region"]
    primary, accent, text_c = palette["primary"], palette["accent"], palette["text"]
    neutral = palette["neutral"]
    visual = visual or {}
    has_skeleton = bool(page_layout.get("_skeleton_inner"))
    visual_kind = str(visual.get("visual_type") or visual.get("layout_type") or "").lower()
    allowed_assets = _allowed_visual_assets(visual)
    has_visual = bool(visual_kind and visual_kind not in {"bullets", "closing", "title-and-body", "image-and-bullets"}) or bool(allowed_assets) or bool(block.get("table"))
    is_evidence_two_box = visual_kind == "evidence-two-box" or visual.get("component_id") == "evidence_two_box.v1"

    parts = [_defs(accent)]
    if not has_skeleton:
        parts.append(_rect(0, 0, cw, ch, "#FFFFFF"))
    page_kind = page_kind or ("cover" if is_cover else "content")
    # Title (editable), wrapped within the template title region.
    title = block.get("title") or "Slide"
    ending_owned_by_contract = page_kind == "ending" and bool(_lab_contract(profile).get("ending_content"))
    draw_content_title_after_rule = page_kind == "content" and not ending_owned_by_contract
    if not ending_owned_by_contract and not draw_content_title_after_rule:
        _draw_lab_slide_title(parts, title, profile, page_kind if page_kind in {"cover", "ending"} else "content", tr, primary)
    # Accent rule under the title. Lab base templates define their own long
    # blue rule, which should be treated as required furniture.
    lab_contract = _lab_contract(profile)
    title_rule = lab_contract.get("title_rule") if isinstance(lab_contract.get("title_rule"), dict) else {}
    if title_rule and page_kind == "content":
        rule_y = float(title_rule.get("line_y", tr["y"] + tr["height"]))
        parts.append(
            '<g id="title-rule">'
            f'<line x1="{float(title_rule.get("line_x1", tr["x"])):.1f}" '
            f'y1="{rule_y:.1f}" '
            f'x2="{float(title_rule.get("line_x2", tr["x"] + tr["width"])):.1f}" '
            f'y2="{rule_y:.1f}" '
            f'stroke="{_hex(str(title_rule.get("line_color") or ""), accent)}" '
            f'stroke-width="{float(title_rule.get("line_width", 5)):.1f}" />'
            "</g>"
        )
    elif title_rule and page_kind in {"cover", "ending"}:
        region = ((lab_contract.get("title_style") or {}).get(page_kind) or {}).get("region") if isinstance((lab_contract.get("title_style") or {}).get(page_kind), dict) else {}
        rule_y = float((region or {}).get("y", tr["y"])) + float((region or {}).get("height", tr["height"])) + 8.0
    else:
        rule_y = float(tr["y"]) + float(tr["height"]) + 6.0
        parts.append(f'<g id="title-rule">{_rect(tr["x"], rule_y, min(tr["width"], 420), 5, accent)}</g>')
    if draw_content_title_after_rule:
        # Content title must visually sit above the DAI blue rule. Drawing it
        # after the rule prevents font-renderer differences from making the
        # rule cut through Chinese glyphs in previews or PowerPoint.
        _draw_lab_slide_title(parts, title, profile, "content", tr, primary)
    content_start_y = rule_y + 28
    if page_kind == "content" and str(block.get("claim") or "").strip() and not is_evidence_two_box:
        content_start_y = _draw_assertion_box(parts, str(block.get("claim") or ""), profile, canvas, y=rule_y + 22)
    if page_kind == "content":
        visual = _offset_visual_start(visual, content_start_y)

    # Body: bullets and/or a simple editable table grid in the template body region.
    table_like = bool(block.get("table") or visual_kind == "table" or visual_kind in {"evidence-matrix", "comparison-matrix", "risk-boundary-table"})
    if has_visual:
        br = _body_region_for_visual(br, canvas, visual_kind=visual_kind, table_like=table_like)
    bx, by, bw, bh = br["x"], content_start_y, br["width"], br["height"]
    body_style = _body_style(profile)
    parts.append('<g id="content-body">')
    legacy_fixed = os.environ.get("PPT_RENDER_LEGACY_FIXED_LAYOUT", "").lower() in {"1", "true", "yes"}
    has_structured_blocks = bool(
        isinstance(visual.get("content_blocks"), list)
        and [b for b in visual.get("content_blocks") if isinstance(b, dict) and (b.get("heading") or b.get("body"))]
    )
    if not is_evidence_two_box and page_kind == "content" and (legacy_fixed or not has_structured_blocks):
        b_size = body_style["font_size"]
        y = by + b_size
        paras = block.get("paragraphs") or ([block.get("body", "")] if block.get("body") else [])
        diagram_like = visual_kind in {"diagram", "process-flow", "layered-architecture", "roadmap"}
        body_limit = 2 if table_like or diagram_like else 5
        for p in paras[:body_limit]:
            if y > by + bh:
                break
            prefix = "" if (p.endswith("：") or p.endswith(":") or is_cover) else "• "
            text_value = _replace_citation_tokens(prefix + p, citation_labels)
            for k, ln in enumerate(_wrap(text_value, b_size, bw)):
                if y > by + bh:
                    break
                parts.append(_text_el(bx, y, ln, b_size, body_style["fill"], font_family=body_style["font_family"]))
                y += b_size * body_style["line_gap"]
    parts.append("</g>")

    if page_kind == "cover":
        _draw_lab_cover_metadata(parts, profile)
    elif page_kind == "ending":
        _draw_ending_takeaway_content(parts, block, visual, palette, canvas, profile)
    elif has_visual or not is_cover:
        _draw_visual(parts, block, visual, palette, canvas, page_no=total_idx, citation_labels=citation_labels)
    if profile and page_kind == "content":
        _draw_slide_citation_footer(parts, block, visual, citation_labels, canvas, profile=profile)
        _draw_lab_footer(parts, profile, canvas, page_no=total_idx)

    skeleton = page_layout.get("_skeleton_inner", "")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'version="1.1" width="{cw:.0f}" height="{ch:.0f}" viewBox="0 0 {cw:.0f} {ch:.0f}">'
        f"{skeleton}{''.join(parts)}</svg>"
    )


def _measure_editability(pptx_path: Path):
    from pptx import Presentation

    prs = Presentation(str(pptx_path))
    per, te, tsg = [], 0, 0
    for slide in prs.slides:
        e = sg = 0
        for sh in slide.shapes:
            if getattr(sh, "has_chart", False) or getattr(sh, "has_table", False):
                e += 1
                sg += 1
            elif getattr(sh, "has_text_frame", False) and sh.text_frame.text.strip():
                e += 1
                sg += 1
            elif str(getattr(sh, "shape_type", "")).startswith("PICTURE"):
                sg += 1
            elif getattr(sh, "has_text_frame", False):
                e += 1
                sg += 1
        per.append(round(e / sg, 4) if sg else 1.0)
        te += e
        tsg += sg
    return len(prs.slides), per, (round(te / tsg, 4) if tsg else 1.0)


def _rasterize(svg_path: Path, png_path: Path, block, palette, canvas, citation_labels: dict[str, str] | None = None) -> None:
    """Write a CJK-legible screenshot preview.

    The PPTX and HTML preview are sourced from the real SVG. For PNG screenshots,
    svglib/reportlab often renders CJK text as tofu even when the SVG is correct,
    so we use a deterministic PIL preview with the installed Noto CJK font.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        W, H = int(float(canvas.get("width_px", 1280))), int(float(canvas.get("height_px", 720)))

        def rgb(hx):
            hx = str(hx or "").strip()
            if hx.lower() in {"none", "transparent"} or hx.startswith("url("):
                return None
            hx = hx.lstrip("#")
            if len(hx) == 3:
                hx = "".join(ch * 2 for ch in hx)
            if len(hx) != 6:
                return None
            return tuple(int(hx[i: i + 2], 16) for i in (0, 2, 4))

        def font(sz, bold: bool = False):
            candidates = [
                os.path.expanduser("~/.fonts/NotoSansCJKsc-Bold.otf") if bold else CJK_FONT,
                CJK_FONT,
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
            for path in candidates:
                try:
                    if path and Path(path).exists():
                        return ImageFont.truetype(path, int(float(sz)))
                except Exception:
                    continue
            return ImageFont.load_default()

        def _float_attr(el, key, default=0.0):
            raw = str(el.attrib.get(key, default)).strip()
            m = re.search(r"-?\d+(?:\.\d+)?", raw)
            return float(m.group(0)) if m else float(default)

        def _color_attr(el, key, default=None):
            val = el.attrib.get(key, default)
            if val is None:
                return None
            return rgb(val)

        def _render_svg_primitives() -> bool:
            if not svg_path.exists():
                return False
            svg_text = svg_path.read_text(encoding="utf-8", errors="ignore")
            try:
                root = ET.fromstring(svg_text)
            except ET.ParseError:
                return False
            img = Image.new("RGB", (W, H), (255, 255, 255))
            d = ImageDraw.Draw(img)
            drawn = 0

            def local_name(el):
                return str(el.tag).rsplit("}", 1)[-1]

            def draw_node(el, ox=0.0, oy=0.0, svg_w=None, svg_h=None):
                nonlocal drawn
                tag = local_name(el)
                if tag == "svg" and el is not root:
                    nx = ox + _float_attr(el, "x", 0)
                    ny = oy + _float_attr(el, "y", 0)
                    nw = _float_attr(el, "width", svg_w or W)
                    nh = _float_attr(el, "height", svg_h or H)
                    for child in list(el):
                        draw_node(child, nx, ny, nw, nh)
                    return
                if tag == "rect":
                    x = ox + _float_attr(el, "x", 0)
                    y = oy + _float_attr(el, "y", 0)
                    w = _float_attr(el, "width", 0)
                    h = _float_attr(el, "height", 0)
                    fill = _color_attr(el, "fill")
                    stroke = _color_attr(el, "stroke")
                    sw = max(1, int(_float_attr(el, "stroke-width", 1)))
                    if fill:
                        d.rectangle([x, y, x + w, y + h], fill=fill)
                        drawn += 1
                    if stroke:
                        d.rectangle([x, y, x + w, y + h], outline=stroke, width=sw)
                        drawn += 1
                elif tag == "line":
                    stroke = _color_attr(el, "stroke")
                    if stroke:
                        sw = max(1, int(_float_attr(el, "stroke-width", 1)))
                        d.line([
                            ox + _float_attr(el, "x1", 0),
                            oy + _float_attr(el, "y1", 0),
                            ox + _float_attr(el, "x2", 0),
                            oy + _float_attr(el, "y2", 0),
                        ], fill=stroke, width=sw)
                        drawn += 1
                elif tag == "circle":
                    fill = _color_attr(el, "fill")
                    stroke = _color_attr(el, "stroke")
                    r = _float_attr(el, "r", 0)
                    cx = ox + _float_attr(el, "cx", 0)
                    cy = oy + _float_attr(el, "cy", 0)
                    box = [cx - r, cy - r, cx + r, cy + r]
                    if fill:
                        d.ellipse(box, fill=fill)
                        drawn += 1
                    if stroke:
                        d.ellipse(box, outline=stroke, width=max(1, int(_float_attr(el, "stroke-width", 1))))
                        drawn += 1
                elif tag == "image":
                    href = el.attrib.get("href") or el.attrib.get("{http://www.w3.org/1999/xlink}href")
                    if href:
                        raw_w = _float_attr(el, "width", 0)
                        raw_h = _float_attr(el, "height", 0)
                        x = ox + _float_attr(el, "x", 0)
                        y = oy + _float_attr(el, "y", 0)
                        w = (svg_w or raw_w) if raw_w <= 2 and svg_w else raw_w
                        h = (svg_h or raw_h) if raw_h <= 2 and svg_h else raw_h
                        img_path = (svg_path.parent / href).resolve()
                        if img_path.exists() and w > 2 and h > 2:
                            try:
                                im = Image.open(img_path).convert("RGB").resize((int(w), int(h)))
                                img.paste(im, (int(x), int(y)))
                                drawn += 1
                            except Exception:
                                pass
                elif tag == "text":
                    value = "".join(el.itertext()).strip()
                    if value:
                        size = _float_attr(el, "font-size", 18)
                        fill = _color_attr(el, "fill", "#000000") or (0, 0, 0)
                        weight = str(el.attrib.get("font-weight") or "").lower()
                        fnt = font(size, bold=weight in {"bold", "700", "800", "900"})
                        x = ox + _float_attr(el, "x", 0)
                        y = oy + _float_attr(el, "y", 0) - size * 0.82
                        anchor = str(el.attrib.get("text-anchor") or "start")
                        try:
                            bbox = d.textbbox((0, 0), value, font=fnt)
                            tw = bbox[2] - bbox[0]
                        except Exception:
                            tw = len(value) * size * 0.55
                        if anchor == "middle":
                            x -= tw / 2
                        elif anchor == "end":
                            x -= tw
                        d.text((x, y), value, fill=fill, font=fnt)
                        drawn += 1
                for child in list(el):
                    if tag != "svg" or el is root:
                        draw_node(child, ox, oy, svg_w, svg_h)

            draw_node(root)
            if drawn:
                img.save(str(png_path))
                return True
            return False

        if _render_svg_primitives():
            return

        img = Image.new("RGB", (W, H), (255, 255, 255))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 14], fill=rgb(palette["primary"]) or (23, 50, 77))

        def draw_wrapped(x, y, text_value, text_font, fill, max_w, max_lines=2, line_h=24):
            try:
                sz = float(getattr(text_font, "size", 18))
            except Exception:
                sz = 18.0
            for line in _fit_lines(str(text_value or ""), sz, max_w, max_lines):
                d.text((x, y), line, fill=fill, font=text_font)
                y += line_h
            return y

        title_font = font(40)
        body_font = font(24)
        small_font = font(18)
        draw_wrapped(60, 54, block.get("title") or "", title_font, rgb(palette["primary"]), W - 120, max_lines=1, line_h=48)
        d.rectangle([60, 116, 480, 122], fill=rgb(palette["accent"]))
        # Render a visual preview zone by inspecting simple SVG group ids.
        svg_text = svg_path.read_text(encoding="utf-8", errors="ignore") if svg_path.exists() else ""
        primary = rgb(palette["primary"])
        accent = rgb(palette["accent"])
        neutral = rgb(palette["neutral"])
        text = rgb(palette["text"])
        side = _visual_region(canvas)
        table_region = _visual_region(canvas, mode="table")
        if "component-evidence-two-box" not in svg_text and "visual-table" not in svg_text and not block.get("table"):
            yy = 150
            body_w = max(260, int(side["x"] - 90))
            compact_preview = any(marker in svg_text for marker in ("visual-flow", "visual-architecture", "visual-roadmap"))
            preview_limit = 1 if compact_preview else 5
            for p in (block.get("paragraphs") or [])[:preview_limit]:
                yy = draw_wrapped(60, yy, _replace_citation_tokens("• " + str(p), citation_labels), body_font, rgb(palette["text"]), body_w, max_lines=2, line_h=31)
                yy += 7
        if "component-evidence-two-box" in svg_text:
            claim = _replace_citation_tokens(block.get("claim") or ((block.get("paragraphs") or [""])[0]), citation_labels)
            evidence = _replace_citation_tokens(block.get("evidence_sentence") or "", citation_labels)
            d.rounded_rectangle([60, 138, W - 60, 214], radius=8, fill=neutral)
            d.rectangle([60, 138, 68, 214], fill=accent)
            yy_claim = draw_wrapped(86, 153, claim, font(21), text, W - 172, max_lines=1, line_h=26)
            if evidence and evidence != claim:
                draw_wrapped(86, yy_claim + 5, f"依据：{evidence}", font(14), primary, W - 172, max_lines=1, line_h=19)
            for x, box, heading in [(78, block.get("left_box") or {}, "依据分析"), (657, block.get("right_box") or {}, "方案含义")]:
                d.rounded_rectangle([x, 246, x + 545, 566], radius=8, outline=primary, width=2, fill=(255, 255, 255))
                d.rectangle([x, 246, x + 545, 290], fill=primary)
                draw_wrapped(x + 18, 258, box.get("heading") or heading, small_font, (255, 255, 255), 500, max_lines=1, line_h=22)
                yy = 320
                body = box.get("body") or []
                if isinstance(body, str):
                    body = [body]
                for item in body[:3]:
                    d.ellipse([x + 22, yy + 5, x + 30, yy + 13], fill=accent)
                    yy = draw_wrapped(x + 42, yy, _replace_citation_tokens(item, citation_labels), font(16), text, 470, max_lines=2, line_h=22)
                    yy += 18
            cites = _slide_citation_footnotes(block, {}, citation_labels)
            if cites:
                draw_wrapped(60, H - 44, cites, font(11), (128, 128, 128), W - 260, max_lines=1, line_h=14)
        elif "visual-quadrant" in svg_text:
            labels = ["What", "When", "How", "Where"]
            nodes = (_nodes(block) + labels)[:4]
            x0, y0, gap = int(side["x"]), int(side["y"]), 14
            card_w = int((side["width"] - gap) / 2)
            card_h = int(min(118, (side["height"] - gap) / 2))
            for i in range(4):
                x = x0 + (i % 2) * (card_w + gap)
                y = y0 + (i // 2) * (card_h + gap)
                d.rounded_rectangle([x, y, x + card_w, y + card_h], radius=8, outline=primary, width=2, fill=(255, 255, 255))
                d.text((x + 16, y + 22), labels[i], fill=accent, font=body_font)
                draw_wrapped(x + 16, y + 62, nodes[i], small_font, text, card_w - 32, max_lines=2, line_h=22)
        elif "visual-cycle" in svg_text:
            cx, cy = int(side["x"] + side["width"] / 2), int(side["y"] + side["height"] / 2)
            d.ellipse([cx - 62, cy - 62, cx + 62, cy + 62], outline=primary, width=2, fill=neutral)
            d.text((cx - 28, cy - 14), "Loop", fill=primary, font=body_font)
            rad = int(min(side["width"], side["height"]) * 0.31)
            for x, y, label in [(cx, cy - rad), (cx + rad, cy), (cx, cy + rad), (cx - rad, cy)]:
                d.ellipse([x - 54, y - 54, x + 54, y + 54], outline=primary, width=2, fill=(255, 255, 255))
                d.text((x - 24, y - 14), label, fill=text, font=small_font)
        elif "visual-table" in svg_text or block.get("table"):
            rows = block.get("table") or []
            if not rows:
                rows = _table_from_boxes(block)
            x0, y0, w = int(table_region["x"]), int(table_region["y"]), int(table_region["width"])
            ncols = max((len(r) for r in rows), default=3)
            rh, cw = min(48, max(34, int(table_region["height"] // max(1, min(len(rows), 5))))), w // ncols
            for r, row in enumerate(rows[:5]):
                for c in range(ncols):
                    x, y = x0 + c * cw, y0 + r * rh
                    fill = primary if r == 0 else (neutral if r % 2 else (255, 255, 255))
                    color = (255, 255, 255) if r == 0 else text
                    d.rectangle([x, y, x + cw, y + rh], outline=primary, fill=fill)
                    cell = row[c] if c < len(row) else ""
                    if r == 0:
                        draw_wrapped(x + 12, y + 16, cell, small_font, color, cw - 24, max_lines=1, line_h=18)
                    else:
                        draw_wrapped(x + 12, y + 10, cell, font(15), color, cw - 24, max_lines=2, line_h=18)
        elif "visual-image-panel" in svg_text:
            x, y, w, h = int(side["x"]), int(side["y"]), int(side["width"]), int(side["height"])
            d.rounded_rectangle([x, y, x + w, y + h], radius=28, fill=neutral)
            m = re.search(r'href="([^"]+)"', svg_text)
            img_path = None
            if m:
                img_path = (svg_path.parent / m.group(1)).resolve()
            if img_path and img_path.exists():
                try:
                    im = Image.open(img_path).convert("RGB")
                    im.thumbnail((w - 36, h - 36))
                    px = x + (w - im.width) // 2
                    py = y + (h - im.height) // 2
                    img.paste(im, (px, py))
                except Exception:
                    img_path = None
        elif "visual-roadmap" in svg_text:
            nodes = (_box_nodes(block) + ["热度分层缓存", "KV offload", "近存卸载", "3D近存/端云"])[:4]
            x0 = int(side["x"])
            y = int(side["y"] + side["height"] * 0.42)
            w = int(side["width"])
            card_w = min(104, max(78, int((w - 24) / 4)))
            step = int((w - card_w) / 3) if len(nodes) > 1 else 0
            d.line([x0 + card_w // 2, y, x0 + w - card_w // 2, y], fill=accent, width=4)
            for i, node in enumerate(nodes):
                px = x0 + card_w // 2 + i * step
                d.ellipse([px - 20, y - 20, px + 20, y + 20], fill=primary)
                d.text((px - 12, y - 58), f"0{i + 1}", fill=accent, font=small_font)
                d.rounded_rectangle([px - card_w // 2, y + 30, px + card_w // 2, y + 126], radius=8, outline=primary, width=2, fill=(255, 255, 255))
                draw_wrapped(px - card_w // 2 + 8, y + 50, _replace_citation_tokens(node, citation_labels), font(14), text, card_w - 16, max_lines=3, line_h=18)
        elif "visual-architecture" in svg_text or "visual-flow" in svg_text:
            nodes = _nodes(block)[:4]
            x = int(side["x"])
            box_w = int(side["width"])
            box_h = min(64, max(50, int((side["height"] - 48) / 4)))
            gap = max(10, int((side["height"] - box_h * 4) / 3))
            for i, node in enumerate(nodes):
                y = int(side["y"]) + i * (box_h + gap)
                d.rounded_rectangle([x, y, x + box_w, y + box_h], radius=8, outline=primary, width=2, fill=neutral if i % 2 else (255, 255, 255))
                d.rectangle([x, y, x + 10, y + box_h], fill=accent)
                draw_wrapped(x + 24, y + 18, _replace_citation_tokens(node, citation_labels), small_font, text, box_w - 44, max_lines=2, line_h=20)
        img.save(str(png_path))
    except Exception:
        png_path.write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        ))


def _finalize_svg_output(build: Path, scripts_dir: Path) -> dict:
    """Run the fused, deterministic SVG finalization subset before PPTX export."""
    svg_dir = build / "svg_output"
    report = {
        "enabled": os.environ.get("PPT_SVG_FINALIZATION", "true").lower() == "true",
        "flatten_tspan": "not-run",
        "validated_files": 0,
    }
    if not report["enabled"]:
        return report
    finalize_dir = scripts_dir / "svg_finalize"
    sys.path.insert(0, str(finalize_dir))
    try:
        import flatten_tspan  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"SVG finalization module unavailable: {exc}") from exc

    changed = 0
    total = 0
    for svg_path in sorted(svg_dir.glob("*.svg")):
        total += 1
        if flatten_tspan.process_svg_file(str(svg_path), str(svg_path), merge_paragraphs=False):
            changed += 1
        try:
            ET.parse(svg_path)
        except ET.ParseError as exc:
            raise RuntimeError(f"finalized SVG is not well-formed: {svg_path.name}: {exc}") from exc
    report["flatten_tspan"] = f"{changed}/{total}"
    report["validated_files"] = total
    return report


def render(run_dir, out_dir, blocks, smoke, backend, min_ratio, scripts_dir, profile, slide_count_expected):
    run_dir = Path(run_dir)
    out_dir = Path(out_dir)
    scripts_dir = Path(scripts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    palette = {k: _hex(profile.get("palette", {}).get(k, d), d) for k, d in (
        ("primary", "#17324D"), ("accent", "#DCA24C"), ("secondary", "#2E7D8A"),
        ("neutral", "#F6F7F9"), ("text", "#151A1F"))}
    canvas = profile.get("canvas", {"width_px": 1280, "height_px": 720})
    page_layouts = profile.get("page_type_layouts", {})
    import_dir = (run_dir / profile["template_import_dir"]).resolve() if profile.get("template_import_dir") else None
    svg_lib = import_dir / "svg" if import_dir else None
    assets_src = import_dir / "assets" if import_dir else None
    free_page_generation = bool(profile.get("free_page_generation"))

    # Preload + cache each page-type's layout skeleton inner markup.
    has_lab_contract = bool(profile.get("lab_template_contract"))
    for pt, L in page_layouts.items():
        if svg_lib and L.get("svg") and (not free_page_generation or pt in {"cover", "ending"}):
            L["_skeleton_inner"] = _layout_skeleton_inner(
                svg_lib / (L.get("svg") or ""),
                strip_lab_footer=has_lab_contract,
                strip_placeholders=has_lab_contract,
            )
        else:
            L["_skeleton_inner"] = ""

    layouts = _visual_layouts(run_dir)
    visuals = _visual_plan(run_dir)
    citation_labels = _citation_map(run_dir)
    total = len(blocks)

    # Draft-reuse mode: when env var PPT_DRAFT_REUSE=1, the renderer pastes the source
    # slide SVG verbatim for every slide that carries a source_slide_svg_ref so the
    # user can confirm reuse before downstream rewrites. Per project policy, draft
    # is "full copy first; later stages decide what to modify".
    draft_reuse_mode = os.environ.get("PPT_DRAFT_REUSE", "0") == "1"

    # SVG build project (svg_output/ + assets/) for ppt-master's converter.
    build = out_dir / "svg_build"
    if build.exists():
        shutil.rmtree(build)
    (build / "svg_output").mkdir(parents=True, exist_ok=True)
    if assets_src and assets_src.exists():
        shutil.copytree(assets_src, build / "assets", dirs_exist_ok=True)
    if (run_dir / "assets").exists():
        shutil.copytree(run_dir / "assets", build / "assets", dirs_exist_ok=True)
    _stage_visual_assets(run_dir, build, visuals)

    for i, blk in enumerate(blocks, 1):
        pt = _page_type(layouts.get(i, ""), i, total)
        visual = visuals.get(i, {"layout_type": layouts.get(i, "")})
        if isinstance(blk, dict):
            blk["_visual_plan"] = visual
        # Detect direct slide reuse intent. The visual plan can declare reuse explicitly
        # (reuse_mode in {direct_slide_reuse, partial_slide_reuse}) and point to a source
        # SVG via source_slide_svg_ref. Fall back to template_svg when reuse_mode says so.
        reuse_mode = str(visual.get("reuse_mode") or "")
        is_direct_reuse = reuse_mode in {"direct_slide_reuse", "partial_slide_reuse"}
        source_slide_ref = str(visual.get("source_slide_svg_ref") or "")

        # Draft-reuse short-circuit: paste the source slide_XX.svg verbatim into
        # svg_output/. Skips build_slide_svg entirely so what the user sees in
        # draft-deck.pptx is the original slide.
        if draft_reuse_mode and source_slide_ref:
            src_path = _resolve_template_svg(import_dir, source_slide_ref, run_dir)
            if src_path and src_path.exists():
                try:
                    text = src_path.read_text(encoding="utf-8")
                    text = _strip_tiny_image_refs(text, src_path)
                    tgt_w = float(canvas.get("width_px") or 1280)
                    tgt_h = float(canvas.get("height_px") or 720)
                    text = _normalize_svg_viewbox(text, tgt_w, tgt_h)

                    # Inject gap warning overlay for partial / weak fits.
                    reuse_fit = str(visual.get("reuse_fit") or "")
                    if reuse_fit in ("partial", "weak"):
                        gap_summary = ""
                        gtypes = visual.get("gap_types") or []
                        if gtypes:
                            gap_summary = "/".join(gtypes[:2])
                        overlay = _gap_warning_overlay(reuse_fit, gap_summary, tgt_w, tgt_h)
                        if overlay:
                            close_idx = text.rfind('</svg>')
                            if close_idx != -1:
                                text = text[:close_idx] + overlay + text[close_idx:]

                    (build / "svg_output" / f"slide_{i:02d}.svg").write_text(text, encoding="utf-8")
                    # Stage assets co-located with the source slide so picture refs
                    # inside the SVG resolve at SVG-to-DrawingML conversion time.
                    src_root = src_path.parent.parent if src_path.parent.name in {"svg", "svg-flat"} else src_path.parent
                    src_assets = src_root / "assets"
                    if src_assets.exists():
                        for f in src_assets.iterdir():
                            if f.is_file():
                                # Skip the tiny placeholders entirely — they
                                # were dropped from the SVG above.
                                if f.stat().st_size < 2048:
                                    continue
                                tgt = build / "assets" / f.name
                                if not tgt.exists():
                                    shutil.copy2(f, tgt)
                    continue
                except Exception:
                    # fall through to standard rendering on read error
                    pass

        base_pl = page_layouts.get(pt) or page_layouts.get("content") or next(iter(page_layouts.values()))
        pl = dict(base_pl)
        content_regions = visual.get("content_regions") if isinstance(visual.get("content_regions"), dict) else {}
        if isinstance(content_regions.get("title"), dict):
            pl["title_region"] = content_regions["title"]
        if isinstance(content_regions.get("body"), dict):
            pl["body_region"] = content_regions["body"]
        skeleton_ref = "" if free_page_generation and pt not in {"cover", "ending"} else visual.get("template_svg")
        if is_direct_reuse and source_slide_ref:
            # Direct slide reuse takes precedence: use the per-slide source SVG even
            # for content pages on lab-contract templates.
            skeleton_ref = source_slide_ref
        elif has_lab_contract and pt not in {"cover", "ending"}:
            # For the required DAI base template, content pages may reference
            # source slides for inspiration, but their SVG bodies must not be
            # pasted into the generated deck. The dynamic renderer owns the body.
            skeleton_ref = ""
        lab_copy_assets = False
        if not skeleton_ref and (not free_page_generation or pt in {"cover", "ending"}):
            skeleton_ref, lab_copy_assets = _lab_reuse_skeleton(profile, pt)
        skeleton_path = _resolve_template_svg(import_dir, skeleton_ref, run_dir)
        if skeleton_path:
            policy = visual.get("adaptation_policy") if isinstance(visual.get("adaptation_policy"), dict) else {}
            template_source = visual.get("template_source") if isinstance(visual.get("template_source"), dict) else {}
            source_policy = template_source.get("adaptation_policy") if isinstance(template_source.get("adaptation_policy"), dict) else {}
            copy_assets = bool(
                lab_copy_assets
                or _lab_reuse_allows_assets(profile, pt, skeleton_ref)
                or policy.get("copy_assets")
                or source_policy.get("copy_assets")
                or is_direct_reuse
            )
            pl["_skeleton_inner"] = _layout_skeleton_inner(
                skeleton_path,
                strip_slide_content_images=(str(skeleton_ref).startswith("svg-flat/slide_") and not is_direct_reuse),
                strip_all_images=(not copy_assets) and (not is_direct_reuse),
                strip_lab_footer=has_lab_contract and not is_direct_reuse,
                strip_placeholders=has_lab_contract and not is_direct_reuse,
                preserve_full_slide=(reuse_mode == "direct_slide_reuse"),
            )
            try:
                pl["_skeleton_source"] = str(skeleton_path.relative_to(import_dir)) if import_dir else str(skeleton_path)
            except ValueError:
                # skeleton_path resolved outside import_dir (cross-deck reuse via run_dir)
                try:
                    pl["_skeleton_source"] = str(skeleton_path.relative_to(run_dir))
                except ValueError:
                    pl["_skeleton_source"] = str(skeleton_path)
        # Gap-page card short-circuit: when this is a placeholder, emit a
        # full-canvas Gap Page card instead of letting build_slide_svg draw
        # the stripped template skeleton + body text.
        draft_action_kind = str(visual.get("draft_action_kind") or visual.get("draft_action") or "")
        if draft_reuse_mode and draft_action_kind in ("placeholder", "new_slide_placeholder"):
            tgt_w = float(canvas.get("width_px") or 1280)
            tgt_h = float(canvas.get("height_px") or 720)
            target_title = str(blk.get("title") or visual.get("target_title") or "")
            target_claim = str(visual.get("target_claim") or "")
            plan_note = str(visual.get("plan_note") or "")
            key_points = visual.get("key_points") if isinstance(visual.get("key_points"), list) else []
            evidence_needed = visual.get("evidence_needed") if isinstance(visual.get("evidence_needed"), list) else []
            gap_types = visual.get("gap_types") if isinstance(visual.get("gap_types"), list) else []
            next_action = visual.get("next_action") or ""
            gap_svg = _gap_page_card_svg(target_title, target_claim, plan_note,
                                          key_points, evidence_needed, gap_types,
                                          next_action, tgt_w, tgt_h)
            (build / "svg_output" / f"slide_{i:02d}.svg").write_text(gap_svg, encoding="utf-8")
            continue

        svg = build_slide_svg(
            blk, pl, palette, canvas,
            is_cover=(pt in ("cover", "ending")),
            total_idx=i,
            visual=visual,
            citation_labels=citation_labels,
            profile=profile,
            page_kind=pt,
        )
        (build / "svg_output" / f"slide_{i:02d}.svg").write_text(svg, encoding="utf-8")

    svg_finalize = _finalize_svg_output(build, scripts_dir)

    # Export native editable DrawingML via the fused SVG-to-DrawingML converter.
    deck_path = out_dir / "deck.pptx"
    conv = scripts_dir / "svg_to_pptx.py"
    proc = subprocess.run(
        [sys.executable, str(conv), str(build), "-s", "output", "--only", "native",
         "-a", "none", "-o", str(deck_path)],
        capture_output=True, text=True,
    )
    if not deck_path.exists():
        sys.stderr.write(f"[svg_skeleton_render] svg_to_pptx failed:\n{proc.stdout[-800:]}\n{proc.stderr[-1200:]}\n")
        raise SystemExit(1)
    if not smoke and (run_dir / "speaker-notes.md").exists():
        speaker_notes.embed_notes(deck_path, run_dir / "speaker-notes.md")
    if not smoke and (run_dir / "transition-plan.json").exists():
        presentation_effects.apply_transitions(deck_path, run_dir / "transition-plan.json")

    # Screenshots + HTML preview from the per-slide SVGs.
    shot_dir = out_dir / "screenshots"
    html_dir = out_dir / "slides-html"
    shot_dir.mkdir(exist_ok=True)
    html_dir.mkdir(exist_ok=True)
    for i, blk in enumerate(blocks, 1):
        svg_path = build / "svg_output" / f"slide_{i:02d}.svg"
        _rasterize(svg_path, shot_dir / f"slide-{i}.png", blk, palette, canvas, citation_labels=citation_labels)
        svg_inline = svg_path.read_text(encoding="utf-8")
        (html_dir / f"slide-{i}.html").write_text(
            f"<!doctype html><meta charset=utf-8><title>{_esc(blk.get('title',''))}</title>"
            f"<section>{svg_inline}</section>\n", encoding="utf-8")

    page_count, per_slide, aggregate = _measure_editability(deck_path)
    expected = len(blocks) if smoke else slide_count_expected
    ts = _now()
    lines = [
        "---", 'schema_version: "1.0"', f'generated_at: "{ts}"',
        'render_mode: "real"', f'backend: "{backend}"', f"smoke: {str(bool(smoke)).lower()}",
        f"slide_count: {expected}", f"page_count: {page_count}",
        f"page_count_ok: {str(page_count == expected).lower()}", "openable: true",
        "assets_ok: true", f"aggregate_editable_ratio: {aggregate}",
        f"min_editable_ratio: {min_ratio}", f"render_path: {'ppt-master-free' if free_page_generation else 'skeleton'}",
        f"svg_finalization_enabled: {str(svg_finalize['enabled']).lower()}",
        f"svg_finalization_flatten_tspan: \"{svg_finalize['flatten_tspan']}\"",
        f"svg_finalization_validated_files: {svg_finalize['validated_files']}",
        "---", "",
        "## Per-slide editable_ratio",
    ]
    for i, r in enumerate(per_slide, 1):
        lines.append(f"- slide {i}: {r}")
    (out_dir / "render-log.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[svg-skeleton] rendered {page_count} slide(s) via template skeleton -> {deck_path} "
          f"(editable_ratio={aggregate})")
    return page_count
