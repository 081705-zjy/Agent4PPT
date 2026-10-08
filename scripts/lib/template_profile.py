#!/usr/bin/env python3
"""Resolve a project-local or built-in PPT template profile.

Project-local templates win. A user can place either a JSON profile or a `.pptx`
reference in <project>/templates before generation. JSON profiles are copied as
the active profile. PPTX references are converted into a conservative JSON profile
that records source metadata and uses editable-renderer defaults until richer
OOXML extraction is added.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


DEFAULT_PROFILE = {
    "schema_version": "1.0",
    "template_id": "consulting",
    "name": "Consulting Executive",
    "description": "Structured executive briefing style with strong hierarchy and restrained accents.",
    "palette": {
        "primary": "#17324D",
        "secondary": "#2E7D8A",
        "accent": "#DCA24C",
        "neutral": "#F6F7F9",
        "text": "#151A1F",
    },
    "typography": {
        "heading": "Aptos Display",
        "body": "Aptos",
        "heading_size": 32,
        "body_size": 18,
    },
    "layouts": {
        "title-image": "Large title, supporting subtitle/copy, one concept image on the right.",
        "title-and-body": "Fixed title area, concise body text, native accent shape.",
        "closing": "Large closing message with compact action bullets.",
    },
    "render": {
        "accent_bar_height": 0.25,
        "picture_x": 6.45,
        "picture_y": 1.2,
        "picture_w": 3.0,
        "picture_h": 1.7,
    },
}


def slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", text.strip()).strip("-").lower()
    return s[:48] or "template"


def load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = ["schema_version", "template_id", "name", "palette", "typography", "layouts", "render"]
    missing = [key for key in required if key not in data]
    if data.get("schema_version") != "1.0" or missing:
        raise SystemExit(f"Invalid template profile: {path} (missing: {', '.join(missing) or 'schema_version'})")
    data["_path"] = str(path)
    return data


def _config() -> dict:
    try:
        return json.loads((ROOT / "config/default_config.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def pptx_to_profile(path: Path) -> dict:
    """Conservative fallback profile when full ppt-master ingest is unavailable."""
    profile = dict(DEFAULT_PROFILE)
    profile["template_id"] = slug(path.stem)
    profile["name"] = path.stem
    profile["description"] = (
        "User-provided PPTX reference (fallback profile — ppt-master import unavailable). "
        "Claude should inspect this source template and preserve its visual system."
    )
    profile["source_pptx"] = str(path)
    profile["_path"] = str(path)
    try:
        from pptx import Presentation

        prs = Presentation(str(path))
        profile["source_slide_count"] = len(prs.slides)
        profile["source_slide_width"] = int(prs.slide_width)
        profile["source_slide_height"] = int(prs.slide_height)
    except Exception:
        profile["source_slide_count"] = None
    return profile


def pptx_profile(path: Path, project_dir: Path | None) -> dict:
    """Process a .pptx template the ppt-master way (import package + real profile +
    spec_lock); fall back to the conservative profile if ppt-master isn't reachable."""
    cfg = _config()
    if cfg.get("template_skeleton_render", True):
        try:
            import template_ingest

            scripts_dir = template_ingest.vendored_scripts_dir(ROOT)
            base_required = bool(_config().get("base_template_required")) and _is_base_template(path)
            profile = template_ingest.ingest(path, None if base_required else project_dir, scripts_dir)
            if profile:
                _apply_base_template_contract(profile, path)
                return profile
        except Exception as e:  # noqa: BLE001
            import sys

            sys.stderr.write(f"[template_profile] ingest failed, using fallback: {e}\n")
    return pptx_to_profile(path)


def first_project_template(project_dir: Path) -> Path | None:
    templates = project_dir / "templates"
    if not templates.exists():
        return None
    for pattern in ("*.json", "*.pptx"):
        # Skip Office lock/owner files (~$name.pptx) and hidden temp files.
        found = sorted(
            p for p in templates.glob(pattern)
            if not p.name.startswith(("~$", "~", "."))
        )
        if found:
            return found[0]
    return None


def _is_base_template(path: Path) -> bool:
    try:
        rel = path.resolve().relative_to((ROOT / "templates" / "base").resolve())
        return bool(rel.parts)
    except Exception:
        return False


def _base_template_path() -> Path | None:
    raw = str(_config().get("base_template") or "").strip()
    if not raw:
        return None
    p = Path(raw)
    p = p if p.is_absolute() else ROOT / p
    return p if p.exists() and not p.name.startswith(("~$", "~", ".")) else None


