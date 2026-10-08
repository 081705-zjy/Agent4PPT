"""v20 D1: Slide brief surgical field enhancement.

For each existing slide_NN.md in data/resources_library/material/decks/, read
its frontmatter, and if any of the 4 v20 fields is missing, call Claude to
generate them from the existing brief context, then merge back into
frontmatter.

Runs in parallel per section (all slides in one section as a batch is not
possible via the per-page enhance skill — we do 1 call per slide, but
concurrent across slides).

Usage:
    python3 -m ppt_agent_app.tools.enhance_slide_briefs --dry-run
    python3 -m ppt_agent_app.tools.enhance_slide_briefs --workers 8
    python3 -m ppt_agent_app.tools.enhance_slide_briefs --deck 华为2012报告-final
"""
from __future__ import annotations

import argparse
import concurrent.futures as _cf
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ppt_agent_app import claude_cli
from ppt_agent_app.models import ROOT

DECKS_DIR = ROOT / "data" / "resources_library" / "material" / "decks"
SKILL = "skills/resources_library/material/slide_brief_enhance.md"
NEW_FIELDS = ("页在section中的作用", "视觉文本层次", "alternate_claims", "layout_tag")


def _split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---"):
        return "", text
    idx = text.find("\n---", 3)
    if idx < 0:
        return "", text
    return text[3:idx].strip(), text[idx + 4:].lstrip()


def _parse_yaml_like(fm_raw: str) -> dict:
    """Minimal YAML-ish parser: supports scalar / list (- item) / nested list."""
    out: dict = {}
    if not fm_raw:
        return out
    lines = fm_raw.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i].rstrip()
        if not ln.strip() or ln.strip().startswith("#"):
            i += 1
            continue
        if ":" in ln:
            key, val = ln.split(":", 1)
            key = key.strip()
            val = val.strip()
            if val == "":
                # list follows
                items = []
                j = i + 1
                while j < len(lines):
                    lj = lines[j]
                    if lj.startswith("  - "):
                        items.append(lj[4:].strip().strip('"').strip("'"))
                        j += 1
                    elif lj.startswith("- "):
                        items.append(lj[2:].strip().strip('"').strip("'"))
                        j += 1
                    else:
                        break
                out[key] = items
                i = j
                continue
            else:
                # try JSON parse for list/dict/number/bool
                try:
                    out[key] = json.loads(val)
                except Exception:
                    out[key] = val.strip('"').strip("'")
                i += 1
        else:
            i += 1
    return out


def _dump_yaml_like(fm: dict) -> str:
    """Emit YAML-ish frontmatter matching library_tree style.
    All string values quoted as JSON, lists on separate lines with `- ` prefix.
    """
    lines = []
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                if isinstance(item, (dict, list)):
                    lines.append(f"  - {json.dumps(item, ensure_ascii=False)}")
                elif isinstance(item, str):
                    lines.append(f"  - {json.dumps(item, ensure_ascii=False)}")
                else:
                    lines.append(f"  - {item}")
        elif isinstance(v, dict):
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
        elif isinstance(v, str):
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
        elif v is None:
            lines.append(f"{k}: null")
        else:
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    return "\n".join(lines)


def _section_role_context(section_dir: Path) -> list[str]:
    """List page roles in a section, ordered by slide_index."""
    roles = []
    for sf in sorted(section_dir.glob("slide_*.md")):
        try:
            text = sf.read_text(encoding="utf-8", errors="ignore")
            fm_raw, _ = _split_frontmatter(text)
            fm = _parse_yaml_like(fm_raw)
            roles.append(fm.get("页面角色") or "?")
        except Exception:
            roles.append("?")
    return roles


def enhance_one_slide(slide_file: Path, deck_title: str, section_title: str,
                       section_role_ctx: list[str],
                       slide_pos: int) -> tuple[Path, bool, str]:
    """Return (path, changed, msg)."""
    try:
        text = slide_file.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return slide_file, False, f"read error: {e}"
    fm_raw, body = _split_frontmatter(text)
    fm = _parse_yaml_like(fm_raw)
    # Check if all 4 fields already present with non-empty values
    missing = [k for k in NEW_FIELDS if k not in fm or (isinstance(fm.get(k), list) and not fm[k]) or (isinstance(fm.get(k), str) and not fm[k])]
    if not missing:
        return slide_file, False, "already has all 4 fields"

    payload = {
        "slide_id": fm.get("页标识") or slide_file.stem,
        "所属deck标题": deck_title,
        "所属章节标题": section_title,
        "该 section 内所有页角色顺序": section_role_ctx,
        "本页原始位置": slide_pos,
        "本页原始关键文字": fm.get("关键文字") if isinstance(fm.get("关键文字"), list) else [],
        "旧brief": {
            "页序号": fm.get("页序号"),
            "标题": fm.get("标题"),
            "核心论断": fm.get("核心论断"),
            "本页讲什么": fm.get("本页讲什么"),
            "关键文字": fm.get("关键文字"),
            "视觉骨架": fm.get("视觉骨架"),
            "页面角色": fm.get("页面角色"),
        },
    }
    prompt = (
        "Enhance slide brief with 4 new v20 fields. Return strict JSON only.\n\n"
        "INPUT:\n" + json.dumps(payload, ensure_ascii=False)
    )
    for attempt in range(1, 4):
        res = claude_cli.call_claude_json(prompt, skill=[SKILL], timeout=180)
        if res.get("ok") and isinstance(res.get("data"), dict):
            new = res["data"]
            # Validate 4 fields
            ok = all(k in new for k in NEW_FIELDS)
            if ok:
                # Merge into fm
                for k in NEW_FIELDS:
                    fm[k] = new[k]
                new_fm_str = _dump_yaml_like(fm)
                new_text = f"---\n{new_fm_str}\n---\n{body}"
                slide_file.write_text(new_text, encoding="utf-8")
                return slide_file, True, "OK"
            else:
                return slide_file, False, f"validation failed: missing keys {[k for k in NEW_FIELDS if k not in new]}"
        else:
            if attempt < 3:
                time.sleep(2 ** attempt)
    return slide_file, False, f"cli failed all retries: {(res.get('error') or '')[:120]}"


