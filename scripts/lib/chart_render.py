#!/usr/bin/env python3
"""chart_render.py — data/chart pipeline backend (AC-13).

Reads PPT_RUN_DIR/chart-spec.json, renders each factual chart as a DATA-DERIVED SVG
into PPT_RUN_DIR/charts/, and writes chart-validation.md tracing every plotted value to
a source. Factual charts must be derived from data, never image-generated:

  - a chart with `generation: "image"` (or `data_derived: false`) is REJECTED;
  - every data point must carry a non-empty `source` and a numeric `value`, else REJECTED.

Exit non-zero if any factual chart fails these rules (chart-validation.md records why).
An empty `charts: []` spec is valid (no factual charts) and exits 0.

SVG is built by hand from the data values — no plotting library, no network, no creds.
"""
import datetime
import json
import os
import sys

RUN_DIR = os.environ.get("PPT_RUN_DIR") or (sys.argv[1] if len(sys.argv) > 1 else ".")


def _now():
    return os.environ.get("PPT_FAKE_NOW") or datetime.datetime.now(
        datetime.timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def render_bar_svg(chart):
    data = chart.get("data", [])
    vals = [float(d["value"]) for d in data]
    mx = max(vals) if vals else 1.0
    mx = mx if mx > 0 else 1.0
    bw, gap, top, base, h = 60, 30, 20, 240, 240
    width = gap + len(data) * (bw + gap)
    height = base + 40
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<title>{chart.get("title", chart.get("chart_id", "chart"))}</title>',
        f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>',
    ]
    x = gap
    for d in data:
        v = float(d["value"])
        bh = int((v / mx) * h)
        y = base - bh
        label = str(d.get("label", "")).replace("<", "&lt;").replace(">", "&gt;")
        parts.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" fill="#2E7D8A"/>')
        parts.append(
            f'<text x="{x + bw // 2}" y="{base + 16}" font-size="12" '
            f'text-anchor="middle" fill="#1A1A1A">{label}</text>'
        )
        parts.append(
            f'<text x="{x + bw // 2}" y="{y - 4}" font-size="11" '
            f'text-anchor="middle" fill="#1A1A1A">{v:g}</text>'
        )
        x += bw + gap
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main():
    spec_path = os.path.join(RUN_DIR, "chart-spec.json")
    spec = json.load(open(spec_path, encoding="utf-8"))
    charts = spec.get("charts", [])
    charts_dir = os.path.join(RUN_DIR, "charts")
    os.makedirs(charts_dir, exist_ok=True)

    ts = _now()
    lines = [
        "---",
        'schema_version: "1.0"',
        f'generated_at: "{ts}"',
        f"chart_count: {len(charts)}",
    ]
    body = ["", "## Value tracing"]
    all_ok = True
    if not charts:
        body.append("- no factual charts in this deck (empty-but-valid).")
    for c in charts:
        cid = c.get("chart_id", "?")
        data = c.get("data", [])
        image_generated = c.get("generation") == "image" or c.get("data_derived") is False
        untraced = [
            d for d in data
            if not str(d.get("source", "")).strip()
            or not isinstance(d.get("value"), (int, float))
        ]
        ok = (not image_generated) and bool(data) and not untraced
        all_ok = all_ok and ok
        body.append(f"### chart {cid} ({c.get('chart_type', '?')}) — {'OK' if ok else 'REJECTED'}")
        if image_generated:
            body.append("- REJECTED: factual chart is image-generated; charts must be data-derived.")
        if not data:
            body.append("- REJECTED: no data points to trace.")
        for d in data:
            src = str(d.get("source", "")).strip() or "<MISSING SOURCE>"
            body.append(f"- {d.get('label', '?')} = {d.get('value', '?')}  <- {src}")
        if ok:
            svg = render_bar_svg(c)
            with open(os.path.join(charts_dir, f"{cid}.svg"), "w", encoding="utf-8") as f:
                f.write(svg)

    lines.append(f"all_values_traced: {str(all_ok).lower()}")
    lines.append(f"data_derived: {str(all_ok).lower()}")
    lines.append("---")
    out = "\n".join(lines + body) + "\n"
    tmp = os.path.join(RUN_DIR, "chart-validation.md.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(out)
    os.replace(tmp, os.path.join(RUN_DIR, "chart-validation.md"))

    if not all_ok:
        print("[gen-charts] REJECTED: a factual chart is not data-derived / has untraced values", file=sys.stderr)
        sys.exit(1)
    print(f"[gen-charts] {len(charts)} chart(s) rendered, all values traced")


if __name__ == "__main__":
    main()
