"""rule_extract.py — Extract Claude-derived rules (visual_authoring + narrative_flow).

Mirror of logic_extract.py but for the rule library. Runs 2 Claude skills
in batches of N decks (default 4), accumulates rules across batches with
cross-batch dedup, writes per-rule .md + .json files + merges into INDEX.json.

Composes with rule_stats.py (Python statistical part):
  - rule_stats.py already wrote ~11 statistical rules to rule/<cat>/*.md
  - This script adds Claude-derived rules under the same rule/ tree
  - Final INDEX.json contains BOTH statistical + Claude rules

Output layout (additive to existing rule/):
  data/resources_library/rule/
    ├── INDEX.json                             (merged: statistical + Claude)
    ├── .batches/                              (raw audit trail)
    ├── visual/<rule_id>.{md,json}             (Claude visual_authoring)
    ├── authoring/<rule_id>.{md,json}          (Claude visual_authoring)
    ├── callback/<rule_id>.{md,json}           (Claude narrative_flow)
    ├── suspense_reveal/<rule_id>.{md,json}    (Claude narrative_flow)
    ├── chapter_transitions/<rule_id>.{md,json}
    ├── repetition_emphasis/<rule_id>.{md,json}
    ├── comparison_evidence/<rule_id>.{md,json}
    ├── anchor_trajectory/<rule_id>.{md,json}
    ├── structural_promise/<rule_id>.{md,json}
    ├── pacing/<rule_id>.{md,json}
    └── (existing statistical subdirs: text/ role_position/ structure/ adjacency/
         scenario/ narrative_flow_stats/)

Usage:
    python3 -m ppt_agent_app.library_extract.rule_extract              # full run
    python3 -m ppt_agent_app.library_extract.rule_extract --dry-run
    python3 -m ppt_agent_app.library_extract.rule_extract --skill visual_authoring
    python3 -m ppt_agent_app.library_extract.rule_extract --batch-size 4
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .. import claude_cli
from ..models import ROOT, now


# ──────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────

BATCH_SIZE_DEFAULT = 1    # rule inputs at bs=4 → 189 KB (Claude ZlibError); bs=1 → 73 KB safe

MATERIAL_DECKS = ROOT / "data" / "resources_library" / "material" / "decks"
DECKS_INDEX_PATH = ROOT / "data" / "resources_library" / "material" / "decks-index.json"
RULE_ROOT = ROOT / "data" / "resources_library" / "rule"
BATCHES_DIR = RULE_ROOT / ".batches"

VISUAL_AUTHORING_SKILL = "skills/resources_library/rule/rule_extract_visual_authoring.md"
NARRATIVE_FLOW_SKILL = "skills/resources_library/rule/rule_extract_narrative_flow.md"

VA_TIMEOUT_DEFAULT = 1500    # 25 min per visual_authoring batch
NF_TIMEOUT_DEFAULT = 1800    # 30 min per narrative_flow batch

# 2-tier mapping (Phase R, 2026-06-28)
LOGIC_STORY_CATEGORIES = {
    "callback", "suspense_reveal", "chapter_transitions",
    "repetition_emphasis", "comparison_evidence", "anchor_trajectory",
    "structural_promise", "pacing",
    "narrative_flow_stats", "role_position", "structure", "scenario", "adjacency",
}
PAGE_SPECIFIC_CATEGORIES = {"visual", "authoring", "text"}


def _tier_for_category(category: str) -> str:
    if category in LOGIC_STORY_CATEGORIES:
        return "logic_story"
    if category in PAGE_SPECIFIC_CATEGORIES:
        return "page_specific"
    return "unknown"


# Subdirs for Claude-derived rules (kept for backward reference)
VISUAL_AUTHORING_CATEGORIES = {"visual", "authoring"}
NARRATIVE_FLOW_CATEGORIES = {
    "callback", "suspense_reveal", "chapter_transitions", "repetition_emphasis",
    "comparison_evidence", "anchor_trajectory", "structural_promise", "pacing",
}

# Same canonical loader as logic_extract
STRUCTURAL_ROLES = {"cover_candidate", "toc_candidate", "chapter_candidate", "ending_candidate"}
SLIDE_KEEP = {
    "页序号", "页面角色", "标题", "核心论断", "本页讲什么",
    "关键文字", "视觉骨架", "上页角色", "下页角色",
}
SECTION_KEEP = {
    "章节标识", "章节序号", "章节角色", "标题", "页码范围", "页数",
    "页ID列表", "章节叙事", "页间关系", "在deck中的位置",
}
DECK_KEEP = {
    "deck标识", "目录名", "标题", "总页数", "章节数", "章节列表",
    "主题标签", "目标受众", "报告类型", "适用场景", "论述总结",
    "论述弧线",
}


# ──────────────────────────────────────────────────────────────────────────
# Corpus loading (same as logic_extract)
# ──────────────────────────────────────────────────────────────────────────


def _strip(d: dict, keep: set) -> dict:
    return {k: v for k, v in d.items() if k in keep}


def load_canonical_deck(deck_dir: Path) -> dict:
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
# Input builders (different from logic — slides organized differently per skill)
# ──────────────────────────────────────────────────────────────────────────


def build_visual_authoring_input(deck_dirs: list[Path],
                                   previous_batches_rules: list[dict],
                                   batch_index: int) -> dict:
    """Build visual_authoring input: per-deck `slides_by_role` (按 role 分桶)."""
    decks_in_batch = []
    for deck_dir in deck_dirs:
        deck = load_canonical_deck(deck_dir)
        slides_by_role: dict[str, list[dict]] = {}
        for sec in deck["sections"]:
            for s in sec.get("slides", []):
                role = s.get("页面角色") or "unknown"
                slim = _strip(s, SLIDE_KEEP)
                slim["section_role"] = sec.get("章节角色") or ""
                slides_by_role.setdefault(role, []).append(slim)
        deck_entry = {
            **_strip(deck, DECK_KEEP),
            "slides_by_role": slides_by_role,
        }
        decks_in_batch.append(deck_entry)
    return {
        "batch_index": batch_index,
        "decks_in_this_batch": decks_in_batch,
        "previous_batches_rules": previous_batches_rules,
    }


def build_narrative_flow_input(deck_dirs: list[Path],
                                 previous_batches_rules: list[dict],
                                 batch_index: int) -> dict:
    """Build narrative_flow input: per-deck `slides_in_order` (保持 deck 顺序)."""
    decks_in_batch = []
    for deck_dir in deck_dirs:
        deck = load_canonical_deck(deck_dir)
        slides_in_order = []
        sections_outline = []
        for sec in deck["sections"]:
            sections_outline.append({
                "section_index": sec.get("章节序号"),
                "section_role": sec.get("章节角色"),
                "标题": sec.get("标题"),
                "页码范围": sec.get("页码范围"),
            })
            for s in sec.get("slides", []):
                slim = _strip(s, SLIDE_KEEP)
                slim["section_id"] = sec.get("章节标识") or ""
                slim["section_role"] = sec.get("章节角色") or ""
                slides_in_order.append(slim)
        # ensure sorted by 页序号
        slides_in_order.sort(key=lambda x: x.get("页序号") or 0)
        deck_entry = {
            **_strip(deck, DECK_KEEP),
            "slides_in_order": slides_in_order,
            "sections_outline": sections_outline,
        }
        decks_in_batch.append(deck_entry)
    return {
        "batch_index": batch_index,
        "decks_in_this_batch": decks_in_batch,
        "previous_batches_rules": previous_batches_rules,
    }


def slim_rules_for_dedup(rules: list[dict]) -> list[dict]:
    """Trim rules for next-batch dedup context."""
    out = []
    for r in rules:
        out.append({
            "id": r.get("id"),
            "category": r.get("category"),
            "title": r.get("title"),
            "description": r.get("description"),
            "applicable_role": r.get("applicable_role"),
            "applicable_when": r.get("applicable_when"),
        })
    return out


# ──────────────────────────────────────────────────────────────────────────
# Claude call wrapper
# ──────────────────────────────────────────────────────────────────────────


def call_skill(label: str, skill_path: str, payload: dict, timeout: int,
                *, required_keys: tuple[str, ...] = ("rules",),
                max_retries: int = 2) -> dict:
    """Call Claude with retry on CLI / JSON / schema failure.

    Retries with corrective prompt when: CLI rc!=0, empty stdout, JSON decode fail,
    top-level is not a dict, or required keys missing.
    """
    BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    in_path = BATCHES_DIR / f"{label}_input.json"
    in_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload_json = json.dumps(payload, ensure_ascii=False)
    print(f"    input: {in_path.name} ({len(payload_json)/1024:.0f} KB)", flush=True)

    base_prompt = (
        f"{label}: Extract rules per the skill rules.\n"
        "Output strict JSON only.\n\nINPUT:\n" + payload_json
    )
    last_err = None
    for attempt in range(1 + max_retries):
        prompt = base_prompt
        if attempt > 0:
            correction = (
                f"⚠️ ATTEMPT {attempt+1}/{max_retries+1}: prior attempt errored "
                f"({(last_err or 'unknown')[:150]}). Ensure output is strict JSON "
                f"with top-level keys {list(required_keys)} + batch_index + coverage. "
                f"First char must be `{{`. No prose preamble, no code fences.\n\n"
            )
            prompt = correction + base_prompt
        t = time.time()
        result = claude_cli.call_claude_json(prompt, skill=[skill_path], timeout=timeout)
        elapsed = time.time() - t
        print(f"    attempt {attempt+1}: done in {elapsed:.0f}s, ok={result.get('ok')}",
              flush=True)

        out_path = BATCHES_DIR / f"{label}.json"
        if not result.get("ok"):
            last_err = (result.get("error") or "unknown")[:300]
            print(f"    FAILED (cli): {last_err}", flush=True)
            raw = result.get("raw_excerpt") or ""
            if raw:
                (BATCHES_DIR / f"{label}_FAIL_raw_attempt{attempt+1}.txt").write_text(
                    raw, encoding="utf-8")
            continue

        data = result.get("data")
        if not isinstance(data, dict):
            last_err = f"non-dict: {type(data).__name__}"
            print(f"    FAILED (not-dict): type={type(data).__name__}", flush=True)
            (BATCHES_DIR / f"{label}_NON_DICT_attempt{attempt+1}.txt").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) if data is not None else "null",
                encoding="utf-8")
            continue

        missing = [k for k in required_keys if k not in data]
        if missing:
            last_err = f"schema drift: missing {missing}"
            print(f"    SCHEMA DRIFT: missing {missing}", flush=True)
            (BATCHES_DIR / f"{label}_SCHEMA_DRIFT_attempt{attempt+1}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            continue

        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "data": data}

    return {"ok": False, "error": last_err or "all retries failed"}


def _load_existing_batch(layer: str, i: int) -> dict | None:
    """Load an already-saved batch output. Returns dict or None if missing."""
    path = BATCHES_DIR / f"{layer}_batch_{i}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "rules" in data:
            return data
    except Exception:
        pass
    return None


def run_skill_layer(skill_label: str, skill_path: str, builder_fn,
                     batches: list[list[Path]], timeout: int,
                     *, parallel_workers: int = 1,
                     skip_existing: bool = True) -> list[dict]:
    """Run one skill across all batches.

    Modes (same as logic_extract):
      - parallel_workers == 1: sequential + cross-batch dedup
      - parallel_workers > 1: parallel + FROZEN seed dedup

    skip_existing=True reuses `.batches/<skill_label>_batch_<i>.json` if saved.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    n = len(batches)
    all_outputs: list[dict | None] = [None] * n

    existing_indices: list[int] = []
    for i in range(n):
        if skip_existing:
            existing = _load_existing_batch(skill_label, i)
            if existing:
                all_outputs[i] = existing
                existing_indices.append(i)
    if existing_indices:
        print(f"  [{skill_label}] found {len(existing_indices)} existing outputs, reusing",
              flush=True)

    seed_rules: list[dict] = []
    for i in existing_indices:
        seed_rules.extend(slim_rules_for_dedup(all_outputs[i].get("rules") or []))

    remaining = [i for i in range(n) if all_outputs[i] is None]
    if not remaining:
        print(f"  [{skill_label}] all {n} batches already done", flush=True)
        return [x for x in all_outputs if x]

    if parallel_workers <= 1:
        previous_rules: list[dict] = list(seed_rules)
        for i in remaining:
            label = f"{skill_label}_batch_{i}"
            print(f"  [{skill_label}] batch {i}/{n-1} ({len(batches[i])} decks)", flush=True)
            payload = builder_fn(batches[i], previous_rules, i)
            result = call_skill(label, skill_path, payload, timeout)
            if not result.get("ok"):
                print(f"    ! batch {i} failed, continuing", flush=True)
                continue
            data = result["data"]
            all_outputs[i] = data
            new_rules = slim_rules_for_dedup(data.get("rules", []))
            previous_rules.extend(new_rules)
            print(f"    +{len(new_rules)} rules this batch "
                  f"(total in dedup pool: {len(previous_rules)})", flush=True)
        return [x for x in all_outputs if x]

    print(f"  [{skill_label}] parallel mode: {parallel_workers} workers × "
          f"{len(remaining)} batches (seed={len(seed_rules)} rules)", flush=True)

    def _run_one(i: int) -> tuple[int, dict | None]:
        label = f"{skill_label}_batch_{i}"
        print(f"  [{skill_label}] START batch {i}/{n-1} ({len(batches[i])} decks)",
              flush=True)
        payload = builder_fn(batches[i], seed_rules, i)
        result = call_skill(label, skill_path, payload, timeout)
        if not result.get("ok"):
            print(f"  [{skill_label}] FAIL batch {i}: "
                  f"{(result.get('error') or 'unknown')[:100]}", flush=True)
            return i, None
        data = result["data"]
        n_new = len(slim_rules_for_dedup(data.get("rules", [])))
        print(f"  [{skill_label}] DONE batch {i}: +{n_new} rules", flush=True)
        return i, data

    with ThreadPoolExecutor(max_workers=parallel_workers) as pool:
        futures = [pool.submit(_run_one, i) for i in remaining]
        for fut in as_completed(futures):
            idx, data = fut.result()
            if data is not None:
                all_outputs[idx] = data

    return [x for x in all_outputs if x]


