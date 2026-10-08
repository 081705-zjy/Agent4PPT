"""Character Revision — applies gap-card unification/edit hints to draft-deck.pptx.

Runs between DRAFT_ASSEMBLY (byte-clone raw source slides) and DRAFT_REVIEW.

Pipeline per slide:
  1. extract_elements(slide) → JSON list of editable elements
       [{"id": "para_0.0", "text": "SpecEE 效果"},
        {"id": "img_2", "desc": "架构图"}]
  2. build gap instruction from gap_card
       (unification_hints + must_replace + must_remove + must_add)
  3. Claude call → produces JSON action list
       {"actions": [
         {"op": "replace_text", "id": "para_0.0", "text": "SpecEE 加速性能"},
         {"op": "remove_bullet", "id": "para_1.2"}
       ]}
   4. apply_actions() executes atoms via python-pptx, preserving formatting
   5. failed slide → retry (up to 3 times) with error feedback

4 atomic ops (inspired by icip-cas/PPTAgent but simplified):
  - replace_text(id, text)          — replace paragraph text, keep font/color
  - append_bullet(container_id, text) — clone last para and set new text
  - remove_bullet(id)               — delete a paragraph
  - replace_image(id, image_path)   — swap image (preserve position/size)

Element id scheme:
  para_<shape_idx>.<para_idx>   — text paragraph (e.g. "para_0.1")
  img_<shape_idx>               — picture shape (e.g. "img_2")
  shape_<shape_idx>             — container shape (used by append_bullet)
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.util import Emu
from lxml import etree


PARA_ID_RE = re.compile(r"^para_(\d+)\.(\d+)$")
IMG_ID_RE = re.compile(r"^img_(\d+)$")
SHAPE_ID_RE = re.compile(r"^shape_(\d+)$")


class RevisionError(Exception):
    """Raised when an action cannot be applied. Caller retries via LLM."""


# ──────────────────────────────────────────────────────────────────────────
# Element extraction
# ──────────────────────────────────────────────────────────────────────────

# v4 (2026-07-29): read XML directly — accessing shape.fill or shape.line
# via python-pptx SIDE-EFFECTS: it materializes default <a:ln>/<a:solidFill>
# elements when they don't exist, changing the file when saved. We use lxml
# to read the source XML instead so nothing gets written into unrelated shapes.

_NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _shape_fill_hex(shape) -> str | None:
    """Read solidFill srgb color from shape XML without touching python-pptx shape.fill."""
    try:
        sp = shape._element
        # spPr is the shape properties container
        spPr = sp.find(f"{{http://schemas.openxmlformats.org/presentationml/2006/main}}spPr")
        if spPr is None:
            # some shape types put spPr under a different parent
            spPr = sp.find(f".//{{http://schemas.openxmlformats.org/presentationml/2006/main}}spPr")
        if spPr is None:
            return None
        # Look for <a:solidFill>/<a:srgbClr val="..."/> directly under spPr
        for child in spPr:
            tag = child.tag
            if tag == f"{{{_NS_A}}}solidFill":
                srgb = child.find(f"{{{_NS_A}}}srgbClr")
                if srgb is not None:
                    val = srgb.get("val")
                    if val:
                        return val.upper()
                return None
            if tag == f"{{{_NS_A}}}noFill":
                return None
    except Exception:
        pass
    return None


def _shape_line_hex(shape) -> str | None:
    """Read <a:ln>/<a:solidFill>/<a:srgbClr> from shape XML — no python-pptx side effects."""
    try:
        sp = shape._element
        spPr = sp.find(f"{{http://schemas.openxmlformats.org/presentationml/2006/main}}spPr")
        if spPr is None:
            spPr = sp.find(f".//{{http://schemas.openxmlformats.org/presentationml/2006/main}}spPr")
        if spPr is None:
            return None
        ln = spPr.find(f"{{{_NS_A}}}ln")
        if ln is None:
            return None
        # Check for noFill
        if ln.find(f"{{{_NS_A}}}noFill") is not None:
            return None
        sf = ln.find(f"{{{_NS_A}}}solidFill")
        if sf is not None:
            srgb = sf.find(f"{{{_NS_A}}}srgbClr")
            if srgb is not None:
                val = srgb.get("val")
                if val:
                    return val.upper()
    except Exception:
        pass
    return None


def _detect_is_title(shape, slide_height_emu: int) -> bool:
    """Heuristic: is this a title shape?
    - is_placeholder with type TITLE / CENTER_TITLE / SUBTITLE
    - OR positioned in top 20% of slide with wide-and-short aspect
    """
    try:
        if shape.is_placeholder:
            ph_type = str(shape.placeholder_format.type).upper()
            if "TITLE" in ph_type:
                return True
    except Exception:
        pass
    try:
        if shape.top is not None and shape.top < slide_height_emu * 0.2:
            if shape.width and shape.height:
                aspect = shape.width / shape.height
                if aspect >= 3.0:  # wide-and-short = likely title
                    return True
    except Exception:
        pass
    return False


def _run_font_color_hex(run) -> str | None:
    try:
        if run.font.color.type is None:
            return None
        rgb = run.font.color.rgb
        return str(rgb).upper() if rgb else None
    except Exception:
        return None


def _para_dominant_color_and_size(para) -> tuple[str | None, float | None]:
    """Return (color_hex, avg_size_pt) of runs in a paragraph via XML only.
    Weighted by text length. Never uses run.font.* to avoid python-pptx side effects."""
    from collections import Counter
    ns_a = _NS_A
    color_counter: Counter = Counter()
    size_counter: Counter = Counter()
    p_elem = para._p
    for r in p_elem.findall(f"{{{ns_a}}}r"):
        ts = r.findall(f"{{{ns_a}}}t")
        w = max(1, sum(len(t.text or "") for t in ts))
        rpr = r.find(f"{{{ns_a}}}rPr")
        if rpr is None:
            continue
        # size from rPr's sz attribute (in hundredths of a point)
        sz = rpr.get("sz")
        if sz:
            try:
                size_counter[float(sz) / 100.0] += w
            except Exception:
                pass
        # color from rPr's <a:solidFill><a:srgbClr>
        sf = rpr.find(f"{{{ns_a}}}solidFill")
        if sf is not None:
            srgb = sf.find(f"{{{ns_a}}}srgbClr")
            if srgb is not None:
                val = srgb.get("val")
                if val:
                    color_counter[val.upper()] += w
    color = color_counter.most_common(1)[0][0] if color_counter else None
    size = size_counter.most_common(1)[0][0] if size_counter else None
    return color, size


def extract_elements(slide) -> list[dict]:
    """Return a JSON-safe list of editable elements for one slide.

    v2 (2026-07-29) adds visual metadata so Claude can decide:
      - which shapes are titles (char-limit enforced)
      - which shapes are "yellow warning boxes" that should be removed entirely
      - which colors to preserve
      - which positions might overflow

    Each entry has:
      shape-level: id, kind, position (in EMU), fill_color, line_color, is_title
      text para:   id, kind='text', text, container_id, char_count, color, size_pt
      image:       id, kind='image', desc, position
      shape:       (extra entry for each shape) shape_<idx> for use as remove_shape target
    """
    from pptx.util import Emu
    from lxml import etree as _et_local
    try:
        slide_h = slide.slide_layout.slide_master.presentation.slide_height
    except Exception:
        slide_h = int(Emu(5143500))  # fallback 5.6"
    out: list[dict] = []
    def _shape_has_text_frame_xml(shape) -> bool:
        """Detect text frame via XML (no python-pptx access) to avoid side effects."""
        for elem in shape._element.iter():
            if _et_local.QName(elem).localname == "txBody":
                return True
        return False

    for shape_idx, shape in enumerate(slide.shapes):
        # Common shape metadata
        pos = {
            "left": int(shape.left) if shape.left is not None else None,
            "top": int(shape.top) if shape.top is not None else None,
            "width": int(shape.width) if shape.width is not None else None,
            "height": int(shape.height) if shape.height is not None else None,
        }
        fill = _shape_fill_hex(shape)
        line = _shape_line_hex(shape)
        is_title = _detect_is_title(shape, slide_h)

        # A shape-level entry (usable as remove_shape target)
        out.append({
            "id": f"shape_{shape_idx}",
            "kind": "shape_meta",
            "position": pos,
            "fill_color": fill,
            "line_color": line,
            "is_title": is_title,
            "has_text": _shape_has_text_frame_xml(shape),
            "is_picture": shape.shape_type == 13,
        })

        # v7: read paragraphs via XML directly to avoid python-pptx side effects
        # that inject empty <a:solidFill/> into rPr elements.
        sp = shape._element
        txBody = None
        for elem in sp.iter():
            if etree.QName(elem).localname == "txBody":
                txBody = elem
                break
        if txBody is not None:
            ps = txBody.findall(f"{{{_NS_A}}}p")
            for para_idx, p_elem in enumerate(ps):
                # Get text by concatenating all <a:t> under this <a:p>
                text = "".join(t.text or "" for t in p_elem.iter(f"{{{_NS_A}}}t"))
                if not text.strip():
                    continue
                para_ref = _XMLParaRef(p_elem)
                pcolor, psize = _para_dominant_color_and_size(para_ref)
                out.append({
                    "id": f"para_{shape_idx}.{para_idx}",
                    "kind": "text",
                    "text": text,
                    "char_count": len(text.strip()),
                    "container_id": f"shape_{shape_idx}",
                    "is_title": is_title,
                    "color": pcolor,
                    "size_pt": psize,
                    "container_fill": fill,
                    "container_line": line,
                })
        elif shape.shape_type == 13:
            desc = getattr(shape, "name", "") or "picture"
            out.append({
                "id": f"img_{shape_idx}",
                "kind": "image",
                "desc": desc,
                "position": pos,
            })
    return out


# ──────────────────────────────────────────────────────────────────────────
# Locators
# ──────────────────────────────────────────────────────────────────────────

def _resolve_shape(slide, shape_idx: int):
    if shape_idx < 0 or shape_idx >= len(slide.shapes):
        raise RevisionError(f"shape_idx {shape_idx} out of range (0..{len(slide.shapes)-1})")
    return slide.shapes[shape_idx]


class _XMLParaRef:
    """A stand-in for python-pptx's _Paragraph, exposing only ._p (the <a:p>
    element). Used to avoid triggering python-pptx side effects that inject
    empty <a:solidFill/> elements into rPr on property access."""
    __slots__ = ("_p",)
    def __init__(self, p_elem):
        self._p = p_elem


def _resolve_paragraph(slide, para_id: str):
    """Resolve para_<shape>.<para> to (shape, XMLParaRef) via lxml, no python-pptx
    high-level API. Returns a shell object exposing only ._p to keep ops working."""
    m = PARA_ID_RE.match(para_id)
    if not m:
        raise RevisionError(f"invalid para id {para_id!r}, want 'para_<shape>.<para>'")
    shape_idx, para_idx = int(m.group(1)), int(m.group(2))
    shape = _resolve_shape(slide, shape_idx)
    # Read <a:p> elements directly from XML, do NOT use shape.text_frame
    ns_a = _NS_A
    sp = shape._element
    txBody = None
    for tag_name in ("txBody", "txbody"):
        # Text body element is in the p:sp / p:pic / p:cxnSp namespace
        for txb in sp.iter():
            local = etree.QName(txb).localname
            if local == "txBody":
                txBody = txb
                break
        if txBody is not None:
            break
    if txBody is None:
        raise RevisionError(f"shape {shape_idx} has no text body")
    ps = txBody.findall(f"{{{ns_a}}}p")
    if para_idx < 0 or para_idx >= len(ps):
        raise RevisionError(f"para_idx {para_idx} out of range in shape {shape_idx} (0..{len(ps)-1})")
    return shape, _XMLParaRef(ps[para_idx])


# ──────────────────────────────────────────────────────────────────────────
# 4 atomic ops
# ──────────────────────────────────────────────────────────────────────────

def op_replace_text(slide, id: str, text: str,
                     is_title: bool | None = None,
                     original_text: str | None = None) -> dict:
    """Replace paragraph text, preserving the first run's formatting.

    v2 (2026-07-29) adds a character-count guard: if is_title=True the new text
    can be at most 1.2× the original length; otherwise up to 2×. This prevents
    Claude from silently blowing up titles into overflow.

    Strategy (mirrors PPTAgent's replace_para): merge all runs into the first
    one, keep its font/color/size, set text = new_text. Remaining runs cleared.
    """
    shape, para = _resolve_paragraph(slide, id)
    # Compute original text from XML if caller didn't provide (para may be _XMLParaRef)
    if original_text is not None:
        original = original_text
    else:
        ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
        original = "".join(t.text or "" for t in para._p.iter(f"{{{ns_a}}}t"))
    limit_ratio = 1.2 if is_title else 2.0
    orig_len = len(original.strip())
    new_len = len(text.strip())
    if orig_len > 0 and new_len > int(orig_len * limit_ratio):
        raise RevisionError(
            f"new text too long: {new_len} chars vs orig {orig_len} "
            f"(limit ×{limit_ratio}); shorten or split into bullets"
        )
    # v6 (2026-07-29) PURE XML + DOMINANT-RUN carrier.
    # Multi-run paragraphs (common for titles like "AI 2.0 关键指标：..." split
    # into English + CJK runs with different fonts/colors) — putting new text
    # into first_run would surface the WRONG font/color (whichever the short
    # first_run had). Instead, we pick the LONGEST-text run as the carrier
    # so the new text takes on the DOMINANT visual style, and clear <a:t> on
    # all OTHER runs (leaving rPr intact but with empty text — no visual
    # impact but preserves the XML structure completely).
    from lxml import etree as _et
    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    p_elem = para._p
    r_children = p_elem.findall(f"{{{ns_a}}}r")
    if not r_children:
        # Empty paragraph: create a bare <a:r><a:t>text</a:t></a:r>
        new_r = _et.SubElement(p_elem, f"{{{ns_a}}}r")
        new_t = _et.SubElement(new_r, f"{{{ns_a}}}t")
        new_t.text = text
        return {"op": "replace_text", "id": id, "result": "ok_created_run",
                "chars": new_len}
    # Find carrier = <a:r> whose combined <a:t> text length is greatest.
    def _run_text_len(r):
        return sum(len(t.text or "") for t in r.findall(f"{{{ns_a}}}t"))
    lens = [(_run_text_len(r), i, r) for i, r in enumerate(r_children)]
    carrier_len, carrier_idx, carrier_r = max(lens, key=lambda x: (x[0], -x[1]))
    # Put new text into carrier's first <a:t>, remove extra <a:t> siblings in carrier.
    carrier_ts = carrier_r.findall(f"{{{ns_a}}}t")
    if carrier_ts:
        carrier_ts[0].text = text
        for extra in carrier_ts[1:]:
            carrier_r.remove(extra)
    else:
        new_t = _et.SubElement(carrier_r, f"{{{ns_a}}}t")
        new_t.text = text
    # Clear <a:t>.text on OTHER runs (preserve rPr, just empty the text).
    # Do NOT delete the <a:r> element — that would drop its rPr formatting,
    # and if the carrier run is not the first one, deleting others changes indexes.
    for i, r in enumerate(r_children):
        if i == carrier_idx:
            continue
        for t in r.findall(f"{{{ns_a}}}t"):
            t.text = ""
    return {"op": "replace_text", "id": id, "result": "ok", "chars": new_len,
            "carrier_idx": carrier_idx, "carrier_orig_chars": carrier_len}


def op_recolor_text(slide, id: str, color: str) -> dict:
    """Set the paragraph's text color (RGB hex, 6 chars, no '#').

    Applied to ALL runs in the paragraph so partial-run coloring stays
    consistent. Used mainly by agenda pages to highlight the current chapter
    (black) vs the others (grey).
    """
    shape, para = _resolve_paragraph(slide, id)
    hex_str = str(color).lstrip("#").upper()
    if len(hex_str) != 6 or any(c not in "0123456789ABCDEF" for c in hex_str):
        raise RevisionError(f"invalid color {color!r}, want 6-hex-char RGB e.g. '000000'")
    # v6 (2026-07-29): refuse to recolor if paragraph is inside a title shape.
    # Titles must keep their original color; recolor_text is intended for
    # agenda-page chapter highlighting (body-level paragraphs only).
    try:
        # Use the slide_height fallback to run _detect_is_title
        slide_h = shape.part.slide_height if hasattr(shape.part, "slide_height") else 5143500
    except Exception:
        slide_h = 5143500
    if _detect_is_title(shape, slide_h):
        raise RevisionError(
            f"recolor_text refused: paragraph {id} is inside a title shape; "
            "titles must preserve their original color. Only use recolor_text "
            "on body paragraphs (typically agenda chapter names)."
        )
    # v5 (2026-07-29): pure XML — iterate <a:r> children of <a:p> directly.
    from lxml import etree as _et
    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    p_elem = para._p
    for r_elem in p_elem.findall(f"{{{ns_a}}}r"):
        rpr = r_elem.find(f"{{{ns_a}}}rPr")
        if rpr is None:
            rpr = _et.Element(f"{{{ns_a}}}rPr")
            r_elem.insert(0, rpr)
        # Remove any existing solidFill under rPr
        for sf in list(rpr):
            if sf.tag == f"{{{ns_a}}}solidFill":
                rpr.remove(sf)
        # Append new solidFill with srgb inside
        sf_new = _et.SubElement(rpr, f"{{{ns_a}}}solidFill")
        srgb = _et.SubElement(sf_new, f"{{{ns_a}}}srgbClr")
        srgb.set("val", hex_str)
    return {"op": "recolor_text", "id": id, "color": hex_str, "result": "ok"}


def op_append_bullet(slide, container_id: str, text: str) -> dict:
    """Append a bullet-paragraph to a text container, cloning the last paragraph's xml
    so bullet formatting/indent are preserved. Set the new run text to `text`.
    """
    m = SHAPE_ID_RE.match(container_id)
    if not m:
        raise RevisionError(f"invalid container id {container_id!r}, want 'shape_<idx>'")
    shape_idx = int(m.group(1))
    shape = _resolve_shape(slide, shape_idx)
    if not shape.has_text_frame:
        raise RevisionError(f"shape {shape_idx} has no text frame")
    tf = shape.text_frame
    paras = tf.paragraphs
    if not paras:
        # empty text frame: just set text
        tf.text = text
        return {"op": "append_bullet", "id": container_id, "result": "ok_seeded"}
    # Clone xml of last paragraph
    from copy import deepcopy
    last_p = paras[-1]._p
    new_p = deepcopy(last_p)
    # Clear text in cloned runs
    for r in new_p.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}r"):
        # each <a:r> has an <a:t> child
        for t in r.findall("{http://schemas.openxmlformats.org/drawingml/2006/main}t"):
            t.text = ""
    # Set first run's text to new content
    ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    r_elems = new_p.findall(f"{ns}r")
    if r_elems:
        t_elems = r_elems[0].findall(f"{ns}t")
        if t_elems:
            t_elems[0].text = text
        else:
            # No <a:t>, create one
            from lxml import etree
            t_new = etree.SubElement(r_elems[0], f"{ns}t")
            t_new.text = text
    else:
        # No <a:r> at all, add a bare paragraph text via python-pptx
        # Fallback: just append using tf.add_paragraph API path
        p = tf.add_paragraph()
        p.text = text
        return {"op": "append_bullet", "id": container_id, "result": "ok_fallback_api"}
    last_p.addnext(new_p)
    return {"op": "append_bullet", "id": container_id, "result": "ok"}


def op_remove_bullet(slide, id: str) -> dict:
    """Delete a paragraph. If it's the last remaining paragraph in the text frame,
    clear its text instead of removing the element (python-pptx requires ≥1 para).
    """
    shape, para = _resolve_paragraph(slide, id)
    tf = shape.text_frame
    if len(tf.paragraphs) == 1:
        para.text = ""
        return {"op": "remove_bullet", "id": id, "result": "ok_cleared_last"}
    p_elem = para._p
    p_elem.getparent().remove(p_elem)
    return {"op": "remove_bullet", "id": id, "result": "ok"}


def op_remove_shape(slide, shape_id: str) -> dict:
    """Delete an entire shape (used for yellow warning boxes, placeholder notes).

    id format: shape_<idx>. shape_idx refers to the ORIGINAL index at the time
    of extract_elements(); apply_actions sorts remove_shape by descending idx to
    keep indexes stable.
    """
    m = SHAPE_ID_RE.match(shape_id)
    if not m:
        raise RevisionError(f"invalid shape id {shape_id!r}, want 'shape_<idx>'")
    shape_idx = int(m.group(1))
    shape = _resolve_shape(slide, shape_idx)
    sp = shape._element
    parent = sp.getparent()
    if parent is None:
        raise RevisionError(f"shape {shape_idx} has no parent (cannot remove)")
    parent.remove(sp)
    return {"op": "remove_shape", "id": shape_id, "result": "ok"}


def op_replace_image(slide, id: str, image_path: str) -> dict:
    """Replace image while preserving position/size. python-pptx has no direct
    replace API on Picture — we swap the underlying image part via the blob.
    """
    m = IMG_ID_RE.match(id)
    if not m:
        raise RevisionError(f"invalid img id {id!r}, want 'img_<idx>'")
    shape_idx = int(m.group(1))
    shape = _resolve_shape(slide, shape_idx)
    if shape.shape_type != 13:
        raise RevisionError(f"shape {shape_idx} is not a picture (type={shape.shape_type})")
    p = Path(image_path)
    if not p.is_absolute():
        # Interpret relative to project root (caller passes proper path usually)
        pass
    if not p.exists():
        raise RevisionError(f"image path not found: {image_path}")
    # Access the image part via the shape's _element and replace the blob
    with open(p, "rb") as f:
        new_blob = f.read()
    # picture.image gives read-only access; we need to swap the related part
    image = shape.image
    image._blob = new_blob  # replaces the in-memory blob
    # For persistent replacement we must alter the part on the package
    # Alternative: python-pptx doesn't officially support replace; the pattern
    # used by community is to delete + re-add with same anchor. Do that:
    left, top, width, height = shape.left, shape.top, shape.width, shape.height
    parent = shape._element.getparent()
    sp_index = list(parent).index(shape._element)
    parent.remove(shape._element)
    new_pic = slide.shapes.add_picture(str(p), left, top, width=width, height=height)
    # Move newly added picture element to original z-order position
    parent.remove(new_pic._element)
    parent.insert(sp_index, new_pic._element)
    return {"op": "replace_image", "id": id, "result": "ok"}


# ──────────────────────────────────────────────────────────────────────────
# Dispatcher
# ──────────────────────────────────────────────────────────────────────────

_OP_TABLE = {
    "replace_text": op_replace_text,
    "recolor_text": op_recolor_text,
    "append_bullet": op_append_bullet,
    "remove_bullet": op_remove_bullet,
    "remove_shape": op_remove_shape,
    # replace_image intentionally removed in v3 (2026-07-29):
    # CHARACTER_REVISION does not touch images per user policy.
}


def apply_actions(slide, actions: list[dict]) -> tuple[list[dict], list[dict]]:
    """Apply a list of actions to a slide.

    Returns (succeeded, failed). Order matters: remove actions should be sorted
    by descending para_idx per shape (else indexes shift). Caller can pre-sort;
    apply_actions itself does that sort.

    Never raises — every failure lands in `failed` with a reason.
    """
    if not isinstance(actions, list):
        return [], [{"error": f"actions must be a list, got {type(actions).__name__}"}]

    # Ordering rule (avoids index shift):
    #   1. All non-remove actions first (using original shape indexes as extracted)
    #   2. Then remove_bullet by desc (shape, para) to keep para indexes stable
    #   3. Finally remove_shape by desc shape_idx (removing higher first)
    # Rationale: if we removed shape earlier, subsequent replace_text would fail
    # because shape_idx changed. Removes come last.
    def sort_key(a):
        op = a.get("op") if isinstance(a, dict) else ""
        if op == "remove_shape":
            m = SHAPE_ID_RE.match(str(a.get("shape_id") or a.get("id") or ""))
            if not m:
                return (2, 0, 0)
            return (2, -int(m.group(1)), 0)  # LAST group, desc shape
        if op == "remove_bullet":
            m = PARA_ID_RE.match(str(a.get("id") or ""))
            if not m:
                return (1, 0, 0)
            return (1, -int(m.group(1)), -int(m.group(2)))  # 2nd group, desc
        return (0, 0, 0)  # first group: everything else, stable order

    ordered = sorted(actions, key=sort_key)
    succeeded: list[dict] = []
    failed: list[dict] = []
    for action in ordered:
        if not isinstance(action, dict):
            failed.append({"action": action, "error": "action not a dict"})
            continue
        op = action.get("op")
        fn = _OP_TABLE.get(op)
        if fn is None:
            failed.append({"action": action, "error": f"unknown op {op!r}"})
            continue
        try:
            kwargs = {k: v for k, v in action.items() if k != "op"}
            # Normalise: remove_shape accepts 'id' or 'shape_id' — always pass shape_id
            if op == "remove_shape":
                if "id" in kwargs and "shape_id" not in kwargs:
                    kwargs["shape_id"] = kwargs.pop("id")
            result = fn(slide, **kwargs)
            succeeded.append(result)
        except RevisionError as exc:
            failed.append({"action": action, "error": str(exc)})
        except TypeError as exc:
            failed.append({"action": action, "error": f"bad args: {exc}"})
        except Exception as exc:  # noqa: BLE001
            failed.append({"action": action, "error": f"{type(exc).__name__}: {exc}"})
    return succeeded, failed


# ──────────────────────────────────────────────────────────────────────────
# Slide-level convenience
# ──────────────────────────────────────────────────────────────────────────

def slide_extract_and_apply(pptx_path: str | Path, slide_idx: int, actions: list[dict],
                              out_path: str | Path | None = None) -> dict:
    """One-shot helper for unit tests / debugging.

    Opens the pptx, applies actions to slide `slide_idx` (0-based), and either
    saves to `out_path` or overwrites the file. Returns audit dict.
    """
    prs = Presentation(str(pptx_path))
    if slide_idx < 0 or slide_idx >= len(prs.slides):
        return {"ok": False, "error": f"slide_idx {slide_idx} out of range (0..{len(prs.slides)-1})"}
    slide = prs.slides[slide_idx]
    elements = extract_elements(slide)
    succeeded, failed = apply_actions(slide, actions)
    prs.save(str(out_path or pptx_path))
    return {
        "ok": not failed,
        "slide_idx": slide_idx,
        "elements_before": len(elements),
        "succeeded": succeeded,
        "failed": failed,
    }
