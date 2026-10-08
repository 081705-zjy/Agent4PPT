"""Data loading helpers for the two-stage OUTLINE_GENERATION pipeline.

These helpers shape the inputs that feed into the section_outline.md (Stage 1)
and slide_detail.md (Stage 2) skills, plus the outline_review.md codex inspector.

All loaders return JSON-serializable dicts/lists, designed to be inlined into a
Claude / codex prompt context. Size-conscious: caller is responsible for the
total prompt budget; helpers crop heavy fields by default.
"""

from __future__ import annotations

import json
from pathlib import Path
import shlex

from .models import ROOT
from . import library_query


# ──────────────────────────────────────────────────────────────────────────
# Path constants
# ──────────────────────────────────────────────────────────────────────────

LOGIC_ROOT = ROOT / "data" / "resources_library" / "logic"
LOGIC_INDEX = LOGIC_ROOT / "INDEX.json"
LIBRARY_DECKS_DIR = ROOT / "data" / "resources_library" / "material" / "decks"

# Phase 4 (2026-06-28): rule library 2-tier root + Helpers for IDEA_ANALYSIS
RULE_ROOT = ROOT / "data" / "resources_library" / "rule"
RULE_LOGIC_STORY_INDEX = RULE_ROOT / "logic_story" / "INDEX.json"
RULE_PAGE_SPECIFIC_INDEX = RULE_ROOT / "page_specific" / "INDEX.json"
LOGIC_DECK_LEVEL_DIR = LOGIC_ROOT / "deck_level"
LOGIC_SECTION_LEVEL_DIR = LOGIC_ROOT / "section_level"


# ──────────────────────────────────────────────────────────────────────────
# Phase 4 P4.5: Loaders for IDEA_ANALYSIS (consume rule + logic libraries)
# ──────────────────────────────────────────────────────────────────────────


# Noise fields never useful in generation payloads (only build-time metadata):
_DECK_LEVEL_DROP_FIELDS = {"layer", "source_layer_before_compaction"}

# carrier subfields we keep in the semantic-compact view:
#   deck_id        - unique source deck identity (traceability)
#   chapter_outline - how the pattern lands (role + slide_range only)
#   match_evidence  - human-written justification (why this deck matches the pattern)
# carrier subfields we drop as noisy or redundant:
#   deck_title      - already implied by deck_id
#   deck_topic_tags - deck's own tags are irrelevant to the pattern's semantics
#   chapter_outline.section_id - long path string; role + slide_range suffices


def _compact_carrier(c: dict, *, with_structural_slides: bool = False) -> dict:
    """Semantic-compact view of a carrier: keep evidence, drop noise.

    with_structural_slides=True is used only by load_deck_level_pattern_full()
    (OUTLINE Stage 1b needs the raw slide XML for byte-clone reuse).
    """
    if not isinstance(c, dict):
        return {}
    out = {
        "deck_id": c.get("deck_id"),
        "chapter_outline": [
            {"role": ch.get("chapter_role"), "pages": ch.get("slide_range")}
            for ch in (c.get("chapter_outline") or [])
            if isinstance(ch, dict)
        ],
        "match_evidence": c.get("match_evidence") or "",
    }
    if with_structural_slides and c.get("structural_slides"):
        out["structural_slides"] = c["structural_slides"]
    return out


def load_deck_level_patterns(*,
                              with_carriers: bool = True,
                              with_structural_slides: bool = False) -> list[dict]:
    """Load unified whole-deck patterns for IDEA_ANALYSIS.

    Current compact view merges the old logic/meta layer into logic/deck_level:
    - pattern_kind=deck_task: former meta patterns; what thinking task the deck
      must accomplish.
    - pattern_kind=deck_arc: former deck_level patterns; concrete chapter-role
      sequence and whole-deck arc.

    v3 (2026-07-30) fixed a latent bug: the previous version returned the RAW
    pattern dict (with full carriers[].structural_slides) alongside a
    carriers_overview summary — carriers were never stripped. Now:
      - with_carriers=True (default): carriers[] replaced by semantic-compact view
        (deck_id + chapter_outline{role,pages} + match_evidence)
      - with_carriers=False: carriers[] omitted entirely
      - with_structural_slides=True: keep the heavy structural_slides inside
        each carrier (only OUTLINE Stage 1b needs this; IDEA never does)

    Additionally strips build-time metadata fields (layer, source_layer_before_compaction).
    """
    if not LOGIC_DECK_LEVEL_DIR.exists():
        return []
    out = []
    for jf in sorted(LOGIC_DECK_LEVEL_DIR.glob("*.json")):
        try:
            p = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        # start with everything except noise
        entry = {k: v for k, v in p.items() if k not in _DECK_LEVEL_DROP_FIELDS}
        entry.setdefault("pattern_kind", "deck_arc")
        # replace carriers (raw or dropped)
        if with_carriers:
            entry["carriers"] = [
                _compact_carrier(c, with_structural_slides=with_structural_slides)
                for c in (p.get("carriers") or [])
            ]
        else:
            entry.pop("carriers", None)
        out.append(entry)
    return out


