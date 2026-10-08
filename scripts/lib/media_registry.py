#!/usr/bin/env python3
"""ppt-agent media registry.

Normalizes asset-manifest entries before render/review. This is the ppt-agent
contract layer for media: ppt-master's lower-level media handling remains an
implementation detail, while every pipeline asset gets explicit provenance,
content type, size, hash, usage role, and editability impact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import struct
from pathlib import Path


IMAGE_MIME = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "webp": "image/webp",
    "tiff": "image/tiff",
    "svg": "image/svg+xml",
}

EDITABILITY_IMPACT = {
    "retrieved_image": "raster_picture_non_editable",
    "generated_concept": "raster_picture_non_editable",
    "data_chart": "native_chart_editable",
    "diagram": "native_shapes_editable",
    "icon": "native_or_vector_editable",
    "table": "native_table_editable",
}

USAGE_ROLE = {
    "retrieved_image": "evidence_or_illustration",
    "generated_concept": "decorative_generated",
    "data_chart": "evidence_data_visualization",
    "diagram": "explanatory_structure",
    "icon": "decorative_symbol",
    "table": "evidence_table",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sniff_mime(path: Path) -> str:
    header = path.read_bytes()[:32]
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    if header.startswith((b"BM",)):
        return "image/bmp"
    if header.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if header.lstrip().startswith((b"<svg", b"<?xml")) and path.suffix.lower() == ".svg":
        return "image/svg+xml"
    guessed = mimetypes.guess_type(str(path))[0]
    if guessed:
        return guessed
    return "application/octet-stream"


def png_size(path: Path) -> tuple[int | None, int | None]:
    with path.open("rb") as f:
        header = f.read(24)
    if len(header) >= 24 and header[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", header[16:24])
    return None, None


def jpeg_size(path: Path) -> tuple[int | None, int | None]:
    data = path.read_bytes()
    if not data.startswith(b"\xff\xd8"):
        return None, None
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        i += 2
        if marker in (0xD8, 0xD9):
            continue
        if i + 2 > len(data):
            break
        seg_len = struct.unpack(">H", data[i:i + 2])[0]
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if i + 7 <= len(data):
                h, w = struct.unpack(">HH", data[i + 3:i + 7])
                return w, h
        i += max(seg_len, 2)
    return None, None


def image_size(path: Path, content_type: str) -> tuple[int | None, int | None]:
    if content_type == "image/png":
        return png_size(path)
    if content_type == "image/jpeg":
        return jpeg_size(path)
    try:
        from PIL import Image

        with Image.open(path) as img:
            return img.size
    except Exception:
        return None, None


def aspect_ratio(width: int, height: int) -> str:
    import math

    g = math.gcd(width, height)
    return f"{width // g}:{height // g}"


def enrich_asset(run_dir: Path, asset: dict) -> dict:
    out = dict(asset)
    rel = out.get("local_path")
    if not rel:
        return out
    path = run_dir / str(rel)
    if not path.exists():
        return out
    ctype = sniff_mime(path)
    width, height = image_size(path, ctype)
    out["content_type"] = ctype
    out["file_size_bytes"] = path.stat().st_size
    out["sha256"] = sha256(path)
    if width and height:
        out["width"] = width
        out["height"] = height
        out["aspect_ratio"] = aspect_ratio(width, height)
    atype = str(out.get("asset_type") or "")
    out.setdefault("usage_role", USAGE_ROLE.get(atype, "unspecified"))
    out.setdefault("editability_impact", EDITABILITY_IMPACT.get(atype, "unknown"))
    return out


def enrich_manifest(run_dir: Path, manifest: dict) -> dict:
    out = dict(manifest)
    out["media_registry_version"] = "1.0"
    out["assets"] = [enrich_asset(run_dir, a) for a in out.get("assets", [])]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Enrich asset-manifest.json with media registry fields.")
    ap.add_argument("run_dir")
    ap.add_argument("--infile", default="asset-manifest.json")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    run_dir = Path(args.run_dir).resolve()
    src = run_dir / args.infile
    manifest = json.loads(src.read_text(encoding="utf-8"))
    enriched = enrich_manifest(run_dir, manifest)
    text = json.dumps(enriched, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
