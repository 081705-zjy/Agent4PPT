#!/usr/bin/env python3
"""template_ingest.py — process a user .pptx template the ppt-master way, BEFORE topic work.

This is the ppt-agent side of "模板包 → 项目模板目录 → 锁定规范". Given a `.pptx`
reference in <project>/templates/, it:

  1. Runs ppt-master's `pptx_template_import.py` (idempotent) to build the template
     package: <project>/templates/<stem>_template_import/{manifest.json, svg/, svg-flat/,
     assets/}. The manifest is the single source of truth (real theme colors, fonts,
     canvas, per-layout placeholder geometry, page-type candidates).
  2. Derives a REAL `template-profile.json` from that manifest (no more hardcoded
     placeholder palette) — including the page-type → layout-skeleton mapping and the
     placeholder regions the renderer injects editable text into.
  3. Writes `spec_lock.md`: the locked, machine-readable contract the renderer obeys per
     page (colors, fonts, canvas, which layout SVG + content regions each page type uses).

The render stage (scripts/lib/svg_skeleton_render.py) inherits each page's layout SVG
skeleton and exports native editable DrawingML via ppt-master's svg_to_pptx.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path


def vendored_scripts_dir(ppt_agent_root: Path) -> Path:
    """ppt-master's template-import + svg_to_pptx modules are vendored INTO ppt-agent
    (scripts/lib/ppt_master) so there is no runtime dependency on an external checkout."""
    return ppt_agent_root / "scripts" / "lib" / "ppt_master"


# Back-compat alias (older callers); the external arg is ignored — always vendored.
def ppt_master_scripts_dir(ppt_agent_root: Path, ppt_master_dir: str | None = None) -> Path:
    return vendored_scripts_dir(ppt_agent_root)


def run_importer(pptx: Path, import_dir: Path, scripts_dir: Path) -> bool:
    """Run ppt-master's importer unless the package is already fresh. Returns ok."""
    manifest = import_dir / "manifest.json"
    if manifest.exists() and manifest.stat().st_mtime >= pptx.stat().st_mtime:
        return True  # cached, up to date
    importer = scripts_dir / "pptx_template_import.py"
    if not importer.exists():
        sys.stderr.write(f"[template_ingest] importer not found: {importer}\n")
        return False
    import_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(importer), str(pptx), "-o", str(import_dir)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not manifest.exists():
        sys.stderr.write(f"[template_ingest] import failed:\n{proc.stderr[-1500:]}\n")
        return False
    return True


def _norm_hex(value: str, default: str) -> str:
    v = str(value or "").strip().lstrip("#")
    return f"#{v.upper()}" if re.fullmatch(r"[0-9A-Fa-f]{6}", v) else default


def palette_from_theme(colors: dict) -> dict:
    """Map OOXML theme colors to ppt-agent's role palette (kept faithful to the source)."""
    return {
        "text": _norm_hex(colors.get("dk1"), "#151A1F"),
        "primary": _norm_hex(colors.get("dk2"), "#17324D"),
        "accent": _norm_hex(colors.get("accent1"), "#DCA24C"),
        "secondary": _norm_hex(colors.get("accent5") or colors.get("accent2"), "#2E7D8A"),
        "neutral": _norm_hex(colors.get("lt2"), "#F6F7F9"),
    }


def _region(ph: dict) -> dict:
    g = ph.get("geometry") or {}
    return {
        "x": float(g.get("x", 0)),
        "y": float(g.get("y", 0)),
        "width": float(g.get("width", 0)),
        "height": float(g.get("height", 0)),
    }


def _slot_base(ph: dict) -> str:
    """Map OOXML placeholder metadata into ppt-agent's typed layout slots."""
    t = str(ph.get("type") or "").strip().lower()
    samples = " ".join(str(x) for x in (ph.get("textSamples") or [])).lower()
    if t in ("title", "ctrtitle"):
        return "title"
    if t in ("subtitle", "subTitle".lower()):
        return "subtitle"
    if t in ("body", "obj", ""):
        return "body"
    if t in ("pic", "picture", "media", "clipart"):
        return "image"
    if t in ("chart",):
        return "chart"
    if t in ("tbl", "table"):
        return "table"
    if t in ("ftr", "footer"):
        return "footer"
    if t in ("sldnum", "slide_number"):
        return "slide_number"
    if t in ("dt", "date"):
        return "date"
    if "logo" in samples:
        return "logo"
    return "body"


