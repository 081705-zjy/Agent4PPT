"""v17 Preprocess CLI.

Manages the 3 read-only resource libraries used by the main pipeline:
  - data/resources_library/material/   (deck briefs from templates/)
  - data/resources_library/logic/      (183 patterns: deck_level + section_level)
  - data/resources_library/rule/       (117 rules: logic_story + page_specific)

These are BAKED IN at deploy time and consumed read-only by OUTLINE stage.
Not part of the per-project pipeline.

Usage:
  python3 -m ppt_agent_app.preprocess status
    Check 3 libs integrity.

  python3 -m ppt_agent_app.preprocess import-all [--only <pptx-path> ...] [--force]
    Run ppt-master importer on every templates/**.pptx (or the paths in
    `--only`), producing data/resources_library/material/imports/<deck_id>/.

  python3 -m ppt_agent_app.preprocess build-all [--only <deck_id> ...] [--force]
    Run the 5-skill Claude brief pipeline on every deck under imports/
    (or the deck_ids in `--only`), producing decks/<dir>/{deck,section,slide}.md
    trees.

  python3 -m ppt_agent_app.preprocess logic-build [--layer deck_level|section_level|both]
                                                    [--batch-size 4] [--dry-run]
    Extract deck_level + section_level logic patterns via Claude, writing to
    data/resources_library/logic/{deck_level,section_level}/{<pattern_id>.md,.json}
    + INDEX.json.

  python3 -m ppt_agent_app.preprocess rule-build [--stats-only | --claude-only]
                                                   [--batch-size 4] [--dry-run]
    Build rule/ library: Python statistical rules (fast) + Claude-derived
    visual_authoring + narrative_flow rules.

  python3 -m ppt_agent_app.preprocess build-full [--force] [--batch-size 4]
    One-shot: import-all → build-all → logic-build → rule-build.

All three libraries (material/logic/rule) live under data/resources_library/
and are consumed read-only by OUTLINE / IDEA_ANALYSIS stages.
"""

from __future__ import annotations

import sys
import json
from pathlib import Path

from .models import ROOT


def cmd_status() -> int:
    """Report readiness of the 3 resource libraries."""
    print("=== v17 preprocess status ===\n")

    def check_dir(path: Path, name: str, min_items: int = 1) -> bool:
        if not path.exists():
            print(f"❌ {name}: MISSING at {path}")
            return False
        # Count top-level items
        items = list(path.iterdir())
        if len(items) < min_items:
            print(f"⚠️  {name}: only {len(items)} items (expected ≥{min_items})")
            return False
        print(f"✅ {name}: {len(items)} items at {path}")
        return True

    def check_index(path: Path, name: str, key: str) -> bool:
        if not path.exists():
            print(f"❌ {name}: MISSING at {path}")
            return False
        try:
            data = json.loads(path.read_text())
            n = len(data.get(key) or [])
            if n < 1:
                print(f"⚠️  {name}: index empty ({key}=[])")
                return False
            print(f"✅ {name}: {n} entries in {key}")
            return True
        except Exception as e:
            print(f"❌ {name}: parse error {e}")
            return False

    ok_material = check_index(
        ROOT / "data" / "resources_library" / "material" / "decks-index.json",
        "material/decks-index.json", "decks")
    ok_material_dir = check_dir(
        ROOT / "data" / "resources_library" / "material" / "decks",
        "material/decks/", min_items=10)

    ok_logic_deck = check_dir(
        ROOT / "data" / "resources_library" / "logic" / "deck_level",
        "logic/deck_level/", min_items=5)
    ok_logic_section = check_dir(
        ROOT / "data" / "resources_library" / "logic" / "section_level",
        "logic/section_level/", min_items=50)

    ok_rule_logic = check_dir(
        ROOT / "data" / "resources_library" / "rule" / "logic_story",
        "rule/logic_story/", min_items=10)
    ok_rule_page = check_dir(
        ROOT / "data" / "resources_library" / "rule" / "page_specific",
        "rule/page_specific/", min_items=1)  # INDEX.json holds all rules inline
    ok_rule_page_idx = check_index(
        ROOT / "data" / "resources_library" / "rule" / "page_specific" / "INDEX.json",
        "rule/page_specific/INDEX.json", "entries")

    all_ok = all([
        ok_material, ok_material_dir,
        ok_logic_deck, ok_logic_section,
        ok_rule_logic, ok_rule_page, ok_rule_page_idx,
    ])
    print("\n" + ("=" * 40))
    print("Overall:", "✅ READY" if all_ok else "❌ INCOMPLETE — pipeline may fail")
    return 0 if all_ok else 1


