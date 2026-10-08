"""Eval CLI — one-shot deterministic + codex-graded scoring of a project.

Usage:
    python3 -m ppt_agent_app.eval <project_id> [--skip-codex]
                                                 [--skill outline_logic|retrieval_match|draft_coherence|all]
                                                 [--out <path>]

Writes `projects/<id>/eval-report.json`.

Design:
- Deterministic side is always computed (fast, ~seconds).
- Codex side is opt-out (`--skip-codex`) or partial (`--skill X`).
- Each codex skill is invoked with a minimal payload tailored to its remit;
  we deliberately shrink the input so codex sees only what it needs to judge.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..models import project_dir
from . import run_all_deterministic


SKILLS = {
    "outline_logic": {
        "skill_path": "skills/review/structure_review.md",
        "timeout": 600,
    },
    "retrieval_match": {
        "skill_path": "skills/review/reuse_review.md",
        "timeout": 900,
    },
    "draft_coherence": {
        "skill_path": "skills/review/narrative_review.md",
        "timeout": 900,
    },
}


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _git_sha() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
        return out or None
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def _slim_outline_for_codex(outline: dict) -> dict:
    """Keep only what the outline_logic skill actually needs."""
    slides = outline.get("slides") or []
    slim = []
    for s in slides:
        slim.append({
            "slide_index": s.get("slide_index"),
            "chapter_index": s.get("chapter_index"),
            "target_role": s.get("target_role"),
            "target_title": s.get("target_title"),
            "target_claim": s.get("target_claim"),
            "key_points": (s.get("key_points") or [])[:6],
        })
    return {
        "topic": outline.get("topic"),
        "language": outline.get("language"),
        "slide_count": outline.get("slide_count"),
        "chapter_to_slide_map": outline.get("chapter_to_slide_map"),
        "selected_narrative_arc": outline.get("selected_narrative_arc"),
        "identity": {
            "anchor_terms": (outline.get("identity") or {}).get("anchor_terms"),
            "topic_tags": (outline.get("identity") or {}).get("topic_tags"),
        },
        "slides": slim,
    }


def _slim_retrieval_input(outline: dict, slide_matches: dict, deck_md_root: Path) -> dict:
    """Attach rank-1 candidate actual markdown snippet for codex to compare against."""
    slides_by_idx = {}
    for s in outline.get("slides") or []:
        try:
            slides_by_idx[int(s.get("slide_index") or 0)] = s
        except (TypeError, ValueError):
            continue

    # Build deck_id -> dir lookup from decks-index.json
    idx = _read_json(deck_md_root / "decks-index.json", {}) or {}
    deck_lookup = {}
    for d in (idx.get("decks") or []):
        deck_lookup[d.get("deck标识")] = d.get("目录名")

    def _find_slide_md(resource_id: str) -> str | None:
        if not resource_id or ".slide_" not in resource_id:
            return None
        deck_id, tail = resource_id.rsplit(".slide_", 1)
        dir_name = deck_lookup.get(deck_id)
        if not dir_name:
            return None
        deck_dir = deck_md_root / "decks" / dir_name
        # Slide files live under section_XX_*/slide_YY.md — scan
        try:
            for sec_dir in deck_dir.iterdir():
                if not sec_dir.is_dir():
                    continue
                candidate = sec_dir / f"slide_{tail}.md"
                if candidate.exists():
                    text = candidate.read_text(encoding="utf-8", errors="ignore")
                    # Return first ~1500 chars to bound codex context
                    return text[:1500]
        except OSError:
            return None
        return None

    slim_matches = []
    for m in (slide_matches.get("slide_matches") or []):
        try:
            sidx = int(m.get("target_slide_index"))
        except (TypeError, ValueError):
            continue
        source_slide = slides_by_idx.get(sidx, {})
        candidates = m.get("candidates") or []
        rank1 = candidates[0] if candidates else None
        rank1_md = _find_slide_md(rank1.get("resource_id")) if rank1 else None

        slim_matches.append({
            "target_slide_index": sidx,
            "target_role": m.get("target_role"),
            "target_title": m.get("target_title"),
            "target_claim": m.get("target_claim"),
            "target_key_points": (source_slide.get("key_points") or [])[:6],
            "rank1": {
                "resource_id": rank1.get("resource_id") if rank1 else None,
                "deck_id": rank1.get("deck_id") if rank1 else None,
                "score": rank1.get("score") if rank1 else None,
                "confidence": rank1.get("confidence") if rank1 else None,
                "match_reasons": (rank1.get("match_reasons") or [])[:3] if rank1 else [],
                "source_content_excerpt": rank1_md,
            } if rank1 else None,
        })
    return {"slide_matches": slim_matches}


def _slim_draft_for_codex(project_id: str, outline: dict) -> dict:
    """Bundle draft-manuscript + speaker-notes samples for coherence review."""
    pdir = project_dir(project_id)
    manuscript = ""
    notes = ""
    m_path = pdir / "draft-manuscript.md"
    n_path = pdir / "speaker-notes.md"
    if m_path.exists():
        manuscript = m_path.read_text(encoding="utf-8", errors="ignore")
    if n_path.exists():
        notes = n_path.read_text(encoding="utf-8", errors="ignore")

    # Cap total; if huge, keep first + last portions so codex sees the whole arc
    def _cap(text: str, budget: int) -> str:
        if len(text) <= budget:
            return text
        half = budget // 2
        return text[:half] + f"\n\n[... truncated {len(text) - budget} chars ...]\n\n" + text[-half:]

    return {
        "topic": outline.get("topic"),
        "slide_count": outline.get("slide_count"),
        "chapter_to_slide_map": outline.get("chapter_to_slide_map"),
        "draft_manuscript_excerpt": _cap(manuscript, 12000),
        "speaker_notes_excerpt": _cap(notes, 18000),
    }


def _run_codex_skill(name: str, project_id: str, payload: dict) -> dict:
    from .. import codex_cli

    spec = SKILLS[name]
    prompt = (
        f"Project: {project_id}\n"
        f"Eval skill: {name}\n\n"
        "Payload (JSON):\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "Follow the skill instructions above. Return strict JSON only per the schema."
    )
    result = codex_cli.call_codex_json(
        prompt,
        skill=[spec["skill_path"]],
        timeout=spec["timeout"],
    )
    if not result.get("ok"):
        return {
            "ok": False,
            "error": result.get("error"),
            "raw_excerpt": (result.get("raw_excerpt") or "")[:400],
        }
    return {"ok": True, "data": result.get("data")}


def _weights() -> dict:
    return _read_json(Path(__file__).parent / "weights.json", {}) or {}


def _weighted_avg(scores: dict, weights: dict) -> int | None:
    if not scores or not weights:
        return None
    num = 0.0
    denom = 0.0
    for k, w in weights.items():
        v = scores.get(k)
        if isinstance(v, (int, float)):
            num += float(v) * float(w)
            denom += float(w)
    if denom <= 0:
        return None
    return round(num / denom)


def build_report(
    project_id: str,
    *,
    skip_codex: bool = False,
    only_skill: str | None = None,
) -> dict:
    weights = _weights()
    pdir = project_dir(project_id)

    deterministic = run_all_deterministic(project_id)

    codex_results: dict[str, Any] = {}
    if not skip_codex:
        outline = _read_json(pdir / "outline.json", {}) or {}
        slide_matches = _read_json(pdir / "slide-matches.json", {}) or {}
        deck_md_root = Path(__file__).resolve().parents[2] / "data" / "resources_library" / "material"

        skills_to_run = list(SKILLS.keys()) if not only_skill or only_skill == "all" else [only_skill]

        for name in skills_to_run:
            if name not in SKILLS:
                codex_results[name] = {"ok": False, "error": f"unknown skill: {name}"}
                continue
            if name == "outline_logic":
                payload = _slim_outline_for_codex(outline)
            elif name == "retrieval_match":
                payload = _slim_retrieval_input(outline, slide_matches, deck_md_root)
            elif name == "draft_coherence":
                payload = _slim_draft_for_codex(project_id, outline)
            else:
                payload = {}
            print(f"[eval] running codex skill: {name} ...", flush=True)
            codex_results[name] = _run_codex_skill(name, project_id, payload)

    # aggregate
    det_scores = {k: v.get("score") for k, v in deterministic.items()}
    det_weighted = _weighted_avg(det_scores, weights.get("deterministic") or {})

    codex_scores: dict[str, Any] = {}
    for name, res in codex_results.items():
        if res.get("ok"):
            d = res.get("data") or {}
            codex_scores[name] = d.get("score")
    codex_weighted = _weighted_avg(codex_scores, weights.get("codex") or {}) if codex_scores else None

    overall_weights = weights.get("overall") or {}
    if det_weighted is not None and codex_weighted is not None:
        overall = _weighted_avg(
            {"deterministic": det_weighted, "codex": codex_weighted},
            overall_weights,
        )
    elif det_weighted is not None:
        overall = det_weighted
    elif codex_weighted is not None:
        overall = codex_weighted
    else:
        overall = None

    return {
        "schema_version": "1.0",
        "project_id": project_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "deterministic": deterministic,
        "codex": codex_results,
        "aggregate": {
            "deterministic_scores": det_scores,
            "codex_scores": codex_scores,
            "deterministic_weighted": det_weighted,
            "codex_weighted": codex_weighted,
            "overall": overall,
            "weights_used": weights,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ppt_agent_app.eval")
    parser.add_argument("project_id")
    parser.add_argument("--skip-codex", action="store_true",
                        help="Only compute deterministic scores")
    parser.add_argument("--skill", choices=list(SKILLS.keys()) + ["all"],
                        default="all", help="Which codex skill to run")
    parser.add_argument("--out", type=str, default=None,
                        help="Output path (default: projects/<id>/eval-report.json)")
    args = parser.parse_args(argv)

    report = build_report(
        args.project_id,
        skip_codex=args.skip_codex,
        only_skill=None if args.skill == "all" else args.skill,
    )

    out_path = Path(args.out) if args.out else (project_dir(args.project_id) / "eval-report.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # print summary
    print(f"\n=== eval-report written to {out_path} ===")
    agg = report["aggregate"]
    print(f"deterministic scores: {agg['deterministic_scores']}")
    print(f"codex scores:         {agg['codex_scores']}")
    print(f"deterministic weighted: {agg['deterministic_weighted']}")
    print(f"codex weighted:         {agg['codex_weighted']}")
    print(f"overall:                {agg['overall']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
