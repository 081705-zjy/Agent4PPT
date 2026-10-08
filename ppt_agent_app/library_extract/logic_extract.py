"""logic_extract.py — Extract deck_level + section_level logic patterns.

Reads 29 deck corpus from data/resources_library/material/decks/,
runs 2 Claude skills in batches of N decks (default 4), accumulates
patterns across batches with cross-batch carrier merge, writes per-pattern
.md + .json files + INDEX.json.

Why batch_size=4: section_level skill output approaches Claude's 32K-token
single-response limit at batch_size=7. Batch 4 keeps output well under cap.

Output layout:
  data/resources_library/logic/
    ├── INDEX.json
    ├── .batches/                              (raw audit trail)
    │   ├── deck_level_batch_<N>_input.json
    │   ├── deck_level_batch_<N>.json
    │   ├── section_level_batch_<N>_input.json
    │   └── section_level_batch_<N>.json
    ├── deck_level/<pattern_id>.md             (human-readable)
    ├── deck_level/<pattern_id>.json           (full data)
    ├── section_level/<pattern_id>.md
    └── section_level/<pattern_id>.json

Usage:
    python3 -m ppt_agent_app.library_extract.logic_extract              # full run
    python3 -m ppt_agent_app.library_extract.logic_extract --dry-run    # plan only
    python3 -m ppt_agent_app.library_extract.logic_extract --layer deck_level
    python3 -m ppt_agent_app.library_extract.logic_extract --batch-size 4
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from .. import claude_cli
from ..models import ROOT, now


# ──────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────

BATCH_SIZE_DEFAULT = 4

MATERIAL_DECKS = ROOT / "data" / "resources_library" / "material" / "decks"
DECKS_INDEX_PATH = ROOT / "data" / "resources_library" / "material" / "decks-index.json"
LOGIC_ROOT = ROOT / "data" / "resources_library" / "logic"
BATCHES_DIR = LOGIC_ROOT / ".batches"

DECK_LEVEL_SKILL = "skills/resources_library/logic/deck_level_extract.md"
SECTION_LEVEL_SKILL = "skills/resources_library/logic/section_level_extract.md"

DECK_TIMEOUT_DEFAULT = 1200    # 20 min per deck_level batch
SECTION_TIMEOUT_DEFAULT = 1800  # 30 min per section_level batch

STRUCTURAL_ROLES = {"cover_candidate", "toc_candidate", "chapter_candidate", "ending_candidate"}

# v30.4 refinement: also treat first slide of "structural" sections as
# structural pages. Only sections whose FIRST page is functionally a
# structural transition (not content) qualify.
STRUCTURAL_SECTION_ROLES = {
    "opening",
    "cover",
    "agenda",
    "framework",
    "closing",
}

# v30.6 refinement (post-process 细分角色 based): fine-grained structural
# subtypes computed by ppt_agent_app.tools.classify_structural_subtype.
STRUCTURAL_SUBTYPES = {
    "cover",              # deck 封面
    "toc_main",           # 总览目录 (无高亮)
    "chapter_transition", # 章间过渡骨架 (进度目录 或 PART XX 分隔)
    "toc_section",        # 章内进度目录 (章内层次/框架 + 某项高亮)
    "ending",             # 结尾致谢
}

SLIDE_KEEP = {
    "页序号", "页面角色", "标题", "核心论断", "本页讲什么",
    "关键文字", "视觉骨架", "上页角色", "下页角色",
    "细分角色",  # v30.5: post-process structural subtype
}
SECTION_KEEP = {
    "章节标识", "章节序号", "章节角色", "标题", "页码范围", "页数",
    "页ID列表", "章节叙事", "页间关系", "适合复用场景", "在deck中的位置",
}
DECK_KEEP = {
    "deck标识", "目录名", "标题", "总页数", "章节数", "章节列表",
    "主题标签", "目标受众", "报告类型", "适用场景", "论述总结",
    "论述弧线", "适合复用场景", "不适合复用场景",
}


# ──────────────────────────────────────────────────────────────────────────
# Corpus loading (canonical filter mirror to /tmp/run_logic_batch0.py)
# ──────────────────────────────────────────────────────────────────────────


def _strip(d: dict, keep: set) -> dict:
    return {k: v for k, v in d.items() if k in keep}


def load_canonical_deck(deck_dir: Path) -> dict:
    """Load deck.json + canonical sections (by 章节列表 whitelist) + all slides."""
    deck = json.loads((deck_dir / "deck.json").read_text(encoding="utf-8"))
    canonical = set(deck.get("章节列表") or [])
    sections = []
    for section_dir in sorted(deck_dir.iterdir()):
        if not section_dir.is_dir() or not section_dir.name.startswith("section_"):
            continue
        if canonical and section_dir.name not in canonical:
            continue
        sec_json_path = section_dir / "section.json"
        if not sec_json_path.exists():
            continue
        sec = json.loads(sec_json_path.read_text(encoding="utf-8"))
        slides = []
        for slide_file in sorted(section_dir.glob("slide_*.json")):
            try:
                slides.append(json.loads(slide_file.read_text(encoding="utf-8")))
            except Exception as e:
                print(f"  ! load fail {slide_file}: {e}", flush=True)
        sec["slides"] = slides
        sections.append(sec)
    deck["sections"] = sections
    return deck


def load_corpus_deck_dirs() -> list[Path]:
    """Return list of deck dirs (all valid decks from decks-index)."""
    idx = json.loads(DECKS_INDEX_PATH.read_text(encoding="utf-8"))
    out = []
    for entry in idx.get("decks") or []:
        if entry.get("分析状态") == "failed":
            continue
        name = entry.get("目录名")
        if not name:
            continue
        deck_dir = MATERIAL_DECKS / name
        if deck_dir.exists() and (deck_dir / "deck.json").exists():
            out.append(deck_dir)
    return out


# ──────────────────────────────────────────────────────────────────────────
# Input builders (per-batch)
# ──────────────────────────────────────────────────────────────────────────


def build_deck_level_input(deck_dirs: list[Path],
                            previous_batches_patterns: list[dict],
                            batch_index: int) -> dict:
    """Build deck_level_extract.md input for one batch.

    Structural slide selection (v30.5, 细分角色 based):
      Prefer the `细分角色` field written by
      `ppt_agent_app.tools.classify_structural_subtype`. Include a slide if
      its `细分角色` ∈ STRUCTURAL_SUBTYPES (cover / toc_main / toc_progress /
      toc_section / ending).

      Fallback (for legacy briefs without 细分角色):
        (a) 页面角色 ∈ STRUCTURAL_ROLES → include
        (b) i==0 AND 章节角色 ∈ STRUCTURAL_SECTION_ROLES → include
      Plus (d) safeguard: deck page 1 always included.
    """
    decks_in_batch = []
    for deck_dir in deck_dirs:
        deck = load_canonical_deck(deck_dir)
        sections_stripped = []
        structural_slides_full = []
        included_page_indices = set()
        for sec in deck["sections"]:
            sections_stripped.append(_strip(sec, SECTION_KEEP))
            sec_role = sec.get("章节角色") or ""
            for i, sl in enumerate(sec.get("slides", [])):
                subtype = sl.get("细分角色")
                slide_role = sl.get("页面角色") or ""
                include = False
                if subtype in STRUCTURAL_SUBTYPES:
                    # v30.5 preferred path
                    include = True
                elif not subtype:
                    # Legacy fallback (no 细分角色 populated yet)
                    if slide_role in STRUCTURAL_ROLES:
                        include = True
                    elif i == 0 and sec_role in STRUCTURAL_SECTION_ROLES:
                        include = True
                if include:
                    structural_slides_full.append(_strip(sl, SLIDE_KEEP))
                    if sl.get("页序号") is not None:
                        included_page_indices.add(sl.get("页序号"))
        # (d) safeguard: deck page 1 must be included as cover
        if 1 not in included_page_indices and deck.get("sections"):
            first_sec = deck["sections"][0]
            first_slides = first_sec.get("slides") or []
            if first_slides and (first_slides[0].get("页序号") == 1):
                structural_slides_full.insert(0, _strip(first_slides[0], SLIDE_KEEP))
        deck_entry = {
            **_strip(deck, DECK_KEEP),
            "sections": sections_stripped,
            "structural_slides_full": structural_slides_full,
        }
        decks_in_batch.append(deck_entry)
    return {
        "batch_index": batch_index,
        "decks_in_this_batch": decks_in_batch,
        "previous_batches_patterns": previous_batches_patterns,
    }


def build_section_level_input(deck_dirs: list[Path],
                                previous_batches_patterns: list[dict],
                                batch_index: int) -> dict:
    """Build section_level_extract.md input for one batch (all slides included)."""
    decks_in_batch = []
    for deck_dir in deck_dirs:
        deck = load_canonical_deck(deck_dir)
        sections_with_slides = []
        for sec in deck["sections"]:
            slides_stripped = [_strip(s, SLIDE_KEEP) for s in sec.get("slides", [])]
            sec_entry = {**_strip(sec, SECTION_KEEP), "slides": slides_stripped}
            sections_with_slides.append(sec_entry)
        deck_entry = {**_strip(deck, DECK_KEEP), "sections": sections_with_slides}
        decks_in_batch.append(deck_entry)
    return {
        "batch_index": batch_index,
        "decks_in_this_batch": decks_in_batch,
        "previous_batches_patterns": previous_batches_patterns,
    }


def slim_patterns_for_dedup(patterns: list[dict]) -> list[dict]:
    """Trim patterns to essential fields for next-batch dedup context.

    Drops carriers (large) but keeps id + applicable_when + abstract_node_sequence +
    applicable_summary so Claude can decide "this new pattern == existing one".
    """
    out = []
    for p in patterns:
        out.append({
            "id": p.get("id"),
            "title": p.get("title"),
            "applicable_when": p.get("applicable_when"),
            "abstract_node_sequence": p.get("abstract_node_sequence"),
            "applicable_summary": p.get("applicable_summary"),
        })
    return out


# ──────────────────────────────────────────────────────────────────────────
# Claude call wrapper
# ──────────────────────────────────────────────────────────────────────────


def call_skill(label: str, skill_path: str, payload: dict, timeout: int,
                *, required_keys: tuple[str, ...] = ("patterns",),
                max_schema_retries: int = 2) -> dict:
    """Call Claude with skill + payload. Save input + raw output. Parse result.

    v30.7 additions:
      - `required_keys`: after JSON-parse, verify these top-level keys exist.
        If missing (e.g., Claude dropped `patterns` array and only emitted
        `coverage` stats), retry with corrective prompt.
      - `max_schema_retries`: how many times to re-invoke Claude when schema
        drift detected.
    """
    BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    in_path = BATCHES_DIR / f"{label}_input.json"
    in_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload_json = json.dumps(payload, ensure_ascii=False)
    print(f"    input: {in_path.name} ({len(payload_json)/1024:.0f} KB)", flush=True)

    base_prompt = (
        f"{label}: Extract logic patterns per the skill rules.\n"
        "Output strict JSON only.\n\nINPUT:\n" + payload_json
    )
    last_result = None
    for attempt in range(1 + max_schema_retries):
        prompt = base_prompt
        if attempt > 0:
            # Corrective prefix for schema retries
            missing = last_result.get("_missing_keys", []) if last_result else []
            correction = (
                f"⚠️ ATTEMPT {attempt+1}/{max_schema_retries+1}: previous output "
                f"was missing required top-level keys {missing}. The output MUST "
                f"contain top-level keys: {list(required_keys)} + batch_index + "
                f"extraction_notes + coverage. Do NOT emit only the `coverage` "
                f"object — that's an inner sub-field, not the whole output. "
                f"Re-read the skill Output section and produce the FULL structure.\n\n"
            )
            prompt = correction + base_prompt

        t = time.time()
        result = claude_cli.call_claude_json(prompt, skill=[skill_path], timeout=timeout)
        elapsed = time.time() - t
        print(f"    attempt {attempt+1}: done in {elapsed:.0f}s, ok={result.get('ok')}",
              flush=True)

        out_path = BATCHES_DIR / f"{label}.json"
        if not result.get("ok"):
            err = (result.get("error") or "unknown")[:300]
            print(f"    FAILED (cli): {err}", flush=True)
            raw = result.get("raw_excerpt") or ""
            if raw:
                (BATCHES_DIR / f"{label}_FAIL_raw_attempt{attempt+1}.txt").write_text(
                    raw, encoding="utf-8")
            last_result = result
            continue

        data = result.get("data")
        # v30.7b: catch non-dict data (e.g. Claude emitted top-level list/null/str)
        if not isinstance(data, dict):
            dtype = type(data).__name__
            preview = json.dumps(data, ensure_ascii=False)[:400] if data is not None else "None"
            print(f"    FAILED (not-dict): type={dtype} preview={preview!r}", flush=True)
            (BATCHES_DIR / f"{label}_NON_DICT_attempt{attempt+1}.txt").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) if data is not None else "null",
                encoding="utf-8")
            last_result = {"ok": False, "error": f"non-dict top level: {dtype}"}
            continue

        # v30.7 schema check
        missing = [k for k in required_keys if k not in data]
        if missing:
            print(f"    SCHEMA DRIFT: missing top-level keys {missing}", flush=True)
            (BATCHES_DIR / f"{label}_SCHEMA_DRIFT_attempt{attempt+1}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            last_result = {"ok": False, "error": "schema drift",
                           "_missing_keys": missing, "data": data}
            continue

        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "data": data}

    # All retries exhausted
    return {"ok": False, "error": (last_result or {}).get("error") or "all retries failed"}


def _load_existing_batch(layer: str, i: int) -> dict | None:
    """Load an already-saved batch output. Returns dict or None if missing."""
    path = BATCHES_DIR / f"{layer}_batch_{i}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "patterns" in data:
            return data
    except Exception:
        pass
    return None


def run_layer(layer: str, skill_path: str, builder_fn,
               batches: list[list[Path]], timeout: int,
               *, parallel_workers: int = 1,
               skip_existing: bool = True) -> list[dict]:
    """Run one layer (deck_level or section_level) across all batches.

    Modes:
      - `parallel_workers == 1` (default): sequential + cross-batch dedup —
        each batch sees prior batches' pattern IDs to reuse them.
      - `parallel_workers > 1`: parallel + FROZEN seed dedup — remaining
        batches see only the seed (existing on-disk outputs), not each
        other's live outputs. Trade-off: faster wall-clock but slightly
        more duplicate pattern IDs (dedup by post-hoc merge only).

    `skip_existing=True` (default): reuse `.batches/<layer>_batch_<i>.json`
    if already saved from a previous run, so interrupted jobs can resume.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    n = len(batches)
    all_outputs: list[dict | None] = [None] * n

    # Pass 1: load existing outputs (both modes benefit from resume)
    existing_indices: list[int] = []
    for i in range(n):
        if skip_existing:
            existing = _load_existing_batch(layer, i)
            if existing:
                all_outputs[i] = existing
                existing_indices.append(i)
    if existing_indices:
        print(f"  [{layer}] found {len(existing_indices)} existing outputs, reusing", flush=True)

    # Seed = patterns from all existing outputs (frozen dedup context)
    seed_patterns: list[dict] = []
    for i in existing_indices:
        seed_patterns.extend(slim_patterns_for_dedup(all_outputs[i].get("patterns") or []))

    remaining = [i for i in range(n) if all_outputs[i] is None]
    if not remaining:
        print(f"  [{layer}] all {n} batches already done", flush=True)
        return [x for x in all_outputs if x]

    # ------------------------------------------------------------------
    # Sequential mode
    # ------------------------------------------------------------------
    if parallel_workers <= 1:
        previous_patterns: list[dict] = list(seed_patterns)
        for i in remaining:
            label = f"{layer}_batch_{i}"
            print(f"  [{layer}] batch {i}/{n-1} ({len(batches[i])} decks)", flush=True)
            payload = builder_fn(batches[i], previous_patterns, i)
            result = call_skill(label, skill_path, payload, timeout)
            if not result.get("ok"):
                print(f"    ! batch {i} failed, continuing with what we have", flush=True)
                continue
            data = result["data"]
            all_outputs[i] = data
            new_patterns = slim_patterns_for_dedup(data.get("patterns", []))
            previous_patterns.extend(new_patterns)
            print(f"    +{len(new_patterns)} patterns this batch "
                  f"(total in dedup pool: {len(previous_patterns)})", flush=True)
        return [x for x in all_outputs if x]

    # ------------------------------------------------------------------
    # Parallel mode — frozen seed, no cross-worker dedup
    # ------------------------------------------------------------------
    print(f"  [{layer}] parallel mode: {parallel_workers} workers × "
          f"{len(remaining)} batches (seed={len(seed_patterns)} patterns)",
          flush=True)

    def _run_one(i: int) -> tuple[int, dict | None]:
        label = f"{layer}_batch_{i}"
        print(f"  [{layer}] START batch {i}/{n-1} ({len(batches[i])} decks)", flush=True)
        payload = builder_fn(batches[i], seed_patterns, i)
        result = call_skill(label, skill_path, payload, timeout)
        if not result.get("ok"):
            print(f"  [{layer}] FAIL batch {i}: "
                  f"{(result.get('error') or 'unknown')[:100]}", flush=True)
            return i, None
        data = result["data"]
        n_new = len(slim_patterns_for_dedup(data.get("patterns", [])))
        print(f"  [{layer}] DONE batch {i}: +{n_new} patterns", flush=True)
        return i, data

    with ThreadPoolExecutor(max_workers=parallel_workers) as pool:
        futures = [pool.submit(_run_one, i) for i in remaining]
        for fut in as_completed(futures):
            idx, data = fut.result()
            if data is not None:
                all_outputs[idx] = data

    return [x for x in all_outputs if x]