def cmd_import_all(only_pptx: list[str] | None = None, *, force: bool = False) -> int:
    """Decompose templates/**.pptx into imports/<deck_id>/ (ppt-master importer).

    `only_pptx`: optional list of pptx paths (relative or absolute) — restricts
    which files are imported. `--force` re-runs importer even if imports exist.
    """
    print("=== v17 preprocess import-all ===\n")
    from . import template_library
    summary = template_library.import_all(only=only_pptx, force=force)
    if summary.get("error"):
        print(f"❌ {summary['error']}")
        return 2
    ok = summary.get("ok") or []
    failed = summary.get("failed") or []
    skipped = summary.get("skipped") or []
    print(f"\nsummary: ok={len(ok)} failed={len(failed)} skipped={len(skipped)}")
    for d in ok[:10]:
        print(f"  ✅ {d}")
    if len(ok) > 10:
        print(f"  ... +{len(ok)-10} more ok")
    for f in failed[:5]:
        print(f"  ❌ {f['deck_id']}: {f['error'][:200]}")
    return 0 if not failed else 1


def cmd_svg_to_png(*, force: bool = False, only: list[str] | None = None,
                    workers: int = 4) -> int:
    """Render every deck's `imports/<deck_id>/svg-flat/slide_*.svg` to `pngs/slide_*.png`.

    Vision-based slide_brief requires these PNGs. Idempotent unless --force.
    """
    print("=== v17 preprocess svg-to-png ===\n")
    from . import svg_to_png as svg_mod
    argv = []
    if force:
        argv.append("--force")
    if workers != 4:
        argv.extend(["--workers", str(workers)])
    if only:
        for d in only:
            argv.extend(["--only", d])
    return svg_mod.main(argv)


def cmd_refine_roles(*, dry_run: bool = False) -> int:
    """Post-process: classify each slide's 细分角色 (structural subtype) based
    on existing vision brief signals. Adds a `细分角色` field to every
    slide_*.json and slide_*.md. Deterministic Python heuristic (~<10s)."""
    print("=== v17 preprocess refine-roles ===\n")
    from .tools import classify_structural_subtype
    classify_structural_subtype.run(dry_run=dry_run)
    return 0


def cmd_build_all(only_deck_ids: list[str] | None = None, *, force: bool = False) -> int:
    """Run the 4-skill Claude brief pipeline for every deck under imports/.

    `only_deck_ids`: optional subset. `--force`: rebuild even if manifest current.
    """
    print("=== v17 preprocess build-all ===\n")
    print("logic/ + rule/ are hand-curated + static, no rebuild.")
    print("Building material/ via template_library...\n")
    from . import template_library
    summary = template_library.build(force=force, only_deck_ids=only_deck_ids)
    if summary.get("error"):
        print(f"❌ {summary['error']}")
        return 2
    if summary.get("skipped"):
        print("[build] library up-to-date, nothing to do")
        return 0
    ok = summary.get("ok") or []
    failed = summary.get("failed") or []
    print(f"\nsummary: ok={len(ok)} failed={len(failed)} "
          f"elapsed={summary.get('elapsed_seconds', 0):.1f}s")
    for d in (ok[:10] if isinstance(ok, list) else []):
        did = d.get("deck_id") if isinstance(d, dict) else d
        print(f"  ✅ {did}")
    for f in failed[:5]:
        print(f"  ❌ {f.get('deck_id')} [{f.get('stage')}]: {(f.get('error') or '')[:200]}")
    print("\n✅ material/ done. Run 'status' to verify.")
    return 0 if not failed else 1


def _parse_only_args(argv: list[str]) -> tuple[list[str] | None, bool, list[str]]:
    """Extract --only <val> [<val> ...] and --force from argv.

    Returns (only_list, force, remaining_positional_args).
    Multiple `--only` may appear; values until next flag are collected.
    """
    only: list[str] | None = None
    force = False
    positional: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--only":
            only = only or []
            j = i + 1
            while j < len(argv) and not argv[j].startswith("--"):
                only.append(argv[j])
                j += 1
            i = j
            continue
        if a == "--force":
            force = True
            i += 1
            continue
        positional.append(a)
        i += 1
    return only, force, positional