def load_deck_level_pattern_full(pattern_id: str) -> dict | None:
    """Load FULL pattern data (including carriers with full structural_slides content)
    by pattern_id. Used by IDEA_ANALYSIS after Claude picks a primary_pattern,
    to load that pattern's complete carrier data for chapter_plan derivation.
    """
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in str(pattern_id))[:100]
    jf = LOGIC_DECK_LEVEL_DIR / f"{safe}.json"
    if not jf.exists():
        return None
    try:
        return json.loads(jf.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_meta_patterns(*, with_instantiations: bool = True) -> list[dict]:
    """Compatibility wrapper for the former logic/meta layer.

    The active logic library is physically compacted: meta patterns now live in
    logic/deck_level with pattern_kind=deck_task.
    """
    return [
        p for p in load_deck_level_patterns(with_carriers=False)
        if isinstance(p, dict) and p.get("pattern_kind") == "deck_task"
    ]


def load_resource_library_contract_summary() -> dict:
    """Return the current material/logic/rule library contract for prompts.

    This is intentionally compact: generation stages need to know what each
    library owns after the 2026-07 resource split, but should not inline every
    slide/rule/pattern unless a later retrieval step selects it.
    """
    from collections import Counter

    def _read(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            return {}

    logic_idx = _read(LOGIC_INDEX)
    rule_idx = _read(RULE_ROOT / "INDEX.json")
    logic_story_idx = _read(RULE_LOGIC_STORY_INDEX)
    page_specific_idx = _read(RULE_PAGE_SPECIFIC_INDEX)
    material_idx = _read(ROOT / "data" / "resources_library" / "material" / "decks-index.json")
    material_manifest = _read(ROOT / "data" / "resources_library" / "material" / "manifest.json")

    report_types = Counter()
    topic_tags = Counter()
    deck_examples = []
    for d in (material_idx.get("decks") or []):
        if not isinstance(d, dict):
            continue
        rt = d.get("报告类型")
        if rt:
            report_types[str(rt)] += 1
        for tag in d.get("主题标签") or []:
            if tag:
                topic_tags[str(tag)] += 1
        if len(deck_examples) < 8:
            deck_examples.append({
                "deck_id": d.get("deck标识"),
                "title": d.get("标题"),
                "report_type": d.get("报告类型"),
                "slide_count": d.get("总页数"),
                "topic_tags": (d.get("主题标签") or [])[:6],
            })

    return {
        "schema_version": "1.0",
        "source": "data/resources_library",
        "material": {
            "role": "source slide/deck/section pool for reuse and byte-clone",
            "deck_count": material_idx.get("deck_count") or material_manifest.get("deck_count"),
            "report_types": dict(report_types),
            "top_topic_tags": [{"tag": k, "count": v} for k, v in topic_tags.most_common(20)],
            "deck_examples": deck_examples,
        },
        "logic": {
            "role": "reusable narrative patterns; generation should pick from unified deck_level and section_level",
            "patterns_count": logic_idx.get("patterns_count"),
            "by_layer": {
                "deck_level": (logic_idx.get("by_layer") or {}).get("deck_level"),
                "section_level": (logic_idx.get("by_layer") or {}).get("section_level"),
            },
            "legacy_meta_merged_into": "logic/deck_level/*.json pattern_kind=deck_task",
            "deck_level_patterns": [
                {"id": e.get("id"), "title": e.get("title"),
                 "pattern_kind": e.get("pattern_kind"), "confidence": e.get("confidence")}
                for e in load_deck_level_patterns(with_carriers=False)
            ][:24],
        },
        "rule": {
            "role": "hard/soft quality constraints; generation should obey, review should audit",
            "total_rules": rule_idx.get("total_rules"),
            "tiers": rule_idx.get("tiers") or {},
            "logic_story": {
                "rules_count": logic_story_idx.get("rules_count"),
                "runtime_prompt_view": "rule/logic_story/INDEX.json",
                "schema_version": logic_story_idx.get("schema_version"),
                "by_category": logic_story_idx.get("by_category") or {},
                "hard_count": (logic_story_idx.get("by_enforcement_level") or {}).get("hard"),
            },
            "page_specific": {
                "rules_count": page_specific_idx.get("rules_count"),
                "by_category": page_specific_idx.get("by_category") or {},
                "hard_count": (page_specific_idx.get("by_enforcement_level") or {}).get("hard"),
            },
        },
        "stage_contract": {
            "IDEA_INTAKE_LIGHT": "classify user answers into fields that match logic/material enums",
            "IDEA_ANALYSIS": "select unified deck_level task/arc patterns, chapter roles, section rhythm pattern, rough page budget, and material section hints; no slide_stubs or source binding",
            "OUTLINE_GENERATION": "Stage 1a creates per-chapter slide stubs from logic/section_level + page_specific + material section capacity; Stage 1b fills slide detail and binds material slide sources",
            "GAP_CARD_GENERATION": "per section use model to produce term/title/metric/style unification hints",
            "DRAFT_ASSEMBLY": "deterministically byte-clone material slides selected upstream; no narrative invention",
        },
    }


def select_candidate_sections_from_library_understanding(
    idea_analysis: dict,
    chapter: dict,
    *,
    max_sections: int = 8,
) -> list[dict]:
    """Pick candidate material sections from IDEA's stored library_understanding.

    IDEA builds a deck→section→slide hierarchy from the optimized material
    library. OUTLINE uses this helper when a chapter lacks explicit
    candidate_carrier_sections, keeping the two stages on the same pool.
    """
    prov = idea_analysis.get("provenance") or {}
    lib = prov.get("library_understanding") or idea_analysis.get("library_understanding") or {}
    hierarchy = lib.get("hierarchy") or {}
    top_decks = hierarchy.get("top_decks") or []
    sections_by_deck = hierarchy.get("sections_by_deck") or {}
    if not isinstance(sections_by_deck, dict):
        return []

    target_role = str(chapter.get("section_role") or "").lower()
    content_roles = {
        "motivation", "background", "problem", "method", "framework",
        "result", "experiment", "comparison", "engineering", "discussion",
        "case_study", "content", "outlook",
    }
    structural_roles = {"opening", "cover", "agenda", "section_divider", "closing", "references"}

    def _tier(role: str) -> str:
        role = str(role or "").lower()
        if role in content_roles:
            return "content"
        if role in structural_roles:
            return "structural"
        return "other"

    deck_title_by_id = {
        str(d.get("deck_id")): (d.get("deck_title") or d.get("title") or "")
        for d in top_decks if isinstance(d, dict) and d.get("deck_id")
    }
    deck_rank = {
        str(d.get("deck_id")): i
        for i, d in enumerate(top_decks) if isinstance(d, dict) and d.get("deck_id")
    }

    rows: list[dict] = []
    for did, secs in sections_by_deck.items():
        if not isinstance(secs, list):
            continue
        for sec in secs:
            if not isinstance(sec, dict):
                continue
            sid = sec.get("section_id")
            if not sid:
                continue
            sec_role = str(sec.get("section_role") or "").lower()
            exact_role = 1 if target_role and sec_role == target_role else 0
            tier_match = 1 if target_role and _tier(sec_role) == _tier(target_role) else 0
            try:
                n_slides = int(sec.get("n_slides_in_pool") or sec.get("page_count") or 0)
            except Exception:
                n_slides = 0
            try:
                score = float(sec.get("score") or 0.0)
            except Exception:
                score = 0.0
            # Prefer exact role, then same tier, then sections with enough slides,
            # then deck rank from IDEA's topic cascade.
            rank_tuple = (
                exact_role,
                tier_match,
                min(n_slides, 12),
                score,
                -deck_rank.get(str(did), 999),
            )
            if not exact_role and target_role in structural_roles:
                continue
            rows.append({
                "_rank_tuple": rank_tuple,
                "deck_id": did,
                "deck_title": deck_title_by_id.get(str(did), ""),
                "section_id": sid,
                "section_title": sec.get("section_title") or sec.get("title") or "",
                "section_role": sec.get("section_role"),
                "page_count": n_slides,
                "rank_score": round(score, 3),
                "source": "idea_library_understanding",
            })

    rows.sort(key=lambda r: r["_rank_tuple"], reverse=True)
    selected = []
    seen = set()
    for r in rows:
        key = (r.get("deck_id"), r.get("section_id"))
        if key in seen:
            continue
        seen.add(key)
        r = {k: v for k, v in r.items() if k != "_rank_tuple"}
        selected.append(r)
        if len(selected) >= max_sections:
            break
    return selected


def recommend_deck_task_patterns_for_intake(intake_light: dict, top_n: int = 3) -> list[dict]:
    """Score deck-level task patterns against intake_light trigger_signals.

    Scoring: count of trigger_signal substrings that appear in the combined
    intake text (topic + audience + scenario + keywords). Returns top_n
    patterns with score > 0, or top_n by order if all score 0.
    """
    import re as _re_m
    tasks = [
        p for p in load_deck_level_patterns(with_carriers=False)
        if isinstance(p, dict) and p.get("pattern_kind") == "deck_task"
    ]
    if not tasks:
        return []

    # Build intake text blob
    st = intake_light.get("topic") or {}
    ap = intake_light.get("audience") or {}
    sc = intake_light.get("scenario") or {}
    bits = [
        str(st.get("subject") or ""),
        str(st.get("deliverable_type") or ""),
        " ".join(str(s) for s in (st.get("sub_topics") or [])),
        str(ap.get("primary") or ""),
        " ".join(str(t) for t in (ap.get("background_tags") or [])),
        str(sc.get("category") or ""),
        " ".join(str(k) for k in (intake_light.get("keywords") or [])),
        str(intake_light.get("story_mode") or ""),
    ]
    blob = " ".join(bits).lower()

    scored = []
    for m in tasks:
        score = 0
        for sig in (m.get("trigger_signals") or []):
            sig_lower = str(sig).lower()
            # substring match on any 4+ char token in the signal
            tokens = [t for t in _re_m.findall(r"[\w一-鿿]{2,}", sig_lower) if len(t) >= 2]
            if tokens and any(t in blob for t in tokens):
                score += 1
        scored.append((score, m))

    scored.sort(key=lambda x: -x[0])
    return [m for _, m in scored[:top_n]]


def recommend_meta_patterns_for_intake(intake_light: dict, top_n: int = 3) -> list[dict]:
    """Compatibility wrapper for old callers.

    The former logic/meta layer is now represented inside unified deck_level as
    pattern_kind=deck_task.
    """
    return recommend_deck_task_patterns_for_intake(intake_light, top_n=top_n)


# ──────────────────────────────────────────────────────────────────────────
# Phase 5 P5.1: Cross-deck section retrieval (content-first IDEA flow)
# ──────────────────────────────────────────────────────────────────────────


STRUCTURAL_ROLES = frozenset({"opening", "cover", "agenda", "section_divider", "closing", "references"})

# Content roles: substantive narrative carriers
CONTENT_ROLES = frozenset({
    "motivation", "background", "problem", "method", "framework",
    "result", "experiment", "comparison", "engineering",
    "discussion", "case_study", "content", "outlook",
})


def _role_tier(role: str) -> str:
    if role in CONTENT_ROLES:
        return "content"
    if role in STRUCTURAL_ROLES:
        return "structural"
    return "other"


CANONICAL_DECKS_INDEX_PATH = ROOT / "data" / "resources_library" / "material" / "decks-index.json"


def _substring_tag_overlap_count(user_tags: list[str], target_tags: list[str]) -> int:
    """Count user_tags that have substring match in any target_tag (or vice versa).

    A user_tag is considered "hit" if it shares a meaningful substring with any
    target_tag — handles phrase-atomic mismatch (e.g. user '大模型软硬件协同'
    matches section '大模型推理' because '大模型' is shared, OR section '大模型推理'
    matches user '大模型推理' exactly).

    Implementation: hit if (user_tag in target_tag) OR (target_tag in user_tag)
    AND both have length >= 2 (avoid degenerate single-char matches).
    """
    if not user_tags or not target_tags:
        return 0
    hits = 0
    for u in user_tags:
        if not u or len(u) < 2:
            continue
        for t in target_tags:
            if not t or len(t) < 2:
                continue
            if u in t or t in u:
                hits += 1
                break
    return hits


def load_logic_story_hard_rules_summary() -> list[dict]:
    """Load hard rules from logic_story tier with 1-line summary for prompt injection.

    Current logic_story is physically compacted: each active rule has one JSON
    file and INDEX.json carries the prompt-facing summary fields. Older backup
    libraries are still supported by falling back to .md headings.
    """
    if not RULE_LOGIC_STORY_INDEX.exists():
        return []
    try:
        idx = json.loads(RULE_LOGIC_STORY_INDEX.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    tier_root = RULE_ROOT / "logic_story"
    for entry in idx.get("entries") or []:
        if entry.get("enforcement_level") != "hard":
            continue
        # Extract 1-line summary from the .md file's title (# heading)
        summary = ""
        rel = entry.get("path")
        if rel:
            md = tier_root / rel
            if md.exists():
                try:
                    for line in md.read_text(encoding="utf-8", errors="ignore").splitlines():
                        line = line.strip()
                        if line.startswith("# "):
                            summary = line[2:].strip()[:120]
                            break
                except Exception:
                    pass
        out.append({
            "id": entry.get("id"),
            "category": entry.get("category"),
            "hit_rate": entry.get("hit_rate"),
            "stage": entry.get("stage") or [],
            "when": entry.get("applicable_when") or entry.get("when") or "",
            "must": entry.get("summary") or "",
            "avoid": entry.get("avoid") or "",
            "check": entry.get("check") or "",
            "summary": entry.get("summary") or summary,
        })
    return out


def recommend_section_rhythm_patterns_for_chapter_role(chapter_role: str,
                                                          top_n: int = 3,
                                                          min_source_count: int = 1) -> list[dict]:
    """For a given chapter_role, return top-N section_level patterns by source_count.

    v2 (2026-07-29): added min_source_count filter. IDEA can pass min=2 to
    prefer multi-source patterns (91% of patterns are source_count=1 arising from
    a single deck; passing min=2 restricts to cross-source generalizable ones).

    Used in IDEA_ANALYSIS to suggest章内节奏模板 per chapter. Patterns ranked by
    carrier count (more carriers = more universal pattern for this role).
    """
    if not LOGIC_SECTION_LEVEL_DIR.exists():
        return []
    matches = []
    for jf in LOGIC_SECTION_LEVEL_DIR.glob("*.json"):
        try:
            p = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        # Check if applicable_when.chapter_role includes our chapter_role
        aw = p.get("applicable_when") or {}
        applicable_roles = aw.get("chapter_role") or []
        if isinstance(applicable_roles, str):
            applicable_roles = [applicable_roles]
        if chapter_role not in applicable_roles and "all" not in applicable_roles:
            # Also infer from pattern id: e.g. "method_..." → method
            pid = p.get("id") or ""
            if not pid.startswith(chapter_role + "_"):
                continue
        # v2: min_source_count filter
        _sc = p.get("source_count", 0) or 0
        if _sc < min_source_count:
            continue
        matches.append({
            "pattern_id": p.get("id"),
            "title": p.get("title", ""),
            "applicable_summary": p.get("applicable_summary", ""),
            "abstract_node_sequence": p.get("abstract_node_sequence", []),
            "source_count": _sc,
            "confidence": p.get("confidence", "low"),
        })
    # Sort by source_count desc, then by confidence (high > medium > low)
    conf_order = {"high": 0, "medium": 1, "low": 2}
    matches.sort(key=lambda x: (-x["source_count"], conf_order.get(x["confidence"], 9)))
    return matches[:top_n]


# ──────────────────────────────────────────────────────────────────────────
# 1. Narrative knowledge loader — by matched_morphology_pattern + OUTLINE consume_hint
# ──────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────
# 2. Reference decks loader — by design_inspirations.reference_deck_shortlist
# ──────────────────────────────────────────────────────────────────────────


def _split_frontmatter(content: str) -> tuple[str, str]:
    """Split YAML frontmatter + body. Returns ('', content) if no frontmatter."""
    if not content.startswith("---"):
        return "", content
    end = content.find("\n---", 3)
    if end < 0:
        return "", content
    frontmatter = content[3:end].strip()
    body = content[end + 4 :].lstrip()
    return frontmatter, body


def _parse_inline_yaml_list(value: str) -> list:
    """Parse a small inline YAML list from material-library frontmatter."""
    text = str(value or "").strip()
    if not (text.startswith("[") and text.endswith("]")):
        return []
    inner = text[1:-1].strip()
    if not inner:
        return []
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        pass
    try:
        lexer = shlex.shlex(inner, posix=True)
        lexer.whitespace = ","
        lexer.whitespace_split = True
        lexer.commenters = ""
        return [item.strip().strip("'\"") for item in lexer if item.strip()]
    except Exception:
        return [
            item.strip().strip("'\"")
            for item in inner.split(",")
            if item.strip()
        ]


def _parse_deck_md_frontmatter(fm: str) -> dict:
    """Parse deck.md frontmatter (Chinese-keyed, mostly inline YAML)."""
    out: dict = {}
    for line in fm.splitlines():
        line = line.rstrip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if not key:
            continue
        if val.startswith("[") and val.endswith("]"):
            out[key] = _parse_inline_yaml_list(val)
        elif val.startswith('"') and val.endswith('"'):
            out[key] = val[1:-1]
        else:
            out[key] = val
    return out


# ──────────────────────────────────────────────────────────────────────────
# 3. Project-side PDF brief loader — compact view
# ──────────────────────────────────────────────────────────────────────────

def load_pdf_briefs_compact(project_id: str, *, max_quotes: int = 3) -> list[dict]:
    """Load per-PDF briefs from projects/<id>/data/pdf/*.json (compact view).

    Returns list with: resource_id, 文件名, 标题, 核心论断, 关键图表索引,
    可引用片段 (first N), 适合章节, relevance_score. Discards entries with
    discard_candidate=true.
    """
    project_data = ROOT / "projects" / project_id / "data" / "pdf"
    if not project_data.exists():
        return []
    out: list[dict] = []
    for p in sorted(project_data.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("discard_candidate") is True:
            continue
        quotes = d.get("可引用片段") or []
        if isinstance(quotes, list):
            quotes = quotes[:max_quotes]
        out.append({
            "resource_id": p.stem,
            "文件名": d.get("文件名") or p.name,
            "标题": d.get("标题"),
            "核心论断": d.get("核心论断"),
            "关键图表索引": d.get("关键图表索引"),
            "可引用片段": quotes,
            "适合章节": d.get("适合章节"),
            "relevance_score": d.get("relevance_score"),
        })
    return out


# ──────────────────────────────────────────────────────────────────────────
# 4. Material → chapter pre-assignment
# ──────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────
# 5. Narrative_logic_constraints chapter slicer
# ──────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────
# 6. Compact brief slicer for OUTLINE Stage 1/2
# ──────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────
# 7. Helpers for OUTLINE Stage 1 stub validation + merging
# ──────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────
# 5. OUTLINE Stage 1 helpers (v3.2 IDEA-aware)
# ──────────────────────────────────────────────────────────────────────────

_DECK_ID_TO_DIR_LOOKUP: dict[str, str] | None = None


def _build_deck_id_to_dir_lookup() -> dict[str, str]:
    """Build {deck_id → directory name under data/resources_library/material/decks/}.

    Scans each deck.md frontmatter for deck标识 → maps to dir.
    """
    global _DECK_ID_TO_DIR_LOOKUP
    if _DECK_ID_TO_DIR_LOOKUP is not None:
        return _DECK_ID_TO_DIR_LOOKUP
    lookup: dict[str, str] = {}
    decks_root = ROOT / "data" / "resources_library" / "material" / "decks"
    if decks_root.exists():
        for deck_dir in decks_root.iterdir():
            md = deck_dir / "deck.md"
            if not md.exists():
                continue
            try:
                content = md.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            fm_raw, _ = _split_frontmatter(content)
            fm = _parse_deck_md_frontmatter(fm_raw)
            did = fm.get("deck标识")
            if did and isinstance(did, str):
                lookup[did] = deck_dir.name
    _DECK_ID_TO_DIR_LOOKUP = lookup
    return lookup


def load_page_specific_archetypes(role_filter: str | None = None) -> list[dict]:
    """Load page_specific rules (archetype enum) with summary metadata.

    v6: Uses INDEX schema 2.0 fields directly. applicable_role is stored as a
    JSON string and is deserialized here. role_filter pre-filters by chapter role
    (e.g. "motivation", "method") to avoid injecting all 204 entries per chapter.

    Returns list with {id, category, enforcement_level, applicable_role, hit_rate,
    summary, consume_hint}.
    """
    idx_path = RULE_PAGE_SPECIFIC_INDEX
    if not idx_path.exists():
        return []
    try:
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    entries = idx.get("entries") or []
    out: list[dict] = []
    for e in entries:
        rid = e.get("id")
        if not rid:
            continue
        # Deserialize applicable_role from JSON string (schema 2.0)
        raw_role = e.get("applicable_role")
        if isinstance(raw_role, str):
            try:
                applicable_role = json.loads(raw_role)
            except Exception:
                applicable_role = [raw_role] if raw_role else []
        else:
            applicable_role = raw_role or []
        # role_filter: keep entries that apply to "all" or match the requested role
        if role_filter:
            applies_to = e.get("applies_to") or ""
            if "all" not in applicable_role and role_filter not in applicable_role:
                continue
        out.append({
            "id": rid,
            "category": e.get("category") or "",
            "enforcement_level": e.get("enforcement_level") or "",
            "applicable_role": applicable_role,
            "applies_to": e.get("applies_to") or "",
            "hit_rate": e.get("hit_rate"),
            "consume_hint": (e.get("consume_hint") or "")[:120],
            "summary": "",  # populated below only when md exists
        })
    # Populate summary from .md title line (only for filtered subset to limit IO)
    rule_root = RULE_ROOT / "page_specific"
    for item in out:
        cat = item["category"]
        if not cat:
            continue
        md_path = rule_root / cat / f"{item['id']}.md"
        if not md_path.exists():
            continue
        try:
            for line in md_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line.startswith("# "):
                    item["summary"] = line[2:].strip()
                    break
        except Exception:
            pass
    return out


def normalize_page_specific_archetype_ids(archetypes: list[str] | str | None,
                                          *, role_hint: str | None = None) -> list[str]:
    """Map free-form archetype ids to current allowed enum ids.

    This is a repair layer for legacy prompts/model drift. It never invents new
    archetypes; it only replaces unknown ids with nearby legal ones, preferring
    role-compatible matches.
    """
    if archetypes is None:
        return []
    if isinstance(archetypes, str):
        archetypes = [archetypes]
    import re
    all_ids = [a.get("id") for a in load_page_specific_archetypes() if a.get("id")]
    allowed = load_page_specific_archetypes()
    if role_hint:
        allowed = [a for a in allowed if role_hint in (a.get("applicable_role") or []) or "content_candidate" in (a.get("applicable_role") or [])]
    allowed_ids = [a.get("id") for a in allowed if a.get("id")]
    if not allowed_ids:
        allowed_ids = all_ids
    if not allowed_ids:
        return [str(a) for a in archetypes if a]

    # Small alias map for known legacy names observed in reviews.
    alias_map = {
        "case_study_opener_uses_paper_full_title_with_authors": "paper_intro_layout_title_authors_venue",
        "paper_title_authors_only": "paper_intro_layout_title_authors_venue",
        "paper_intro_layout_title_authors_venue": "paper_intro_layout_title_authors_venue",
        "method_formula_overview_with_positioning": "formula_recap_uses_stacked_upgrade_boxes",
        "prior_works_taxonomy_table": "multi_column_parallel_comparison_grid_for_technique_survey",
        "challenge_key_contradiction_statement": "problem_page_carries_quantified_pain_point",
        "toc_progress_highlight": "toc_layout_progressive_highlight_current_section",
        "title_uses_noun_phrase_or_colon_subtitle": "slide_title_uses_noun_phrase_or_colon_subtitle",
    }
    normalized: list[str] = []
    for raw in archetypes:
        if not raw:
            continue
        aid = alias_map.get(str(raw), str(raw))
        if aid in all_ids:
            normalized.append(aid)
            continue
        # Fallback: fuzzy family match by token overlap.
        toks = [t for t in re.split(r"[_\-\s]+", aid) if len(t) >= 3]
        best = None
        best_score = -1
        for cand in allowed_ids:
            c_toks = [t for t in re.split(r"[_\-\s]+", cand) if len(t) >= 3]
            score = sum(1 for t in toks if t in c_toks or any(t in ct or ct in t for ct in c_toks))
            if score > best_score:
                best = cand
                best_score = score
        normalized.append(best or allowed_ids[0])
    return normalized


def load_rhythm_pattern_full(pattern_id: str) -> dict | None:
    """Load logic/section_level/<pattern_id>.json full content."""
    safe_id = str(pattern_id or "")
    path = LOGIC_SECTION_LEVEL_DIR / f"{safe_id}.json"
    if not path.exists():
        try:
            idx = json.loads(LOGIC_INDEX.read_text(encoding="utf-8"))
            alias = (idx.get("aliases") or {}).get(safe_id)
        except Exception:
            alias = None
        if alias:
            path = LOGIC_SECTION_LEVEL_DIR / f"{alias}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("id") != safe_id:
            data.setdefault("resolved_from_pattern_id", safe_id)
        return data
    except Exception:
        return None


def load_rhythm_pattern_trimmed(pattern_id: str, *, max_carriers: int = 5) -> dict | None:
    """Load rhythm pattern but strip inline carriers[].slides (redundant + huge).

    Stage 1a only needs abstract_node_sequence + applicable_summary +
    page_transitions_pattern + anti_patterns + carriers metadata
    (deck_id/section_id/section_role/section_narrative). Per-slide details
    are loaded separately via load_slide_briefs_for_rhythm_pattern in Stage 1b.

    Some pattern files inline up to 200+ slide briefs (~130KB), which blows
    the cli stdin pipe — this trim brings payload down to <10KB.
    """
    full = load_rhythm_pattern_full(pattern_id)
    if not full:
        return None
    trimmed = {k: v for k, v in full.items() if k != "carriers"}
    carriers = full.get("carriers") or []
    trimmed_carriers = []
    for c in carriers[:max_carriers]:
        if not isinstance(c, dict):
            continue
        tc = {k: v for k, v in c.items() if k != "slides"}
        slides = c.get("slides") or []
        tc["slide_count"] = len(slides)
        trimmed_carriers.append(tc)
    trimmed["carriers"] = trimmed_carriers
    return trimmed


def load_section_summaries_for_briefs(briefs: list[dict], *, max_chars: int = 400) -> list[dict]:
    """v20 W1: Load section.md summaries for the sections owning these slide briefs.

    Given a flat list of slide briefs, extract unique (deck_id, section_id) pairs,
    locate each section.md, and return a compact summary per section:
      - narrative (str, from frontmatter '章节叙事' or similar)
      - intra_flow_hint (str, prose from body describing slide-to-slide relation)
      - slide_range (list of slide indexes in this section)
      - section_role (from candidate)
      - deck_id, section_id, deck_title

    Purpose: give Stage 1b LLM the "why slide N→N+1" context so it can
    prefer contiguous same-section reuse over scattered picks.
    """
    if not briefs:
        return []
    lookup = _build_deck_id_to_dir_lookup()
    decks_root = ROOT / "data" / "resources_library" / "material" / "decks"
    unique_pairs: dict[tuple, dict] = {}
    for b in briefs:
        key = (b.get("deck_id"), b.get("section_id"))
        if not (key[0] and key[1]):
            continue
        if key not in unique_pairs:
            unique_pairs[key] = {
                "deck_id": key[0],
                "section_id": key[1],
                "deck_title": b.get("deck_title") or "",
                "section_role": b.get("section_role"),
                "slide_indexes": [],
            }
        idx = b.get("slide_index_in_source")
        if idx is not None:
            unique_pairs[key]["slide_indexes"].append(idx)
    out: list[dict] = []
    for (did, sid), info in unique_pairs.items():
        deck_dir_name = lookup.get(did)
        if not deck_dir_name:
            continue
        sec_suffix = sid.split(".")[-1] if "." in sid else sid
        sec_num = sec_suffix.replace("sec", "").lstrip("_")
        deck_path = decks_root / deck_dir_name
        section_subdirs = list(deck_path.glob(f"section_{sec_num}_*")) or list(deck_path.glob(f"section_{sec_num}"))
        if not section_subdirs:
            continue
        sec_dir = section_subdirs[0]
        sf = sec_dir / "section.md"
        if not sf.exists():
            continue
        try:
            text = sf.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        fm_raw, body = _split_frontmatter(text)
        fm = _parse_deck_md_frontmatter(fm_raw)
        # Extract intra-flow prose from body:
        # find heading like "## 章内 slide 间的关系" or "## slide 间关系"
        intra = ""
        lines = body.splitlines() if body else []
        in_intra = False
        buf = []
        for ln in lines:
            if any(kw in ln for kw in ("章内 slide 间", "章内slide", "slide 间的关系", "章内 slide")):
                in_intra = True
                continue
            if in_intra:
                if ln.startswith("## "):
                    break
                if ln.strip():
                    buf.append(ln.strip())
                    if sum(len(x) for x in buf) > max_chars:
                        break
        intra = " ".join(buf)[:max_chars]
        out.append({
            "deck_id": did,
            "section_id": sid,
            "deck_title": info["deck_title"],
            "section_role": info["section_role"],
            "slide_range": sorted(set(info["slide_indexes"])),
            "narrative": (fm.get("章节叙事") or fm.get("叙事") or "")[:max_chars],
            "intra_flow_hint": intra,
        })
    return out


def load_slide_briefs_for_chapter(candidate_carrier_sections: list[dict],
                                    *, max_slides_per_section: int = 20) -> list[dict]:
    """Load all slide_NN.md briefs from each candidate section.

    For each candidate (deck_id + section_id), find directory under
    data/resources_library/material/decks/<dir>/<section_subdir>/, then load all
    slide_NN.md files. Returns flat list of slide briefs (compact dict).

    Each slide brief contains:
      deck_id, deck_title, section_id, section_role,
      slide_index_in_source, slide_id, 页面角色, 标题, 核心论断, 本页讲什么,
      关键文字, 视觉骨架, 资源ID列表, 适合复用场景, 不适合复用场景, 上页角色, 下页角色
    """
    if not candidate_carrier_sections:
        return []
    lookup = _build_deck_id_to_dir_lookup()
    out: list[dict] = []
    decks_root = ROOT / "data" / "resources_library" / "material" / "decks"

    def _brief_from_slide_file(sf: Path, *, deck_id: str, deck_title: str,
                               section_id: str, section_role: str | None) -> dict | None:
        try:
            content = sf.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None
        fm_raw, _ = _split_frontmatter(content)
        fm = _parse_deck_md_frontmatter(fm_raw)
        try:
            idx = int(sf.stem.split("_")[1])
        except Exception:
            idx = None
        return {
            "deck_id": deck_id,
            "deck_title": deck_title,
            "section_id": section_id,
            "section_role": section_role,
            "slide_index_in_source": idx,
            "slide_id": fm.get("页标识") or f"{deck_id}.slide_{idx}",
            "页面角色": fm.get("页面角色"),
            "标题": fm.get("标题"),
            "核心论断": fm.get("核心论断"),
            "本页讲什么": fm.get("本页讲什么"),
            "关键文字": fm.get("关键文字") if isinstance(fm.get("关键文字"), list) else [],
            "视觉骨架": fm.get("视觉骨架") if isinstance(fm.get("视觉骨架"), list) else [],
            "资源ID列表": fm.get("资源ID列表") if isinstance(fm.get("资源ID列表"), list) else [],
            "适合复用场景": fm.get("适合复用场景") if isinstance(fm.get("适合复用场景"), list) else [],
            "不适合复用场景": fm.get("不适合复用场景") if isinstance(fm.get("不适合复用场景"), list) else [],
            "上页角色": fm.get("上页角色"),
            "下页角色": fm.get("下页角色"),
            # v20 D1: multi-layer semantic fields (backward-compatible; None if not rebuilt)
            "页在section中的作用": fm.get("页在section中的作用"),
            "视觉文本层次": fm.get("视觉文本层次") if isinstance(fm.get("视觉文本层次"), list) else [],
            "alternate_claims": fm.get("alternate_claims") if isinstance(fm.get("alternate_claims"), list) else [],
            "layout_tag": fm.get("layout_tag"),
        }

    for cand in candidate_carrier_sections:
        deck_id = cand.get("deck_id")
        section_id = cand.get("section_id")
        deck_title = cand.get("deck_title") or cand.get("section_title") or ""
        if not (deck_id and section_id):
            continue
        deck_dir_name = lookup.get(deck_id)
        if not deck_dir_name:
            continue
        deck_path = decks_root / deck_dir_name
        if not deck_path.exists():
            continue
        if "::pages::" in str(section_id):
            try:
                range_part = str(section_id).rsplit("::pages::", 1)[1]
                start_s, end_s = range_part.split("-", 1)
                start_i, end_i = int(start_s), int(end_s)
            except Exception:
                start_i = end_i = None
            loaded = 0
            if start_i is not None and end_i is not None:
                for sf in sorted(deck_path.glob("section_*/slide_*.md")):
                    try:
                        idx = int(sf.stem.split("_")[1])
                    except Exception:
                        continue
                    if idx < start_i or idx > end_i:
                        continue
                    brief = _brief_from_slide_file(
                        sf,
                        deck_id=deck_id,
                        deck_title=deck_title,
                        section_id=section_id,
                        section_role=cand.get("section_role"),
                    )
                    if brief:
                        out.append(brief)
                        loaded += 1
                    if loaded >= max_slides_per_section:
                        break
            continue
        # section subdirectory: section_id ends with `.sec.NN`, dir starts with `section_NN_`
        sec_suffix = section_id.split(".")[-1] if "." in section_id else section_id
        # Try to match: `sec.03` → `section_03_*` or just `section_03`
        sec_num = sec_suffix.replace("sec", "").lstrip("_")  # e.g. "03"
        if not sec_num:
            continue
        section_subdirs = list(deck_path.glob(f"section_{sec_num}_*")) or list(deck_path.glob(f"section_{sec_num}"))
        if not section_subdirs:
            continue
        sec_dir = section_subdirs[0]
        # load all slide_NN.md
        slide_files = sorted(sec_dir.glob("slide_*.md"))
        for sf in slide_files[:max_slides_per_section]:
            brief = _brief_from_slide_file(
                sf,
                deck_id=deck_id,
                deck_title=deck_title,
                section_id=section_id,
                section_role=cand.get("section_role"),
            )
            if brief:
                out.append(brief)
    return out


def slice_narrative_constraints_for_chapter(narrative_constraints: dict,
                                              chapter_index: int) -> dict:
    """Extract narrative_constraints fragments relevant to chapter `chapter_index`."""
    nc = narrative_constraints or {}
    thesis = nc.get("thesis_callback") or {}
    framework = nc.get("framework_anchor_repeat") or {}
    anchor_traj = nc.get("anchor_term_trajectory") or []
    hooks = nc.get("cross_section_hooks") or []

    raise_at = thesis.get("raise_at_chapter")
    callback_at = thesis.get("callback_at_chapters") or []
    repeat_at = framework.get("repeat_at_chapters") or []

    relevant_anchors = []
    for a in anchor_traj:
        if isinstance(a, dict):
            chs = a.get("must_appear_in_chapters") or []
            if chapter_index in chs:
                relevant_anchors.append(a)

    hook_from_prev = None
    hook_to_next = None
    for h in hooks:
        if isinstance(h, dict):
            if h.get("to") == chapter_index:
                hook_from_prev = h
            if h.get("from") == chapter_index:
                hook_to_next = h

    return {
        "thesis_raise_at_this_chapter": raise_at == chapter_index,
        "thesis_callback_at_this_chapter": chapter_index in callback_at,
        "thesis_text": thesis.get("thesis"),
        "framework_anchor_repeat_at_this_chapter": chapter_index in repeat_at,
        "framework_anchor_text": framework.get("anchor"),
        "anchor_terms_must_appear_in_this_chapter": relevant_anchors,
        "cross_section_hooks_from_prev": hook_from_prev,
        "cross_section_hooks_to_next": hook_to_next,
        "anti_patterns_to_avoid": nc.get("anti_patterns_to_avoid") or [],
    }


def merge_chapter_outlines(per_chapter_slides: list[dict]) -> dict:
    """Merge per-chapter outline slides into a single outline.json structure.

    Input: list of {chapter_index, slides[]} (from outline_slide_detail.md per chapter)
    Output: {slides[] with absolute slide_index, chapter_to_slide_map, rhythm_adherence_log}
    """
    all_slides: list[dict] = []
    chapter_to_slide_map: dict[int, list[int]] = {}
    rhythm_adherence_log: list[dict] = []
    abs_idx = 0
    for ch_out in per_chapter_slides:
        if not isinstance(ch_out, dict):
            continue
        ch_idx = ch_out.get("chapter_index")
        slides = ch_out.get("slides") or []
        chapter_slide_indices: list[int] = []
        for s in slides:
            abs_idx += 1
            new_s = dict(s)
            new_s["slide_index"] = abs_idx
            new_s["chapter_index"] = ch_idx
            # Downstream stages group by section_index, while Stage 1b's skill
            # schema only guarantees chapter_index at the chapter wrapper level.
            # Treat chapter_index/section_index as the same canonical chapter id.
            new_s["section_index"] = new_s.get("section_index") or ch_idx
            all_slides.append(new_s)
            chapter_slide_indices.append(abs_idx)
        if ch_idx is not None:
            chapter_to_slide_map[ch_idx] = chapter_slide_indices
        if "rhythm_adherence" in ch_out:
            rhythm_adherence_log.append({
                "chapter_index": ch_idx,
                **ch_out["rhythm_adherence"],
            })
    return {
        "slides": all_slides,
        "chapter_to_slide_map": chapter_to_slide_map,
        "rhythm_adherence_log": rhythm_adherence_log,
    }


def trim_slide_briefs_by_chapter_relevance(slide_briefs: list[dict],
                                              chapter: dict,
                                              *, max_keep: int = 15) -> list[dict]:
    """Trim slide_briefs to top-N most relevant to a chapter (avoid prompt bloat).

    Discovered: ch with 40+ briefs caused Claude CLI timeout on slide_detail call.
    Trim by:
      - chapter.section_role + chapter.chapter title keywords
      - score = section_role match + (适合复用场景 keyword overlap) + (核心论断 keyword overlap)
      - keep top max_keep (default 15) preserving relevance order

    If len(slide_briefs) <= max_keep, returns unchanged.
    """
    if not slide_briefs or len(slide_briefs) <= max_keep:
        return slide_briefs

    chapter_role = chapter.get("section_role") or ""
    ch_title = chapter.get("chapter") or ""
    purpose = chapter.get("purpose") or ""
    # Extract chapter keywords (Chinese tokens of length >= 2 from title/purpose)
    import re as _re
    keywords = []
    for src_text in (ch_title, purpose):
        # split on common punctuation
        for tok in _re.split(r"[\s·:：·，。/\-_()（）\[\]]+", src_text):
            tok = tok.strip()
            if len(tok) >= 2 and tok not in keywords:
                keywords.append(tok)
        if len(keywords) >= 8:
            break
    keywords = keywords[:8]

    def score(b: dict) -> int:
        s = 0
        # section_role match (high weight)
        if b.get("section_role") == chapter_role:
            s += 5
        elif chapter_role and b.get("section_role") in {"content_candidate"}:
            s += 1
        # 适合复用场景 keyword overlap
        scenarios = b.get("适合复用场景") or []
        for kw in keywords:
            for sc in scenarios:
                if isinstance(sc, str) and kw in sc:
                    s += 2
                    break
        # 核心论断 / 本页讲什么 / 标题 substring
        for f in ("核心论断", "本页讲什么", "标题"):
            v = b.get(f) or ""
            if isinstance(v, str):
                for kw in keywords:
                    if kw in v:
                        s += 1
                        break
        return s

    scored = [(score(b), i, b) for i, b in enumerate(slide_briefs)]
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [b for (_, _, b) in scored[:max_keep]]


def compact_idea_for_fix(idea_analysis: dict) -> dict:
    """Slim idea-analysis.json for use in fix-loop prompts (Bug-2 fix).

    Full idea-analysis.json is ~60 KB; fix prompts include prior outline (~80 KB)
    + idea + codex_issues + rules → ~150 KB exceeds Claude CLI safe payload.

    Strip to ~15 KB by keeping only fields fix skills actually need:
      - chapter_plan (without candidate_carrier_sections — those are 60% of size)
      - narrative_constraints (for user_concern + framework anchor)
      - reuse_strategy
      - selected_narrative_arc (id + arc only, not full pattern body)
      - user_concern_history (cross-stage guard)
      - identity
      - provenance.section_inclusion_rationale + rule_relaxed_with_reason

    Drops:
      - chapter_plan[i].candidate_carrier_sections (driver gave OUTLINE; fix doesn't need)
      - chapter_plan[i].section_rhythm_patterns (OUTLINE consumed)
      - source_materials_overview (Mode 1 only)
    """
    if not isinstance(idea_analysis, dict):
        return {}
    out: dict = {
        "schema_version": idea_analysis.get("schema_version"),
        "identity": idea_analysis.get("identity"),
        "presentation_goal": idea_analysis.get("presentation_goal"),
        "core_message": idea_analysis.get("core_message"),
        "story_design_mode": idea_analysis.get("story_design_mode"),
        "narrative_constraints": idea_analysis.get("narrative_constraints"),
        "reuse_strategy": idea_analysis.get("reuse_strategy"),
        "user_concern_history": idea_analysis.get("user_concern_history") or [],
    }
    sna = idea_analysis.get("selected_narrative_arc") or {}
    out["selected_narrative_arc"] = {
        "primary_pattern_id": sna.get("primary_pattern_id"),
        "borrowed_patterns": sna.get("borrowed_patterns") or [],
        "narrative_arc": sna.get("narrative_arc"),
    }
    chapter_plan_slim: list[dict] = []
    for ch in (idea_analysis.get("chapter_plan") or []):
        if not isinstance(ch, dict):
            continue
        chapter_plan_slim.append({
            "section_index": ch.get("section_index"),
            "chapter": ch.get("chapter"),
            "section_role": ch.get("section_role"),
            "purpose": ch.get("purpose"),
            "expected_pages_indicative": ch.get("expected_pages_indicative"),
            "expected_pages_range": ch.get("expected_pages_range"),
            "may_be_revised_by_outline": ch.get("may_be_revised_by_outline"),
            "claims_to_make": ch.get("claims_to_make") or [],
            "claims_to_setup_for_later": ch.get("claims_to_setup_for_later") or [],
            "section_rhythm_pattern_id": ch.get("section_rhythm_pattern_id"),
            "section_rhythm_summary": ch.get("section_rhythm_summary"),
            "section_rhythm_source_count": ch.get("section_rhythm_source_count"),
            "material_section_hints": ch.get("material_section_hints") or [],
            "parallel_group_id": ch.get("parallel_group_id"),
            "parallel_group_terminology": ch.get("parallel_group_terminology"),
            "chapter_bridge_hint": ch.get("chapter_bridge_hint"),
            # v28: claims_pending_data 已弃 (库驱动生成, 不允许待补外部数据)
            "source_carrier_resource_kind": ch.get("source_carrier_resource_kind"),
            # Drop: candidate_carrier_sections, section_rhythm_patterns, materials
        })
    out["chapter_plan"] = chapter_plan_slim
    prov = idea_analysis.get("provenance") or {}
    out["provenance"] = {
        "section_inclusion_rationale": prov.get("section_inclusion_rationale") or {},
        "rule_relaxed_with_reason": prov.get("rule_relaxed_with_reason") or [],
    }
    return out


def compact_outline_for_fix(outline: dict, *, max_slide_snippets: int = 0) -> dict:
    """Slim outline.json for use in fix-loop prompts (Bug-2 fix complement).

    Full outline.json with 55 slides is ~80 KB. Fix prompts only need:
      - slides[] with stub-level fields (no full source_resource_ids details)
      - chapter_to_slide_map
      - user_concern_history
      - provenance

    Drops per-slide:
      - alternates (long match_reasons strings)
      - delivery_hint (verbose)
      - needed_evidence (dict array, large)

    Keeps per-slide:
      - slide_index, chapter_index, target_role, archetype, archetype_placement
      - target_title, target_claim (short)
      - source_carrier_resource_kind
      - source_resource_ids (id only, no match_reasons)
      - gap_research_hint (short)
      - claim_status_link
    """
    if not isinstance(outline, dict):
        return {}
    slides_slim: list[dict] = []
    for s in (outline.get("slides") or []):
        if not isinstance(s, dict):
            continue
        src_ids = s.get("source_resource_ids") or []
        src_slim = [
            {"deck_id": x.get("deck_id"), "slide_id": x.get("slide_id"),
             "rank_score": x.get("rank_score")}
            for x in src_ids if isinstance(x, dict)
        ]
        slides_slim.append({
            "slide_index": s.get("slide_index"),
            "chapter_index": s.get("chapter_index"),
            "target_role": s.get("target_role"),
            "archetype": s.get("archetype"),
            "archetype_placement": s.get("archetype_placement"),
            "target_title": s.get("target_title"),
            "target_claim": s.get("target_claim"),
            "key_points": (s.get("key_points") or [])[:3],
            "anchor_terms": s.get("anchor_terms") or [],
            "source_carrier_resource_kind": s.get("source_carrier_resource_kind"),
            "source_resource_ids": src_slim,
            "gap_research_hint": s.get("gap_research_hint"),
            "claim_status_link": s.get("claim_status_link"),
        })
    return {
        "schema_version": outline.get("schema_version"),
        "identity": outline.get("identity"),
        "slide_count": outline.get("slide_count"),
        "slides": slides_slim,
        "chapter_to_slide_map": outline.get("chapter_to_slide_map"),
        "rhythm_adherence_log": outline.get("rhythm_adherence_log"),
        "user_concern_history": outline.get("user_concern_history") or [],
        "provenance": outline.get("provenance") or {},
    }


def load_slide_briefs_for_rhythm_pattern(
    pattern_id: str,
    *,
    max_carriers: int = 5,
    max_slides_per_section: int = 20,
) -> list[dict]:
    """v4.0 helper: 根据 rhythm pattern_id 反查 slide briefs (替代 v3.2 中 IDEA 直接给的
    candidate_carrier_sections).

    步骤:
      1. 加载 logic/section_level/<pattern_id>.json 获取 carriers (含 deck_id + section_id)
      2. 取 top-N carriers (按出现顺序, 即 source_count 排序)
      3. 把每个 carrier 当 candidate_carrier_section 喂给 load_slide_briefs_for_chapter
         以获取该 section 下所有 slide 的 brief

    返回: 跟 load_slide_briefs_for_chapter 同样格式的 slide brief 列表
      [{deck_id, deck_title, section_id, section_role, slide_index_in_source, slide_id,
        页面角色, 标题, 核心论断, 本页讲什么, 关键文字, 视觉骨架, 资源ID列表,
        适合复用场景, 不适合复用场景, 上页角色, 下页角色}, ...]
    """
    if not pattern_id:
        return []
    pat = load_rhythm_pattern_full(pattern_id)
    if not pat:
        return []
    carriers = (pat.get("carriers") or [])[:max_carriers]
    # 转成 candidate_carrier_sections 喂给 load_slide_briefs_for_chapter
    fake_candidates = [
        {
            "deck_id": c.get("deck_id"),
            "section_id": c.get("section_id"),
            "deck_title": c.get("deck_title") or c.get("section_title") or "",
            "section_role": c.get("section_role"),
            "section_title": c.get("section_title"),
        }
        for c in carriers if isinstance(c, dict) and c.get("deck_id") and c.get("section_id")
    ]
    return load_slide_briefs_for_chapter(
        fake_candidates, max_slides_per_section=max_slides_per_section)


# ============================================================
# Phase A: Global slide index (cross-deck/cross-section/cross-rhythm)
# Lets Stage 1b reach slides outside the current rhythm.carriers pool.
# Cached in module-level dict; lazy build on first call.
# ============================================================

_GLOBAL_SLIDE_INDEX_CACHE: list[dict] | None = None


def _infer_layer_from_text(*texts: str) -> str:
    """Heuristic: classify a slide into algorithm/system/hardware/structural/other.

    Used both for indexing (per slide) and for chapter-layer inference.
    """
    blob = " ".join(t for t in texts if isinstance(t, str)).lower()
    # cheap keyword buckets; can be tuned later
    hw_keys = ["fpga", "asic", "加速器", "芯片", "3d 集成", "3d集成", "可重构",
               "pe 阵列", "硬件架构", "硬件层", "verilog", "rtl", "硅",
               "存内", "近存", "片上", "tpu", "npu", "gpu 架构"]
    sys_keys = ["调度", "通信", "并行", "vllm", "splitwise", "pagedattention",
                "kv cache", "kv-cache", "推理引擎", "推理服务", "服务框架",
                "triton", "tgi", "算子优化", "tensor parallel", "pipeline parallel",
                "ep ", "moe 并行", "系统层", "集群", "推理系统", "运行时"]
    algo_keys = ["稀疏", "量化", "剪枝", "蒸馏", "投机解码", "投机", "早退",
                 "flashattention", "flashdecoding", "解码加速", "kv 压缩",
                 "模型压缩", "算法层", "moe 路由", "推理算法",
                 "long context", "长文本", "长上下文"]
    struct_keys = ["封面", "致谢", "目录", "agenda", "签名", "联系方式",
                   "首页", "末页", "section_divider", "framework", "框架图",
                   "三层", "总览", "导览", "introduction"]
    hw_hits = sum(1 for k in hw_keys if k in blob)
    sys_hits = sum(1 for k in sys_keys if k in blob)
    algo_hits = sum(1 for k in algo_keys if k in blob)
    struct_hits = sum(1 for k in struct_keys if k in blob)
    score = {"hardware": hw_hits, "system": sys_hits,
             "algorithm": algo_hits, "structural": struct_hits}
    best = max(score.items(), key=lambda kv: kv[1])
    if best[1] == 0:
        return "other"
    return best[0]


def _parse_one_slide_md(slide_path: Path, deck_id: str, deck_title: str,
                         section_id: str, section_role: str) -> dict | None:
    """Parse a single slide_NN.md into compact brief dict. Adds inferred_layer."""
    try:
        content = slide_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    fm_raw, _ = _split_frontmatter(content)
    fm = _parse_deck_md_frontmatter(fm_raw)
    try:
        idx = int(slide_path.stem.split("_")[1])
    except Exception:
        idx = None
    title = fm.get("标题") or ""
    claim = fm.get("核心论断") or ""
    body = fm.get("本页讲什么") or ""
    visuals = fm.get("视觉骨架") if isinstance(fm.get("视觉骨架"), list) else []
    key_text = fm.get("关键文字") if isinstance(fm.get("关键文字"), list) else []
    fit = fm.get("适合复用场景") if isinstance(fm.get("适合复用场景"), list) else []
    layer = _infer_layer_from_text(
        title, claim, body, section_role or "",
        " ".join(visuals) if visuals else "",
        " ".join(key_text) if key_text else "",
        " ".join(fit) if fit else "",
    )
    return {
        "deck_id": deck_id,
        "deck_title": deck_title,
        "section_id": section_id,
        "section_role": section_role,
        "slide_index_in_source": idx,
        "slide_id": fm.get("页标识") or f"{deck_id}.slide_{idx}",
        "页面角色": fm.get("页面角色"),
        "标题": title,
        "核心论断": claim,
        "本页讲什么": body[:200],   # truncate body for index size
        "关键文字": key_text[:5],
        "视觉骨架": visuals[:5],
        "资源ID列表": fm.get("资源ID列表") if isinstance(fm.get("资源ID列表"), list) else [],
        "适合复用场景": fit[:5],
        "不适合复用场景": fm.get("不适合复用场景") if isinstance(fm.get("不适合复用场景"), list) else [],
        "inferred_layer": layer,
        # v20 D1 multi-layer fields (post-enhance)
        "页在section中的作用": fm.get("页在section中的作用"),
        "视觉文本层次": fm.get("视觉文本层次") if isinstance(fm.get("视觉文本层次"), list) else [],
        "alternate_claims": fm.get("alternate_claims") if isinstance(fm.get("alternate_claims"), list) else [],
        "layout_tag": fm.get("layout_tag"),
    }


def _infer_deck_id_from_dir(deck_dir: Path) -> str:
    """Infer canonical deck_id from a slide_NN.md frontmatter inside the deck dir.

    Fallback: use the deck dirname itself.
    """
    for sf in deck_dir.glob("section_*/slide_*.md"):
        try:
            fm_raw, _ = _split_frontmatter(sf.read_text(encoding="utf-8", errors="ignore"))
            fm = _parse_deck_md_frontmatter(fm_raw)
            d = fm.get("所属deck")
            if d:
                return d
        except Exception:
            continue
    return deck_dir.name


def _infer_section_id_from_dir(section_dir: Path, deck_id: str) -> tuple[str, str]:
    """Return (section_id, section_role) by reading first slide_NN.md in the section dir."""
    for sf in section_dir.glob("slide_*.md"):
        try:
            fm_raw, _ = _split_frontmatter(sf.read_text(encoding="utf-8", errors="ignore"))
            fm = _parse_deck_md_frontmatter(fm_raw)
            sid = fm.get("所属章节") or ""
            role = fm.get("section_role") or ""
            return sid, role
        except Exception:
            continue
    # fallback: build from dir name e.g. section_05_xxx
    name = section_dir.name
    parts = name.split("_", 2)
    sec_num = parts[1] if len(parts) >= 2 else ""
    return f"{deck_id}.sec.{sec_num}", ""


def load_global_slide_index(force_rebuild: bool = False) -> list[dict]:
    """Build (or return cached) flat list of ALL slide briefs across the library.

    Walks `data/resources_library/material/decks/<deck_dir>/section_*/slide_*.md`.
    Each entry includes `inferred_layer` for layer-aware querying.

    Size: ~3000 slides × ~600 bytes ≈ 1.5MB in memory. Loaded once per process.
    """
    global _GLOBAL_SLIDE_INDEX_CACHE
    if _GLOBAL_SLIDE_INDEX_CACHE is not None and not force_rebuild:
        return _GLOBAL_SLIDE_INDEX_CACHE
    decks_root = ROOT / "data" / "resources_library" / "material" / "decks"
    if not decks_root.exists():
        _GLOBAL_SLIDE_INDEX_CACHE = []
        return _GLOBAL_SLIDE_INDEX_CACHE
    out: list[dict] = []
    for deck_dir in sorted(decks_root.iterdir()):
        if not deck_dir.is_dir():
            continue
        deck_id = _infer_deck_id_from_dir(deck_dir)
        deck_title = deck_dir.name
        for sec_dir in sorted(deck_dir.glob("section_*")):
            if not sec_dir.is_dir():
                continue
            section_id, section_role = _infer_section_id_from_dir(sec_dir, deck_id)
            for sf in sorted(sec_dir.glob("slide_*.md")):
                brief = _parse_one_slide_md(sf, deck_id, deck_title, section_id, section_role)
                if brief:
                    out.append(brief)
    _GLOBAL_SLIDE_INDEX_CACHE = out
    return out


def load_slide_briefs_by_ids(slide_ids: list[str]) -> list[dict]:
    """Given slide_ids, return matching briefs from the global material index.

    Preserves the input order (so caller's ranking is kept). Missing IDs are
    silently skipped. This is a Stage 1b material helper; IDEA_ANALYSIS should
    not call it or store slide-level pools.
    """
    if not slide_ids:
        return []
    idx = load_global_slide_index()
    by_id = {b.get("slide_id"): b for b in idx if b.get("slide_id")}
    out: list[dict] = []
    seen: set = set()
    for sid in slide_ids:
        if sid in seen:
            continue
        seen.add(sid)
        b = by_id.get(sid)
        if b:
            out.append(dict(b))  # copy so caller can mutate _tier/_score
    return out


def load_structural_slide_briefs_for_role(role: str, *, max_keep: int = 12) -> list[dict]:
    """Return real material-library slides suitable for structural outline roles.

    These are still source slides, not placeholders. OUTLINE Stage 1b feeds them
    to Claude so structural pages (opening/cover/agenda/divider/closing) can be
    explicitly source-bound instead of using `not_applicable`.
    """
    role_norm = str(role or "").lower()
    wanted: set[str] = set()
    title_hints: tuple[str, ...] = ()
    if role_norm in {"opening", "cover"}:
        wanted = {"cover_candidate", "toc_candidate"}
        title_hints = ("封面", "目录", "agenda", "contents", "outline")
    elif role_norm == "agenda":
        wanted = {"toc_candidate"}
        title_hints = ("目录", "agenda", "contents", "outline", "议程", "提纲")
    elif role_norm == "section_divider":
        wanted = {"chapter_candidate", "toc_candidate"}
        title_hints = ("章节", "目录", "agenda", "contents", "outline", "过渡")
    elif role_norm in {"closing", "references"}:
        wanted = {"ending_candidate"}
        title_hints = ("致谢", "thanks", "thank", "q&a", "结束", "结尾", "参考文献", "references")
    else:
        return []

    scored: list[tuple[int, int, dict]] = []
    for i, b in enumerate(load_global_slide_index()):
        page_role = str(b.get("页面角色") or "").lower()
        title = str(b.get("标题") or "")
        title_lc = title.lower()
        score = 0
        if page_role in wanted:
            score += 10
        if any(h in title_lc or h in title for h in title_hints):
            score += 4
        # Prefer the clean lab template for purely structural pages when present.
        deck_id = str(b.get("deck_id") or "")
        if "通用模板" in deck_id or "DAI-实验室PPT模版" in deck_id:
            score += 3
        if role_norm == "opening" and page_role == "toc_candidate":
            # Keep opening pools cover-first, but still include agenda candidates.
            score -= 1
        if role_norm == "closing" and "参考文献" in title:
            score -= 4
        if score <= 0:
            continue
        item = dict(b)
        item["_score"] = score
        item["_search_mode"] = f"structural_{role_norm}"
        scored.append((score, i, item))

    scored.sort(key=lambda t: (-t[0], t[1]))
    out: list[dict] = []
    seen: set[str] = set()
    for _, _, item in scored:
        sid = item.get("slide_id")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(item)
        if len(out) >= max_keep:
            break
    return out


def _tokenize_zh(text: str) -> list[str]:
    """Cheap CJK-aware tokenizer: split on whitespace + ascii punct, keep CJK chars as bigrams."""
    if not text:
        return []
    import re
    # extract ascii words
    asc = re.findall(r"[A-Za-z][A-Za-z0-9\-/_]+", text)
    asc = [w.lower() for w in asc if len(w) >= 2]
    # extract CJK runs and emit bigrams
    cjk_chars = re.findall(r"[一-鿿]+", text)
    bigrams: list[str] = []
    for run in cjk_chars:
        if len(run) <= 1:
            bigrams.append(run)
        else:
            for i in range(len(run) - 1):
                bigrams.append(run[i:i+2])
    return asc + bigrams


def _slide_brief_text_blob(brief: dict) -> str:
    """Concat searchable fields for keyword scoring."""
    fields = [
        brief.get("标题") or "",
        brief.get("核心论断") or "",
        brief.get("本页讲什么") or "",
        brief.get("section_role") or "",
        " ".join(brief.get("关键文字") or []),
        " ".join(brief.get("视觉骨架") or []),
        " ".join(brief.get("适合复用场景") or []),
    ]
    return " ".join(fields).lower()


def infer_chapter_layer(chapter: dict) -> str:
    """Infer the layer the chapter is about (algorithm/system/hardware/structural/other).

    Used by Stage 1b to drive global slide search.
    """
    role = (chapter.get("section_role") or "").lower()
    if role in {"opening", "cover", "agenda", "closing", "references", "section_divider"}:
        return "structural"
    name = chapter.get("chapter") or ""
    purpose = chapter.get("purpose") or ""
    claims = " ".join(chapter.get("claims_to_make") or [])
    return _infer_layer_from_text(name, purpose, claims, role)


# ============================================================
# Phase G: deck → section → slide three-tier coarse-to-fine search
# Used by Stage 1b PASS-2 to fill gaps with content-specific candidates,
# instead of going flat against the global slide index.
# ============================================================


def _score_keyword_overlap(blob: str, keywords: list[str]) -> float:
    """Lowercase keyword token overlap. Returns float (each hit = 1.0)."""
    if not blob or not keywords:
        return 0.0
    blob_l = blob.lower()
    hits = 0
    for kw in keywords:
        if not kw:
            continue
        kw_l = kw.lower().strip()
        if len(kw_l) >= 2 and kw_l in blob_l:
            hits += 1
    return float(hits)


def search_global_decks_by_keywords(
    keywords: list[str],
    *,
    exclude_decks: list[str] | None = None,
    max_keep: int = 5,
) -> list[dict]:
    """Tier-2a coarse: rank decks via decks-index frontmatter keyword overlap.

    Looks at deck['标题'], deck['主题标签'], deck['章节列表'] (joined),
    deck['论述总结'] (if present in index — older indices may lack it),
    deck['适合复用场景'].

    Returns top-N {deck_id, title, score, _matched_field_count}.
    """
    try:
        idx = library_query.load_decks_index()
    except Exception:
        return []
    decks = (idx or {}).get("decks") or []
    excl = set(exclude_decks or [])
    scored: list[tuple[float, dict]] = []
    for d in decks:
        if not isinstance(d, dict):
            continue
        deck_id = d.get("deck标识") or d.get("deck_id")
        if not deck_id or deck_id in excl:
            continue
        # Build searchable blob from index fields
        parts = [
            d.get("标题") or "",
            " ".join(d.get("主题标签") or []),
            " ".join(d.get("章节列表") or []),
            " ".join(d.get("适合复用场景") or []),
            d.get("论述总结") or "",
            d.get("适用场景") or "",
        ]
        blob = " ".join(parts)
        score = _score_keyword_overlap(blob, keywords)
        if score > 0:
            scored.append((score, {
                "deck_id": deck_id,
                "deck_title": d.get("标题"),
                "deck_dir": d.get("目录名"),
                "topic_tags": d.get("主题标签") or [],
                "section_titles": d.get("章节列表") or [],
                "_score": round(score, 2),
            }))
    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:max_keep]]


def _read_section_md_frontmatter(section_dir: Path) -> dict | None:
    """Read section.md frontmatter into dict."""
    sf = section_dir / "section.md"
    if not sf.exists():
        return None
    try:
        fm_raw, _ = _split_frontmatter(sf.read_text(encoding="utf-8", errors="ignore"))
        return _parse_deck_md_frontmatter(fm_raw)
    except Exception:
        return None


def cascade_search_for_gap(
    keywords: list[str],
    *,
    layer: str | None = None,
    role_hint: str | None = None,
    exclude_slide_ids: list[str] | None = None,
    exclude_decks: list[str] | None = None,
    max_decks: int = 5,
    max_sections: int = 10,
    max_slides: int = 15,
    mode: str = "slide",
    span_size: int = 3,
) -> dict:
    """End-to-end: deck-coarse → section-mid → slide-fine cascade.

    Returns {'decks': [...], 'sections': [...], 'slides': [...]} for caller to inspect.
    `slides` is the actionable output (top-N slide briefs ready to feed Stage 1b PASS-2).

    v20 P1-W3: mode='section_span' additionally returns 'section_groups':
      [{deck_id, section_id, slide_ids_ordered, group_score, section_role, deck_title}]
    Each group contains up to `span_size` consecutive slide_ids (byte-sorted).
    Callers wanting "reuse 3-5 continuous pages from same section" read this.
    """
    decks = search_global_decks_by_keywords(
        keywords, exclude_decks=exclude_decks, max_keep=max_decks)
    deck_ids = [d["deck_id"] for d in decks if d.get("deck_id")]
    sections = search_global_sections_in_decks(
        deck_ids, keywords, role_hint=role_hint, max_keep=max_sections)
    slides = search_global_slides_in_sections(
        sections, keywords, role_hint=role_hint, max_keep=max_slides)
    # Apply layer + exclusion filters at slide level
    if layer:
        slides = [s for s in slides if s.get("inferred_layer") == layer]
    if exclude_slide_ids:
        excl = set(exclude_slide_ids)
        slides = [s for s in slides if s.get("slide_id") not in excl]
    result = {"decks": decks, "sections": sections, "slides": slides}
    if mode == "section_span":
        # Group slides by (deck_id, section_id), pick top spans of span_size
        from collections import defaultdict
        grouped: dict = defaultdict(list)
        for s in slides:
            key = (s.get("deck_id"), s.get("section_id"))
            if key[0] and key[1]:
                grouped[key].append(s)
        section_groups: list = []
        for (did, sid), items in grouped.items():
            items_sorted = sorted(items, key=lambda x: x.get("slide_index_in_source") or 0)
            slide_ids = [i.get("slide_id") for i in items_sorted[:span_size]]
            slide_indexes = [i.get("slide_index_in_source") for i in items_sorted[:span_size]]
            # Simple group score: sum of individual slide _score (existing field or fallback)
            group_score = sum((i.get("_score") or 1.0) for i in items_sorted[:span_size])
            section_groups.append({
                "deck_id": did,
                "section_id": sid,
                "slide_ids_ordered": slide_ids,
                "slide_indexes_ordered": slide_indexes,
                "group_score": round(group_score, 2),
                "size": len(slide_ids),
                "section_role": items_sorted[0].get("section_role") if items_sorted else None,
                "deck_title": items_sorted[0].get("deck_title") if items_sorted else None,
            })
        # sort desc by (size, group_score)
        section_groups.sort(key=lambda g: (-g["size"], -g["group_score"]))
        result["section_groups"] = section_groups
    return result


# ============================================================
# Phase I: library keyword evidence extractor (used by Stage 1b)
# 给定 abstract_topics (Stage 1a 输出, e.g. ["调度", "服务框架"]) 和 chapter_layer,
# 从资源库 material/decks-index.json + section.md 抽出**真实存在**的具体技术名 keyword.
# 替代 Stage 1a LLM 拍脑袋写 "vLLM/FlightLLM" 这种猜测.
# ============================================================


def _strip_section_dir_prefix(name: str) -> str:
    """Strip 'section_NN_' prefix from a section directory name or title."""
    import re
    return re.sub(r"^section_\d+[_\s]*", "", str(name)).strip()


def _is_proper_noun_like(text: str) -> bool:
    """Heuristic: does this token contain a likely work name (CamelCase / acronym / digits)?"""
    import re
    if not text or len(text) < 2:
        return False
    # CamelCase: ≥2 uppercase letters somewhere
    if re.search(r"[A-Z][a-z]+[A-Z]|[A-Z]{2,}", text):
        return True
    # Numbers/version suffix (e.g. "GPT-4", "LLaMA-2")
    if re.search(r"[A-Za-z][-_]?\d", text):
        return True
    # ASCII word with hyphen like "PD-分离" or "KV-cache"
    if re.search(r"[A-Z][a-zA-Z0-9]+", text):
        return True
    return False


def extract_library_keywords_for_topic(
    abstract_topics: list[str],
    *,
    chapter_layer: str | None = None,
    section_role: str | None = None,
    top_decks: int = 8,
    max_keywords: int = 30,
) -> dict:
    """For given abstract_topics (e.g. ["调度", "服务框架"]),
    extract REAL concrete keywords from the resource library.

    Strategy:
      1) Score decks via decks-index.json (主题标签 + 章节列表 + 论述总结 + 适合复用场景)
      2) Top-N decks: harvest concrete names from `章节列表` (strip section_NN_ prefix)
      3) Also harvest from section.md `标题` and `章节叙事` for the chapter_layer-matching sections
      4) Score each concrete name by:
          - deck score (how many topics it matched in step 1)
          - occurrence count across decks (cross-deck evidence)
          - whether it looks like a proper-noun work name (CamelCase / 数字版本 / 含 -)
      5) Return top-N with evidence (which decks/sections they came from)

    Returns:
      {
        "concrete_keywords": [
          {"keyword": "FlightLLM", "evidence_count": 3, "decks": [...], "is_work_name": True},
          {"keyword": "PD 分离", ...},
          ...
        ],
        "top_decks": [{"deck_id": ..., "title": ..., "score": ...}, ...],
        "abstract_topics": [...]  # echo back for caller
      }
    """
    if not abstract_topics:
        return {"concrete_keywords": [], "top_decks": [], "abstract_topics": []}

    # Step 1+2: deck coarse search reusing existing helper
    # Augment search keywords with layer name to bias
    search_keys = list(abstract_topics)
    if chapter_layer and chapter_layer not in {"structural", "other"}:
        layer_zh = {"algorithm": "算法层", "system": "系统层", "hardware": "硬件层"}.get(chapter_layer)
        if layer_zh:
            search_keys.append(layer_zh)
    decks_ranked = search_global_decks_by_keywords(
        search_keys, max_keep=top_decks)

    # Step 3: harvest concrete names from 章节列表 and section.md
    try:
        idx = library_query.load_decks_index()
    except Exception:
        idx = {"decks": []}
    deck_id_to_meta = {d.get("deck标识"): d for d in (idx.get("decks") or [])
                        if isinstance(d, dict)}

    # candidate name → {"count": int, "decks": set, "is_work": bool, "score": float}
    candidates: dict[str, dict] = {}
    decks_root = ROOT / "data" / "resources_library" / "material" / "decks"

    for d_entry in decks_ranked:
        did = d_entry.get("deck_id")
        d_score = float(d_entry.get("_score") or 0.0)
        meta = deck_id_to_meta.get(did) or {}

        # 3a: 章节列表 from decks-index
        for title in (meta.get("章节列表") or []):
            clean = _strip_section_dir_prefix(title)
            if not clean or len(clean) > 50:
                continue
            # split by colon "层次一: 算法层 TB-STC" or "FlashOverlap: 计算通信重叠"
            for part in (clean.split(":") + clean.split("：") + [clean]):
                p = part.strip()
                if len(p) < 2 or len(p) > 40:
                    continue
                rec = candidates.setdefault(p, {"count": 0, "decks": set(),
                                                  "is_work": False, "score": 0.0,
                                                  "source": "section_title"})
                rec["count"] += 1
                rec["decks"].add(did)
                rec["score"] += d_score
                if _is_proper_noun_like(p):
                    rec["is_work"] = True

        # 3b: harvest from section.md frontmatter inside this deck
        deck_dir = meta.get("目录名")
        if not deck_dir:
            continue
        deck_path = decks_root / deck_dir
        if not deck_path.exists():
            continue
        for sec_dir in deck_path.glob("section_*"):
            fm = _read_section_md_frontmatter(sec_dir)
            if not fm:
                continue
            # Filter by section_role if hint
            if section_role and fm.get("章节角色") and fm.get("章节角色") != section_role:
                # don't strict skip — keep but reduce score
                contrib = 0.5
            else:
                contrib = 1.0
            sec_title = _strip_section_dir_prefix(fm.get("标题") or "")
            if sec_title and 2 <= len(sec_title) <= 40:
                rec = candidates.setdefault(sec_title, {"count": 0, "decks": set(),
                                                          "is_work": False, "score": 0.0,
                                                          "source": "section_md_title"})
                rec["count"] += 1
                rec["decks"].add(did)
                rec["score"] += d_score * contrib
                if _is_proper_noun_like(sec_title):
                    rec["is_work"] = True
            # also harvest from 适合复用场景 list (these are short re-use phrases)
            for fit in (fm.get("适合复用场景") or [])[:3]:
                f = (fit or "").strip()
                if 3 <= len(f) <= 40:
                    rec = candidates.setdefault(f, {"count": 0, "decks": set(),
                                                      "is_work": False, "score": 0.0,
                                                      "source": "fit_phrase"})
                    rec["count"] += 1
                    rec["decks"].add(did)
                    rec["score"] += d_score * contrib * 0.5

    # Step 4: rank candidates
    # Work-name bias: is_work=True gets +1.0 score boost
    # Cross-deck bias: appearing in ≥2 decks gets +0.5
    ranked: list[tuple[float, str, dict]] = []
    for name, rec in candidates.items():
        s = rec["score"]
        if rec["is_work"]:
            s += 1.0
        if len(rec["decks"]) >= 2:
            s += 0.5
        # downweight overly generic phrases
        generic = {"研究背景", "总结", "致谢", "封面", "目录", "动机", "未来", "展望"}
        if any(g in name for g in generic):
            s -= 1.0
        ranked.append((s, name, rec))
    ranked.sort(key=lambda x: -x[0])

    out_kws = []
    seen_normalized = set()
    for s, name, rec in ranked:
        # dedup near-duplicates (substring containment)
        norm = name.lower().replace(" ", "")
        if any(norm in nx or nx in norm for nx in seen_normalized):
            continue
        seen_normalized.add(norm)
        out_kws.append({
            "keyword": name,
            "score": round(s, 2),
            "evidence_count": rec["count"],
            "decks": sorted(rec["decks"]),
            "is_work_name": rec["is_work"],
            "source": rec.get("source", "?"),
        })
        if len(out_kws) >= max_keywords:
            break

    return {
        "abstract_topics": list(abstract_topics),
        "chapter_layer": chapter_layer,
        "section_role": section_role,
        "top_decks": [
            {"deck_id": d["deck_id"], "title": d.get("deck_title"),
             "score": d.get("_score")}
            for d in decks_ranked
        ],
        "concrete_keywords": out_kws,
    }


# ============================================================
# Phase J-1: claim alignment LLM scoring (Stage 1b helper)
# Replace pure keyword overlap with judgment-direction semantic alignment.
# Lightweight: 1 batched call per chapter (~30s, ~$0.05).
# ============================================================

def _clip_text(value, limit: int = 220) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _compact_brief_for_claim_alignment(brief: dict) -> dict:
    """Keep only the semantic fields Claude needs for source/target alignment."""
    if not isinstance(brief, dict):
        return {}
    return {
        "slide_id": brief.get("slide_id") or brief.get("页标识"),
        "deck_title": _clip_text(brief.get("deck_title") or brief.get("deck_id"), 120),
        "section_title": _clip_text(brief.get("section_title"), 120),
        "section_role": brief.get("section_role"),
        "page_role": brief.get("页面角色") or brief.get("page_role"),
        "title": _clip_text(brief.get("标题") or brief.get("title"), 160),
        "claim": _clip_text(brief.get("核心论断") or brief.get("claim"), 260),
        "alternate_claims": [
            _clip_text(x, 160)
            for x in (brief.get("alternate_claims") or [])[:3]
        ],
        "talk_track": _clip_text(
            brief.get("本页讲什么") or brief.get("content_summary") or brief.get("body"),
            260,
        ),
    }


def score_claims_alignment_batch(
    target_claim: str,
    candidate_briefs: list[dict],
    *,
    target_role: str | None = None,
    chapter_layer: str | None = None,
    timeout: int = 240,
) -> list[dict]:
    """Ask Claude to score whether each source slide supports the target claim.

    Returns records shaped as:
      {slide_id, claim_alignment: 0..1, reason}

    This intentionally stays model-driven. If Claude fails or returns unusable
    JSON, the caller catches the raised error and keeps neutral scores.
    """
    if not candidate_briefs:
        return []
    candidates = [
        _compact_brief_for_claim_alignment(b)
        for b in candidate_briefs
        if isinstance(b, dict) and (b.get("slide_id") or b.get("页标识"))
    ]
    if not candidates:
        return []

    from . import claude_cli

    payload = {
        "target": {
            "claim": _clip_text(target_claim, 700),
            "target_role": target_role,
            "chapter_layer": chapter_layer,
        },
        "candidate_source_slides": candidates,
    }
    prompt = (
        "You are scoring source-slide reuse for a generated PPT outline.\n"
        "Task: compare the TARGET page claim with each candidate SOURCE slide.\n"
        "Score semantic judgment-direction alignment, not keyword overlap.\n"
        "Important rules:\n"
        "- 0.8-1.0: same object/scope and the source can directly support the target page.\n"
        "- 0.5-0.7: related but needs rewriting or only supports part of the target.\n"
        "- 0.2-0.4: weak relation, wrong scope, or source is only background/navigation.\n"
        "- 0.0-0.1: mismatched object, mismatched owner, opposite claim, or unusable as content.\n"
        "- Penalize TOC/agenda/cover/divider slides for content targets unless the target role itself is structural.\n"
        "- Penalize personal/student/deck-level overview sources when the target is a lab/group/team overview.\n"
        "Return JSON only, exactly this shape:\n"
        "{\"scores\":[{\"slide_id\":\"...\",\"claim_alignment\":0.0,\"reason\":\"short reason\"}]}\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
    outcome = claude_cli.call_claude_json(prompt, timeout=timeout)
    if not outcome.get("ok"):
        raise RuntimeError(outcome.get("error") or "claude claim alignment failed")
    data = outcome.get("data")
    if isinstance(data, list):
        raw_scores = data
    elif isinstance(data, dict):
        raw_scores = data.get("scores") or data.get("items") or []
    else:
        raw_scores = []
    if not isinstance(raw_scores, list):
        raise RuntimeError("claude claim alignment returned non-list scores")

    valid_ids = {c.get("slide_id") for c in candidates if c.get("slide_id")}
    out: list[dict] = []
    for rec in raw_scores:
        if not isinstance(rec, dict):
            continue
        sid = rec.get("slide_id")
        if sid not in valid_ids:
            continue
        try:
            score = float(rec.get("claim_alignment"))
        except Exception:
            continue
        score = max(0.0, min(1.0, score))
        out.append({
            "slide_id": sid,
            "claim_alignment": score,
            "reason": _clip_text(rec.get("reason"), 180),
        })
    if not out:
        raise RuntimeError("claude claim alignment returned no usable slide scores")
    return out


def annotate_briefs_with_claim_alignment(
    target_claim: str,
    candidate_briefs: list[dict],
    *,
    target_role: str | None = None,
    chapter_layer: str | None = None,
) -> list[dict]:
    """Convenience: in-place add `_claim_alignment` and `_alignment_reason` to each brief.

    Returns the same list (mutated). Failures keep _claim_alignment=0.5 neutral.
    """
    if not candidate_briefs:
        return candidate_briefs
    scores = score_claims_alignment_batch(
        target_claim, candidate_briefs,
        target_role=target_role, chapter_layer=chapter_layer)
    score_by_id = {s["slide_id"]: s for s in scores if s.get("slide_id")}
    for b in candidate_briefs:
        sid = b.get("slide_id")
        rec = score_by_id.get(sid, {})
        b["_claim_alignment"] = rec.get("claim_alignment", 0.5)
        b["_alignment_reason"] = rec.get("reason", "")
    return candidate_briefs


# ══════════════════════════════════════════════════════════════════════════
# v30 fix: Full library inventory loader for IDEA_ANALYSIS
#
# 目的: 让 IDEA_ANALYSIS 阶段 Claude 看到全库真实内容 (deck / section / slide
# 三层) 而不是仅 top-N filtered 子集. 这样 Claude 决定 chapter_plan 时只能
# 从库里实际有的具体工作 / 方法 / 结果里编排, 不会凭训练知识编造出库里没有
# 的东西 (如"软硬件接口协同 paper"), 从而避免下游 no_supporting_material.
# ══════════════════════════════════════════════════════════════════════════

_FULL_LIBRARY_INVENTORY_CACHE: dict | None = None
_FULL_LIBRARY_INVENTORY_CACHE_MTIME: float = 0.0    # decks-index.json 最后 mtime


def _library_material_mtime() -> float:
    """Compute a mtime signature for the material library: decks-index.json's
    mtime is the primary signal (any deck add/remove/rename updates it). This
    is a lightweight cache-invalidation check.

    Note: 只 stat decks-index.json 不 walk 全部 slide.md — 若单张 slide.md
    改内容而 decks-index.json 未动, cache 仍会返回旧值. 若要更严格, 需 walk
    整个 material 树, 但 stat 1285 个文件成本较高. 当前设计假设 slide.md 修改
    通常伴随 decks-index.json 重建 (preprocess.py 会一起写).
    """
    from pathlib import Path as _P
    p = ROOT / "data" / "resources_library" / "material" / "decks-index.json"
    try:
        return p.stat().st_mtime if p.exists() else 0.0
    except Exception:
        return 0.0


def search_global_sections_in_decks(
    deck_ids: list[str],
    keywords: list[str],
    *,
    role_hint: str | None = None,
    max_keep: int = 10,
) -> list[dict]:
    """Tier-2b mid: in the given decks, score section.md frontmatter by keyword overlap.

    Looks at section['标题'], section['章节叙事'], section['适合复用场景'].

    Returns top-N {deck_id, section_id, section_role, section_title, score}.
    """
    if not deck_ids:
        return []
    try:
        idx = library_query.load_decks_index()
    except Exception:
        return []
    decks = (idx or {}).get("decks") or []
    deck_id_to_dir = {}
    for d in decks:
        if isinstance(d, dict):
            deck_id_to_dir[d.get("deck标识")] = d.get("目录名")
    decks_root = ROOT / "data" / "resources_library" / "material" / "decks"
    scored: list[tuple[float, dict]] = []
    for did in deck_ids:
        sub = deck_id_to_dir.get(did)
        if not sub:
            continue
        deck_path = decks_root / sub
        if not deck_path.exists():
            continue
        for sec_dir in sorted(deck_path.glob("section_*")):
            if not sec_dir.is_dir():
                continue
            fm = _read_section_md_frontmatter(sec_dir)
            if not fm:
                continue
            blob = " ".join([
                fm.get("标题") or "",
                fm.get("章节叙事") or "",
                " ".join(fm.get("适合复用场景") or []),
                fm.get("章节角色") or "",
            ])
            score = _score_keyword_overlap(blob, keywords)
            sec_role = fm.get("章节角色") or ""
            if role_hint and sec_role == role_hint:
                score += 1.0
            if score > 0:
                scored.append((score, {
                    "deck_id": did,
                    "section_id": fm.get("章节标识") or "",
                    "section_role": sec_role,
                    "section_title": fm.get("标题") or "",
                    "section_narrative": (fm.get("章节叙事") or "")[:200],
                    "page_count": fm.get("页数"),
                    "section_dir": str(sec_dir),
                    "_score": round(score, 2),
                }))
    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:max_keep]]


def search_global_slides_in_sections(
    sections: list[dict],
    keywords: list[str],
    *,
    role_hint: str | None = None,
    max_keep: int = 15,
) -> list[dict]:
    """Tier-2c fine: in given sections, load slide_*.md and rank by keyword overlap.

    `sections` items must contain `section_dir` (path to section directory).
    Returns slide briefs (same shape as load_global_slide_index entries) with `_score`.
    """
    if not sections:
        return []
    out: list[tuple[float, dict]] = []
    for sec in sections:
        sec_dir = Path(sec.get("section_dir") or "")
        if not sec_dir.exists():
            continue
        deck_id = sec.get("deck_id") or ""
        section_id = sec.get("section_id") or ""
        sec_role = sec.get("section_role") or ""
        for sf in sorted(sec_dir.glob("slide_*.md")):
            brief = _parse_one_slide_md(sf, deck_id, sec.get("section_title") or "",
                                          section_id, sec_role)
            if not brief:
                continue
            blob = _slide_brief_text_blob(brief)
            score = _score_keyword_overlap(blob, keywords)
            # carry the section's score forward as a small prior
            score += float(sec.get("_score") or 0.0) * 0.2
            if score > 0:
                b2 = dict(brief)
                b2["_score"] = round(score, 2)
                out.append((score, b2))
    out.sort(key=lambda x: -x[0])
    return [item for _, item in out[:max_keep]]
