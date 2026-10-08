"""SVG → PNG conversion for slide vision analysis.

Converts `imports/<deck_id>/svg-flat/slide_NN.svg` → `imports/<deck_id>/pngs/slide_NN.png`
so slide_brief.md skill can read the rendered slide via Claude's Read tool.

Each PNG is rendered at 1920 px width (~1.7 MB source → ~80 KB PNG typical).
Requires `cairosvg` (installed via pip).
"""
from __future__ import annotations

import concurrent.futures
import sys
from pathlib import Path

try:
    import cairosvg  # type: ignore
except ImportError as _exc:
    cairosvg = None  # type: ignore
    _CAIRO_IMPORT_ERROR = str(_exc)


DEFAULT_WIDTH = 1920  # px; produces ~80 KB PNGs, plenty for vision


def _ensure_cairo():
    if cairosvg is None:
        raise RuntimeError(
            f"cairosvg is not installed ({_CAIRO_IMPORT_ERROR}); run: pip install cairosvg"
        )


def svg_to_png(svg_path: Path, png_path: Path, *, width: int = DEFAULT_WIDTH) -> bool:
    """Convert one SVG to PNG. Returns True on success."""
    _ensure_cairo()
    png_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        cairosvg.svg2png(url=str(svg_path.resolve()),
                         write_to=str(png_path),
                         output_width=width)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[svg_to_png] FAIL {svg_path.name}: {exc}", flush=True)
        return False


def convert_deck_svgs_to_pngs(deck_import_dir: Path, *,
                               width: int = DEFAULT_WIDTH,
                               force: bool = False,
                               workers: int = 4) -> dict:
    """Convert every `svg-flat/slide_*.svg` in one deck to `pngs/slide_*.png`.

    Args:
        deck_import_dir: e.g. data/resources_library/material/imports/<deck_id>/
        force: re-render even if PNG already exists.
        workers: parallel conversion workers.

    Returns summary {ok, skipped, failed}.
    """
    _ensure_cairo()
    svg_flat = deck_import_dir / "svg-flat"
    if not svg_flat.exists():
        return {"ok": 0, "skipped": 0, "failed": 0,
                "error": f"missing svg-flat dir: {svg_flat}"}
    png_dir = deck_import_dir / "pngs"
    png_dir.mkdir(parents=True, exist_ok=True)

    tasks: list[tuple[Path, Path]] = []
    skipped = 0
    for svg in sorted(svg_flat.glob("slide_*.svg")):
        png = png_dir / (svg.stem + ".png")
        if png.exists() and not force:
            skipped += 1
            continue
        tasks.append((svg, png))

    if not tasks:
        return {"ok": 0, "skipped": skipped, "failed": 0}

    ok = 0
    failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(svg_to_png, s, p, width=width): s for s, p in tasks}
        for fut in concurrent.futures.as_completed(futs):
            if fut.result():
                ok += 1
            else:
                failed += 1

    return {"ok": ok, "skipped": skipped, "failed": failed}


def convert_all_decks(imports_root: Path, *, force: bool = False,
                       workers: int = 4) -> dict:
    """Walk imports/<deck_id>/, convert every deck. Deck-level parallelism = 1
    (conversion is CPU-bound, per-slide workers handle parallelism)."""
    total = {"decks": 0, "ok": 0, "skipped": 0, "failed": 0}
    for deck_dir in sorted(imports_root.iterdir()):
        if not deck_dir.is_dir():
            continue
        result = convert_deck_svgs_to_pngs(deck_dir, force=force, workers=workers)
        total["decks"] += 1
        total["ok"] += result.get("ok", 0)
        total["skipped"] += result.get("skipped", 0)
        total["failed"] += result.get("failed", 0)
        if result.get("error"):
            print(f"[svg_to_png] deck {deck_dir.name}: {result['error']}", flush=True)
        else:
            print(f"[svg_to_png] {deck_dir.name}: "
                  f"ok={result['ok']} skipped={result['skipped']} failed={result['failed']}",
                  flush=True)
    return total


def main(argv: list[str] | None = None) -> int:
    """CLI: python3 -m ppt_agent_app.svg_to_png [--force] [--workers N] [--only <deck_id>]"""
    argv = argv if argv is not None else sys.argv[1:]
    force = "--force" in argv
    workers = 4
    only: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--workers" and i + 1 < len(argv):
            workers = int(argv[i + 1]); i += 2; continue
        if argv[i] == "--only" and i + 1 < len(argv):
            only.append(argv[i + 1]); i += 2; continue
        i += 1

    from .models import ROOT
    imports_root = ROOT / "data" / "resources_library" / "material" / "imports"
    if only:
        total = {"decks": 0, "ok": 0, "skipped": 0, "failed": 0}
        for deck_id in only:
            d = imports_root / deck_id
            if not d.exists():
                print(f"[svg_to_png] not found: {d}"); continue
            result = convert_deck_svgs_to_pngs(d, force=force, workers=workers)
            print(f"[svg_to_png] {deck_id}: {result}")
            total["decks"] += 1
            for k in ("ok", "skipped", "failed"):
                total[k] += result.get(k, 0)
    else:
        total = convert_all_decks(imports_root, force=force, workers=workers)

    print(f"\n=== summary: decks={total['decks']} ok={total['ok']} "
          f"skipped={total['skipped']} failed={total['failed']} ===")
    return 0 if total["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