def _put_slot(slots: dict, base: str, region: dict, ph: dict | None = None) -> None:
    """Insert a slot, suffixing duplicates while preserving the primary name."""
    if region["width"] <= 0 or region["height"] <= 0:
        return
    name = base
    if name in slots:
        n = 2
        while f"{base}_{n}" in slots:
            n += 1
        name = f"{base}_{n}"
    record = dict(region)
    if ph:
        if ph.get("type") is not None:
            record["source_type"] = ph.get("type")
        if ph.get("idx") is not None:
            record["source_idx"] = ph.get("idx")
    slots[name] = record


def layout_slots(layout: dict, title: dict, body: dict) -> dict:
    """Return typed layout slots derived from the imported template manifest.

    `title` and `body` are always present as compatibility anchors. Additional
    placeholders become typed slots used by planning and validation.
    """
    slots: dict = {}
    for ph in layout.get("placeholders", []) or []:
        reg = _region(ph)
        _put_slot(slots, _slot_base(ph), reg, ph)
    if "title" not in slots:
        slots["title"] = dict(title)
    if "body" not in slots:
        slots["body"] = dict(body)
    return slots


def layout_affordances(slots: dict) -> dict:
    names = set(slots)
    return {
        "slots": sorted(names),
        "supports_subtitle": "subtitle" in names,
        "supports_image": any(k.startswith("image") or k == "logo" for k in names),
        "supports_chart": any(k.startswith("chart") for k in names),
        "supports_table": any(k.startswith("table") for k in names),
        "supports_footer": any(k in names for k in ("footer", "slide_number", "date")),
        "body_slot_count": sum(1 for k in names if k.startswith("body")),
    }


def extract_layout(layout: dict, canvas_w: float, canvas_h: float) -> dict:
    """Pick the title + body content regions from a layout's placeholders."""
    placeholders = layout.get("placeholders", []) or []
    title = None
    body = None
    for ph in placeholders:
        t = (ph.get("type") or "").lower()
        reg = _region(ph)
        if reg["width"] <= 0 or reg["height"] <= 0:
            continue
        if t == "title" and title is None:
            title = reg
        elif t in ("body", "subtitle", "") and body is None and t != "title":
            body = reg
    # Body fallback: the largest non-title placeholder region.
    if body is None:
        cands = [_region(p) for p in placeholders if (p.get("type") or "").lower() != "title"]
        cands = [r for r in cands if r["width"] > 0 and r["height"] > 0]
        if cands:
            body = max(cands, key=lambda r: r["width"] * r["height"])
    if title is None:
        title = {"x": 0.07 * canvas_w, "y": 0.05 * canvas_h, "width": 0.86 * canvas_w, "height": 0.16 * canvas_h}
    if body is None:
        by = title["y"] + title["height"] + 0.03 * canvas_h
        body = {"x": title["x"], "y": by, "width": 0.86 * canvas_w, "height": canvas_h - by - 0.06 * canvas_h}
    slots = layout_slots(layout, title, body)
    return {
        "name": layout.get("name"),
        "svg": layout.get("svgFile"),
        "title_region": title,
        "body_region": body,
        "layout_slots": slots,
        "layout_affordances": layout_affordances(slots),
    }


def page_type_layouts(manifest: dict, canvas_w: float, canvas_h: float) -> dict:
    """Map each page type (cover/content/chapter/ending) to its representative layout."""
    layouts = manifest.get("layouts", []) or []
    by_name = {L.get("name"): L for L in layouts}
    slides = manifest.get("slides", []) or []
    ptc = manifest.get("pageTypeCandidates", {}) or {}

    def layout_for(indices):
        c = Counter()
        for s in slides:
            if s.get("index") in indices:
                c[os.path.basename(s.get("layoutPath", ""))] += 1
        if not c:
            return None
        return by_name.get(c.most_common(1)[0][0])

    out = {}
    content_idx = ptc.get("content_candidate", [])
    for ptype, key in (
        ("cover", "cover_candidate"),
        ("content", "content_candidate"),
        ("chapter", "chapter_candidate"),
        ("ending", "ending_candidate"),
    ):
        L = layout_for(ptc.get(key, [])) or layout_for(content_idx) or (layouts[0] if layouts else None)
        if L:
            out[ptype] = extract_layout(L, canvas_w, canvas_h)
    return out


