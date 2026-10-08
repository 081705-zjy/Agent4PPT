from __future__ import annotations

import hashlib
import mimetypes
import re
import zipfile
from html import unescape
from xml.etree import ElementTree as ET
from pathlib import Path


RESOURCE_EXTS = {
    ".ppt": "ppt_deck",
    ".pptx": "ppt_deck",
    ".pps": "ppt_deck",
    ".ppsx": "ppt_deck",
    ".doc": "document",
    ".docx": "document",
    ".docs": "document",
    ".rtf": "document",
    ".odt": "document",
    ".pdf": "document",
    ".xls": "spreadsheet",
    ".xlsx": "spreadsheet",
    ".xlsm": "spreadsheet",
    ".ods": "spreadsheet",
    ".csv": "data",
    ".tsv": "data",
    ".json": "data",
    ".yaml": "data",
    ".yml": "data",
    ".mm": "mindmap",
    ".xmind": "mindmap",
    ".md": "text",
    ".txt": "text",
    ".html": "text",
    ".htm": "text",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".svg": "image",
    ".webp": "image",
    ".gif": "image",
    ".mp4": "video",
    ".mov": "video",
    ".avi": "video",
    ".mp3": "audio",
    ".wav": "audio",
    ".m4a": "audio",
}


def resource_kind(path: Path) -> str:
    return RESOURCE_EXTS.get(path.suffix.lower(), "file")


def reusable_level(kind: str) -> str:
    if kind == "ppt_deck":
        return "page"
    if kind in {"image", "audio", "video"}:
        return "asset"
    if kind in {"document", "spreadsheet", "data", "mindmap", "text"}:
        return "source"
    return "file"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_project(project_dir: Path) -> list[dict]:
    roots = [project_dir / "templates", project_dir / "sources", project_dir / "assets"]
    out = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            kind = resource_kind(path)
            rel = path.relative_to(project_dir).as_posix()
            out.append({
                "resource_id": sha256(path)[:16],
                "path": rel,
                "type": kind,
                "extension": path.suffix.lower(),
                "content_type": mimetypes.guess_type(str(path))[0] or "application/octet-stream",
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
                "reusable_level": reusable_level(kind),
            })
    return out


def _clean_text(text: str, limit: int = 5000) -> str:
    text = unescape(re.sub(r"\s+", " ", str(text or ""))).strip()
    return text[:limit]


def _xml_text(raw: bytes) -> str:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return ""
    parts = []
    for node in root.iter():
        if node.text and node.tag.rsplit("}", 1)[-1] in {"t", "instrText"}:
            parts.append(node.text)
    return _clean_text(" ".join(parts))


def _extract_docx(path: Path) -> dict:
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n.startswith("word/") and n.endswith(".xml")]
        document = _xml_text(zf.read("word/document.xml")) if "word/document.xml" in names else ""
        comments = " ".join(_xml_text(zf.read(n)) for n in names if "comments" in n)
    return {"text": _clean_text(f"{document} {comments}"), "tables": []}


def _extract_pptx(path: Path) -> dict:
    slides = []
    with zipfile.ZipFile(path) as zf:
        names = sorted(
            [n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)],
            key=lambda n: int(re.search(r"slide(\d+)\.xml", n).group(1)),
        )
        for idx, name in enumerate(names, start=1):
            text = _xml_text(zf.read(name))
            if text:
                slides.append({"index": idx, "text": text[:1200]})
    joined = " ".join(s["text"] for s in slides)
    return {"text": _clean_text(joined), "slides": slides[:30]}


def _extract_xlsx(path: Path) -> dict:
    shared = []
    sheets = []
    with zipfile.ZipFile(path) as zf:
        if "xl/sharedStrings.xml" in zf.namelist():
            try:
                root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for si in root:
                    vals = [n.text or "" for n in si.iter() if n.tag.rsplit("}", 1)[-1] == "t"]
                    shared.append("".join(vals))
            except ET.ParseError:
                shared = []
        sheet_names = sorted(
            [n for n in zf.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)],
            key=lambda n: int(re.search(r"sheet(\d+)\.xml", n).group(1)),
        )
        for idx, name in enumerate(sheet_names, start=1):
            try:
                root = ET.fromstring(zf.read(name))
            except ET.ParseError:
                continue
            rows = []
            for row in root.iter():
                if row.tag.rsplit("}", 1)[-1] != "row":
                    continue
                vals = []
                for cell in row:
                    if cell.tag.rsplit("}", 1)[-1] != "c":
                        continue
                    typ = cell.attrib.get("t")
                    val = ""
                    for child in cell:
                        if child.tag.rsplit("}", 1)[-1] == "v":
                            val = child.text or ""
                            break
                    if typ == "s" and val.isdigit() and int(val) < len(shared):
                        val = shared[int(val)]
                    vals.append(val)
                if any(v for v in vals):
                    rows.append(vals)
                if len(rows) >= 12:
                    break
            sheets.append({"index": idx, "rows": rows})
    text = " ".join(" ".join(" ".join(row) for row in sheet.get("rows", [])) for sheet in sheets)
    return {"text": _clean_text(text), "sheets": sheets[:12]}


