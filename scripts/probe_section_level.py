#!/usr/bin/env python3
"""Diagnostic probe — call section_level skill on ONE deck, save raw output.

Purpose: figure out why call_claude_json returns non-dict data on
section_level batches. Runs directly (no batching, no retry), saves both
raw Claude stdout and post-parse result.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ppt_agent_app import claude_cli
from ppt_agent_app.library_extract.logic_extract import (
    build_section_level_input,
    SECTION_LEVEL_SKILL,
    BATCHES_DIR,
)


def main() -> int:
    deck_name = sys.argv[1] if len(sys.argv) > 1 else \
        "DATE26-Endor-Exploit-Nearly-Decode-Only-Opportunities.50cfbf4f"
    deck_dir = ROOT / "data" / "resources_library" / "material" / "decks" / deck_name
    if not deck_dir.exists():
        print(f"deck not found: {deck_dir}")
        return 1

    print(f"probe deck: {deck_name}")
    payload = build_section_level_input([deck_dir], [], 0)
    payload_json = json.dumps(payload, ensure_ascii=False)
    print(f"input size: {len(payload_json)/1024:.0f} KB")

    BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    probe_in = BATCHES_DIR / f"probe_{deck_name}_input.json"
    probe_in.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"input saved: {probe_in.name}")

    # Direct claude CLI subprocess so we can see raw stdout
    skill_text = claude_cli._load_skill_text([SECTION_LEVEL_SKILL])
    prompt = (
        f"section_level_batch_0: Extract logic patterns per the skill rules.\n"
        f"Output strict JSON only.\n\nINPUT:\n{payload_json}"
    )
    cmd = [
        claude_cli.CLI_PATH_DEFAULT,
        "-p",
        "--model", claude_cli.MODEL_DEFAULT,
        "--output-format", "text",
        "--permission-mode", "bypassPermissions",
        "--append-system-prompt", skill_text,
    ]
    print(f"cmd model: {claude_cli.MODEL_DEFAULT}")
    print(f"skill: {SECTION_LEVEL_SKILL}")
    print(f"launching claude cli (timeout 1800s)...")

    t = time.time()
    rc, stdout, stderr, terminal_err = claude_cli._run_cli(cmd, prompt, 1800)
    elapsed = time.time() - t
    print(f"claude done in {elapsed:.0f}s, rc={rc}, terminal_err={terminal_err}")
    print(f"stdout: {len(stdout)} bytes, stderr: {len(stderr)} bytes")

    probe_out = BATCHES_DIR / f"probe_{deck_name}_stdout.txt"
    probe_err = BATCHES_DIR / f"probe_{deck_name}_stderr.txt"
    probe_out.write_text(stdout or "", encoding="utf-8")
    probe_err.write_text(stderr or "", encoding="utf-8")
    print(f"stdout saved: {probe_out.name} ({len(stdout)} bytes)")
    print(f"stderr saved: {probe_err.name} ({len(stderr)} bytes)")

    # Inspection
    print("\n=== stdout head (400 chars) ===")
    print((stdout or "")[:400])
    print("\n=== stdout tail (400 chars) ===")
    print((stdout or "")[-400:])

    # Try to parse
    raw = claude_cli._strip_code_fence(stdout or "")
    try:
        data = json.loads(raw)
        print(f"\ndirect parse: OK type={type(data).__name__}")
        if isinstance(data, dict):
            print(f"  top-level keys: {list(data.keys())}")
    except json.JSONDecodeError as e:
        print(f"\ndirect parse: FAIL {e}")
        candidate = claude_cli._extract_first_json_object(raw)
        try:
            data = json.loads(candidate)
            print(f"first-object parse: OK type={type(data).__name__}")
            if isinstance(data, dict):
                print(f"  top-level keys: {list(data.keys())}")
            else:
                print(f"  preview: {json.dumps(data, ensure_ascii=False)[:400]}")
        except json.JSONDecodeError as e2:
            print(f"first-object parse: FAIL {e2}")
            print(f"  candidate head: {candidate[:400]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
