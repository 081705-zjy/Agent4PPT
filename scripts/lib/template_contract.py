#!/usr/bin/env python3
"""Validate that style and visual artifacts stay faithful to template-profile.json."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}")


def norm_hex(value: object) -> str | None:
    text = str(value or "").strip()
    if not HEX_RE.fullmatch(text):
        return None
    return text.upper()


def profile_for(artifact: Path) -> dict | None:
    profile_path = artifact.parent / "template-profile.json"
    if not profile_path.exists():
        return None
    try:
        return json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"template-profile.json is unreadable: {exc}") from exc


def allowed_colors(profile: dict) -> set[str]:
    values: set[str] = {"#000000", "#FFFFFF"}
    for section in ("palette", "theme_colors"):
        for value in (profile.get(section) or {}).values():
            hx = norm_hex(value)
            if hx:
                values.add(hx)
    return values


def required_palette(profile: dict) -> set[str]:
    out: set[str] = set()
    for value in (profile.get("palette") or {}).values():
        hx = norm_hex(value)
        if hx:
            out.add(hx)
    return out


def validate_style_guide(artifact: Path, profile: dict) -> list[str]:
    text = artifact.read_text(encoding="utf-8")
    found = {m.group(0).upper() for m in HEX_RE.finditer(text)}
    allowed = allowed_colors(profile)
    required = required_palette(profile)
    errors: list[str] = []

    drift = sorted(found - allowed)
    if drift:
        errors.append(
            "style-guide uses color(s) outside template-profile palette/theme_colors: "
            + ", ".join(drift)
        )

    missing = sorted(required - found)
    if missing:
        errors.append(
            "style-guide must explicitly carry every template palette color: "
            + ", ".join(missing)
        )

    typography = profile.get("typography") or {}
    low = text.lower()
    for role in ("heading", "body"):
        font = str(typography.get(role) or "").strip()
        if font and font.lower() not in low:
            errors.append(f"style-guide missing template {role} font: {font}")
    return errors


def validate_visual_plan(artifact: Path, profile: dict) -> list[str]:
    try:
        data = json.loads(artifact.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [f"visual-plan JSON unreadable after base validation: {exc}"]
    errors: list[str] = []

    expected_id = profile.get("template_id")
    if expected_id and data.get("template_id") != expected_id:
        errors.append(
            f"visual-plan template_id must match template-profile.json: {expected_id}"
        )

    expected_palette = profile.get("palette") or {}
    actual_palette = ((data.get("theme") or {}).get("palette") or {})
    if expected_palette and actual_palette != expected_palette:
        errors.append("visual-plan theme.palette must exactly match template-profile palette")

    expected_typography = profile.get("typography") or {}
    actual_typography = ((data.get("theme") or {}).get("typography") or {})
    if expected_typography and actual_typography != expected_typography:
        errors.append("visual-plan theme.typography must exactly match template-profile typography")

    if profile.get("skeleton_render"):
        page_layouts = profile.get("page_type_layouts") or {}
        valid_page_types = set(page_layouts)
        valid_svgs = {str(v.get("svg")) for v in page_layouts.values() if v.get("svg")}
        for slide in data.get("slides") or []:
            idx = slide.get("slide_index", "?")
            ptype = slide.get("template_page_type")
            svg = slide.get("template_layout_svg")
            regions = slide.get("content_regions")
            slots = slide.get("layout_slots")
            if ptype not in valid_page_types:
                errors.append(
                    f"visual-plan slide {idx} template_page_type must be one of: "
                    + ", ".join(sorted(valid_page_types))
                )
                expected_layout = {}
            else:
                expected_layout = page_layouts.get(ptype) or {}
            if svg not in valid_svgs:
                errors.append(f"visual-plan slide {idx} template_layout_svg is not from template-profile")
            if not isinstance(regions, dict) or not regions.get("title") or not regions.get("body"):
                errors.append(f"visual-plan slide {idx} must include title/body content_regions")
            expected_slots = expected_layout.get("layout_slots") or {}
            if expected_slots:
                if not isinstance(slots, dict) or not slots.get("title") or not slots.get("body"):
                    errors.append(f"visual-plan slide {idx} must include template-derived title/body layout_slots")
                else:
                    unknown = sorted(set(slots) - set(expected_slots))
                    if unknown:
                        errors.append(
                            f"visual-plan slide {idx} uses slot(s) not present in template-profile: "
                            + ", ".join(unknown)
                        )
                    for key in ("title", "body"):
                        if regions.get(key) != slots.get(key):
                            errors.append(
                                f"visual-plan slide {idx} content_regions.{key} must match layout_slots.{key}"
                            )
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: template_contract.py <style-guide|visual-plan> <artifact>", file=sys.stderr)
        return 2
    artifact_type = argv[1]
    artifact = Path(argv[2]).resolve()
    profile = profile_for(artifact)
    if profile is None:
        return 0
    if artifact_type == "style-guide":
        errors = validate_style_guide(artifact, profile)
    elif artifact_type == "visual-plan":
        errors = validate_visual_plan(artifact, profile)
    else:
        return 0
    for err in errors:
        print(f"[template-contract] {err}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