# ──────────────────────────────────────────────────────────────────────────
# Cross-batch merge — same pattern_id from different batches → combine carriers
# ──────────────────────────────────────────────────────────────────────────


def merge_carriers_across_batches(batch_outputs: list[dict]) -> dict:
    """Merge batch outputs into deduped {pattern_id: merged_pattern_dict}.

    For each pattern_id:
      - If first seen, copy entirely (incl. carriers).
      - If seen before, append carriers (dedup by (deck_id, section_id_or_none)).
      - Update source_count + confidence based on total carrier count.
    """
    merged: dict[str, dict] = {}
    for batch_out in batch_outputs:
        for p in batch_out.get("patterns") or []:
            pid = p.get("id")
            if not pid:
                continue
            if pid not in merged:
                merged[pid] = json.loads(json.dumps(p))  # deep copy
                merged[pid].setdefault("carriers", [])
            else:
                existing_carriers = merged[pid].get("carriers") or []
                existing_keys = {
                    (c.get("deck_id"), c.get("section_id") or "_deck_level_")
                    for c in existing_carriers
                }
                for c in (p.get("carriers") or []):
                    key = (c.get("deck_id"), c.get("section_id") or "_deck_level_")
                    if key not in existing_keys:
                        existing_carriers.append(c)
                        existing_keys.add(key)
                merged[pid]["carriers"] = existing_carriers

    # Recompute source_count + confidence (final, after merge)
    for pid, p in merged.items():
        c_count = len(p.get("carriers") or [])
        p["source_count"] = c_count
        p.pop("source_count_in_this_batch", None)
        if c_count >= 3:
            p["confidence"] = "high"
        elif c_count == 2:
            p["confidence"] = "medium"
        else:
            p["confidence"] = "low"
        p.pop("confidence_estimate", None)
    return merged


