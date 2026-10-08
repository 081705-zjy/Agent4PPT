#!/usr/bin/env python3
"""Presentation effects contracts for transitions, animations, and narration."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_transition_plan(slide_count: int) -> dict:
    return {
        "schema_version": "1.0",
        "generated_at": now(),
        "enabled": True,
        "default": {"effect": "fade", "duration": 0.4, "advance_after": None},
        "slides": [
            {"slide_index": i, "effect": "fade", "duration": 0.4, "advance_after": None}
            for i in range(1, slide_count + 1)
        ],
    }


def default_animation_plan(slide_count: int) -> dict:
    return {
        "schema_version": "1.0",
        "generated_at": now(),
        "enabled": False,
        "reason": "Object animations are disabled by default for editable business decks.",
        "default": {"effect": "none", "trigger": "after-previous", "duration": 0.0, "stagger": 0.0},
        "slides": [{"slide_index": i, "groups": {}} for i in range(1, slide_count + 1)],
    }


def default_narration_plan(slide_count: int) -> dict:
    return {
        "schema_version": "1.0",
        "generated_at": now(),
        "enabled": False,
        "reason": "No narration audio directory was provided.",
        "audio_dir": None,
        "require_complete_audio": False,
        "slides": [
            {"slide_index": i, "audio_path": None, "duration_seconds": None}
            for i in range(1, slide_count + 1)
        ],
    }


def write_default_plans(run_dir: Path, slide_count: int) -> list[Path]:
    paths = [
        (run_dir / "transition-plan.json", default_transition_plan(slide_count)),
        (run_dir / "animation-plan.json", default_animation_plan(slide_count)),
        (run_dir / "narration-plan.json", default_narration_plan(slide_count)),
    ]
    out = []
    for path, data in paths:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        out.append(path)
    return out


def _transition_xml(effect: str, duration: float, advance_after) -> str:
    from ppt_master.pptx_animations import create_transition_xml

    return create_transition_xml(effect=effect, duration=duration, advance_after=advance_after)


def apply_transitions(pptx_path: Path, plan_path: Path) -> int:
    if not plan_path.exists() or not pptx_path.exists():
        return 0
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if not plan.get("enabled", False):
        return 0
    by_slide = {int(s["slide_index"]): s for s in plan.get("slides", []) if s.get("slide_index")}
    default = plan.get("default") or {}
    tmp = Path(tempfile.mkdtemp())
    try:
        with zipfile.ZipFile(pptx_path, "r") as zf:
            zf.extractall(tmp)
        count = 0
        for slide_path in sorted((tmp / "ppt" / "slides").glob("slide*.xml")):
            m = re.search(r"slide(\d+)\.xml$", slide_path.name)
            if not m:
                continue
            idx = int(m.group(1))
            cfg = by_slide.get(idx, default)
            effect = cfg.get("effect", default.get("effect", "fade"))
            if not effect or effect == "none":
                continue
            duration = float(cfg.get("duration", default.get("duration", 0.4)))
            advance = cfg.get("advance_after", default.get("advance_after"))
            xml = slide_path.read_text(encoding="utf-8")
            xml = re.sub(r"\s*<p:transition\b.*?</p:transition>", "", xml, flags=re.DOTALL)
            trans = _transition_xml(str(effect), duration, advance)
            if "<p:timing>" in xml:
                xml = xml.replace("<p:timing>", trans + "\n  <p:timing>", 1)
            else:
                xml = xml.replace("</p:sld>", trans + "\n</p:sld>", 1)
            slide_path.write_text(xml, encoding="utf-8")
            count += 1
        tmp_pptx = pptx_path.with_suffix(".effects.tmp.pptx")
        with zipfile.ZipFile(tmp_pptx, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(tmp):
                for name in files:
                    path = Path(root) / name
                    zf.write(path, path.relative_to(tmp).as_posix())
        tmp_pptx.replace(pptx_path)
        return count
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def count_transitions(pptx_path: Path) -> int:
    if not pptx_path.exists():
        return 0
    total = 0
    with zipfile.ZipFile(pptx_path, "r") as zf:
        for name in zf.namelist():
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name):
                text = zf.read(name).decode("utf-8", errors="ignore")
                if "<p:transition" in text:
                    total += 1
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description="Write/apply ppt-agent presentation effect plans.")
    ap.add_argument("run_dir")
    ap.add_argument("--slide-count", type=int, default=None)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    run_dir = Path(args.run_dir).resolve()
    if args.slide_count is not None:
        for p in write_default_plans(run_dir, args.slide_count):
            print(p)
    if args.apply:
        print(apply_transitions(run_dir / "deck.pptx", run_dir / "transition-plan.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
