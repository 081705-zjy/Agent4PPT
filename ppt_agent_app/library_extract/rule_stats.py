"""rule_stats.py — Statistical rule extractor (Python-only, no Claude).

Scans 28 deck corpus from data/resources_library/material/decks/ and writes
statistical rules to data/resources_library/rule/<category>/<rule_id>.md.

Categories (Python-derivable):
  text/                 — title/claim/body length stats
  role_position/        — cover=slide_1, agenda=slide_2 hit rates
  structure/            — agenda/closing/references presence rates
  adjacency/            — top role-transitions (e.g. cover→agenda)
  scenario/             — per-scenario defaults (slide_count, section_count)
  narrative_flow_stats/ — anchor_first_appearance / structural_promise /
                         chapter_role_sequence statistics

Each rule.md has YAML frontmatter:
  ---
  id: <snake_case>
  category: <one of 6>
  enforcement_level: hard | soft | discard
  source: statistical
  hit_rate: 0.98
  sample_count: 1842
  applies_to: all | scenario-list
  ---
  # <Title>
  ## 描述
  ## 消费场景

Also writes INDEX.json summarizing all rules.

Usage:
    python3 -m ppt_agent_app.library_extract.rule_stats           # full build
    python3 -m ppt_agent_app.library_extract.rule_stats --dry-run # plan only
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median, quantiles

from ..models import ROOT, now


# ──────────────────────────────────────────────────────────────────────────
# Path constants
# ──────────────────────────────────────────────────────────────────────────

MATERIAL_DECKS = ROOT / "data" / "resources_library" / "material" / "decks"
RULE_ROOT = ROOT / "data" / "resources_library" / "rule"
DECKS_INDEX_PATH = ROOT / "data" / "resources_library" / "material" / "decks-index.json"

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


# 6 categories — each gets a subdirectory under rule/<tier>/
CATEGORIES = [
    "text",
    "role_position",
    "structure",
    "adjacency",
    "scenario",
    "narrative_flow_stats",
]


# ──────────────────────────────────────────────────────────────────────────
# Corpus loading (canonical-only, mirror logic_extract loader)
# ──────────────────────────────────────────────────────────────────────────


def load_corpus() -> list[dict]:
    """Load all valid decks with canonical sections + slides."""
    decks_index = json.loads(DECKS_INDEX_PATH.read_text(encoding="utf-8"))
    decks_out = []
    for entry in decks_index.get("decks") or []:
        if entry.get("分析状态") == "failed":
            continue
        deck_name = entry.get("目录名")
        if not deck_name:
            continue
        deck_dir = MATERIAL_DECKS / deck_name
        if not deck_dir.exists():
            continue
        deck_json_path = deck_dir / "deck.json"
        if not deck_json_path.exists():
            continue
        deck = json.loads(deck_json_path.read_text(encoding="utf-8"))
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
                except Exception:
                    continue
            sec["slides"] = slides
            sections.append(sec)
        deck["sections"] = sections
        decks_out.append(deck)
    return decks_out


# ──────────────────────────────────────────────────────────────────────────
# Stat helpers
# ──────────────────────────────────────────────────────────────────────────


def p_value(values: list[float], p: float) -> float:
    """Compute the p-th percentile (0.0-1.0). Returns max if values empty."""
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(p * (len(s) - 1))))
    return s[k]


def hit_rate_to_enforcement(hr: float) -> str:
    """≥0.95 → hard, 0.7-0.95 → soft, else discard."""
    if hr >= 0.95:
        return "hard"
    if hr >= 0.7:
        return "soft"
    return "discard"


def safe_int(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def has_quantitative(text: str) -> bool:
    """Heuristic: does the text contain a number/percentage/multiplier?"""
    if not text:
        return False
    return bool(re.search(r"\d[\d.,]*\s*[%×倍kKMG]", text) or re.search(r"\b\d{1,3}(?:[.,]\d+)?\b", text))


# ──────────────────────────────────────────────────────────────────────────
# Rule builders — one per category
# ──────────────────────────────────────────────────────────────────────────


def build_text_rules(decks: list[dict]) -> list[dict]:
    """Title / claim / body length statistics."""
    rules = []
    titles = []
    claims = []
    # bucket body lengths by report_type (enum, larger samples) not 适用场景 (free-text)
    body_lengths_by_report_type = defaultdict(list)
    for d in decks:
        report_type = d.get("报告类型") or "unknown"
        for sec in d["sections"]:
            for s in sec["slides"]:
                t = s.get("标题") or ""
                c = s.get("核心论断") or ""
                if t:
                    titles.append(len(t))
                if c:
                    claims.append(len(c))
                kt = s.get("关键文字") or []
                if isinstance(kt, list):
                    body_lengths_by_report_type[report_type].append(sum(len(x) for x in kt))

    if titles:
        rules.append({
            "id": "title_max_length_p95",
            "title": "Title 长度上限 p95",
            "description": f"全 corpus 中 slide 标题字数 95% 分位 ≤ {p_value(titles, 0.95):.0f} 字, 中位数 {median(titles):.0f} 字.",
            "consume_hint": "IDEA + OUTLINE prompt 灌入 + codex review Cat 1",
            "extra_fields": {
                "stat_summary": {
                    "p50": median(titles),
                    "p75": p_value(titles, 0.75),
                    "p95": p_value(titles, 0.95),
                    "max": max(titles),
                    "sample_count": len(titles),
                },
            },
            "hit_rate": sum(1 for x in titles if x <= 14) / len(titles),
        })

    if claims:
        rules.append({
            "id": "claim_max_length_p95",
            "title": "Claim 长度上限 p95",
            "description": f"全 corpus 中 slide 核心论断字数 95% 分位 ≤ {p_value(claims, 0.95):.0f} 字, 中位数 {median(claims):.0f} 字.",
            "consume_hint": "IDEA + OUTLINE prompt + codex review",
            "extra_fields": {
                "stat_summary": {
                    "p50": median(claims),
                    "p75": p_value(claims, 0.75),
                    "p95": p_value(claims, 0.95),
                    "max": max(claims),
                    "sample_count": len(claims),
                },
            },
            "hit_rate": sum(1 for x in claims if x <= 45) / len(claims),
        })

    # body density by report_type (enum-bucketed for real sample sizes)
    by_rt_summary = {}
    for rt, lengths in body_lengths_by_report_type.items():
        if lengths:
            by_rt_summary[rt] = {
                "p50": median(lengths),
                "p95": p_value([float(x) for x in lengths], 0.95),
                "sample_count": len(lengths),
            }
    if by_rt_summary:
        rules.append({
            "id": "body_density_by_report_type",
            "title": "Body 字数密度·按 报告类型 分桶",
            "description": "不同 报告类型 (paper_share / research_report / tutorial 等) 下 slide 关键文字字数的 p50/p95 分布.",
            "consume_hint": "IDEA prompt 灌入 — 按 brief.deliverable_type 取 报告类型, 用对应密度",
            "extra_fields": {"by_report_type": by_rt_summary},
            "hit_rate": 1.0,  # descriptive
        })

    for r in rules:
        r["category"] = "text"
        r["applies_to"] = "all"
    return rules


def build_role_position_rules(decks: list[dict]) -> list[dict]:
    """Cover / agenda / closing position consistency.

    agenda_at_slide_2 is **conditional** — only count decks that actually have
    an agenda (because most paper_share decks skip agenda).
    """
    rules = []
    cover_at_1_count = 0
    agenda_at_2_count = 0
    decks_with_agenda = 0
    refs_at_last_count = 0
    closing_at_last_2_count = 0
    total = len(decks)

    for d in decks:
        slides_flat = [(s.get("页序号"), s.get("页面角色") or "") for sec in d["sections"] for s in sec["slides"]]
        slides_flat.sort(key=lambda x: x[0] or 0)
        if not slides_flat:
            continue
        # cover_at_1
        if slides_flat[0][1] == "cover_candidate":
            cover_at_1_count += 1
        # agenda detection (anywhere in deck)
        agenda_indices = [i for i, (_, role) in enumerate(slides_flat) if role == "toc_candidate"]
        if agenda_indices:
            decks_with_agenda += 1
            # agenda at slide_2 (index 1 = position 2)
            if 1 in agenda_indices:
                agenda_at_2_count += 1
        # closing/references position
        last_role = slides_flat[-1][1]
        if last_role == "ending_candidate":
            refs_at_last_count += 1
        elif len(slides_flat) > 1 and slides_flat[-2][1] == "ending_candidate":
            closing_at_last_2_count += 1

    rules.append({
        "id": "cover_at_slide_1",
        "category": "role_position",
        "title": "Cover 仅 slide_1",
        "description": f"封面 (cover_candidate) 出现在 slide_index=1 的比例: {cover_at_1_count}/{total} = {cover_at_1_count/total:.2%}",
        "consume_hint": "IDEA / OUTLINE codex review Cat 8 (role_placement_violation)",
        "hit_rate": cover_at_1_count / max(total, 1),
        "applies_to": "all",
    })
    # Conditional rule: only meaningful for decks that have agenda
    if decks_with_agenda > 0:
        rules.append({
            "id": "agenda_at_slide_2_if_present",
            "category": "role_position",
            "title": "若 deck 有 Agenda, 则 Agenda 在 slide_2 (conditional)",
            "description": (
                f"在含 agenda 的 deck 中 ({decks_with_agenda}/{total}="
                f"{decks_with_agenda/total:.0%}), agenda 出现在 slide_2 的比例: "
                f"{agenda_at_2_count}/{decks_with_agenda} = {agenda_at_2_count/decks_with_agenda:.2%}"
            ),
            "consume_hint": "OUTLINE codex review (仅当 brief 决定含 agenda 时校验)",
            "hit_rate": agenda_at_2_count / max(decks_with_agenda, 1),
            "applies_to": "decks_with_agenda",
            "extra_fields": {
                "conditional_on": "deck has agenda (toc_candidate slide)",
                "denominator_decks": decks_with_agenda,
                "denominator_rate": decks_with_agenda / total,
            },
        })
    rules.append({
        "id": "closing_or_references_at_last_2_slides",
        "category": "role_position",
        "title": "Closing/References 必在末页 1-2 张",
        "description": f"deck 末页或倒数第 2 页是 ending_candidate 的比例: {(refs_at_last_count + closing_at_last_2_count)}/{total}",
        "consume_hint": "OUTLINE codex review",
        "hit_rate": (refs_at_last_count + closing_at_last_2_count) / max(total, 1),
        "applies_to": "all",
    })
    return rules


def build_structure_rules(decks: list[dict]) -> list[dict]:
    """Agenda / framework / closing presence rates."""
    rules = []
    total = len(decks)
    have_agenda = 0
    have_closing = 0
    have_refs = 0
    for d in decks:
        roles = set()
        for sec in d["sections"]:
            for s in sec["slides"]:
                roles.add(s.get("页面角色") or "")
        if "toc_candidate" in roles:
            have_agenda += 1
        if "ending_candidate" in roles:
            have_closing += 1
            have_refs += 1

    rules.append({
        "id": "agenda_presence_rate",
        "category": "structure",
        "title": "Agenda 在 deck 中存在",
        "description": f"含 agenda (toc_candidate) 的 deck 比例: {have_agenda}/{total} = {have_agenda/total:.2%}",
        "consume_hint": "IDEA prompt: 默认推荐含 agenda",
        "hit_rate": have_agenda / max(total, 1),
        "applies_to": "all",
    })
    rules.append({
        "id": "closing_presence_rate",
        "category": "structure",
        "title": "Closing 在 deck 末页",
        "description": f"含 closing (ending_candidate) 的 deck 比例: {have_closing}/{total} = {have_closing/total:.2%}",
        "consume_hint": "OUTLINE: 必须含 closing",
        "hit_rate": have_closing / max(total, 1),
        "applies_to": "all",
    })
    return rules


def build_adjacency_rules(decks: list[dict]) -> list[dict]:
    """Top role-transition frequencies."""
    transitions = Counter()
    total_trans = 0
    for d in decks:
        slides_flat = []
        for sec in d["sections"]:
            for s in sec["slides"]:
                slides_flat.append((s.get("页序号") or 0, s.get("页面角色") or ""))
        slides_flat.sort(key=lambda x: x[0])
        for i in range(len(slides_flat) - 1):
            transitions[(slides_flat[i][1], slides_flat[i + 1][1])] += 1
            total_trans += 1
    if total_trans == 0:
        return []
    # Top 10 most common transitions
    top10 = transitions.most_common(10)
    return [{
        "id": "top_role_transitions",
        "category": "adjacency",
        "title": "顶部 10 个上下页 role 过渡",
        "description": f"corpus 中 {total_trans} 个上下页 role 过渡, 前 10 频率.",
        "consume_hint": "OUTLINE prompt: 暗示自然过渡模式",
        "extra_fields": {
            "top_transitions": [
                {"from": frm or "<none>", "to": to_, "count": cnt, "rate": cnt / total_trans}
                for (frm, to_), cnt in top10
            ],
        },
        "hit_rate": 1.0,
        "applies_to": "all",
    }]


def build_scenario_rules(decks: list[dict]) -> list[dict]:
    """Per-report_type default deck size / section count.

    Group by `报告类型` (enum: paper_share / research_report / tutorial / ...)
    rather than `适用场景` (free-form string with sample_count=1 per scenario).
    `适用场景` kept as secondary axis for richer context.
    """
    by_type = defaultdict(lambda: {"slide_counts": [], "section_counts": [], "scenarios": Counter()})
    for d in decks:
        rt = d.get("报告类型") or "unknown"
        sc = d.get("适用场景") or "unknown"
        by_type[rt]["slide_counts"].append(safe_int(d.get("总页数")))
        by_type[rt]["section_counts"].append(safe_int(d.get("章节数")))
        by_type[rt]["scenarios"][sc] += 1
    if not by_type:
        return []
    summary = {}
    for rt, vals in by_type.items():
        if vals["slide_counts"]:
            summary[rt] = {
                "slide_count_p50": median(vals["slide_counts"]),
                "slide_count_p95": p_value([float(x) for x in vals["slide_counts"]], 0.95),
                "section_count_p50": median(vals["section_counts"]),
                "section_count_p95": p_value([float(x) for x in vals["section_counts"]], 0.95),
                "sample_count": len(vals["slide_counts"]),
                "top_scenarios": [{"scenario": s, "count": c} for s, c in vals["scenarios"].most_common(3)],
            }
    return [{
        "id": "report_type_default_deck_size",
        "category": "scenario",
        "title": "报告类型默认 deck 规模",
        "description": (
            "不同 报告类型 (paper_share / research_report / tutorial / 等) 下 deck 总页数 / "
            "章节数 的 p50/p95 分布. 每桶含 top-3 适用场景作上下文."
        ),
        "consume_hint": "IDEA prompt 灌入 — 按 brief.deliverable_type 取对应 report_type 默认 slide_count_target",
        "extra_fields": {"by_report_type": summary},
        "hit_rate": 1.0,
        "applies_to": "all",
    }]


def build_narrative_flow_stats_rules(decks: list[dict]) -> list[dict]:
    """anchor_first_appearance / structural_promise / chapter_role_sequence."""
    rules = []
    total = len(decks)

    # 1. main_anchor_first_appearance_at_cover (slide_1 含 主题标签 中 anchor 的比例)
    anchor_at_cover_count = 0
    for d in decks:
        tags = d.get("主题标签") or []
        if not tags:
            continue
        first_slide = None
        for sec in d["sections"]:
            for s in sec["slides"]:
                if s.get("页序号") == 1:
                    first_slide = s
                    break
            if first_slide:
                break
        if first_slide:
            title = first_slide.get("标题") or ""
            kt = " ".join(first_slide.get("关键文字") or [])
            text_lc = (title + " " + kt).lower()
            if any(t.lower() in text_lc for t in tags if isinstance(t, str)):
                anchor_at_cover_count += 1
    rules.append({
        "id": "main_anchor_first_appearance_at_cover",
        "category": "narrative_flow_stats",
        "title": "主 anchor 首现于封面",
        "description": f"deck.主题标签 中至少 1 个 anchor 在 slide_1 (cover) 出现的比例: {anchor_at_cover_count}/{total} = {anchor_at_cover_count/total:.2%}",
        "consume_hint": "IDEA / OUTLINE codex review",
        "hit_rate": anchor_at_cover_count / max(total, 1),
        "applies_to": "all",
    })

    # 2. chapter_role_sequence_invariant (motivation → method → result)
    classic_count = 0
    motivation_before_method = 0
    method_before_result = 0
    for d in decks:
        seq = []
        for sec in d["sections"]:
            role = sec.get("章节角色") or ""
            if role:
                seq.append(role)
        if "motivation" in seq and "method" in seq:
            if seq.index("motivation") < seq.index("method"):
                motivation_before_method += 1
            if "result" in seq:
                if seq.index("method") < seq.index("result"):
                    method_before_result += 1
                    if seq.index("motivation") < seq.index("method") < seq.index("result"):
                        classic_count += 1

    rules.append({
        "id": "motivation_before_method_invariant",
        "category": "narrative_flow_stats",
        "title": "Motivation 在 Method 之前",
        "description": f"含 motivation+method 的 deck 中, motivation 章在 method 章之前的比例: {motivation_before_method}/{total}",
        "consume_hint": "OUTLINE codex review",
        "hit_rate": motivation_before_method / max(total, 1),
        "applies_to": "all",
    })

    # 3. agenda_chapter_match_rate (string match of agenda topics vs section list)
    # Stretch: skip if too complex — Python alone can't reliably extract agenda items from
    # slide content. Defer to narrative_flow_semantic skill.

    # 4. per_chapter_avg_pages by role
    role_page_counts = defaultdict(list)
    for d in decks:
        for sec in d["sections"]:
            role = sec.get("章节角色") or "unknown"
            role_page_counts[role].append(safe_int(sec.get("页数")))
    role_summary = {}
    for role, counts in role_page_counts.items():
        if counts:
            role_summary[role] = {
                "p50": median(counts),
                "p95": p_value([float(x) for x in counts], 0.95),
                "sample_count": len(counts),
            }
    rules.append({
        "id": "per_chapter_avg_pages_by_role",
        "category": "narrative_flow_stats",
        "title": "各 chapter_role 的章内页数分布",
        "description": "每种 章节角色 下章内页数的 p50/p95 分布. e.g. motivation 通常 4-6 页, method 8-14 页.",
        "consume_hint": "IDEA prompt 灌入 chapter_plan 推荐页数",
        "extra_fields": {"by_role": role_summary},
        "hit_rate": 1.0,
        "applies_to": "all",
    })

    return rules


# ──────────────────────────────────────────────────────────────────────────
# Output writing — .md per rule + INDEX.json
# ──────────────────────────────────────────────────────────────────────────


def write_rule_md(rule: dict) -> Path:
    category = rule["category"]
    rule_id = rule["id"]
    tier = _tier_for_category(category)
    out_dir = RULE_ROOT / tier / category
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{rule_id}.md"

    hr = float(rule["hit_rate"])
    enforcement = hit_rate_to_enforcement(hr)
    if enforcement == "discard":
        # Skip emitting rules with hit_rate < 0.7
        return None

    extra = rule.get("extra_fields") or {}
    fm_lines = [
        "---",
        f"id: {rule_id}",
        f"category: {category}",
        f"tier: {tier}",
        f"enforcement_level: {enforcement}",
        "source: statistical",
        f"hit_rate: {hr:.3f}",
        f"applies_to: {rule.get('applies_to', 'all')}",
        f"generated_at: {now()}",
    ]
    if extra:
        # Pretty-print extra fields as YAML-ish (Python's json output is YAML-compatible)
        fm_lines.append(f"extra: {json.dumps(extra, ensure_ascii=False)}")
    fm_lines.append("---")
    fm = "\n".join(fm_lines)

    body_parts = [
        f"# {rule.get('title', rule_id)}",
        "",
        "## 描述",
        rule.get("description", ""),
        "",
        "## 消费场景",
        rule.get("consume_hint", "(未指定)"),
    ]
    if extra:
        body_parts += [
            "",
            "## 统计快照",
            "```json",
            json.dumps(extra, ensure_ascii=False, indent=2),
            "```",
        ]
    body = "\n".join(body_parts)

    out_path.write_text(fm + "\n\n" + body, encoding="utf-8")
    return out_path


def write_index(all_rules: list[dict]) -> Path:
    """Write tier-aware INDEX.json files: per-tier + top-level."""
    by_tier_entries = {"logic_story": [], "page_specific": []}
    for r in all_rules:
        enforcement = hit_rate_to_enforcement(r["hit_rate"])
        if enforcement == "discard":
            continue
        cat = r["category"]
        tier = _tier_for_category(cat)
        if tier == "unknown":
            continue
        by_tier_entries[tier].append({
            "id": r["id"],
            "category": cat,
            "tier": tier,
            "enforcement_level": enforcement,
            "hit_rate": round(r["hit_rate"], 3),
            "applies_to": r.get("applies_to", "all"),
            "source": "statistical",
            "consume_hint": r.get("consume_hint", ""),
            "path": f"{cat}/{r['id']}.md",
        })

    # Write per-tier INDEX (only handles statistical entries — Claude's
    # rule_extract.py will need to merge these with its own when rebuilding)
    for tier, entries in by_tier_entries.items():
        if not entries:
            continue
        from collections import Counter
        idx = {
            "tier": tier,
            "tier_label_zh": "逻辑故事层" if tier == "logic_story" else "页面具体层",
            "schema_version": "2.0",
            "generated_at": now(),
            "rules_count_statistical": len(entries),
            "by_category_statistical": dict(Counter(e["category"] for e in entries)),
            "by_enforcement_statistical": dict(Counter(e["enforcement_level"] for e in entries)),
            "entries_statistical_only": entries,
            "note": (
                "This is a PARTIAL index from rule_stats.py (statistical rules only). "
                "Run rule_extract.py to merge with Claude-extracted rules into the "
                "full per-tier INDEX.json."
            ),
        }
        out_path = RULE_ROOT / tier / "INDEX.json"
        # If full INDEX exists, don't overwrite it — leave a hint instead
        if out_path.exists():
            # Update only statistical-related fields if existing INDEX has more
            try:
                existing = json.loads(out_path.read_text(encoding="utf-8"))
                if "entries" in existing:
                    # Full INDEX exists; just refresh statistical entries inside it
                    print(f"  ! tier {tier}/INDEX.json exists with full entries; "
                          f"not overwriting (use rule_extract.py for full rebuild)", flush=True)
                    continue
            except Exception:
                pass
        out_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")

    return RULE_ROOT / "INDEX.json"  # top-level, may exist


# ──────────────────────────────────────────────────────────────────────────
# Main entry
# ──────────────────────────────────────────────────────────────────────────


def run(dry_run: bool = False) -> dict:
    print(f">>> rule_stats: loading corpus from {MATERIAL_DECKS}", flush=True)
    decks = load_corpus()
    print(f"  loaded {len(decks)} decks", flush=True)

    all_rules = []
    builders = [
        ("text", build_text_rules),
        ("role_position", build_role_position_rules),
        ("structure", build_structure_rules),
        ("adjacency", build_adjacency_rules),
        ("scenario", build_scenario_rules),
        ("narrative_flow_stats", build_narrative_flow_stats_rules),
    ]
    for cat, fn in builders:
        print(f"  building {cat}...", flush=True)
        cat_rules = fn(decks)
        for r in cat_rules:
            r.setdefault("category", cat)
            all_rules.append(r)
        print(f"    {len(cat_rules)} rules", flush=True)

    if dry_run:
        print(f"\n[dry-run] would write {len(all_rules)} rule.md files", flush=True)
        for r in all_rules:
            enf = hit_rate_to_enforcement(r["hit_rate"])
            print(f"  [{enf:>7s}] {r['category']}/{r['id']} (hit={r['hit_rate']:.2%})")
        return {"ok": True, "dry_run": True, "rules_count": len(all_rules)}

    print(f"\n  writing .md files to {RULE_ROOT}/", flush=True)
    written = 0
    skipped = 0
    for r in all_rules:
        out_path = write_rule_md(r)
        if out_path:
            written += 1
        else:
            skipped += 1
    idx_path = write_index(all_rules)

    print(f"  written: {written} (skipped {skipped} discard-level)", flush=True)
    print(f"  INDEX:   {idx_path}", flush=True)
    return {"ok": True, "rules_written": written, "rules_skipped_discard": skipped,
            "rules_total": len(all_rules), "index_path": str(idx_path)}


def main():
    dry_run = "--dry-run" in sys.argv
    return run(dry_run=dry_run)


if __name__ == "__main__":
    main()