def enhance_deck(deck_dir: Path, workers: int = 4, dry_run: bool = False) -> dict:
    if not (deck_dir / "deck.md").exists():
        return {"deck": deck_dir.name, "skipped": "no deck.md"}
    try:
        deck_text = (deck_dir / "deck.md").read_text(encoding="utf-8", errors="ignore")
        deck_fm_raw, _ = _split_frontmatter(deck_text)
        deck_fm = _parse_yaml_like(deck_fm_raw)
        deck_title = deck_fm.get("标题") or deck_dir.name
    except Exception:
        deck_title = deck_dir.name

    section_dirs = sorted([p for p in deck_dir.iterdir() if p.is_dir() and p.name.startswith("section_")])
    tasks: list = []
    for sec_dir in section_dirs:
        try:
            sec_text = (sec_dir / "section.md").read_text(encoding="utf-8", errors="ignore")
            sec_fm_raw, _ = _split_frontmatter(sec_text)
            sec_fm = _parse_yaml_like(sec_fm_raw)
            sec_title = sec_fm.get("章节标题") or sec_dir.name
        except Exception:
            sec_title = sec_dir.name
        role_ctx = _section_role_context(sec_dir)
        for pos, sf in enumerate(sorted(sec_dir.glob("slide_*.md")), 1):
            tasks.append((sf, deck_title, sec_title, role_ctx, pos))

    if dry_run:
        # count how many need enhancement
        need = 0
        for sf, _, _, _, _ in tasks:
            try:
                text = sf.read_text(encoding="utf-8", errors="ignore")
                fm_raw, _ = _split_frontmatter(text)
                fm = _parse_yaml_like(fm_raw)
                if any(k not in fm or (isinstance(fm.get(k), list) and not fm[k]) or (isinstance(fm.get(k), str) and not fm[k]) for k in NEW_FIELDS):
                    need += 1
            except Exception:
                need += 1
        return {"deck": deck_dir.name, "total_slides": len(tasks), "need_enhance": need, "dry_run": True}

    changed = 0
    skipped = 0
    failed = 0
    fail_msgs: list = []
    with _cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(enhance_one_slide, *t): t[0] for t in tasks}
        for fut in _cf.as_completed(futs):
            try:
                sf, did_change, msg = fut.result()
            except Exception as e:
                failed += 1
                fail_msgs.append(f"executor exc: {e}")
                continue
            if did_change:
                changed += 1
            elif "OK" in msg or "already has" in msg:
                skipped += 1
            else:
                failed += 1
                fail_msgs.append(f"{sf.name}: {msg}")
    return {
        "deck": deck_dir.name,
        "total_slides": len(tasks),
        "changed": changed,
        "skipped_already_done": skipped,
        "failed": failed,
        "failure_details": fail_msgs[:5],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", help="Restrict to one deck dir name (default: all)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.deck:
        target = DECKS_DIR / args.deck
        if not target.exists():
            print(f"deck not found: {target}")
            return 1
        deck_dirs = [target]
    else:
        deck_dirs = sorted([p for p in DECKS_DIR.iterdir() if p.is_dir() and (p / "deck.md").exists()])

    print(f"Processing {len(deck_dirs)} deck(s) with {args.workers} workers, dry_run={args.dry_run}")
    total_changed = total_failed = 0
    for i, dd in enumerate(deck_dirs, 1):
        t0 = time.time()
        r = enhance_deck(dd, workers=args.workers, dry_run=args.dry_run)
        dt = time.time() - t0
        print(f"[{i}/{len(deck_dirs)}] {r} ({dt:.1f}s)", flush=True)
        total_changed += r.get("changed") or 0
        total_failed += r.get("failed") or 0
    print(f"\nDONE. total changed: {total_changed}, failed: {total_failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