def cmd_logic_build(*, layer: str = "both", batch_size: int = 4,
                     dry_run: bool = False) -> int:
    """Extract deck_level + section_level logic patterns via Claude.

    Delegates to `library_extract.logic_extract.main(argv)`. Reads material/
    decks and writes to data/resources_library/logic/{deck_level,section_level}/.
    """
    print("=== v17 preprocess logic-build ===\n")
    from .library_extract import logic_extract
    argv = ["--layer", layer, "--batch-size", str(batch_size)]
    if dry_run:
        argv.append("--dry-run")
    # logic_extract.main() uses sys.argv; call its inner run() to avoid that
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--layer", choices=["deck_level", "section_level", "both"],
                   default="both")
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--deck-timeout", type=int,
                   default=logic_extract.DECK_TIMEOUT_DEFAULT)
    p.add_argument("--section-timeout", type=int,
                   default=logic_extract.SECTION_TIMEOUT_DEFAULT)
    args = p.parse_args(argv)
    result = logic_extract.run(args)
    if not result.get("ok"):
        print(f"❌ logic-build failed: {result}")
        return 2
    print(f"\n✅ logic/ built. deck_patterns={result.get('deck_patterns')} "
          f"section_patterns={result.get('section_patterns')}")
    return 0


def cmd_logic_synthesize(*, stage: str = "both", parallel: int = 4,
                          layer: str | None = None, limit: int | None = None,
                          dry_run: bool = False) -> int:
    """Enrich logic library: meta-pattern synthesis (A) + per-pattern enrichment (C).

    Reads existing logic/{deck_level,section_level}/*.json, adds reasoning-level
    abstract fields, and creates logic/meta/*.json for cross-scenario meta-patterns.
    """
    print("=== v17 preprocess logic-synthesize ===\n")
    from .library_extract import logic_synthesis
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--stage")
    p.add_argument("--parallel-workers", type=int)
    p.add_argument("--layer")
    p.add_argument("--limit", type=int)
    p.add_argument("--dry-run", action="store_true")
    argv = ["--stage", stage, "--parallel-workers", str(parallel)]
    if layer:
        argv.extend(["--layer", layer])
    if limit:
        argv.extend(["--limit", str(limit)])
    if dry_run:
        argv.append("--dry-run")
    args = p.parse_args(argv)
    result = logic_synthesis.run(args)
    return 0 if all(v.get("ok", True) for k, v in result.items() if isinstance(v, dict)) else 2


def cmd_rule_build(*, stats_only: bool = False, claude_only: bool = False,
                    batch_size: int = 1, dry_run: bool = False,
                    parallel_workers: int = 4) -> int:
    """Build rule/ library: stats (Python, seconds) + Claude (visual + narrative).

    Order:
      1. rule_stats.run()      — Python statistical rules (fast, no Claude)
      2. rule_extract.run()    — Claude visual_authoring + narrative_flow rules

    Use --stats-only to skip the Claude part; --claude-only to skip stats.
    Defaults: batch_size=1 (safe for Claude), parallel_workers=4 (fast).
    """
    print("=== v17 preprocess rule-build ===\n")
    from .library_extract import rule_stats, rule_extract

    if not claude_only:
        print(">> Phase 1: statistical rules (Python)")
        stats_result = rule_stats.run(dry_run=dry_run)
        print(f"   stats rules: {stats_result.get('rules_count', 0)}")

    if not stats_only:
        print(f"\n>> Phase 2: Claude-derived rules (visual + narrative, "
              f"bs={batch_size}, workers={parallel_workers})")
        import argparse
        p = argparse.ArgumentParser()
        p.add_argument("--skill",
                       choices=["visual_authoring", "narrative_flow", "both"],
                       default="both")
        p.add_argument("--batch-size", type=int, default=batch_size)
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--va-timeout", type=int, default=1500)
        p.add_argument("--nf-timeout", type=int, default=1800)
        p.add_argument("--parallel-workers", type=int, default=parallel_workers)
        p.add_argument("--no-skip-existing", action="store_true")
        argv = ["--skill", "both", "--batch-size", str(batch_size),
                "--parallel-workers", str(parallel_workers)]
        if dry_run:
            argv.append("--dry-run")
        args = p.parse_args(argv)
        result = rule_extract.run(args)
        if not result.get("ok"):
            print(f"❌ rule-build (Claude phase) failed: {result}")
            return 2
        print(f"   Claude rules written: {result.get('rules_written')}")

    print("\n✅ rule/ built. Run 'status' to verify.")
    return 0


