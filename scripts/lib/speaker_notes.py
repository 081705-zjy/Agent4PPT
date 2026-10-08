#!/usr/bin/env python3
"""Speaker-notes artifact and PPTX notes embedding for ppt-agent."""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _blocks(manuscript: str) -> list[str]:
    lines = manuscript.splitlines()
    fences = [i for i, line in enumerate(lines) if line.strip() == "---"]
    body = "\n".join(lines[fences[1] + 1:]) if len(fences) >= 2 else manuscript
    return [c.strip() for c in re.split(r"(?m)^---\s*$", body) if c.strip()]


def extract_notes(manuscript_path: Path) -> list[dict]:
    text = manuscript_path.read_text(encoding="utf-8")
    notes = []
    for i, block in enumerate(_blocks(text), 1):
        title = f"Slide {i}"
        m_title = re.search(r"^##\s+Slide\s+\d+:\s*(.+)$", block, re.MULTILINE)
        if m_title:
            title = m_title.group(1).strip()
        note = ""
        m_note = re.search(r"^Speaker notes:\s*(.*)$", block, re.MULTILINE)
        if m_note:
            note = m_note.group(1).strip()
        notes.append({"slide_index": i, "title": title, "notes": note})
    return notes


def render_markdown(notes: list[dict]) -> str:
    lines = [
        "---",
        'schema_version: "1.0"',
        f'generated_at: "{now()}"',
        f"slide_count: {len(notes)}",
        "---",
        "",
        "# Speaker Notes",
        "",
    ]
    for item in notes:
        lines.extend([
            f"## Slide {item['slide_index']}: {item['title']}",
            "",
            str(item.get("notes") or "(no speaker notes)"),
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def write_from_manuscript(run_dir: Path) -> Path:
    notes = extract_notes(run_dir / "manuscript.md")
    out = run_dir / "speaker-notes.md"
    out.write_text(render_markdown(notes), encoding="utf-8")
    return out


def _read_artifact(notes_path: Path) -> list[dict]:
    text = notes_path.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r"(?ms)^##\s+Slide\s+(\d+):\s*(.*?)\n\n(.*?)(?=^##\s+Slide\s+\d+:|\Z)", text):
        out.append({
            "slide_index": int(m.group(1)),
            "title": m.group(2).strip(),
            "notes": m.group(3).strip(),
        })
    return out


def _append_relationship(rels_path: Path, rel_type: str, target: str) -> None:
    rels = rels_path.read_text(encoding="utf-8")
    if target in rels and rel_type in rels:
        return
    ids = [int(x) for x in re.findall(r'Id="rId(\d+)"', rels)]
    rid = f"rId{max(ids, default=0) + 1}"
    entry = f'  <Relationship Id="{rid}" Type="{rel_type}" Target="{target}"/>'
    rels = rels.replace("</Relationships>", entry + "\n</Relationships>")
    rels_path.write_text(rels, encoding="utf-8")


def _add_content_type(content_types: str, slide_num: int) -> str:
    override = (
        f'  <Override PartName="/ppt/notesSlides/notesSlide{slide_num}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>'
    )
    if override in content_types:
        return content_types
    return content_types.replace("</Types>", override + "\n</Types>")


def embed_notes(pptx_path: Path, notes_path: Path) -> int:
    notes = _read_artifact(notes_path)
    if not notes:
        return 0
    from ppt_master.svg_to_pptx.pptx_notes import create_notes_slide_rels_xml, create_notes_slide_xml

    tmp = Path(tempfile.mkdtemp())
    try:
        with zipfile.ZipFile(pptx_path, "r") as zf:
            zf.extractall(tmp)
        notes_dir = tmp / "ppt" / "notesSlides"
        notes_rels_dir = notes_dir / "_rels"
        notes_dir.mkdir(parents=True, exist_ok=True)
        notes_rels_dir.mkdir(parents=True, exist_ok=True)
        content_types_path = tmp / "[Content_Types].xml"
        content_types = content_types_path.read_text(encoding="utf-8")
        count = 0
        for item in notes:
            idx = int(item["slide_index"])
            slide_xml = tmp / "ppt" / "slides" / f"slide{idx}.xml"
            slide_rels = tmp / "ppt" / "slides" / "_rels" / f"slide{idx}.xml.rels"
            if not slide_xml.exists() or not slide_rels.exists():
                continue
            (notes_dir / f"notesSlide{idx}.xml").write_text(
                create_notes_slide_xml(idx, item.get("notes") or ""),
                encoding="utf-8",
            )
            (notes_rels_dir / f"notesSlide{idx}.xml.rels").write_text(
                create_notes_slide_rels_xml(idx),
                encoding="utf-8",
            )
            _append_relationship(
                slide_rels,
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide",
                f"../notesSlides/notesSlide{idx}.xml",
            )
            content_types = _add_content_type(content_types, idx)
            count += 1
        content_types_path.write_text(content_types, encoding="utf-8")
        tmp_pptx = pptx_path.with_suffix(".notes.tmp.pptx")
        with zipfile.ZipFile(tmp_pptx, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(tmp):
                for name in files:
                    path = Path(root) / name
                    zf.write(path, path.relative_to(tmp).as_posix())
        tmp_pptx.replace(pptx_path)
        return count
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def count_notes(pptx_path: Path) -> int:
    if not pptx_path.exists():
        return 0
    with zipfile.ZipFile(pptx_path, "r") as zf:
        return len([n for n in zf.namelist() if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", n)])


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate or embed ppt-agent speaker notes.")
    ap.add_argument("run_dir")
    ap.add_argument("--embed", action="store_true")
    args = ap.parse_args()
    run_dir = Path(args.run_dir).resolve()
    notes = write_from_manuscript(run_dir)
    if args.embed:
        print(embed_notes(run_dir / "deck.pptx", notes))
    else:
        print(notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