# ──────────────────────────────────────────────────────────────────────────
# Cross-batch merge — same rule_id from different batches → combine carriers + hit_rate
# ──────────────────────────────────────────────────────────────────────────


def merge_rules_across_batches(batch_outputs: list[dict]) -> dict:
    """Merge: {rule_id: merged_rule} with combined hit_carriers + miss_carriers
    + recomputed hit_rate (weighted by batch sample counts).
    """
    merged: dict[str, dict] = {}
    for batch_out in batch_outputs:
        for r in batch_out.get("rules") or []:
            rid = r.get("id")
            if not rid:
                continue
            if rid not in merged:
                merged[rid] = json.loads(json.dumps(r))
                merged[rid].setdefault("hit_carriers", [])
                merged[rid].setdefault("miss_carriers", [])
                # Track per-batch hit_rates for final aggregation
                merged[rid]["_per_batch_hit_rates"] = [r.get("estimated_hit_rate_in_batch") or 0.0]
            else:
                # Append carriers (dedup by deck_id + slide_index_or_section_id)
                existing = merged[rid]
                hit_keys = {
                    (c.get("deck_id"), c.get("slide_index") or c.get("section_id") or "?")
                    for c in (existing.get("hit_carriers") or [])
                }
                for c in (r.get("hit_carriers") or []):
                    key = (c.get("deck_id"), c.get("slide_index") or c.get("section_id") or "?")
                    if key not in hit_keys:
                        existing["hit_carriers"].append(c)
                        hit_keys.add(key)
                miss_keys = {
                    (c.get("deck_id"), c.get("slide_index") or c.get("section_id") or "?")
                    for c in (existing.get("miss_carriers") or [])
                }
                for c in (r.get("miss_carriers") or []):
                    key = (c.get("deck_id"), c.get("slide_index") or c.get("section_id") or "?")
                    if key not in miss_keys:
                        existing["miss_carriers"].append(c)
                        miss_keys.add(key)
                existing["_per_batch_hit_rates"].append(r.get("estimated_hit_rate_in_batch") or 0.0)

    # Recompute final hit_rate (avg of per-batch) and enforcement_level
    for rid, r in merged.items():
        per_batch = r.pop("_per_batch_hit_rates", [])
        if per_batch:
            final_rate = sum(per_batch) / len(per_batch)
        else:
            final_rate = 0.0
        r["hit_rate"] = round(final_rate, 3)
        if final_rate >= 0.95:
            r["enforcement_level"] = "hard"
        elif final_rate >= 0.7:
            r["enforcement_level"] = "soft"
        else:
            r["enforcement_level"] = "discard"
        r.pop("estimated_hit_rate_in_batch", None)
    return merged


