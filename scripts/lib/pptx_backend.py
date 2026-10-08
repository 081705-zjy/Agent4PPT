#!/usr/bin/env python3
"""pptx_backend.py — render + structural-validate backend for export-pptx.sh.

Driven entirely by environment variables set by export-pptx.sh:
  PPT_RUN_DIR    run directory (artifacts in/out)
  PPT_BACKEND    render backend id ("stub" | "native-svg" | "ppt-master-free";
                 "ppt-master"/"real" aliases)
  PPT_SMOKE      "1" => render only the smoke sample (cover + 1 content slide)
  PPT_MIN_RATIO  hard editability gate threshold (e.g. "0.8")

Subcommand is argv[1]: "render" or "validate".

The stub builds a genuinely editable deck (native text boxes) so editability
measurement is exercised end-to-end; the deck-quality gate still fails because
render_mode=stub (only render_mode=real may pass), per the plan.
"""
import base64
import datetime
import json
import os
import re
import sys
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt

import speaker_notes
import presentation_effects

RUN_DIR = os.environ["PPT_RUN_DIR"]
BACKEND_REQUESTED = os.environ.get("PPT_BACKEND", "stub")
SMOKE = os.environ.get("PPT_SMOKE", "0") == "1"
MIN_RATIO = float(os.environ.get("PPT_MIN_RATIO", "0.8"))


def normalize_backend(value):
    """Canonicalize legacy backend names into ppt-agent-owned capabilities."""
    v = str(value or "stub").strip()
    aliases = {
        "ppt-master": "ppt-master-free",
        "ppt_master": "native-svg",
        "real": "native-svg",
        "editable-drawingml": "native-svg",
        "editable-svg": "native-svg",
        "free": "ppt-master-free",
        "ppt-master-free": "ppt-master-free",
        "ppt_master_free": "ppt-master-free",
    }
    return aliases.get(v, v)


BACKEND = normalize_backend(BACKEND_REQUESTED)

# render_mode: only stub is orchestration-only; native/export backends are real.
RENDER_MODE = "stub" if BACKEND == "stub" else "real"