# ──────────────────────────────────────────────────────────────────────────
# Output writing
# ──────────────────────────────────────────────────────────────────────────


def _safe_id(s: str) -> str:
    """Make a string safe for use as a filename."""
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in str(s))[:100] or "unnamed"


def write_pattern_files(layer: str, pattern: dict) -> tuple[Path, Path]:
    """Write per-pattern .md (human) + .json (full data) under logic/<layer>/."""
    pid = pattern.get("id") or "unknown"
    safe = _safe_id(pid)
    out_dir = LOGIC_ROOT / layer
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{safe}.md"
    json_path = out_dir / f"{safe}.json"

    # Full pattern dict → .json
    json_path.write_text(json.dumps(pattern, ensure_ascii=False, indent=2), encoding="utf-8")

    # Light frontmatter + readable summary → .md
    fm_lines = ["---"]
    fm_lines.append(f"id: {pid}")
    fm_lines.append(f"layer: {layer}")
    fm_lines.append(f"title: {pattern.get('title', '')}")
    fm_lines.append(f"source_count: {pattern.get('source_count', 0)}")
    fm_lines.append(f"confidence: {pattern.get('confidence', 'low')}")
    aw = pattern.get("applicable_when") or {}
    if aw.get("report_type"):
        fm_lines.append(f"report_types: {json.dumps(aw['report_type'], ensure_ascii=False)}")
    if aw.get("chapter_role"):
        fm_lines.append(f"chapter_roles: {json.dumps(aw['chapter_role'], ensure_ascii=False)}")
    fm_lines.append(f"generated_at: {now()}")
    fm_lines.append("---")

    body_lines = [
        f"# {pattern.get('title', pid)}",
        "",
        f"**ID**: `{pid}`",
        f"**Layer**: {layer}",
        f"**Source count**: {pattern.get('source_count', 0)} carriers",
        f"**Confidence**: {pattern.get('confidence', 'low')}",
        "",
        "## 适用条件",
        "```json",
        json.dumps(aw, ensure_ascii=False, indent=2),
        "```",
        "",
        "## 抽象骨架 (abstract_node_sequence)",
        "```json",
        json.dumps(pattern.get("abstract_node_sequence") or [], ensure_ascii=False, indent=2),
        "```",
        "",
        f"## Carriers ({pattern.get('source_count', 0)} 个)",
    ]
    for i, c in enumerate(pattern.get("carriers") or []):
        body_lines.append(f"\n### Carrier {i+1}: {c.get('deck_id', '?')}")
        body_lines.append(f"- section_id: `{c.get('section_id', '(deck-level)')}`")
        if c.get("deck_topic_tags"):
            body_lines.append(f"- deck_topic_tags: {c['deck_topic_tags']}")
        if c.get("match_evidence"):
            body_lines.append(f"- match_evidence: {c['match_evidence']}")

    body_lines += [
        "",
        f"## Applicable summary",
        pattern.get("applicable_summary", ""),
        "",
        f"## Anti-patterns",
        "```json",
        json.dumps(pattern.get("anti_patterns") or [], ensure_ascii=False, indent=2),
        "```",
        "",
        f"## 完整 pattern 数据",
        f"见同目录 `{safe}.json`",
    ]

    md_path.write_text("\n".join(fm_lines) + "\n\n" + "\n".join(body_lines), encoding="utf-8")
    return md_path, json_path


