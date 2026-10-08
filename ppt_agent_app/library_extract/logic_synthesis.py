"""Logic Synthesis — build meta-patterns (A) + enrich concrete patterns (C).

Prereqs:
  - data/resources_library/logic/deck_level/<id>.json exists
  - data/resources_library/logic/section_level/<id>.json exists
  - data/resources_library/logic/INDEX.json exists

Outputs:
  - data/resources_library/logic/meta/<id>.md + <id>.json     (A output)
  - Each existing deck_level/*.json + section_level/*.json    (C: merged in-place under `enrichment`)
  - data/resources_library/logic/INDEX.json                   (updated: meta section + enrichment flags)

Skills used:
  - skills/resources_library/logic/meta_synthesis.md   (A: 1 call, slim 186 patterns → 5-10 meta)
  - skills/resources_library/logic/pattern_enrich.md   (C: parallel per-pattern enrichment)
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ..models import ROOT
from .. import claude_cli

LOGIC_ROOT = ROOT / "data" / "resources_library" / "logic"
META_DIR = LOGIC_ROOT / "meta"
META_JSON = LOGIC_ROOT / "logic_meta_patterns.json"

META_SKILL = "skills/resources_library/logic/meta_synthesis.md"
ENRICH_SKILL = "skills/resources_library/logic/pattern_enrich.md"

META_TIMEOUT = 1800    # 30 min for one big meta call
ENRICH_TIMEOUT = 900   # 15 min per pattern (should be <5 min in practice)


# ─────────────────────────────────────────────────────────────────────────────
# A — Meta-pattern synthesis
# ─────────────────────────────────────────────────────────────────────────────


def _slim_pattern(p: dict, layer: str, *, minimal: bool = False) -> dict:
    """Trim a pattern for meta-synthesis input — drop carriers + heavy nested fields.

    Kept: id / title / applicable_when (report_type + chapter_role only) /
          applicable_summary / anti_patterns / archetype_names (from abstract_node_sequence) /
          source_count / confidence.
    Dropped: full carriers, per-node purpose/count/position, page_transitions detail —
             Claude infers structure from `applicable_summary` + archetype_names.

    `minimal=True` further drops applicable_summary + scenario_keywords + anti_patterns
    for size-critical calls (section_level meta 180 patterns risks 141 KB+ → ZlibError).
    """
    aw = p.get("applicable_when") or {}
    seq = p.get("abstract_node_sequence") or []
    archetype_names = []
    for node in seq:
        if isinstance(node, dict):
            archetype_names.append(node.get("role") or node.get("archetype") or "?")
    out = {
        "id": p.get("id"),
        "layer": layer,
        "title": p.get("title"),
        "applicable_when": {
            "report_type": aw.get("report_type"),
            "chapter_role": aw.get("chapter_role"),
        },
        "archetype_sequence": archetype_names,
        "source_count": p.get("source_count") or len(p.get("carriers") or []),
        "confidence": p.get("confidence"),
    }
    if not minimal:
        out["applicable_when"]["scenario_keywords"] = aw.get("scenario_keywords")
        out["applicable_summary"] = p.get("applicable_summary")
        out["anti_patterns"] = p.get("anti_patterns") or []
    return out


def load_all_slim_patterns(*, layer_filter: str | None = None,
                             minimal: bool = False) -> list[dict]:
    """Read every pattern JSON under deck_level/ + section_level/ and return slim form."""
    out: list[dict] = []
    for layer in ("deck_level", "section_level"):
        if layer_filter and layer != layer_filter:
            continue
        d = LOGIC_ROOT / layer
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                out.append(_slim_pattern(data, layer, minimal=minimal))
            except Exception as e:
                print(f"    skip {p.name}: {e}", flush=True)
    return out


def _run_one_meta_call(slim: list[dict], label: str, minimal_hint: bool = False) -> dict:
    """One meta-synthesis Claude call. Returns {ok, data|error}."""
    payload = {"concrete_patterns": slim}
    payload_json = json.dumps(payload, ensure_ascii=False)
    print(f"  [{label}] input size: {len(payload_json)/1024:.0f} KB "
          f"({len(slim)} patterns)", flush=True)
    (LOGIC_ROOT / ".batches" / f"meta_{label}_input.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    extra_hint = ""
    if minimal_hint:
        extra_hint = ("NOTE: input is trimmed (no applicable_summary or scenario_keywords) — "
                       "use `id`, `title`, `archetype_sequence`, and `applicable_when` to "
                       "cluster patterns by narrative intent.\n\n")
    prompt = (
        f"meta_synthesis [{label}]: extract 3-8 universal narrative meta-patterns "
        "from these concrete patterns, per skill rules. Output strict JSON only.\n\n"
        + extra_hint
        + "INPUT:\n" + payload_json
    )
    t = time.time()
    result = claude_cli.call_claude_json(prompt, skill=[META_SKILL], timeout=META_TIMEOUT)
    elapsed = time.time() - t
    if not (result.get("ok") and isinstance(result.get("data"), dict)):
        err = (result.get("error") or "unknown")[:400]
        print(f"  [{label}] FAILED in {elapsed:.0f}s: {err}", flush=True)
        raw = result.get("raw_excerpt") or ""
        if raw:
            (LOGIC_ROOT / ".batches" / f"meta_{label}_FAIL_raw.txt").write_text(
                raw, encoding="utf-8")
        return {"ok": False, "error": err, "elapsed": elapsed}
    data = result["data"]
    print(f"  [{label}] OK in {elapsed:.0f}s, {len(data.get('meta_patterns') or [])} metas",
          flush=True)
    return {"ok": True, "data": data, "elapsed": elapsed}


def run_meta_synthesis(*, dry_run: bool = False) -> dict:
    """Phase A — split into 2 calls (deck_level + section_level) to avoid 141 KB → ZlibError.

    Each layer produces its own meta-patterns. Then merged into logic_meta_patterns.json.
    """
    print("=== Phase A: meta-pattern synthesis (2 sub-calls) ===", flush=True)
    META_DIR.mkdir(parents=True, exist_ok=True)
    (LOGIC_ROOT / ".batches").mkdir(parents=True, exist_ok=True)

    # Split — deck_level uses richer input (only 6 patterns, tiny)
    # section_level uses minimal input (180 patterns, ~50 KB after trim)
    deck_slim = load_all_slim_patterns(layer_filter="deck_level", minimal=False)
    section_slim = load_all_slim_patterns(layer_filter="section_level", minimal=True)
    print(f"  deck_level: {len(deck_slim)} patterns", flush=True)
    print(f"  section_level: {len(section_slim)} patterns (minimal slim)", flush=True)
    if dry_run:
        return {"ok": True, "dry_run": True}

    all_metas: list[dict] = []
    all_coverage_deck: list[str] = []
    all_coverage_section: list[str] = []

    if deck_slim:
        r = _run_one_meta_call(deck_slim, "deck_level", minimal_hint=False)
        if r.get("ok"):
            data = r["data"]
            metas = data.get("meta_patterns") or []
            all_metas.extend(metas)
            cov = data.get("coverage") or {}
            all_coverage_deck.extend(cov.get("instantiated_deck_level_ids") or [])

    if section_slim:
        r = _run_one_meta_call(section_slim, "section_level", minimal_hint=True)
        if r.get("ok"):
            data = r["data"]
            metas = data.get("meta_patterns") or []
            all_metas.extend(metas)
            cov = data.get("coverage") or {}
            all_coverage_section.extend(cov.get("instantiated_section_level_ids") or [])

    if not all_metas:
        return {"ok": False, "error": "both meta calls failed"}

    # Save aggregate + per-meta files
    aggregate = {
        "meta_patterns": all_metas,
        "coverage": {
            "instantiated_deck_level_ids": all_coverage_deck,
            "instantiated_section_level_ids": all_coverage_section,
        },
        "extraction_notes": f"2 sub-calls: deck_level({len(deck_slim)}) + section_level({len(section_slim)}), "
                             f"produced {len(all_metas)} total meta-patterns",
    }
    META_JSON.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
    for m in all_metas:
        mid = m.get("id")
        if not mid:
            continue
        (META_DIR / f"{mid}.json").write_text(
            json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        (META_DIR / f"{mid}.md").write_text(_meta_to_md(m), encoding="utf-8")

    print(f"  wrote {len(all_metas)} meta patterns to {META_DIR}", flush=True)
    return {"ok": True, "meta_count": len(all_metas)}


def _meta_to_md(m: dict) -> str:
    """Render one meta-pattern as markdown."""
    fm = [
        "---",
        f"id: {m.get('id')}",
        "layer: meta",
        f"title: {m.get('title')}",
        f"narrative_purpose: {m.get('narrative_purpose')}",
        f"target_audience_types: {json.dumps(m.get('target_audience_types') or [], ensure_ascii=False)}",
        f"instantiations_count: {len(m.get('instantiations') or [])}",
        f"generated_at: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        "---",
        "",
        f"# {m.get('title')}",
        "",
        f"**ID**: `{m.get('id')}`",
        f"**Narrative purpose**: {m.get('narrative_purpose')}",
        "",
        "## Trigger signals",
    ]
    for s in (m.get("trigger_signals") or []):
        fm.append(f"- {s}")
    fm.append("")
    fm.append("## Core task sequence")
    fm.append("```json")
    fm.append(json.dumps(m.get("core_task_sequence") or [], ensure_ascii=False, indent=2))
    fm.append("```")
    fm.append("")
    fm.append("## Invariant principles")
    for p in (m.get("invariant_principles") or []):
        fm.append(f"- {p}")
    fm.append("")
    fm.append("## Swappable dimensions")
    for s in (m.get("swappable_dimensions") or []):
        fm.append(f"- {s}")
    fm.append("")
    fm.append(f"## Info density arc\n\n{m.get('info_density_arc')}")
    fm.append("")
    fm.append(f"## Instantiations ({len(m.get('instantiations') or [])})")
    for i in (m.get("instantiations") or []):
        fm.append(f"- `{i}`")
    fm.append("")
    fm.append("## Anti-patterns")
    for a in (m.get("anti_patterns") or []):
        fm.append(f"- {a}")
    return "\n".join(fm) + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# C — Per-pattern enrichment
# ─────────────────────────────────────────────────────────────────────────────


def _enrich_one(pattern_path: Path, layer: str, timeout: int,
                 *, max_retries: int = 2) -> dict:
    """Read one pattern → call Claude → merge enrichment back into pattern JSON.

    Retries on transient CLI errors (ZlibError / JSON decode / empty stdout).
    """
    label = f"enrich_{layer}_{pattern_path.stem}"
    try:
        pattern = json.loads(pattern_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "path": str(pattern_path), "error": f"read: {e}"}

    if "enrichment" in pattern and pattern["enrichment"]:
        return {"ok": True, "path": str(pattern_path), "skipped": True}

    payload = {"pattern": {"layer": layer, **pattern}}
    payload_json = json.dumps(payload, ensure_ascii=False)
    base_prompt = (
        f"{label}: enrich this {layer} pattern with reasoning-level abstract fields, "
        "per skill rules. Output strict JSON only.\n\nINPUT:\n" + payload_json
    )
    last_err = None
    for attempt in range(1 + max_retries):
        prompt = base_prompt
        if attempt > 0:
            correction = (
                f"⚠️ ATTEMPT {attempt+1}/{max_retries+1}: prior attempt errored "
                f"({last_err[:150] if last_err else 'unknown'}). Ensure output is "
                f"strict JSON with exactly `pattern_id` + `layer` + `enrichment` "
                f"top-level keys. No prose. First char must be `{{`.\n\n"
            )
            prompt = correction + base_prompt
        t = time.time()
        result = claude_cli.call_claude_json(prompt, skill=[ENRICH_SKILL], timeout=timeout)
        elapsed = time.time() - t
        if result.get("ok") and isinstance(result.get("data"), dict):
            data = result["data"]
            enrichment = data.get("enrichment")
            if isinstance(enrichment, dict):
                pattern["enrichment"] = enrichment
                pattern_path.write_text(
                    json.dumps(pattern, ensure_ascii=False, indent=2), encoding="utf-8")
                md_path = pattern_path.with_suffix(".md")
                if md_path.exists():
                    _append_enrichment_md(md_path, enrichment)
                return {"ok": True, "path": str(pattern_path),
                        "keys": list(enrichment.keys()), "elapsed": elapsed,
                        "attempts": attempt + 1}
            last_err = "no enrichment dict in output"
        else:
            last_err = (result.get("error") or "unknown")[:200]

    return {"ok": False, "path": str(pattern_path),
            "error": last_err, "attempts": 1 + max_retries}


def _append_enrichment_md(md_path: Path, enrichment: dict) -> None:
    text = md_path.read_text(encoding="utf-8")
    if "## Enrichment (reasoning-level)" in text:
        return  # already appended
    add = ["", "## Enrichment (reasoning-level)", ""]
    if "reasoning_level_summary" in enrichment:
        add.append(f"**Summary**: {enrichment['reasoning_level_summary']}")
        add.append("")
    add.append("```json")
    add.append(json.dumps(enrichment, ensure_ascii=False, indent=2))
    add.append("```")
    md_path.write_text(text + "\n" + "\n".join(add) + "\n", encoding="utf-8")


def run_enrichment(*, parallel_workers: int = 4, timeout: int = ENRICH_TIMEOUT,
                    layer_filter: str | None = None,
                    dry_run: bool = False, limit: int | None = None) -> dict:
    """Phase C — enrich every existing pattern in parallel."""
    print(f"\n=== Phase C: per-pattern enrichment ({parallel_workers} workers) ===",
          flush=True)
    tasks: list[tuple[Path, str]] = []
    for layer in ("deck_level", "section_level"):
        if layer_filter and layer != layer_filter:
            continue
        d = LOGIC_ROOT / layer
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            tasks.append((p, layer))
    if limit:
        tasks = tasks[:limit]
    print(f"  {len(tasks)} pattern files to enrich", flush=True)
    if dry_run:
        for p, l in tasks[:5]:
            print(f"    would enrich [{l}] {p.name}")
        return {"ok": True, "dry_run": True, "count": len(tasks)}

    ok = 0
    fail = 0
    skipped = 0
    t_all = time.time()
    with ThreadPoolExecutor(max_workers=parallel_workers) as pool:
        futures = {pool.submit(_enrich_one, p, l, timeout): (p, l) for p, l in tasks}
        for i, fut in enumerate(as_completed(futures), 1):
            r = fut.result()
            if r.get("skipped"):
                skipped += 1
                if i % 20 == 0:
                    print(f"  [{i}/{len(tasks)}] progress ok={ok} skipped={skipped} fail={fail}",
                          flush=True)
                continue
            if r.get("ok"):
                ok += 1
                print(f"  [{i}/{len(tasks)}] OK {Path(r['path']).stem} "
                      f"({r.get('elapsed', 0):.0f}s)", flush=True)
            else:
                fail += 1
                print(f"  [{i}/{len(tasks)}] FAIL {Path(r['path']).stem}: "
                      f"{r.get('error', 'unknown')[:120]}", flush=True)
    elapsed = time.time() - t_all
    print(f"\n  enrichment done in {elapsed:.0f}s: "
          f"ok={ok} skipped={skipped} fail={fail}", flush=True)
    return {"ok": True, "enriched": ok, "skipped": skipped, "failed": fail,
            "elapsed": elapsed}


# ─────────────────────────────────────────────────────────────────────────────
# INDEX update — add meta layer + enrichment flags
# ─────────────────────────────────────────────────────────────────────────────


def update_index() -> Path:
    """Rebuild INDEX.json to include meta entries + enrichment flags."""
    idx_path = LOGIC_ROOT / "INDEX.json"
    entries: list[dict] = []
    by_layer = {"meta": 0, "deck_level": 0, "section_level": 0}
    by_confidence: dict[str, int] = {}
    n_enriched = {"deck_level": 0, "section_level": 0}

    for layer in ("meta", "deck_level", "section_level"):
        d = LOGIC_ROOT / layer
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            enriched = "enrichment" in data and bool(data.get("enrichment"))
            if enriched and layer in n_enriched:
                n_enriched[layer] += 1
            conf = data.get("confidence") or "n/a"
            entries.append({
                "id": data.get("id"),
                "layer": layer,
                "title": data.get("title"),
                "confidence": conf,
                "source_count": data.get("source_count"),
                "enriched": enriched,
                "path": str(p.relative_to(LOGIC_ROOT)),
            })
            by_layer[layer] = by_layer.get(layer, 0) + 1
            by_confidence[conf] = by_confidence.get(conf, 0) + 1

    idx = {
        "schema_version": "1.1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "patterns_count": len(entries),
        "by_layer": by_layer,
        "by_confidence": by_confidence,
        "enriched_counts": n_enriched,
        "entries": entries,
    }
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    return idx_path


# ─────────────────────────────────────────────────────────────────────────────
# Entry
# ─────────────────────────────────────────────────────────────────────────────


def run(args) -> dict:
    """Programmatic entry — args = argparse.Namespace."""
    stage = getattr(args, "stage", "both")
    parallel = getattr(args, "parallel_workers", 4)
    dry_run = getattr(args, "dry_run", False)
    limit = getattr(args, "limit", None)
    layer_filter = getattr(args, "layer", None)

    results: dict = {"stage": stage}
    if stage in ("meta", "both"):
        results["meta"] = run_meta_synthesis(dry_run=dry_run)
        if not results["meta"].get("ok") and stage == "meta":
            return results
    if stage in ("enrich", "both"):
        results["enrich"] = run_enrichment(
            parallel_workers=parallel, dry_run=dry_run,
            limit=limit, layer_filter=layer_filter,
        )
    if not dry_run:
        idx = update_index()
        results["index"] = str(idx)
        print(f"\n  INDEX updated: {idx}", flush=True)
    return results


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Logic synthesis (A meta + C enrich)")
    p.add_argument("--stage", choices=["meta", "enrich", "both"], default="both")
    p.add_argument("--parallel-workers", type=int, default=4)
    p.add_argument("--layer", choices=["deck_level", "section_level"],
                   help="Restrict enrichment to one layer (default both)")
    p.add_argument("--limit", type=int, help="Only enrich first N patterns (smoke)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    result = run(args)
    print(f"\nresult: {json.dumps({k: v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if kk != 'coverage'} for k, v in result.items()}, ensure_ascii=False)[:500]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