def _extract_plain(path: Path) -> dict:
    return {"text": _clean_text(path.read_text(encoding="utf-8", errors="ignore")), "tables": []}


def _extract_pdf(path: Path) -> dict:
    """Extract text from a PDF. Prefers pdfplumber, falls back to pypdf.

    Output mirrors the other extractors:
      {"text": "joined plain text", "chunks": [{section, text}], "figures": [...], "tables": [...], "page_count": int}
    """
    text_parts: list[str] = []
    chunks: list[dict] = []
    page_count = 0
    used = None
    try:
        import pdfplumber  # type: ignore
        used = "pdfplumber"
        with pdfplumber.open(str(path)) as pdf:
            page_count = len(pdf.pages)
            for i, page in enumerate(pdf.pages, start=1):
                try:
                    t = page.extract_text() or ""
                except Exception:
                    t = ""
                if not t.strip():
                    continue
                text_parts.append(t)
                chunks.append({
                    "chunk_index": i,
                    "section": f"page_{i}",
                    "text": t[:1500],
                })
    except Exception:
        try:
            from pypdf import PdfReader  # type: ignore
            used = "pypdf"
            reader = PdfReader(str(path))
            page_count = len(reader.pages)
            for i, page in enumerate(reader.pages, start=1):
                try:
                    t = page.extract_text() or ""
                except Exception:
                    t = ""
                if not t.strip():
                    continue
                text_parts.append(t)
                chunks.append({
                    "chunk_index": i,
                    "section": f"page_{i}",
                    "text": t[:1500],
                })
        except Exception as exc:
            return {"text": "", "chunks": [], "page_count": 0,
                    "note": f"no pdf reader available: {exc}"}
    full_text = "\n\n".join(text_parts)
    return {
        "text": full_text,
        "chunks": chunks,
        "figures": [],
        "tables": [],
        "page_count": page_count,
        "extractor": used,
    }


def build_resource_digest(project_dir: Path, resources: list[dict] | None = None) -> dict:
    """Create lightweight, generation-ready summaries for scanned resources.

    The scan index answers "what files exist"; this digest answers "what usable content
    can the model cite or reuse". Extraction is best-effort and never raises.
    """
    resources = resources if resources is not None else scan_project(project_dir)
    items = []
    for item in resources:
        rel = item.get("path")
        if not rel:
            continue
        path = project_dir / rel
        kind = item.get("type")
        ext = path.suffix.lower()
        entry = {
            "resource_id": item.get("resource_id"),
            "path": rel,
            "type": kind,
            "reusable_level": item.get("reusable_level"),
            "summary": "",
            "text_excerpt": "",
            "structured": {},
            "ok": True,
            "error": None,
        }
        try:
            if ext == ".docx":
                extracted = _extract_docx(path)
            elif ext == ".pptx":
                extracted = _extract_pptx(path)
            elif ext == ".xlsx":
                extracted = _extract_xlsx(path)
            elif ext == ".pdf":
                extracted = _extract_pdf(path)
            elif ext in {".md", ".txt", ".csv", ".tsv", ".json", ".yaml", ".yml", ".html", ".htm"}:
                extracted = _extract_plain(path)
            else:
                extracted = {"text": "", "note": "binary or unsupported source for text extraction"}
            text = _clean_text(extracted.get("text") or "", 1800)
            entry["text_excerpt"] = text
            entry["summary"] = text[:320] if text else f"{kind} resource available for reuse"
            entry["structured"] = {k: v for k, v in extracted.items() if k != "text"}
        except Exception as exc:  # noqa: BLE001 - digest must not block generation
            entry["ok"] = False
            entry["error"] = str(exc)
        items.append(entry)
    return {
        "schema_version": "1.0",
        "items": items,
        "source_count": len(items),
        "parsed_count": sum(1 for item in items if item.get("ok") and item.get("text_excerpt")),
    }