def cmd_build_full(*, force: bool = False, batch_size: int = 4) -> int:
    """One-shot pipeline: import-all → svg-to-png → build-all → refine-roles → logic-build → rule-build."""
    print("=== v17 preprocess build-full ===\n")

    print(">> Stage 1/6: import-all")
    r = cmd_import_all(only_pptx=None, force=force)
    if r != 0:
        print("❌ import-all failed, aborting"); return r

    print("\n>> Stage 2/6: svg-to-png (vision assets)")
    r = cmd_svg_to_png(force=force)
    if r != 0:
        print("❌ svg-to-png failed, aborting"); return r

    print("\n>> Stage 3/6: build-all (material/)")
    r = cmd_build_all(only_deck_ids=None, force=force)
    if r != 0:
        print("❌ build-all failed, aborting"); return r

    print("\n>> Stage 4/6: refine-roles (细分角色 post-process)")
    r = cmd_refine_roles(dry_run=False)
    if r != 0:
        print("❌ refine-roles failed, aborting"); return r

    print("\n>> Stage 5/6: logic-build (logic/)")
    r = cmd_logic_build(batch_size=batch_size)
    if r != 0:
        print("❌ logic-build failed, aborting"); return r

    print("\n>> Stage 6/6: rule-build (rule/)")
    r = cmd_rule_build(batch_size=batch_size)
    if r != 0:
        print("❌ rule-build failed, aborting"); return r

    print("\n✅ full library rebuilt. Run 'status' to verify.")
    return 0


def _parse_layer_arg(argv: list[str]) -> str:
    """Extract --layer <val> from argv, default 'both'."""
    for i, a in enumerate(argv):
        if a == "--layer" and i + 1 < len(argv):
            return argv[i + 1]
    return "both"


def _parse_batch_size(argv: list[str]) -> int:
    for i, a in enumerate(argv):
        if a == "--batch-size" and i + 1 < len(argv):
            try:
                return int(argv[i + 1])
            except ValueError:
                pass
    return 4


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    if cmd == "status":
        return cmd_status()
    elif cmd == "import-all":
        only, force, _ = _parse_only_args(argv[1:])
        return cmd_import_all(only_pptx=only, force=force)
    elif cmd == "svg-to-png":
        only, force, _ = _parse_only_args(argv[1:])
        workers = _parse_batch_size(argv[1:]) if "--workers" in argv else 4
        # reuse --batch-size parser trick but rename
        for i, a in enumerate(argv):
            if a == "--workers" and i + 1 < len(argv):
                try:
                    workers = int(argv[i + 1])
                except ValueError:
                    pass
                break
        return cmd_svg_to_png(only=only, force=force, workers=workers)
    elif cmd == "build-all":
        only, force, _ = _parse_only_args(argv[1:])
        return cmd_build_all(only_deck_ids=only, force=force)
    elif cmd == "refine-roles":
        return cmd_refine_roles(dry_run=("--dry-run" in argv))
    elif cmd == "logic-build":
        layer = _parse_layer_arg(argv[1:])
        bs = _parse_batch_size(argv[1:])
        dry = "--dry-run" in argv
        return cmd_logic_build(layer=layer, batch_size=bs, dry_run=dry)
    elif cmd == "logic-synthesize":
        # parse --stage / --parallel-workers / --layer / --limit / --dry-run
        stage = "both"
        parallel = 4
        layer = None
        limit = None
        for i, a in enumerate(argv):
            if a == "--stage" and i + 1 < len(argv):
                stage = argv[i + 1]
            elif a == "--parallel-workers" and i + 1 < len(argv):
                try:
                    parallel = int(argv[i + 1])
                except ValueError:
                    pass
            elif a == "--layer" and i + 1 < len(argv):
                layer = argv[i + 1]
            elif a == "--limit" and i + 1 < len(argv):
                try:
                    limit = int(argv[i + 1])
                except ValueError:
                    pass
        dry = "--dry-run" in argv
        return cmd_logic_synthesize(stage=stage, parallel=parallel,
                                     layer=layer, limit=limit, dry_run=dry)
    elif cmd == "rule-build":
        stats_only = "--stats-only" in argv
        claude_only = "--claude-only" in argv
        bs = _parse_batch_size(argv[1:])
        dry = "--dry-run" in argv
        return cmd_rule_build(stats_only=stats_only, claude_only=claude_only,
                               batch_size=bs, dry_run=dry)
    elif cmd == "build-full":
        _, force, _ = _parse_only_args(argv[1:])
        bs = _parse_batch_size(argv[1:])
        return cmd_build_full(force=force, batch_size=bs)
    else:
        print(f"Unknown command: {cmd}\n")
        print(__doc__)
        return 1


if __name__ == "__main__":
    sys.exit(main())