def write_logic_index(deck_patterns: dict, section_patterns: dict) -> Path:
    """Write INDEX.json summarizing all logic patterns."""
    entries = []
    for layer, patterns_dict in [("deck_level", deck_patterns), ("section_level", section_patterns)]:
        for pid, p in patterns_dict.items():
            entries.append({
                "id": pid,
                "layer": layer,
                "title": p.get("title", ""),
                "source_count": p.get("source_count", 0),
                "confidence": p.get("confidence", "low"),
                "applicable_when_summary": p.get("applicable_when") or {},
                "applicable_summary": p.get("applicable_summary", ""),
                "path_json": f"{layer}/{_safe_id(pid)}.json",
                "path_md": f"{layer}/{_safe_id(pid)}.md",
            })
    # Sort: layer (deck_level first), then confidence (high > medium > low), then source_count desc
    conf_rank = {"high": 0, "medium": 1, "low": 2}
    entries.sort(key=lambda e: (e["layer"], conf_rank.get(e["confidence"], 9), -e["source_count"]))

    idx = {
        "schema_version": "1.0",
        "generated_at": now(),
        "patterns_count": len(entries),
        "by_layer": {
            "deck_level": len(deck_patterns),
            "section_level": len(section_patterns),
        },
        "by_confidence": {
            "high": sum(1 for e in entries if e["confidence"] == "high"),
            "medium": sum(1 for e in entries if e["confidence"] == "medium"),
            "low": sum(1 for e in entries if e["confidence"] == "low"),
        },
        "entries": entries,
    }
    out_path = LOGIC_ROOT / "INDEX.json"
    out_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Show plan + batch split, no Claude calls.")
    parser.add_argument("--layer", choices=["deck_level", "section_level", "both"],
                        default="both", help="Which layer to extract.")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE_DEFAULT,
                        help=f"Decks per batch for deck_level (default {BATCH_SIZE_DEFAULT}).")
    parser.add_argument("--section-batch-size", type=int, default=1,
                        help="Decks per batch for section_level (default 2; smaller "
                             "than deck_level because section_level input includes all "
                             "slide content and can trigger CLI ZlibError / schema drift "
                             "at 4 decks/batch).")
    parser.add_argument("--deck-timeout", type=int, default=DECK_TIMEOUT_DEFAULT)
    parser.add_argument("--section-timeout", type=int, default=SECTION_TIMEOUT_DEFAULT)
    parser.add_argument("--parallel-workers", type=int, default=1,
                        help="Concurrent Claude CLI subprocess count for run_layer. "
                             "Default 1 (sequential). >1 = parallel with frozen dedup seed "
                             "(existing on-disk batches provide the seed, remaining batches "
                             "see the same frozen seed — no cross-worker cross-contamination).")
    parser.add_argument("--no-skip-existing", action="store_true",
                        help="Rerun all batches even if `.batches/<layer>_batch_<i>.json` exists.")
    args = parser.parse_args()
    return run(args)


