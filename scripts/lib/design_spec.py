#!/usr/bin/env python3
"""Generate a project-level design_spec.md from template-profile.json.

This file is the human-readable strategy layer between raw template ingestion and
stage artifacts. It mirrors the useful part of ppt-master's design_spec contract
without changing the existing ppt-agent state machine.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path


SECTIONS = [
    "I Project Info",
    "II Canvas",
    "III Visual Theme",
    "IV Typography",
    "V Layout",
    "VI Icon",
    "VII Visualization",
    "VIII Image",
    "IX Outline",
    "X Speaker Notes",
    "XI Tech Constraints",
]


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bullets(mapping: dict) -> list[str]:
    return [f"- {key}: {value}" for key, value in mapping.items()]


def layout_lines(profile: dict) -> list[str]:
    page_layouts = profile.get("page_type_layouts") or {}
    if not page_layouts:
        return ["- No imported skeleton layouts; use the built-in profile layout guidance."]
    out = []
    for page_type, layout in page_layouts.items():
        title = layout.get("title_region") or {}
        body = layout.get("body_region") or {}
        out.append(
            "- "
            f"{page_type}: svg={layout.get('svg')} | "
            f"title=({title.get('x')},{title.get('y')},{title.get('width')},{title.get('height')}) | "
            f"body=({body.get('x')},{body.get('y')},{body.get('width')},{body.get('height')})"
        )
        slots = layout.get("layout_slots") or {}
        if slots:
            out.append(f"  - slots: {', '.join(sorted(slots))}")
            affordances = layout.get("layout_affordances") or {}
            if affordances:
                flags = [
                    key for key in (
                        "supports_subtitle",
                        "supports_image",
                        "supports_chart",
                        "supports_table",
                        "supports_footer",
                    )
                    if affordances.get(key)
                ]
                out.append(f"  - affordances: {', '.join(flags) if flags else 'text-only'}")
    return out


def build(profile: dict, project_dir: Path) -> str:
    template_id = profile.get("template_id", "unknown")
    template_name = profile.get("name", template_id)
    source = profile.get("source_pptx") or profile.get("_path") or ""
    canvas = profile.get("canvas") or {}
    palette = profile.get("palette") or {}
    theme_colors = profile.get("theme_colors") or {}
    typography = profile.get("typography") or {}
    render = profile.get("render") or {}
    timestamp = now()

    lines = [
        "---",
        'schema_version: "1.0"',
        f'generated_at: "{timestamp}"',
        f'template_id: "{template_id}"',
        f'template_name: "{template_name}"',
        f'source_template: "{source}"',
        "---",
        "",
        f"# Design Spec — {template_name}",
        "",
        "This file is generated from `template-profile.json` and is the strategy-level",
        "template contract for downstream planning, rendering, and review.",
        "",
        f"## {SECTIONS[0]}",
        f"- project_dir: {project_dir}",
        f"- template_id: {template_id}",
        f"- template_name: {template_name}",
        f"- source_template: {source or 'built-in profile'}",
        f"- source_slide_count: {profile.get('source_slide_count', 'n/a')}",
        "",
        f"## {SECTIONS[1]}",
        f"- width_px: {canvas.get('width_px', 1280)}",
        f"- height_px: {canvas.get('height_px', 720)}",
        f"- viewBox: 0 0 {int(float(canvas.get('width_px', 1280)))} {int(float(canvas.get('height_px', 720)))}",
        "",
        f"## {SECTIONS[2]}",
        *bullets(palette),
        "",
        "### Theme Colors",
        *(bullets(theme_colors) if theme_colors else ["- theme_colors: not available in this profile"]),
        "",
        f"## {SECTIONS[3]}",
        *bullets(typography),
        "",
        f"## {SECTIONS[4]}",
        "Template layout skeletons are authoritative. Downstream visual plans must",
        "choose from this roster; do not invent alternate skeleton names.",
        *layout_lines(profile),
        "",
        "### Render Hints",
        *(bullets(render) if render else ["- render hints: none"]),
        "",
        f"## {SECTIONS[5]}",
        "- icon_library: inherited from template/user request when declared; otherwise keep icons minimal.",
        "- icon_rule: one icon style per deck; icons may not introduce non-template colors.",
        "",
        f"## {SECTIONS[6]}",
        "- charts must be data-derived and editable.",
        "- chart colors and typography must come from this design spec / spec_lock.md.",
        "",
        f"## {SECTIONS[7]}",
        "- user/template assets are authoritative.",
        "- generated images are decorative unless backed by an explicit source artifact.",
        "- image placement must respect template content regions.",
        "",
        f"## {SECTIONS[8]}",
                        "- outline_source: generated later by REUSE_OUTLINE.",
        "- page-level template mapping is generated in visual-plan.json.",
        "",
        f"## {SECTIONS[9]}",
        "- speaker notes are generated after slide copy is locked.",
        "- notes must not introduce unsupported factual claims.",
        "",
        f"## {SECTIONS[10]}",
        "- Use only template palette/theme colors except black/white where required for contrast.",
        "- Use only template typography unless the user explicitly overrides fonts.",
        "- If skeleton_render is true, rendering must inherit listed layout SVGs.",
        "- Silent fallback to a non-template render path is forbidden for imported PPTX templates.",
        "- All final PPT elements should remain editable when the backend supports it.",
        "",
    ]
    return "\n".join(str(line) for line in lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate design_spec.md from template-profile.json")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    profile_path = Path(args.profile).resolve() if args.profile else project_dir / "template-profile.json"
    out_path = Path(args.out).resolve() if args.out else project_dir / "design_spec.md"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    out_path.write_text(build(profile, project_dir), encoding="utf-8")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