# ──────────────────────────────────────────────────────────────────────────
# Output writing
# ──────────────────────────────────────────────────────────────────────────


def _safe_id(s: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in str(s))[:100] or "unnamed"


def write_rule_files(rule: dict) -> tuple[Path, Path] | None:
    """Write per-rule .md + .json under rule/<tier>/<category>/.

    Returns None if rule is enforcement_level=discard (not emitted).
    """
    if rule.get("enforcement_level") == "discard":
        return None
    rid = rule.get("id") or "unknown"
    category = rule.get("category") or "unknown"
    tier = _tier_for_category(category)
    if tier == "unknown":
        print(f"  ! unknown tier for category {category!r} (rule {rid}); skipping", flush=True)
        return None
    safe = _safe_id(rid)
    out_dir = RULE_ROOT / tier / category
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{safe}.md"
    json_path = out_dir / f"{safe}.json"

    # Stamp tier on the JSON object for self-description
    rule = {**rule, "tier": tier}
    json_path.write_text(json.dumps(rule, ensure_ascii=False, indent=2), encoding="utf-8")

    fm_lines = ["---"]
    fm_lines.append(f"id: {rid}")
    fm_lines.append(f"category: {category}")
    fm_lines.append(f"tier: {tier}")
    fm_lines.append(f"enforcement_level: {rule.get('enforcement_level', 'soft')}")
    fm_lines.append("source: claude_extracted")
    fm_lines.append(f"hit_rate: {rule.get('hit_rate', 0.0)}")
    if rule.get("applicable_role"):
        fm_lines.append(f"applicable_role: {json.dumps(rule['applicable_role'], ensure_ascii=False)}")
    if rule.get("applicable_when"):
        fm_lines.append(f"applicable_when: {json.dumps(rule['applicable_when'], ensure_ascii=False)}")
    fm_lines.append(f"hit_carriers_count: {len(rule.get('hit_carriers') or [])}")
    fm_lines.append(f"miss_carriers_count: {len(rule.get('miss_carriers') or [])}")
    fm_lines.append(f"generated_at: {now()}")
    fm_lines.append("---")

    body = "\n".join([
        f"# {rule.get('title', rid)}",
        "",
        "## 描述",
        rule.get("description", ""),
        "",
        "## Evidence signals / what to check",
        "```json",
        json.dumps(rule.get("evidence_signals") or rule.get("what_to_check") or [],
                   ensure_ascii=False, indent=2),
        "```",
        "",
        f"## Hit carriers ({len(rule.get('hit_carriers') or [])} 个)",
        "见同目录 .json 文件",
        "",
        f"## Miss carriers ({len(rule.get('miss_carriers') or [])} 个反例)",
        "见同目录 .json 文件",
    ])

    md_path.write_text("\n".join(fm_lines) + "\n\n" + body, encoding="utf-8")
    return md_path, json_path