def _apply_base_template_contract(profile: dict, source: Path) -> None:
    if not _is_base_template(source):
        return
    cfg = _config()
    profile["template_scope"] = "global_base"
    profile["base_template"] = True
    profile["reuse_policy"] = {
        "style": True,
        "layout_pattern": True,
        "required_background": True,
        "cover_assets": True,
        "ending_assets": True,
        "specific_content_assets": False,
        "speaker_footer_editable": True,
    }
    profile["lab_template_contract"] = {
        "kind": "dai_lab_base",
        "speaker_name": str(cfg.get("default_speaker_name") or "xxx"),
        "speaker_affiliation": str(cfg.get("default_speaker_affiliation") or "Shanghai Jiao Tong University"),
        "speaker_email": str(cfg.get("default_speaker_email") or "xxx@shanghai jiaotong"),
        "footer_text_template": "{speaker_name} @ {speaker_affiliation}",
        "footer_placeholder_regex": r"Guohao\s+Dai\s*@\s*Shanghai\s+Jiao\s+Tong\s+University",
        "footer_region": {
            "x": 324.57,
            "y": 514.87,
            "width": 310.86,
            "height": 29.08,
            "text_x": 480.0,
            "text_y": 533.27,
            "font_family": "Calibri",
            "font_size": 16,
            "fill": "#A6A6A6",
            "anchor": "middle",
        },
        "page_number_region": {
            "x": 799.94,
            "y": 516.48,
            "width": 162.0,
            "height": 28.75,
            "text_x": 807.14,
            "text_y": 533.85,
            "prefix": "Page ",
            "font_family": "Arial",
            "font_size": 12,
            "fill": "#808080",
            "anchor": "start",
        },
        "title_rule": {
            "description": "每页标题位于顶部蓝色横线之上或贴近蓝色横线区域，内容页标题居中。",
            "line_y": 64.71,
            "line_x1": 30.14,
            "line_x2": 929.86,
            "line_color": "#074BA2",
            "line_width": 7.667,
            "title_region": {"x": 66, "y": 0, "width": 828, "height": 68},
        },
        "title_style": {
            "content": {
                "x": 480.0,
                "y": 51.26,
                "anchor": "middle",
                "font_family": '"Cambria Math", "黑体", "Times New Roman", sans-serif',
                "font_size": 42.67,
                "min_font_size": 28,
                "fill": "#074BA2",
                "weight": "bold",
            },
            "cover": {
                "region": {"x": 120.0, "y": 146.0, "width": 720.0, "height": 108.0},
                "anchor": "middle",
                "font_family": "Calibri",
                "font_size": 25,
                "min_font_size": 20,
                "fill": "#000000",
                "weight": "bold",
            },
            "ending": {
                "region": {"x": 66.0, "y": 134.63, "width": 828.0, "height": 224.62},
                "anchor": "middle",
                "font_family": '"Cambria Math", "黑体", "Times New Roman", sans-serif',
                "font_size": 42.67,
                "min_font_size": 30,
                "fill": "#074BA2",
                "weight": "bold",
            },
        },
        "body_style": {
            "font_family": '"Microsoft YaHei", "微软雅黑", Arial, sans-serif',
            "font_size": 20,
            "fill": "#000000",
            "visual_font_size": 17,
            "table_font_size": 14.5,
            "line_gap": 1.28,
        },
        "cover_metadata": {
            "region": {"x": 120.0, "y": 283.62, "width": 720.0, "height": 130.38},
            "speaker_y": 318.0,
            "affiliation_y": 356.0,
            "date_y": 394.0,
            "x": 480.0,
            "anchor": "middle",
            "font_family": "Arial, sans-serif",
            "font_size": 24,
            "fill": "#000000",
            "affiliation_fill": "#262626",
            "date_fill": "#7F7F7F",
            "presentation_date_format": "%Y.%m.%d",
        },
        "ending_content": {
            "title": "Thanks",
            "title_region": {"x": 120.0, "y": 142.0, "width": 720.0, "height": 88.0},
            "metadata_region": {"x": 120.0, "y": 274.0, "width": 720.0, "height": 150.0},
            "name_y": 306.0,
            "date_y": 344.0,
            "email_y": 382.0,
            "x": 480.0,
            "anchor": "middle",
            "font_family": "Arial, sans-serif",
            "title_font_size": 42.67,
            "metadata_font_size": 24,
            "title_fill": "#000000",
            "metadata_fill": "#262626",
            "date_fill": "#7F7F7F",
            "email_fill": "#262626",
        },
        "cover_reuse": {
            "source_slide_index": 1,
            "template_svg": "svg-flat/slide_01.svg",
            "copy_assets": True,
            "reason": "实验室封面图标和背景必须复用",
        },
        "ending_reuse": {
            "source_slide_index": 7,
            "template_svg": "svg-flat/slide_07.svg",
            "copy_assets": True,
            "reason": "实验室结束页图形必须复用",
        },
    }


def resolve_path(template_arg: str | None, project_dir: Path | None) -> Path:
    if template_arg:
        p = Path(template_arg)
        candidates = []
        if project_dir:
            candidates.extend([
                project_dir / "templates" / template_arg,
                project_dir / "templates" / f"{template_arg}.json",
                project_dir / "templates" / f"{template_arg}.pptx",
            ])
        if not p.suffix and "/" not in template_arg:
            candidates.append(ROOT / "ppt-templates" / f"{template_arg}.json")
        candidates.append(p if p.is_absolute() else ROOT / p)
        for c in candidates:
            if c.exists():
                return c
        raise SystemExit(f"Template not found: {template_arg}")
    if project_dir:
        local = first_project_template(project_dir)
        if local and not _config().get("base_template_required"):
            return local
    base = _base_template_path()
    if base:
        return base
    cfg = json.loads((ROOT / "config/default_config.json").read_text(encoding="utf-8"))
    return ROOT / "ppt-templates" / f"{cfg.get('default_template', 'consulting')}.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", default=None)
    parser.add_argument("--template", default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve() if args.project_dir else None
    source = resolve_path(args.template, project_dir)
    profile = pptx_profile(source, project_dir) if source.suffix.lower() == ".pptx" else load_json(source)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if project_dir and not profile.get("base_template"):
        templates_dir = project_dir / "templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        local_copy = templates_dir / source.name
        if source.resolve() != local_copy.resolve() and source.exists():
            shutil.copy2(source, local_copy)
    print(source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