def layout_catalog(manifest: dict, canvas_w: float, canvas_h: float) -> list[dict]:
    """Expose every imported layout, not only the representative page-type layouts."""
    out = []
    for layout in manifest.get("layouts", []) or []:
        item = extract_layout(layout, canvas_w, canvas_h)
        item["kind"] = "layout"
        item["shape_count"] = int(layout.get("shapeCount") or 0)
        item["text_count"] = int(layout.get("textCount") or 0)
        item["template_svg"] = f"svg/{item['svg']}" if item.get("svg") else None
        out.append(item)
    return out


def source_slide_catalog(manifest: dict) -> list[dict]:
    """Expose ppt-master's per-slide SVG exemplars as reusable render skeletons.

    The flat SVGs preserve real master/layout/slide furniture. The renderer strips
    text before injecting new content, so these work as visual exemplars rather than
    copied content slides.
    """
    out = []
    for slide in manifest.get("slides", []) or []:
        idx = int(slide.get("index") or 0)
        if idx <= 0:
            continue
        flat = slide.get("flatSvgFile") or slide.get("svgFile")
        layered = slide.get("svgFile")
        page_type = str(slide.get("pageType") or "")
        role = (
            "cover" if "cover" in page_type else
            "ending" if "ending" in page_type else
            "chapter" if "chapter" in page_type else
            "content"
        )
        out.append({
            "kind": "source_slide",
            "index": idx,
            "role": role,
            "page_type": page_type,
            "template_svg": f"svg-flat/{flat}" if flat else (f"svg/{layered}" if layered else None),
            "layered_svg": f"svg/{layered}" if layered else None,
            "layout_path": slide.get("layoutPath"),
            "shape_count": int(slide.get("shapeCount") or 0),
            "text_count": int(slide.get("textCount") or 0),
            "image_assets": slide.get("imageAssets") or [],
            "text_samples": slide.get("textSamples") or [],
        })
    return out


def slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", str(text).strip()).strip("-").lower()
    return s[:48] or "template"


def build_profile(pptx: Path, import_dir: Path, project_dir: Path | None) -> dict:
    manifest = json.loads((import_dir / "manifest.json").read_text(encoding="utf-8"))
    size = manifest.get("slideSize", {})
    cw = float(size.get("width_px") or 1280)
    ch = float(size.get("height_px") or 720)
    colors = manifest.get("theme", {}).get("colors", {}) or {}
    fonts = manifest.get("theme", {}).get("fonts", {}) or {}
    palette = palette_from_theme(colors)
    # template_import_dir relative to project dir (so the render dir is portable).
    if project_dir:
        try:
            rel_import = os.path.relpath(import_dir, project_dir)
        except ValueError:
            rel_import = str(import_dir)
    else:
        rel_import = str(import_dir)

    profile = {
        "schema_version": "1.0",
        "template_id": slug(pptx.stem),
        "name": pptx.stem,
        "description": (
            "Real template profile derived from the user PPTX via ppt-master import. "
            "The render stage inherits each page's layout SVG skeleton and exports native "
            "editable DrawingML (svg_to_pptx)."
        ),
        "source_pptx": str(pptx),
        "source_slide_count": len(manifest.get("slides", []) or []),
        "source_slide_width": int(size.get("width_emu") or 0),
        "source_slide_height": int(size.get("height_emu") or 0),
        "palette": palette,
        "theme_colors": {k: _norm_hex(v, "#000000") for k, v in colors.items()},
        "typography": {
            "heading": fonts.get("majorLatin") or "Arial",
            "body": fonts.get("minorLatin") or "Arial",
            "heading_size": 32,
            "body_size": 18,
        },
        "canvas": {"width_px": cw, "height_px": ch},
        "layouts": {
            "title-image": "Inherited from the template cover layout skeleton.",
            "title-and-body": "Inherited from the template content layout skeleton.",
            "closing": "Inherited from the template ending layout skeleton.",
        },
        "render": {
            "accent_bar_height": 0.25,
            "picture_x": 6.45,
            "picture_y": 1.2,
            "picture_w": 3.0,
            "picture_h": 1.7,
        },
        "template_import_dir": rel_import,
        "skeleton_render": True,
        "page_type_layouts": page_type_layouts(manifest, cw, ch),
        "layout_catalog": layout_catalog(manifest, cw, ch),
        "source_slide_catalog": source_slide_catalog(manifest),
        "_path": str(pptx),
    }
    return profile