def rebuild_index_merged() -> Path:
    """Rebuild tier-aware INDEX.json files by scanning all .md frontmatters under
    rule/<tier>/.

    Writes 3 files:
      - rule/INDEX.json                  (top-level pointer)
      - rule/logic_story/INDEX.json      (per-tier full)
      - rule/page_specific/INDEX.json    (per-tier full)
    """
    from collections import Counter
    tier_entries: dict[str, list[dict]] = {"logic_story": [], "page_specific": []}
    for tier in ("logic_story", "page_specific"):
        tier_root = RULE_ROOT / tier
        if not tier_root.exists():
            continue
        for md_path in tier_root.rglob("*.md"):
            try:
                content = md_path.read_text(encoding="utf-8")
            except Exception:
                continue
            if not content.startswith("---"):
                continue
            end = content.find("\n---", 3)
            if end < 0:
                continue
            fm = content[3:end].strip()
            meta = {}
            for line in fm.splitlines():
                if ":" not in line:
                    continue
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
            rel_path = md_path.relative_to(tier_root).as_posix()
            try:
                hit_rate = float(meta.get("hit_rate", "0"))
            except ValueError:
                hit_rate = 0.0
            tier_entries[tier].append({
                "id": meta.get("id"),
                "category": meta.get("category"),
                "tier": tier,
                "enforcement_level": meta.get("enforcement_level", "soft"),
                "source": meta.get("source", "unknown"),
                "hit_rate": round(hit_rate, 3),
                "applies_to": meta.get("applies_to", "all"),
                "applicable_role": meta.get("applicable_role", ""),
                "applicable_when": meta.get("applicable_when", ""),
                "consume_hint": meta.get("consume_hint", ""),
                "path": rel_path,
            })

    # Per-tier INDEX
    tier_indexes = {}
    for tier, entries in tier_entries.items():
        by_cat = Counter(e["category"] for e in entries)
        by_enf = Counter(e["enforcement_level"] for e in entries)
        by_src = Counter(e["source"] for e in entries)
        idx = {
            "tier": tier,
            "tier_label_zh": "逻辑故事层" if tier == "logic_story" else "页面具体层",
            "schema_version": "2.0",
            "generated_at": now(),
            "rules_count": len(entries),
            "by_category": dict(by_cat),
            "by_enforcement_level": dict(by_enf),
            "by_source": dict(by_src),
            "entries": sorted(entries, key=lambda e: (
                e["source"],
                {"hard": 0, "soft": 1}.get(e["enforcement_level"], 9),
                e["category"] or "",
                e["id"] or "",
            )),
        }
        out_path = RULE_ROOT / tier / "INDEX.json"
        out_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
        tier_indexes[tier] = idx

    # Top-level INDEX
    top_idx = {
        "schema_version": "2.0",
        "generated_at": now(),
        "structure": "2-tier",
        "tiers": [
            {
                "tier": t,
                "tier_label_zh": "逻辑故事层" if t == "logic_story" else "页面具体层",
                "rules_count": idx["rules_count"],
                "index_path": f"{t}/INDEX.json",
                "by_category": idx["by_category"],
                "by_enforcement_level": idx["by_enforcement_level"],
            }
            for t, idx in tier_indexes.items()
        ],
        "total_rules": sum(idx["rules_count"] for idx in tier_indexes.values()),
    }
    out_top = RULE_ROOT / "INDEX.json"
    out_top.write_text(json.dumps(top_idx, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_top


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skill", choices=["visual_authoring", "narrative_flow", "both"],
                        default="both")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE_DEFAULT)
    parser.add_argument("--va-timeout", type=int, default=VA_TIMEOUT_DEFAULT)
    parser.add_argument("--nf-timeout", type=int, default=NF_TIMEOUT_DEFAULT)
    parser.add_argument("--parallel-workers", type=int, default=1,
                        help="Concurrent Claude CLI subprocess count (default 1 = serial). "
                             ">1 uses frozen seed dedup (same as logic_extract).")
    parser.add_argument("--no-skip-existing", action="store_true",
                        help="Rerun all batches even if `.batches/<layer>_batch_<i>.json` exists.")
    args = parser.parse_args()
    return run(args)