# A 1x1 transparent PNG — placeholder raster for screenshots/ (no headless
# renderer is available credential-free; slides-html/ is the real preview).
_PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _now():
    return os.environ.get("PPT_FAKE_NOW") or datetime.datetime.now(
        datetime.timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


# Manuscript labels that delimit the On-slide copy region within a slide block.
_OTHER_LABELS = (
    "Visual instruction:",
    "Speaker notes:",
    "QA notes:",
    "Source references:",
)


def parse_manuscript(path):
    """Return (slide_count, [ {title, paragraphs, table, body}, ... ]).

    The `On-slide copy:` label introduces a multi-line region (heading + bullets +
    optional markdown table) that ends at the next labelled section. The first heading
    in that region is the slide title; the remaining non-table lines are body
    paragraphs; contiguous `| ... |` rows become a native table. `body` is the joined
    paragraph text, kept for HTML preview and overflow measurement.
    """
    text = open(path, encoding="utf-8").read()
    slide_count = None
    m = re.search(r"^slide_count:\s*(\d+)", text, re.MULTILINE)
    if m:
        slide_count = int(m.group(1))
    # Drop the leading frontmatter block (first two '---' fences).
    lines_all = text.splitlines()
    fences = [i for i, line in enumerate(lines_all) if line.strip() == "---"]
    if len(fences) >= 2:
        body_text = "\n".join(lines_all[fences[1] + 1 :])
    else:
        body_text = text
    blocks = []
    for chunk in re.split(r"(?m)^---\s*$", body_text):
        chunk = chunk.strip()
        if not chunk:
            continue
        chunk_title = None
        for line in chunk.splitlines():
            hm = re.match(r"^##\s+Slide\s+\d+\s*:\s*(.*)$", line.strip(), re.IGNORECASE)
            if hm:
                chunk_title = hm.group(1).strip()
                break
            hm = re.match(r"^#{1,4}\s+(.*)$", line.strip())
            if hm:
                chunk_title = hm.group(1).strip()
                break
        # Collect the On-slide copy region (until the next labelled section).
        copy_lines = []
        in_copy = False
        for line in chunk.splitlines():
            stripped = line.strip()
            if stripped.startswith("On-slide copy:"):
                in_copy = True
                rest = stripped[len("On-slide copy:") :].strip()
                if rest:
                    copy_lines.append(rest)
                continue
            if in_copy and any(stripped.startswith(lb) for lb in _OTHER_LABELS):
                in_copy = False
                continue
            if in_copy:
                copy_lines.append(stripped)
        title = None
        paragraphs = []
        table_rows = []
        claim = ""
        evidence_sentence = ""
        left_box = {"heading": "", "body": []}
        right_box = {"heading": "", "body": []}
        footer_citations = ""
        current_box = None
        for line in copy_lines:
            if not line:
                continue
            lower = line.lower()
            if lower.startswith("claim:"):
                claim = line.split(":", 1)[1].strip()
                continue
            if lower.startswith("evidence sentence:"):
                evidence_sentence = line.split(":", 1)[1].strip()
                paragraphs.append(evidence_sentence)
                continue
            if lower.startswith("left box:"):
                left_box["heading"] = line.split(":", 1)[1].strip()
                current_box = "left"
                continue
            if lower.startswith("right box:"):
                right_box["heading"] = line.split(":", 1)[1].strip()
                current_box = "right"
                continue
            if re.match(r"^[A-Za-z][A-Za-z /_-]{0,40}:\s*$", line) and current_box in {"left", "right"}:
                current_box = None
                paragraphs.append(line)
                continue
            if lower.startswith("footer citations:"):
                footer_citations = line.split(":", 1)[1].strip()
                current_box = None
                continue
            if line.startswith("- ") and current_box in {"left", "right"}:
                (left_box if current_box == "left" else right_box)["body"].append(line[2:].strip())
                continue
            hm = re.match(r"^#{1,4}\s+(.*)$", line)
            if hm:
                if title is None:
                    title = hm.group(1).strip()
                else:
                    paragraphs.append(hm.group(1).strip())
                continue
            if line.startswith("|") and line.endswith("|"):
                cells = [c.strip() for c in line.strip("|").split("|")]
                # Skip markdown separator rows (---|:--:| etc.).
                if all(re.fullmatch(r":?-{2,}:?", (c or "-")) for c in cells):
                    continue
                table_rows.append(cells)
                continue
            paragraphs.append(line)
        blocks.append(
            {
                "title": title or chunk_title or "Slide",
                "paragraphs": paragraphs,
                "table": table_rows or None,
                "body": " ".join(paragraphs).strip(),
                "claim": claim,
                "evidence_sentence": evidence_sentence,
                "left_box": left_box,
                "right_box": right_box,
                "footer_citations": footer_citations,
            }
        )
    if slide_count is None:
        slide_count = len(blocks)
    return slide_count, blocks


def _style_primary_hex():
    """Read the first hex color from style-guide.md Palette, else a default."""
    sg = os.path.join(RUN_DIR, "style-guide.md")
    if os.path.exists(sg):
        m = re.search(r"#([0-9A-Fa-f]{6})", open(sg, encoding="utf-8").read())
        if m:
            return m.group(1)
    return "1F3A5F"


def _visual_theme():
    vp = os.path.join(RUN_DIR, "visual-plan.json")
    if not os.path.exists(vp):
        return {}
    try:
        data = json.load(open(vp, encoding="utf-8"))
        return data.get("theme", {}) if isinstance(data.get("theme", {}), dict) else {}
    except Exception:
        return {}


def _hex_from_theme(theme, key, default):
    value = str(theme.get("palette", {}).get(key, default)).strip().lstrip("#")
    return value if re.fullmatch(r"[0-9A-Fa-f]{6}", value) else default


def _float_from_theme(theme, key, default):
    try:
        return float(theme.get("render", {}).get(key, default))
    except (TypeError, ValueError):
        return default


def _int_from_theme(theme, key, default):
    try:
        return int(theme.get("typography", {}).get(key, default))
    except (TypeError, ValueError):
        return default


def _template_palette():
    """Authoritative deck colors from template-profile.json palette (hex w/o '#')."""
    pal = {
        "primary": "17324D",
        "secondary": "2E7D8A",
        "accent": "DCA24C",
        "neutral": "F6F7F9",
        "text": "151A1F",
    }
    tp = os.path.join(RUN_DIR, "template-profile.json")
    if os.path.exists(tp):
        try:
            d = json.load(open(tp, encoding="utf-8")).get("palette", {})
            for k in pal:
                v = str(d.get(k, "")).strip().lstrip("#")
                if re.fullmatch(r"[0-9A-Fa-f]{6}", v):
                    pal[k] = v
        except Exception:
            pass
    return pal


# Editable elements whose presence implies a native concept shape / diagram on a slide.
_DIAGRAM_HINTS = ("diagram", "concept", "ring", "pyramid", "triangle", "radial", "shape")


def visual_elements_by_slide():
    """Return {1-based slide_index: [editable_element names]} from visual-plan.json."""
    vp = os.path.join(RUN_DIR, "visual-plan.json")
    out = {}
    if not os.path.exists(vp):
        return out
    try:
        data = json.load(open(vp, encoding="utf-8"))
        for s in data.get("slides", []):
            idx = int(s.get("slide_index", 0))
            if idx > 0:
                out[idx] = s.get("editable_elements", []) or []
    except Exception:
        return {}
    return out


# Layouts that stay clean (no concept diagram): cover, closing, section dividers.
_NO_DIAGRAM_LAYOUTS = ("title", "closing", "section")


def visual_layout_by_slide():
    """Return {1-based slide_index: layout_type} from visual-plan.json."""
    vp = os.path.join(RUN_DIR, "visual-plan.json")
    out = {}
    if not os.path.exists(vp):
        return out
    try:
        data = json.load(open(vp, encoding="utf-8"))
        for s in data.get("slides", []):
            idx = int(s.get("slide_index", 0))
            if idx > 0:
                out[idx] = str(s.get("layout_type", ""))
    except Exception:
        return {}
    return out


def visual_assets_by_slide():
    """Return {1-based slide_index: [asset relpaths]} from visual-plan.json."""
    vp = os.path.join(RUN_DIR, "visual-plan.json")
    out = {}
    if not os.path.exists(vp):
        return out
    try:
        data = json.load(open(vp, encoding="utf-8"))
        for s in data.get("slides", []):
            idx = int(s.get("slide_index", 0))
            assets = s.get("assets", []) or []
            rels = []
            for asset in assets:
                if isinstance(asset, dict):
                    rel = str(asset.get("local_path") or asset.get("path") or "")
                else:
                    rel = str(asset or "")
                if os.path.splitext(rel.lower())[1] in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                    rels.append(rel)
            if idx > 0 and rels:
                out[idx] = rels
    except Exception:
        return {}
    return out


# Generic lead-in words: when a bullet is "<lead>：<content>", the content is the
# substantive label, so the node uses the content rather than the generic prefix.
_GENERIC_LEADS = (
    "矛盾", "解法", "定位", "结论", "趋势", "职责", "典型用途", "典型对象", "关系",
    "关系定位", "纠偏", "演进", "标注", "要点", "核心", "难点", "目标", "方法",
    "场景", "边界", "工作定义", "适配", "用途", "对象",
)
# Item/marker separators used to cut a bullet down to its first clean clause. Deliberately
# EXCLUDES "/" and "→" so compound terms like "冷/热分层" and "热→内存/快存" stay intact.
_NODE_SEPS = ("：", ":", "　", "•", "；", ";", "↔", "——", "—", " = ", "=", "，", ",", " ", "（", "(", "‘", "’")


def _diagram_nodes(blk):
    """Derive up to 3 short, COMPLETE, marker-free node labels from a slide's bullets.

    Prefers the content after a generic lead-in ("矛盾：X" -> X), splits multi-item
    bullet lines to the first item, cuts at the earliest structural separator, and strips
    stray bullet/quote markers — so labels are never truncated mid-phrase nor carry a
    dangling "•"."""
    def first_clause(s):
        cut = len(s)
        for sep in _NODE_SEPS:
            i = s.find(sep)
            if i > 0:
                cut = min(cut, i)
        return s[:cut].strip().strip("‘’'\"·•—- ")

    nodes = []
    for p in blk.get("paragraphs", []) or []:
        s = p.lstrip("•-·*　 ").strip()
        if not s or s.endswith("：") or s.endswith(":"):
            continue  # skip lead-in lines like "要点：" / "示意对照："
        # If "<generic lead>：<content>", use the content.
        for c in ("：", ":"):
            if c in s:
                lead, _, rest = s.partition(c)
                if lead.strip() in _GENERIC_LEADS and rest.strip():
                    s = rest.strip()
                break
        label = first_clause(s)
        if len(label) > 14:
            label = label[:14]
        if label:
            nodes.append(label)
        if len(nodes) >= 3:
            break
    return nodes


def _set_cjk_fonts(prs):
    """Set the Latin + East Asian typeface on every run so CJK glyphs render in
    PowerPoint (size/color are left as authored). Tables and text boxes both covered."""
    from pptx.oxml.ns import qn

    def fix_run(run):
        run.font.name = CJK_FAMILY  # creates a:latin
        rpr = run._r.get_or_add_rPr()
        for tag in ("a:ea", "a:cs"):
            el = rpr.find(qn(tag))
            if el is None:
                el = rpr.makeelement(qn(tag), {})
                rpr.append(el)
            el.set("typeface", CJK_FAMILY)

    def fix_tf(tf):
        for para in tf.paragraphs:
            for run in para.runs:
                fix_run(run)

    for slide in prs.slides:
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                fix_tf(shape.text_frame)
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    for cell in row.cells:
                        fix_tf(cell.text_frame)


def build_deck(blocks):
    """Build a Presentation with native (editable) title + body text boxes.

    The real (`ppt-master`) backend additionally consumes the style guide and emits an
    extra native, style-colored accent shape per slide — a genuinely distinct, richer
    render path than the orchestration-only `stub` (not merely a render_mode tag).
    """
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE

    prs = Presentation()
    blank = prs.slide_layouts[6]  # truly blank layout — we add our own text boxes
    is_real = RENDER_MODE == "real"
    theme = _visual_theme() if is_real else {}
    pal = _template_palette()
    primary = _hex_from_theme(theme, "primary", pal["primary"]) if is_real else None
    accent = pal["accent"]
    neutral = pal["neutral"]
    text_color = _hex_from_theme(theme, "text", pal["text"]) if is_real else pal["text"]
    heading_size = _int_from_theme(theme, "heading_size", 32)
    body_size = _int_from_theme(theme, "body_size", 18)
    accent_h = _float_from_theme(theme, "accent_bar_height", 0.25)
    pic_x = _float_from_theme(theme, "picture_x", 6.45)
    pic_y = _float_from_theme(theme, "picture_y", 1.2)
    pic_w = _float_from_theme(theme, "picture_w", 3.0)
    pic_h = _float_from_theme(theme, "picture_h", 1.7)
    assets_by_slide = visual_assets_by_slide() if is_real else {}
    elements_by_slide = visual_elements_by_slide() if is_real else {}
    layouts_by_slide = visual_layout_by_slide() if is_real else {}
    for idx, blk in enumerate(blocks, 1):
        slide = prs.slides.add_slide(blank)
        elements = elements_by_slide.get(idx, [])
        layout = layouts_by_slide.get(idx, "")
        has_asset = bool(assets_by_slide.get(idx))
        # A native concept shape stands in for the planned diagram when no raster asset
        # exists, so the deck keeps text-image balance with fully editable objects.
        # Cover/closing/section layouts stay clean (no diagram).
        want_diagram = (
            is_real
            and not has_asset
            and not blk["table"]
            and layout not in _NO_DIAGRAM_LAYOUTS
            and any(any(h in str(e).lower() for h in _DIAGRAM_HINTS) for e in elements)
        )
        is_cover = layout in ("title", "section")
        if is_real:
            # Style-driven accent bar (native auto-shape) — only the real backend draws it.
            bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.0), Inches(0.0), Inches(10.0), Inches(accent_h))
            bar.fill.solid()
            bar.fill.fore_color.rgb = RGBColor.from_string(primary)
            bar.line.fill.background()
            for rel in assets_by_slide.get(idx, [])[:1]:
                asset_path = os.path.join(RUN_DIR, rel)
                if os.path.exists(asset_path):
                    slide.shapes.add_picture(asset_path, Inches(pic_x), Inches(pic_y), width=Inches(pic_w), height=Inches(pic_h))
        tb = slide.shapes.add_textbox(Inches(0.6), Inches(0.4), Inches(9.0), Inches(1.2))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.text = blk["title"]
        title_pt = 40 if is_cover else heading_size
        tf.paragraphs[0].runs[0].font.size = Pt(title_pt)
        tf.paragraphs[0].runs[0].font.bold = True
        tf.paragraphs[0].runs[0].font.color.rgb = RGBColor.from_string(primary or text_color)
        # Body text box: one native paragraph per copy line (all editable).
        narrow = has_asset or want_diagram or is_cover
        body_width = Inches(5.55) if narrow else Inches(9.0)
        bb = slide.shapes.add_textbox(Inches(0.6), Inches(1.8), body_width, Inches(4.4))
        bf = bb.text_frame
        bf.word_wrap = True
        paras = blk["paragraphs"] or [blk["body"] or "(speaker-supported slide)"]
        bf.text = paras[0]
        bf.paragraphs[0].runs[0].font.size = Pt(body_size)
        bf.paragraphs[0].runs[0].font.color.rgb = RGBColor.from_string(text_color)
        for p in paras[1:]:
            par = bf.add_paragraph()
            run = par.add_run()
            run.text = p
            run.font.size = Pt(body_size)
            run.font.color.rgb = RGBColor.from_string(text_color)
        # Restrained native cover accent block (matches `cover_accent_block` in the plan):
        # a short accent rule + a soft neutral panel that composes the otherwise sparse cover.
        if is_cover:
            panel = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(6.7), Inches(1.4), Inches(2.7), Inches(4.6))
            panel.fill.solid()
            panel.fill.fore_color.rgb = RGBColor.from_string(neutral)
            panel.line.fill.background()
            # Accent stripe + caption make the panel read as an intentional accent area.
            stripe = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(6.7), Inches(1.4), Inches(0.14), Inches(4.6))
            stripe.fill.solid()
            stripe.fill.fore_color.rgb = RGBColor.from_string(accent)
            stripe.line.fill.background()
            cap = slide.shapes.add_textbox(Inches(7.0), Inches(1.7), Inches(2.3), Inches(1.4))
            ctf = cap.text_frame
            ctf.word_wrap = True
            ctf.text = "记忆基座"
            ctf.paragraphs[0].runs[0].font.size = Pt(20)
            ctf.paragraphs[0].runs[0].font.bold = True
            ctf.paragraphs[0].runs[0].font.color.rgb = RGBColor.from_string(primary)
            csub = ctf.add_paragraph()
            crun = csub.add_run()
            crun.text = "Memory Substrate"
            crun.font.size = Pt(14)
            crun.font.color.rgb = RGBColor.from_string(text_color)
            rule = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.62), Inches(5.5), Inches(3.4), Inches(0.16))
            rule.fill.solid()
            rule.fill.fore_color.rgb = RGBColor.from_string(accent)
            rule.line.fill.background()
        # Native concept diagram on the right: a header node + up to 3 labelled nodes
        # (each a real, editable auto-shape with text) wired in a vertical flow.
        if want_diagram:
            nodes = _diagram_nodes(blk)
            cx, cw = pic_x, pic_w
            top = max(pic_y, 1.8)  # clear wrapped 2-line titles
            # Header node (filled with primary, white label).
            head = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(cx), Inches(top), Inches(cw), Inches(0.6))
            head.fill.solid()
            head.fill.fore_color.rgb = RGBColor.from_string(primary)
            head.line.fill.background()
            htf = head.text_frame
            htf.word_wrap = True
            htf.text = "示意图 / Concept"
            htf.paragraphs[0].runs[0].font.size = Pt(16)
            htf.paragraphs[0].runs[0].font.color.rgb = RGBColor.from_string("FFFFFF")
            ny = top + 0.95
            for n in nodes:
                node = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(cx), Inches(ny), Inches(cw), Inches(0.82))
                node.fill.solid()
                node.fill.fore_color.rgb = RGBColor.from_string(neutral)
                node.line.color.rgb = RGBColor.from_string(primary)
                ntf = node.text_frame
                ntf.word_wrap = True
                ntf.text = n
                ntf.paragraphs[0].runs[0].font.size = Pt(18)
                ntf.paragraphs[0].runs[0].font.color.rgb = RGBColor.from_string(text_color)
                # Connector from the previous node/header down to this one.
                conn = slide.shapes.add_connector(2, Inches(cx + cw / 2), Inches(ny - 0.18), Inches(cx + cw / 2), Inches(ny))
                conn.line.color.rgb = RGBColor.from_string(primary)
                ny += 1.05
        # Native, editable comparison table.
        if blk["table"]:
            rows = blk["table"]
            ncols = max(len(r) for r in rows)
            top = Inches(1.8 + 0.32 * max(1, len(paras)))
            gframe = slide.shapes.add_table(len(rows), ncols, Inches(0.6), top, Inches(8.9), Inches(0.4 * len(rows)))
            tbl = gframe.table
            for r, row in enumerate(rows):
                for c in range(ncols):
                    cell = tbl.cell(r, c)
                    cell.text = row[c] if c < len(row) else ""
                    cpara = cell.text_frame.paragraphs[0]
                    if cpara.runs:
                        cpara.runs[0].font.size = Pt(12)
                        cpara.runs[0].font.color.rgb = RGBColor.from_string(primary if r == 0 else text_color)
    _set_cjk_fonts(prs)
    return prs


