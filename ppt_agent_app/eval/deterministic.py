"""Deterministic scoring — pure Python, no LLM, reproducible.

Reads artifacts under projects/<id>/ and returns numeric scores + subscores +
raw stats. Each score is 0-100. Missing artifacts degrade gracefully (score
0 with an explanatory note in `raw.error`).

Entry point: run_all_deterministic(project_id) -> dict
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ..models import project_dir


# ---------- helpers ----------

def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _deck_id_from_resource_id(rid: str | None) -> str | None:
    """`tpl.topic.对外汇报展示.16646a0c959a.slide_01` -> deck prefix."""
    if not rid:
        return None
    if ".slide_" in rid:
        return rid.rsplit(".slide_", 1)[0]
    return rid


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _shannon_entropy_norm(counts: dict) -> float:
    """Normalised Shannon entropy in [0,1]. 0 if single bucket, 1 if uniform."""
    total = sum(counts.values())
    if total <= 0 or len(counts) <= 1:
        return 0.0
    h = 0.0
    for c in counts.values():
        if c <= 0:
            continue
        p = c / total
        h -= p * math.log(p)
    max_h = math.log(len(counts))
    return h / max_h if max_h > 0 else 0.0


def _gini(counts: list[int]) -> float:
    """Gini coefficient in [0,1]. 0 = perfectly equal, 1 = one bucket takes all."""
    n = len(counts)
    if n == 0:
        return 0.0
    s = sum(counts)
    if s <= 0:
        return 0.0
    sorted_c = sorted(counts)
    cum = 0.0
    for i, c in enumerate(sorted_c, start=1):
        cum += i * c
    return (2 * cum) / (n * s) - (n + 1) / n


def _bigram_jaccard(a: str, b: str) -> float:
    def bigrams(s: str) -> set[str]:
        s = (s or "").strip()
        if len(s) < 2:
            return set()
        return {s[i:i + 2] for i in range(len(s) - 1)}
    A, B = bigrams(a), bigrams(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


# ---------- 1. outline structure ----------

def score_outline_structure(outline: dict) -> dict:
    """Structural quality of the outline itself. Higher = better.

    Subscores (0-100):
      * section_monotonic — slides ordered by chapter_index / slide_index
      * role_diversity — normalised Shannon entropy of target_role
      * adjacent_claim_dissimilarity — 100 * (1 - mean adjacent-page bigram Jaccard)
      * arc_coverage — how many chapters have >= 1 slide (from chapter_to_slide_map)
      * field_completeness — % slides with non-empty target_claim + key_points + target_role
    """
    slides = outline.get("slides") or []
    if not slides:
        return {"score": 0, "subscores": {}, "raw": {"error": "no slides in outline.json"}}

    # monotonic order
    prev = -1
    mono_ok = 0
    for s in slides:
        idx = int(s.get("slide_index") or 0)
        if idx > prev:
            mono_ok += 1
        prev = idx
    section_monotonic = 100.0 * mono_ok / len(slides)

    # role diversity
    role_counts = Counter((s.get("target_role") or "unknown") for s in slides)
    role_diversity = 100.0 * _shannon_entropy_norm(dict(role_counts))

    # adjacent-claim dissimilarity
    claims = [(s.get("target_claim") or "") for s in slides]
    if len(claims) >= 2:
        sims = [_bigram_jaccard(claims[i], claims[i + 1]) for i in range(len(claims) - 1)]
        mean_sim = sum(sims) / len(sims) if sims else 0.0
    else:
        mean_sim = 0.0
    adjacent_claim_dissimilarity = 100.0 * (1.0 - mean_sim)

    # arc coverage — chapter_to_slide_map non-empty chapters
    ch_map = outline.get("chapter_to_slide_map") or {}
    non_empty_chapters = sum(1 for v in ch_map.values() if v)
    total_chapters = len(ch_map) if ch_map else 0
    arc_coverage = (100.0 * non_empty_chapters / total_chapters) if total_chapters else 0.0

    # field completeness
    complete = 0
    for s in slides:
        if s.get("target_claim") and s.get("key_points") and s.get("target_role"):
            complete += 1
    field_completeness = 100.0 * complete / len(slides)

    subscores = {
        "section_monotonic": round(section_monotonic, 1),
        "role_diversity": round(role_diversity, 1),
        "adjacent_claim_dissimilarity": round(adjacent_claim_dissimilarity, 1),
        "arc_coverage": round(arc_coverage, 1),
        "field_completeness": round(field_completeness, 1),
    }
    # weighted score
    score = (
        0.15 * section_monotonic
        + 0.25 * role_diversity
        + 0.25 * adjacent_claim_dissimilarity
        + 0.20 * arc_coverage
        + 0.15 * field_completeness
    )
    return {
        "score": round(_clamp(score)),
        "subscores": subscores,
        "raw": {
            "slide_count": len(slides),
            "role_counts": dict(role_counts),
            "chapter_count": total_chapters,
            "mean_adjacent_bigram_sim": round(mean_sim, 3),
        },
    }


# ---------- 2. source distribution ----------

def score_source_distribution(lineage: dict, assembly_plan: dict) -> dict:
    """How diverse are the reused source decks and section-level slots.

    Subscores (0-100):
      * distinct_deck_score — 100 * min(1, distinct_decks / target=6)
      * top_deck_share_score — 100 * (1 - top_deck_share), capped so >0.6 hurts sharply
      * deck_gini_score — 100 * (1 - gini)
      * section_deck_balance — mean Shannon entropy per section (normalised)
      * placeholder_penalty — 100 - placeholder_ratio*100 (fewer placeholders is better)
    """
    entries = lineage.get("entries") or []
    plan_slides = assembly_plan.get("slides") or []
    if not entries and not plan_slides:
        return {"score": 0, "subscores": {}, "raw": {"error": "no lineage or assembly plan"}}

    # deck usage across whole deck (prefer lineage; fallback plan)
    deck_counter: Counter[str] = Counter()
    placeholder_count = 0
    total = 0
    for e in entries:
        rid = e.get("source_resource_id")
        deck = _deck_id_from_resource_id(rid)
        action = e.get("draft_action") or ""
        total += 1
        if deck:
            deck_counter[deck] += 1
        if "placeholder" in action.lower() or not deck:
            placeholder_count += 1

    if not deck_counter and plan_slides:
        for s in plan_slides:
            rid = s.get("source_resource_id")
            deck = _deck_id_from_resource_id(rid) or s.get("deck_id")
            total += 1
            if deck:
                deck_counter[deck] += 1
            if (s.get("draft_action") or "").lower().startswith("placeholder"):
                placeholder_count += 1

    distinct_decks = len(deck_counter)
    top_deck_count = max(deck_counter.values()) if deck_counter else 0
    top_deck_share = (top_deck_count / total) if total else 0.0
    gini = _gini(list(deck_counter.values()))

    distinct_deck_score = 100.0 * min(1.0, distinct_decks / 6.0)
    # sharp penalty above 0.6
    if top_deck_share <= 0.4:
        top_deck_share_score = 100.0
    elif top_deck_share <= 0.6:
        top_deck_share_score = 100.0 - (top_deck_share - 0.4) / 0.2 * 20
    else:
        top_deck_share_score = max(0.0, 80.0 - (top_deck_share - 0.6) / 0.4 * 80)
    deck_gini_score = 100.0 * (1.0 - gini)

    # section-level deck balance
    section_deck: dict[int, Counter[str]] = defaultdict(Counter)
    for s in plan_slides:
        sec = s.get("section_id") or s.get("chapter_index") or 0
        try:
            sec_key = int(sec) if sec is not None else 0
        except (TypeError, ValueError):
            sec_key = 0
        rid = s.get("source_resource_id")
        deck = _deck_id_from_resource_id(rid) or s.get("deck_id")
        if deck:
            section_deck[sec_key][deck] += 1
    sec_entropies = [
        _shannon_entropy_norm(dict(c))
        for c in section_deck.values() if sum(c.values()) >= 2
    ]
    section_deck_balance = 100.0 * (sum(sec_entropies) / len(sec_entropies)) if sec_entropies else 100.0

    placeholder_ratio = placeholder_count / total if total else 0.0
    placeholder_penalty_score = _clamp(100.0 - placeholder_ratio * 100.0 * 2)

    subscores = {
        "distinct_deck_score": round(distinct_deck_score, 1),
        "top_deck_share_score": round(top_deck_share_score, 1),
        "deck_gini_score": round(deck_gini_score, 1),
        "section_deck_balance": round(section_deck_balance, 1),
        "placeholder_penalty_score": round(placeholder_penalty_score, 1),
    }
    score = (
        0.20 * distinct_deck_score
        + 0.25 * top_deck_share_score
        + 0.15 * deck_gini_score
        + 0.20 * section_deck_balance
        + 0.20 * placeholder_penalty_score
    )
    return {
        "score": round(_clamp(score)),
        "subscores": subscores,
        "raw": {
            "total_slides": total,
            "distinct_decks": distinct_decks,
            "top_deck_share": round(top_deck_share, 3),
            "top_deck_id": max(deck_counter, key=deck_counter.get) if deck_counter else None,
            "deck_counts": dict(deck_counter.most_common(10)),
            "section_counts": {str(k): dict(v) for k, v in section_deck.items()},
            "placeholder_count": placeholder_count,
        },
    }


# ---------- 3. retrieval match ----------

def score_retrieval_match(outline: dict, slide_matches: dict) -> dict:
    """How well the retrieved candidates align with the target claim per slide.

    Uses the already-computed `_claim_alignment` and `rank_score` in
    outline.slides[*].source_resource_ids[0] (rank-1) — this is a deterministic
    self-report from the outline stage. Codex independently rescores in the
    retrieval_match_review skill.

    Subscores (0-100):
      * mean_claim_alignment — mean of rank-1 _claim_alignment * 100
      * mean_rank1_score — mean of rank-1 rank_score, rescaled from 0-10 to 0-100
      * high_confidence_ratio — % slides where matches.confidence=='high'
      * candidate_coverage — 1 - % slides with 0 candidates
      * low_match_penalty — 1 - % slides with rank-1 score < 3.5
    """
    slides = outline.get("slides") or []
    if not slides:
        return {"score": 0, "subscores": {}, "raw": {"error": "no outline slides"}}

    matches_by_idx: dict[int, dict] = {}
    for m in (slide_matches.get("slide_matches") or []):
        try:
            idx = int(m.get("target_slide_index"))
            matches_by_idx[idx] = m
        except (TypeError, ValueError):
            continue

    alignments: list[float] = []
    rank_scores: list[float] = []
    high_conf = 0
    no_candidate = 0
    low_match = 0
    per_slide: list[dict] = []

    for s in slides:
        try:
            sidx = int(s.get("slide_index") or 0)
        except (TypeError, ValueError):
            sidx = 0
        sources = s.get("source_resource_ids") or []
        rank1 = sources[0] if sources else None
        m = matches_by_idx.get(sidx, {})
        candidates = m.get("candidates") or []
        rank1_match = candidates[0] if candidates else None

        if not rank1 and not rank1_match:
            no_candidate += 1
            per_slide.append({"slide_index": sidx, "status": "no_candidate"})
            continue

        align = rank1.get("_claim_alignment") if rank1 else None
        rscore = rank1.get("rank_score") if rank1 else (rank1_match.get("score") if rank1_match else None)
        conf = rank1_match.get("confidence") if rank1_match else None

        if align is not None:
            try:
                alignments.append(float(align))
            except (TypeError, ValueError):
                pass
        if rscore is not None:
            try:
                rs = float(rscore)
                rank_scores.append(rs)
                if rs < 3.5:
                    low_match += 1
            except (TypeError, ValueError):
                pass
        if conf == "high":
            high_conf += 1

        per_slide.append({
            "slide_index": sidx,
            "claim_alignment": align,
            "rank_score": rscore,
            "confidence": conf,
        })

    slide_n = len(slides)
    mean_align = (sum(alignments) / len(alignments)) if alignments else 0.0
    mean_rank_score = (sum(rank_scores) / len(rank_scores)) if rank_scores else 0.0

    mean_claim_alignment = 100.0 * mean_align
    # rank_score is on a 0-10 scale in outline.json
    mean_rank1_score = 10.0 * mean_rank_score
    high_confidence_ratio = 100.0 * high_conf / slide_n
    candidate_coverage = 100.0 * (1.0 - no_candidate / slide_n)
    low_match_penalty = 100.0 * (1.0 - low_match / slide_n)

    subscores = {
        "mean_claim_alignment": round(mean_claim_alignment, 1),
        "mean_rank1_score": round(mean_rank1_score, 1),
        "high_confidence_ratio": round(high_confidence_ratio, 1),
        "candidate_coverage": round(candidate_coverage, 1),
        "low_match_penalty": round(low_match_penalty, 1),
    }
    score = (
        0.35 * mean_claim_alignment
        + 0.25 * mean_rank1_score
        + 0.15 * high_confidence_ratio
        + 0.15 * candidate_coverage
        + 0.10 * low_match_penalty
    )
    return {
        "score": round(_clamp(score)),
        "subscores": subscores,
        "raw": {
            "slide_count": slide_n,
            "no_candidate_count": no_candidate,
            "low_match_count": low_match,
            "high_confidence_count": high_conf,
            "mean_alignment_raw": round(mean_align, 3),
            "mean_rank_score_raw": round(mean_rank_score, 3),
            "per_slide_sample": per_slide[:8],
        },
    }


# ---------- 4. timing ----------

def score_timing(timings: list[dict]) -> dict:
    """Wall-clock cost per stage. Non-punitive by default — just a signal.

    Subscores (0-100):
      * total_wall_score — 100 - min(total_seconds/1800, 1)*40 (30min = 60pts)
      * bottleneck_share_score — 100*(1 - bottleneck_share) (one stage < 40% ideal)
      * completed_stages_score — 100 * % stages with duration_s > 0

    Interpretation: high score means "fast and balanced". Absolute wall-clock
    limits are project-specific; treat as a comparator between runs.
    """
    if not timings:
        return {"score": None, "subscores": {}, "raw": {"error": "no stage-timings.jsonl"}}

    per_stage: dict[str, float] = {}
    ok_stages = 0
    for t in timings:
        stage = t.get("stage") or "UNKNOWN"
        d = float(t.get("duration_s") or 0.0)
        per_stage[stage] = per_stage.get(stage, 0.0) + d
        if d > 0:
            ok_stages += 1

    total = sum(per_stage.values())
    if total <= 0:
        return {"score": None, "subscores": {}, "raw": {"error": "zero total duration", "per_stage": per_stage}}

    bottleneck_stage = max(per_stage, key=per_stage.get)
    bottleneck_s = per_stage[bottleneck_stage]
    bottleneck_share = bottleneck_s / total

    # 30min-neutral, 60min = 0 score; anything faster = better
    total_wall_score = _clamp(100.0 - (total / 1800.0) * 40.0)
    bottleneck_share_score = _clamp(100.0 * (1.0 - bottleneck_share) + 20.0, 0, 100)
    completed_stages_score = 100.0 * ok_stages / len(timings) if timings else 0.0

    subscores = {
        "total_wall_score": round(total_wall_score, 1),
        "bottleneck_share_score": round(bottleneck_share_score, 1),
        "completed_stages_score": round(completed_stages_score, 1),
    }
    score = (
        0.5 * total_wall_score
        + 0.3 * bottleneck_share_score
        + 0.2 * completed_stages_score
    )
    return {
        "score": round(_clamp(score)),
        "subscores": subscores,
        "raw": {
            "total_wall_s": round(total, 1),
            "bottleneck_stage": bottleneck_stage,
            "bottleneck_share": round(bottleneck_share, 3),
            "per_stage_s": {k: round(v, 1) for k, v in sorted(per_stage.items(), key=lambda kv: -kv[1])},
            "event_count": len(timings),
        },
    }


# ---------- orchestrator ----------

def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def run_all_deterministic(project_id: str) -> dict:
    """Read all artifacts under projects/<id>/ and compute all deterministic scores."""
    pdir = project_dir(project_id)
    outline = _read_json(pdir / "outline.json", {}) or {}
    slide_matches = _read_json(pdir / "slide-matches.json", {}) or {}
    lineage = _read_json(pdir / "draft-source-lineage.json", {}) or {}
    assembly_plan = _read_json(pdir / "draft-assembly-plan.json", {}) or {}
    timings = _read_jsonl(pdir / "stage-timings.jsonl")

    return {
        "outline_structure": score_outline_structure(outline),
        "source_distribution": score_source_distribution(lineage, assembly_plan),
        "retrieval_match": score_retrieval_match(outline, slide_matches),
        "timing": score_timing(timings),
    }