def run(args):
    """Programmatic entry point. `args` = argparse.Namespace with same fields as main()."""
    print(f">>> rule_extract start at {time.strftime('%H:%M:%S')}", flush=True)
    print(f"  args: skill={args.skill} batch_size={args.batch_size}", flush=True)

    deck_dirs = load_corpus_deck_dirs()
    print(f"  loaded {len(deck_dirs)} deck dirs", flush=True)

    bs = args.batch_size
    batches = [deck_dirs[i:i + bs] for i in range(0, len(deck_dirs), bs)]
    print(f"  {len(batches)} batches (size={bs}): {[len(b) for b in batches]}", flush=True)

    if args.dry_run:
        print(f"\n[dry-run] plan:", flush=True)
        if args.skill in ("visual_authoring", "both"):
            print(f"  visual_authoring: {len(batches)} Claude calls × ≤{args.va_timeout}s")
        if args.skill in ("narrative_flow", "both"):
            print(f"  narrative_flow: {len(batches)} Claude calls × ≤{args.nf_timeout}s")
        print(f"  output: {RULE_ROOT}/")
        for i, b in enumerate(batches):
            print(f"    batch {i}: " + ", ".join(d.name[:40] for d in b))
        return {"ok": True, "dry_run": True}

    RULE_ROOT.mkdir(parents=True, exist_ok=True)
    BATCHES_DIR.mkdir(parents=True, exist_ok=True)

    va_outputs: list[dict] = []
    nf_outputs: list[dict] = []
    parallel_workers = getattr(args, "parallel_workers", 1)
    skip_existing = not getattr(args, "no_skip_existing", False)

    if args.skill in ("visual_authoring", "both"):
        print(f"\n=== Phase 1: visual_authoring ({len(batches)} batches) ===", flush=True)
        t = time.time()
        va_outputs = run_skill_layer(
            "visual_authoring", VISUAL_AUTHORING_SKILL,
            build_visual_authoring_input, batches, args.va_timeout,
            parallel_workers=parallel_workers, skip_existing=skip_existing,
        )
        print(f"  visual_authoring done in {time.time()-t:.0f}s", flush=True)

    if args.skill in ("narrative_flow", "both"):
        print(f"\n=== Phase 2: narrative_flow ({len(batches)} batches) ===", flush=True)
        t = time.time()
        nf_outputs = run_skill_layer(
            "narrative_flow", NARRATIVE_FLOW_SKILL,
            build_narrative_flow_input, batches, args.nf_timeout,
            parallel_workers=parallel_workers, skip_existing=skip_existing,
        )
        print(f"  narrative_flow done in {time.time()-t:.0f}s", flush=True)

    print(f"\n=== Phase 3: cross-batch rule merge ===", flush=True)
    va_rules = merge_rules_across_batches(va_outputs) if va_outputs else {}
    nf_rules = merge_rules_across_batches(nf_outputs) if nf_outputs else {}
    print(f"  visual_authoring: {len(va_rules)} unique rules", flush=True)
    print(f"  narrative_flow: {len(nf_rules)} unique rules", flush=True)

    print(f"\n=== Phase 4: write per-rule .md + .json ===", flush=True)
    written = 0
    skipped = 0
    for rid, r in {**va_rules, **nf_rules}.items():
        res = write_rule_files(r)
        if res:
            written += 1
        else:
            skipped += 1
    print(f"  wrote {written} rule files (skipped {skipped} discard-level)", flush=True)

    print(f"\n=== Phase 5: rebuild INDEX.json (merge statistical + Claude) ===", flush=True)
    idx_path = rebuild_index_merged()
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    print(f"  INDEX: {idx_path}", flush=True)
    print(f"  rules_count: {idx.get('total_rules') or idx.get('rules_count')}", flush=True)
    print(f"  by_source: {idx['by_source']}", flush=True)
    print(f"  by_enforcement: {idx['by_enforcement_level']}", flush=True)

    return {"ok": True, "va_rules": len(va_rules), "nf_rules": len(nf_rules), "index": str(idx_path)}


if __name__ == "__main__":
    main()