def measure_editability(prs):
    """Per-slide and aggregate editable_ratio over the rendered deck."""
    per_slide = []
    tot_edit = 0
    tot_sig = 0
    for slide in prs.slides:
        edit = 0
        sig = 0
        for shape in slide.shapes:
            if getattr(shape, "has_chart", False) or getattr(shape, "has_table", False):
                edit += 1
                sig += 1
            elif getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
                edit += 1
                sig += 1
            elif str(getattr(shape, "shape_type", "")).startswith("PICTURE"):
                sig += 1  # placed picture: significant but not editable
            elif getattr(shape, "has_text_frame", False):
                edit += 1
                sig += 1  # empty auto-shape / placeholder still editable
        ratio = (edit / sig) if sig else 1.0
        per_slide.append(round(ratio, 4))
        tot_edit += edit
        tot_sig += sig
    aggregate = (tot_edit / tot_sig) if tot_sig else 1.0
    return per_slide, round(aggregate, 4)


def referenced_assets():
    """Local asset paths declared by visual-plan.json + asset-manifest.json."""
    paths = []

    def add_asset_path(value):
        if isinstance(value, str) and value:
            paths.append(value)
            return
        if not isinstance(value, dict):
            return
        candidate = (
            value.get("local_path")
            or value.get("path")
            or value.get("asset_path")
            or value.get("source_path")
        )
        if isinstance(candidate, str) and candidate:
            paths.append(candidate)

    vp = os.path.join(RUN_DIR, "visual-plan.json")
    if os.path.exists(vp):
        try:
            data = json.load(open(vp, encoding="utf-8"))
            for s in data.get("slides", []):
                for asset in s.get("assets", []) or []:
                    add_asset_path(asset)
        except Exception:
            pass
    am = os.path.join(RUN_DIR, "asset-manifest.json")
    if os.path.exists(am):
        try:
            data = json.load(open(am, encoding="utf-8"))
            for a in data.get("assets", []):
                add_asset_path(a)
        except Exception:
            pass
    return paths