def write_spec_lock(profile: dict, project_dir: Path) -> None:
    pal = profile["palette"]
    typ = profile["typography"]
    cv = profile["canvas"]
    lines = [
        "---",
        'schema_version: "1.0"',
        f'template_id: "{profile["template_id"]}"',
        f'source_pptx: "{profile.get("source_pptx", "")}"',
        f'template_import_dir: "{profile.get("template_import_dir", "")}"',
        "---",
        "",
        f"# spec_lock — {profile['name']}",
        "",
        "Machine contract derived from the imported template manifest. The render stage",
        "(svg_skeleton_render) MUST obey these locked values per page; do not drift.",
        "",
        "## canvas",
        f"- viewBox: 0 0 {int(cv['width_px'])} {int(cv['height_px'])}",
        "",
        "## colors (role <- OOXML theme)",
        f"- text: {pal['text']}",
        f"- primary: {pal['primary']}",
        f"- accent: {pal['accent']}",
        f"- secondary: {pal['secondary']}",
        f"- neutral: {pal['neutral']}",
        "",
        "## theme_colors (full)",
    ]
    for k, v in profile.get("theme_colors", {}).items():
        lines.append(f"- {k}: {v}")
    lines += [
        "",
        "## typography",
        f"- heading_family: {typ['heading']}",
        f"- body_family: {typ['body']}",
        f"- heading_size: {typ['heading_size']}",
        f"- body_size: {typ['body_size']}",
        "",
        "## page_type → layout skeleton + content regions",
    ]
    for ptype, L in profile.get("page_type_layouts", {}).items():
        tr, br = L["title_region"], L["body_region"]
        lines.append(
            f"- {ptype}: svg={L['svg']} | title=({tr['x']:.0f},{tr['y']:.0f},{tr['width']:.0f},{tr['height']:.0f})"
            f" | body=({br['x']:.0f},{br['y']:.0f},{br['width']:.0f},{br['height']:.0f})"
        )
        slots = L.get("layout_slots") or {}
        if slots:
            slot_names = ", ".join(sorted(slots))
            lines.append(f"  - slots: {slot_names}")
            for slot_name, reg in sorted(slots.items()):
                lines.append(
                    f"    - {slot_name}=({reg.get('x', 0):.0f},{reg.get('y', 0):.0f},"
                    f"{reg.get('width', 0):.0f},{reg.get('height', 0):.0f})"
                )
    lines += [
        "",
        "## allowed_layout_svgs",
    ]
    for L in profile.get("page_type_layouts", {}).values():
        if L.get("svg"):
            lines.append(f"- {L['svg']}")
    for L in profile.get("layout_catalog", []):
        if L.get("template_svg"):
            lines.append(f"- {L['template_svg']}")
    for S in profile.get("source_slide_catalog", []):
        if S.get("template_svg"):
            lines.append(f"- {S['template_svg']}")
    lines += [
        "",
        "## default_page_rhythm",
        "- cover: anchor",
        "- chapter: anchor",
        "- content: dense",
        "- ending: anchor",
        "",
        "## forbidden",
        "- Colors outside the palette/theme_colors above",
        "- Font families outside the typography section above",
        "- Layout SVGs not listed in allowed_layout_svgs",
        "- Silent fallback to a non-template render path when skeleton_render is true",
    ]
    (project_dir / "spec_lock.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def ingest(pptx: Path, project_dir: Path | None, scripts_dir: Path) -> dict | None:
    """Full ingest: import package (idempotent) + real profile + spec_lock. None on failure."""
    pptx = pptx.resolve()
    base_dir = project_dir if project_dir else pptx.parent
    import_dir = base_dir / "templates" / f"{pptx.stem}_template_import"
    if project_dir is None:
        import_dir = pptx.parent / f"{pptx.stem}_template_import"
    if not run_importer(pptx, import_dir, scripts_dir):
        return None
    try:
        profile = build_profile(pptx, import_dir, project_dir)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[template_ingest] profile build failed: {e}\n")
        return None
    if project_dir:
        try:
            write_spec_lock(profile, project_dir)
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"[template_ingest] spec_lock write failed: {e}\n")
    return profile


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Ingest a .pptx template into a real profile + spec_lock.")
    ap.add_argument("pptx")
    ap.add_argument("--project-dir", default=None)
    ap.add_argument("--scripts-dir", required=True, help="ppt-master scripts dir")
    ap.add_argument("--out", default=None, help="write template-profile.json here")
    args = ap.parse_args()
    project_dir = Path(args.project_dir).resolve() if args.project_dir else None
    profile = ingest(Path(args.pptx), project_dir, Path(args.scripts_dir))
    if profile is None:
        return 1
    if args.out:
        Path(args.out).write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(profile, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