def run(args):
    """Programmatic entry point. `args` = argparse.Namespace with same fields as main()."""
    print(f">>> logic_extract start at {time.strftime('%H:%M:%S')}", flush=True)
    sec_bs = getattr(args, "section_batch_size", 1)
    print(f"  args: layer={args.layer} deck_batch_size={args.batch_size} "
          f"section_batch_size={sec_bs}", flush=True)

    deck_dirs = load_corpus_deck_dirs()
    print(f"  loaded {len(deck_dirs)} deck dirs from {MATERIAL_DECKS}", flush=True)

    # Split into batches — separate per layer (section_level uses smaller batches
    # to avoid CLI ZlibError / Claude schema drift on large inputs)
    bs = args.batch_size
    batches = [deck_dirs[i:i + bs] for i in range(0, len(deck_dirs), bs)]
    sec_batches = [deck_dirs[i:i + sec_bs] for i in range(0, len(deck_dirs), sec_bs)]
    print(f"  deck_level: {len(batches)} batches (size={bs}): {[len(b) for b in batches]}",
          flush=True)
    print(f"  section_level: {len(sec_batches)} batches (size={sec_bs}): "
          f"{[len(b) for b in sec_batches]}", flush=True)

    if args.dry_run:
        print(f"\n[dry-run] plan:", flush=True)
        if args.layer in ("deck_level", "both"):
            print(f"  deck_level: {len(batches)} Claude calls × ≤{args.deck_timeout}s timeout")
        if args.layer in ("section_level", "both"):
            print(f"  section_level: {len(sec_batches)} Claude calls × ≤{args.section_timeout}s timeout")
        print(f"  output: {LOGIC_ROOT}/")
        return {"ok": True, "dry_run": True}

    # Ensure output dirs
    LOGIC_ROOT.mkdir(parents=True, exist_ok=True)
    (LOGIC_ROOT / "deck_level").mkdir(exist_ok=True)
    (LOGIC_ROOT / "section_level").mkdir(exist_ok=True)
    BATCHES_DIR.mkdir(parents=True, exist_ok=True)

    deck_outputs: list[dict] = []
    section_outputs: list[dict] = []

    parallel_workers = getattr(args, "parallel_workers", 1)
    skip_existing = not getattr(args, "no_skip_existing", False)

    if args.layer in ("deck_level", "both"):
        print(f"\n=== Phase 1: deck_level layer ({len(batches)} batches) ===", flush=True)
        t = time.time()
        deck_outputs = run_layer(
            "deck_level", DECK_LEVEL_SKILL, build_deck_level_input,
            batches, args.deck_timeout,
            parallel_workers=parallel_workers, skip_existing=skip_existing,
        )
        print(f"  deck_level phase done in {time.time()-t:.0f}s", flush=True)

    if args.layer in ("section_level", "both"):
        print(f"\n=== Phase 2: section_level layer ({len(sec_batches)} batches, "
              f"size={sec_bs}) ===", flush=True)
        t = time.time()
        section_outputs = run_layer(
            "section_level", SECTION_LEVEL_SKILL, build_section_level_input,
            sec_batches, args.section_timeout,
            parallel_workers=parallel_workers, skip_existing=skip_existing,
        )
        print(f"  section_level phase done in {time.time()-t:.0f}s", flush=True)

    print(f"\n=== Phase 3: cross-batch carrier merge ===", flush=True)
    deck_patterns = merge_carriers_across_batches(deck_outputs) if deck_outputs else {}
    section_patterns = merge_carriers_across_batches(section_outputs) if section_outputs else {}
    print(f"  deck_level: {len(deck_patterns)} unique patterns", flush=True)
    print(f"  section_level: {len(section_patterns)} unique patterns", flush=True)

    print(f"\n=== Phase 4: write per-pattern .md + .json ===", flush=True)
    for pid, p in deck_patterns.items():
        write_pattern_files("deck_level", p)
    for pid, p in section_patterns.items():
        write_pattern_files("section_level", p)
    print(f"  wrote {len(deck_patterns)+len(section_patterns)} pattern files", flush=True)

    idx_path = write_logic_index(deck_patterns, section_patterns)
    print(f"  INDEX: {idx_path}", flush=True)

    return {
        "ok": True,
        "deck_patterns": len(deck_patterns),
        "section_patterns": len(section_patterns),
        "index": str(idx_path),
    }


if __name__ == "__main__":
    main()