def write_html(out_dir, blocks):
    html_dir = os.path.join(out_dir, "slides-html")
    os.makedirs(html_dir, exist_ok=True)
    for i, blk in enumerate(blocks, 1):
        title = blk["title"].replace("<", "&lt;").replace(">", "&gt;")
        body = blk["body"].replace("<", "&lt;").replace(">", "&gt;")
        with open(os.path.join(html_dir, f"slide-{i}.html"), "w", encoding="utf-8") as f:
            f.write(
                f"<!doctype html><meta charset=utf-8><title>{title}</title>"
                f"<section><h1>{title}</h1><p>{body}</p></section>\n"
            )


def _cjk_font_path():
    """Locate a CJK-capable TTF/OTF (env override, ~/.fonts, then fontconfig)."""
    cand = [os.environ.get("PPT_CJK_FONT", "")]
    cand.append(os.path.expanduser("~/.fonts/NotoSansCJKsc-Regular.otf"))
    for p in cand:
        if p and os.path.exists(p):
            return p
    try:
        import subprocess

        out = subprocess.run(
            ["fc-match", "-f", "%{file}", ":lang=zh"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        if out and os.path.exists(out):
            return out
    except Exception:
        pass
    return ""


# Font family name PowerPoint should use for CJK + Latin glyphs (must be installed
# on the viewer's machine; macOS/Windows ship CJK fonts so the editable deck renders).
CJK_FAMILY = "Noto Sans CJK SC"


def _load_font(size, bold=False):
    from PIL import ImageFont

    cjk = _cjk_font_path()
    if cjk:
        try:
            return ImageFont.truetype(cjk, size)
        except Exception:
            pass
    path = "/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if bold else "")
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    """Greedy wrap supporting CJK (per-char) and Latin (per-word)."""
    words = text.split(" ")
    lines, cur = [], ""

    def width(s):
        try:
            return draw.textlength(s, font=font)
        except Exception:
            return len(s) * font.size * 0.6

    for w in words:
        # Break very long unbroken (CJK) runs character by character.
        if width(w) > max_w:
            for ch in w:
                trial = cur + ch
                if width(trial) <= max_w:
                    cur = trial
                else:
                    lines.append(cur)
                    cur = ch
            continue
        trial = (cur + " " + w).strip()
        if width(trial) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def write_screenshots(out_dir, blocks, elements_by_slide, layouts_by_slide=None):
    """Render valid presentation-resolution (1280x720) PNG previews per slide.

    Uses Pillow with a structural layout (accent bar, title, body paragraphs, native
    concept-shape / table sketch) so screenshots are inspectable artifacts rather than
    placeholder 1x1 rasters. Falls back to a 1x1 PNG only if Pillow is unavailable.
    """
    shot_dir = os.path.join(out_dir, "screenshots")
    os.makedirs(shot_dir, exist_ok=True)
    layouts_by_slide = layouts_by_slide or {}
    try:
        from PIL import Image, ImageDraw
    except Exception:
        for i in range(1, len(blocks) + 1):
            with open(os.path.join(shot_dir, f"slide-{i}.png"), "wb") as f:
                f.write(_PNG_1x1)
        return

    pal = _template_palette()

    def rgb(hexv):
        return tuple(int(hexv[k : k + 2], 16) for k in (0, 2, 4))

    W, H = 1280, 720
    primary, accent, neutral, text = (
        rgb(pal["primary"]),
        rgb(pal["accent"]),
        rgb(pal["neutral"]),
        rgb(pal["text"]),
    )
    title_font = _load_font(40, bold=True)
    body_font = _load_font(24)
    node_font = _load_font(26)  # structural diagram labels: >= body, never tiny
    small_font = _load_font(18)
    for i, blk in enumerate(blocks, 1):
        img = Image.new("RGB", (W, H), (255, 255, 255))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 16], fill=primary)  # accent bar
        elements = elements_by_slide.get(i, [])
        layout = layouts_by_slide.get(i, "")
        has_diagram = (
            blk.get("table") is None
            and layout not in _NO_DIAGRAM_LAYOUTS
            and any(any(h in str(e).lower() for h in _DIAGRAM_HINTS) for e in elements)
        )
        right_margin = 430 if (has_diagram or blk.get("table") or layout in ("title", "section")) else 90
        col_w = W - 80 - right_margin
        # Title (wrapped).
        y = 56
        for ln in _wrap(d, blk["title"], title_font, W - 140):
            d.text((60, y), ln, fill=primary, font=title_font)
            y += 52
        d.line([(60, y + 4), (W - 80, y + 4)], fill=accent, width=3)
        y += 26
        # Body paragraphs.
        for p in (blk.get("paragraphs") or [blk.get("body", "")]):
            for ln in _wrap(d, p, body_font, col_w):
                if y > H - 50:
                    break
                d.text((60, y), ln, fill=text, font=body_font)
                y += 32
            y += 6
        # Restrained cover accent block (mirrors the deck's `cover_accent_block`).
        if layout in ("title", "section"):
            d.rectangle([858, 130, 1216, 600], fill=neutral)
            d.rectangle([858, 130, 872, 600], fill=accent)  # accent stripe
            d.text((895, 158), "记忆基座", fill=primary, font=body_font)
            d.text((895, 200), "Memory Substrate", fill=text, font=small_font)
            d.rectangle([60, 360, 420, 376], fill=accent)
        # Concept diagram sketch on the right: header node + up to 3 labelled nodes.
        if has_diagram:
            x0, x1 = W - right_margin + 10, W - 60
            d.rounded_rectangle([x0, 188, x1, 240], radius=12, fill=primary)
            d.text((x0 + 20, 202), "示意图 / Concept", fill=(255, 255, 255), font=small_font)
            ny = 272
            inner_w = (x1 - x0) - 40
            for n in _diagram_nodes(blk):
                lines = _wrap(d, n, node_font, inner_w)[:2]
                box_h = 28 + 32 * len(lines)
                d.line([((x0 + x1) // 2, ny - 32), ((x0 + x1) // 2, ny)], fill=primary, width=2)
                d.rounded_rectangle([x0, ny, x1, ny + box_h], radius=12, outline=primary, width=2, fill=neutral)
                for k, ln in enumerate(lines):
                    d.text((x0 + 20, ny + 12 + k * 32), ln, fill=text, font=node_font)
                ny += box_h + 30
        # Table sketch.
        if blk.get("table"):
            rows = blk["table"]
            ncols = max(len(r) for r in rows)
            tx, ty, tw = 60, y + 4, W - 140
            rh = min(46, (H - ty - 30) // max(1, len(rows)))
            cw = tw // max(1, ncols)
            for r in range(len(rows)):
                for c in range(ncols):
                    x0, yy0 = tx + c * cw, ty + r * rh
                    d.rectangle([x0, yy0, x0 + cw, yy0 + rh], outline=primary, fill=(neutral if r == 0 else (255, 255, 255)))
                    cell = rows[r][c] if c < len(rows[r]) else ""
                    d.text((x0 + 6, yy0 + 10), cell[:8], fill=(primary if r == 0 else text), font=small_font)
        img.save(os.path.join(shot_dir, f"slide-{i}.png"))


def atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _agent_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _skeleton_context():
    """Return (profile, scripts_dir) for the SVG->PPTX page renderer when available.

    With a user template, a real profile from the ppt-master import drives the SVG
    skeleton render path. Without a user template, a free-design SVG profile still
    routes through the same ppt-master SVG-to-DrawingML converter, which is much
    closer to ppt-master's page-level design path than the python-pptx fallback."""
    if RENDER_MODE != "real":
        return None
    root = _agent_root()
    try:
        cfg = json.load(open(os.path.join(root, "config/default_config.json"), encoding="utf-8"))
    except Exception:
        cfg = {}
    if not cfg.get("template_skeleton_render", True):
        return None
    import sys as _sys

    _sys.path.insert(0, os.path.join(root, "scripts", "lib"))
    import template_ingest

    scripts_dir = template_ingest.vendored_scripts_dir(Path(root))
    if not (scripts_dir / "svg_to_pptx.py").exists():
        return None
    tp = os.path.join(RUN_DIR, "template-profile.json")
    profile = {}
    try:
        if os.path.exists(tp):
            profile = json.load(open(tp, encoding="utf-8"))
    except Exception:
        profile = {}
    if BACKEND == "ppt-master-free":
        page_type_layouts = profile.get("page_type_layouts") if isinstance(profile.get("page_type_layouts"), dict) else {}
        if not page_type_layouts:
            page_type_layouts = {
                "cover": {
                    "title_region": {"x": 72, "y": 88, "width": 760, "height": 160},
                    "body_region": {"x": 72, "y": 280, "width": 650, "height": 330},
                },
                "content": {
                    "title_region": {"x": 72, "y": 54, "width": 1060, "height": 92},
                    "body_region": {"x": 72, "y": 160, "width": 1060, "height": 470},
                },
                "ending": {
                    "title_region": {"x": 72, "y": 92, "width": 920, "height": 150},
                    "body_region": {"x": 72, "y": 280, "width": 820, "height": 310},
                },
            }
        profile = {
            **profile,
            "skeleton_render": True,
            "render_source": "ppt_master_free_design",
            "free_page_generation": True,
            "palette": profile.get("palette") or _template_palette(),
            "canvas": profile.get("canvas") or {"width_px": 1280, "height_px": 720},
            "page_type_layouts": page_type_layouts,
        }
        return profile, scripts_dir
    if profile.get("skeleton_render") and profile.get("template_import_dir"):
        import_dir = os.path.join(RUN_DIR, profile["template_import_dir"])
        if os.path.exists(os.path.join(import_dir, "manifest.json")):
            return profile, scripts_dir
    profile = {
        "skeleton_render": True,
        "render_source": "free_design_svg",
        "palette": _template_palette(),
        "canvas": {"width_px": 1280, "height_px": 720},
        "page_type_layouts": {
            "cover": {
                "title_region": {"x": 72, "y": 88, "width": 760, "height": 160},
                "body_region": {"x": 72, "y": 280, "width": 650, "height": 330},
            },
            "content": {
                "title_region": {"x": 72, "y": 54, "width": 1060, "height": 92},
                "body_region": {"x": 72, "y": 160, "width": 1060, "height": 470},
            },
            "ending": {
                "title_region": {"x": 72, "y": 92, "width": 920, "height": 150},
                "body_region": {"x": 72, "y": 280, "width": 820, "height": 310},
            },
        },
    }
    return profile, scripts_dir


def cmd_render():
    slide_count, blocks = parse_manuscript(os.path.join(RUN_DIR, "manuscript.md"))
    out_dir = RUN_DIR
    rendered = blocks
    if SMOKE:
        out_dir = os.path.join(RUN_DIR, "smoke")
        os.makedirs(out_dir, exist_ok=True)
        # Cover + one representative content slide.
        rendered = blocks[:1] + (blocks[1:2] if len(blocks) > 1 else [])
    # Template-inheriting path: when a ppt-master template package is present, render by
    # inheriting the template's layout SVG skeletons and exporting native DrawingML.
    skel = _skeleton_context()
    if skel is not None:
        profile, scripts_dir = skel
        import sys as _sys

        _sys.path.insert(0, os.path.join(_agent_root(), "scripts", "lib"))
        import svg_skeleton_render

        try:
            svg_skeleton_render.render(
                RUN_DIR, out_dir, rendered, SMOKE, BACKEND, MIN_RATIO,
                scripts_dir, profile, slide_count,
            )
            return
        except SystemExit:
            print("[export-pptx] skeleton render failed; strict template mode blocks fallback", file=sys.stderr)
            raise
        except Exception as e:  # noqa: BLE001
            print(f"[export-pptx] skeleton render error ({e}); strict template mode blocks fallback", file=sys.stderr)
            raise SystemExit(1) from e
    prs = build_deck(rendered)
    deck_path = os.path.join(out_dir, "deck.pptx")
    prs.save(deck_path)
    if not SMOKE and os.path.exists(os.path.join(RUN_DIR, "speaker-notes.md")):
        speaker_notes.embed_notes(Path(deck_path), Path(RUN_DIR) / "speaker-notes.md")
    if not SMOKE and os.path.exists(os.path.join(RUN_DIR, "transition-plan.json")):
        presentation_effects.apply_transitions(Path(deck_path), Path(RUN_DIR) / "transition-plan.json")
    write_html(out_dir, rendered)
    write_screenshots(out_dir, rendered, visual_elements_by_slide(), visual_layout_by_slide())
    per_slide, aggregate = measure_editability(prs)
    page_count = len(rendered)
    # In smoke mode the expected page count is the smoke sample size, not slide_count.
    expected = len(rendered) if SMOKE else slide_count
    page_count_ok = page_count == expected
    missing = [p for p in referenced_assets() if not os.path.exists(os.path.join(RUN_DIR, p))]
    assets_ok = len(missing) == 0
    ts = _now()
    lines = [
        "---",
        'schema_version: "1.0"',
        f'generated_at: "{ts}"',
        f'render_mode: "{RENDER_MODE}"',
        f'backend: "{BACKEND}"',
        f"smoke: {str(SMOKE).lower()}",
        f"slide_count: {expected}",
        f"page_count: {page_count}",
        f"page_count_ok: {str(page_count_ok).lower()}",
        "openable: true",
        f"assets_ok: {str(assets_ok).lower()}",
        f"aggregate_editable_ratio: {aggregate}",
        f"min_editable_ratio: {MIN_RATIO}",
        "---",
        "",
        "## Per-slide editable_ratio",
    ]
    for i, r in enumerate(per_slide, 1):
        lines.append(f"- slide {i}: {r}")
    if missing:
        lines.append("")
        lines.append("## Missing assets")
        for p in missing:
            lines.append(f"- {p}")
    atomic_write(os.path.join(out_dir, "render-log.md"), "\n".join(lines) + "\n")
    print(f"[export-pptx] rendered {page_count} slide(s) -> {deck_path} (mode={RENDER_MODE})")


def _fm_value(text, key):
    m = re.search(rf"^{re.escape(key)}:\s*(.*)$", text, re.MULTILINE)
    if not m:
        return None
    return m.group(1).strip().strip('"')


def _validation_visual_plan():
    path = Path(RUN_DIR) / "visual-plan.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for item in data.get("slides", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("slide_index") or item.get("index") or 0)
        except Exception:
            idx = 0
        if idx:
            out[idx] = {
                "layout_type": str(item.get("layout_type") or "").lower(),
                "visual_type": str(item.get("visual_type") or "").lower(),
                "component_id": str(item.get("component_id") or "").lower(),
            }
    return out


def _text_width_units(text: str) -> float:
    total = 0.0
    for ch in str(text or ""):
        if ord(ch) > 0x2E80:
            total += 1.02
        elif ch in " .,:;'\"|!iltf":
            total += 0.34
        else:
            total += 0.56
    return total


def cmd_validate():
    deck_path = os.path.join(RUN_DIR, "deck.pptx")
    slide_count, _blocks = parse_manuscript(os.path.join(RUN_DIR, "manuscript.md"))
    visual_plan = _validation_visual_plan()
    openable = False
    page_count = 0
    per_slide, aggregate = [], 0.0
    overflow_ok = True
    overflow_warnings = []
    try:
        prs = Presentation(deck_path)
        openable = True
        page_count = len(prs.slides)
        per_slide, aggregate = measure_editability(prs)
        # Conservative overflow heuristic. PowerPoint does not expose a reliable
        # rendered-overflow bit, so combine reopened text-frame budgets with
        # manuscript-level budgets for dense two-box evidence pages.
        for slide_idx, slide in enumerate(prs.slides, 1):
            for shape in slide.shapes:
                if getattr(shape, "has_text_frame", False):
                    text_value = shape.text_frame.text
                    if len(text_value) > 700:
                        overflow_ok = False
                        overflow_warnings.append(f"slide {slide_idx}: text frame exceeds 700 characters")
                    if "..." in text_value:
                        overflow_ok = False
                        overflow_warnings.append(f"slide {slide_idx}: visible ellipsis suggests text truncation")
                    if "References:" in text_value:
                        overflow_ok = False
                        overflow_warnings.append(f"slide {slide_idx}: long References footer should be shortened to Sources: [n]")
    except Exception as e:  # noqa: BLE001 — any open failure means not openable
        print(f"[export-pptx] deck not openable: {e}", file=sys.stderr)

    for slide_idx, block in enumerate(_blocks, 1):
        vp = visual_plan.get(slide_idx, {})
        layout = str(vp.get("layout_type") or "").lower()
        visual_type = str(vp.get("visual_type") or "").lower()
        component_id = str(vp.get("component_id") or "").lower()
        compact_visual_page = (
            layout in {
                "evidence-matrix",
                "comparison-matrix",
                "risk-boundary-table",
                "roadmap",
                "layered-architecture",
                "process-flow",
                "timeline",
            }
            or visual_type in {"table", "diagram"}
            or component_id.startswith("editable_")
        )
        claim = str(block.get("claim") or "")
        evidence = str(block.get("evidence_sentence") or "")
        claim_two_line_budget = (1280.0 - 2 * max(54.0, 1280.0 * 0.065) - 34.0) / 18.5 * 2
        if claim and _text_width_units(claim) > claim_two_line_budget:
            overflow_ok = False
            overflow_warnings.append(f"slide {slide_idx}: claim is too long for two-line assertion box")
        if evidence and len(evidence) > 125 and not compact_visual_page:
            overflow_ok = False
            overflow_warnings.append(f"slide {slide_idx}: evidence sentence may be visually compressed")
        for side in ("left_box", "right_box"):
            box = block.get(side) or {}
            body = box.get("body") or []
            if isinstance(body, str):
                body = [body]
            if len(body) > 3:
                overflow_ok = False
                overflow_warnings.append(f"slide {slide_idx}: {side} has {len(body)} bullets; renderer will show first 3")
            for item in body:
                if len(str(item)) > 96:
                    overflow_ok = False
                    overflow_warnings.append(f"slide {slide_idx}: {side} bullet exceeds compact two-line budget")

    # The editability number used by the gate is the value MEASURED from the reopened
    # deck — NEVER a value copied from render-log.md. render-log is only consulted for
    # render_mode (the render output's own declaration) and recorded for comparison, so
    # a deck whose render log falsely claims a high ratio cannot pass the hard gate.
    measured_aggregate = aggregate
    render_mode = RENDER_MODE
    render_log_aggregate = None
    rl = os.path.join(RUN_DIR, "render-log.md")
    if os.path.exists(rl):
        rl_text = open(rl, encoding="utf-8").read()
        render_mode = _fm_value(rl_text, "render_mode") or render_mode
        rl_ratio = _fm_value(rl_text, "aggregate_editable_ratio")
        if rl_ratio is not None:
            try:
                render_log_aggregate = float(rl_ratio)
            except ValueError:
                render_log_aggregate = None

    page_count_ok = page_count == slide_count
    missing = [p for p in referenced_assets() if not os.path.exists(os.path.join(RUN_DIR, p))]
    assets_ok = len(missing) == 0
    speaker_notes_count = speaker_notes.count_notes(Path(deck_path)) if openable else 0
    speaker_notes_expected = os.path.exists(os.path.join(RUN_DIR, "speaker-notes.md"))
    speaker_notes_ok = (not speaker_notes_expected) or (speaker_notes_count == page_count)
    transition_count = presentation_effects.count_transitions(Path(deck_path)) if openable else 0
    transition_expected = os.path.exists(os.path.join(RUN_DIR, "transition-plan.json"))
    transitions_ok = (not transition_expected) or (transition_count == page_count)
    # Deck-quality gate: hard editability gate applies ONLY to a real backend, and ONLY
    # on the measured ratio.
    editability_gate_pass = (render_mode == "real") and (measured_aggregate >= MIN_RATIO)
    deck_quality_pass = (
        editability_gate_pass and openable and page_count_ok and assets_ok and overflow_ok
        and speaker_notes_ok and transitions_ok
    )
    ts = _now()
    rl_agg_str = "null" if render_log_aggregate is None else str(render_log_aggregate)
    lines = [
        "---",
        'schema_version: "1.0"',
        f'generated_at: "{ts}"',
        f'render_mode: "{render_mode}"',
        f"slide_count: {slide_count}",
        f"page_count: {page_count}",
        f"page_count_ok: {str(page_count_ok).lower()}",
        f"openable: {str(openable).lower()}",
        f"assets_ok: {str(assets_ok).lower()}",
        f"speaker_notes_count: {speaker_notes_count}",
        f"speaker_notes_ok: {str(speaker_notes_ok).lower()}",
        f"transition_count: {transition_count}",
        f"transitions_ok: {str(transitions_ok).lower()}",
        f"overflow_ok: {str(overflow_ok).lower()}",
        f"measured_aggregate_editable_ratio: {measured_aggregate}",
        f"render_log_aggregate_editable_ratio: {rl_agg_str}",
        f"aggregate_editable_ratio: {measured_aggregate}",
        f"min_editable_ratio: {MIN_RATIO}",
        f"editability_gate_pass: {str(editability_gate_pass).lower()}",
        f"deck_quality_pass: {str(deck_quality_pass).lower()}",
        "---",
        "",
        "## Structural validation",
        f"- render_mode: {render_mode} (deck-quality gate requires render_mode=real)",
        f"- page count: {page_count}/{slide_count} ({'ok' if page_count_ok else 'MISMATCH'})",
        f"- openable: {openable}",
        f"- local assets present: {assets_ok}",
        f"- speaker notes: {speaker_notes_count}/{page_count} ({'ok' if speaker_notes_ok else 'MISMATCH'})",
        f"- transitions: {transition_count}/{page_count} ({'ok' if transitions_ok else 'MISMATCH'})",
        f"- text overflow ok: {overflow_ok}",
        f"- measured editable_ratio: {measured_aggregate} (min {MIN_RATIO}; gate uses this)",
        f"- render-log claimed editable_ratio: {rl_agg_str} (recorded for comparison only)",
        f"- deck_quality_pass: {deck_quality_pass}",
    ]
    if overflow_warnings:
        lines.append("")
        lines.append("## Overflow warnings")
        for warning in overflow_warnings[:40]:
            lines.append(f"- {warning}")
    if missing:
        lines.append("")
        lines.append("## Missing assets")
        for p in missing:
            lines.append(f"- {p}")
    atomic_write(os.path.join(RUN_DIR, "structural-validation.md"), "\n".join(lines) + "\n")
    print(
        f"[export-pptx] structural validation: deck_quality_pass={deck_quality_pass} "
        f"(mode={render_mode}, measured_ratio={measured_aggregate}, page {page_count}/{slide_count})"
    )


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("render", "validate"):
        print("usage: pptx_backend.py {render|validate}", file=sys.stderr)
        sys.exit(1)
    if sys.argv[1] == "render":
        cmd_render()
    else:
        cmd_validate()
