"""PPTX slide-clone — byte-level integration of source slides into a target deck.

Replaces the lossy SVG → DrawingML conversion path for ``direct_slide_reuse``
pages. By copying ``ppt/slides/slideN.xml`` plus its companion layout / master
/ theme / media parts directly into the target ``deck.pptx``, the cloned slide
is **identical** to the source — text fits, fonts, charts, embedded objects,
all preserved.

Two public entry points:

    clone_slide(target_pres, src_pres, src_slide_index_1based) -> Slide

    build_deck_from_clone_plan(
        plan: list[dict],          # draft-assembly-plan.json slides
        out_pptx: Path,
        section_titles: list[str], # for fixed_agenda pages
        gap_renderer: callable,    # for placeholder pages
    ) -> dict                       # {ok, total, cloned, agenda, placeholder, errors}

The plan is the per-page directive. Each entry needs at minimum:

    {
      "draft_action": "direct_slide_reuse" | "fixed_agenda" | "placeholder" | "new_slide",
      # for direct_slide_reuse:
      "source_pptx_path": "/abs/path/to/source.pptx",
      "source_slide_index": 34,     # 1-based
      # for fixed_agenda:
      "active_section_index": 1,    # 1-based; current section highlighted
      # for placeholder/new_slide:
      "gap_card": {...},            # forwarded to gap_renderer
    }

Layout / master / theme / image dedup is handled internally by hashing the
serialized XML / bytes; identical content is reused.
"""

from __future__ import annotations

import copy
import hashlib
import io
from pathlib import Path
from typing import Callable

from lxml import etree
from pptx import Presentation
from pptx.opc.constants import CONTENT_TYPE as CT, RELATIONSHIP_TYPE as RT
from pptx.opc.package import PartFactory, Part
from pptx.opc.packuri import PackURI


# ---------------------------------------------------------------------------
# Source pptx caching — opening a 100 MB pptx repeatedly is expensive.
# ---------------------------------------------------------------------------

_SRC_CACHE: dict[str, Presentation] = {}


# Lightweight wrappers in case SlideLayoutPart / SlideMasterPart's .slide_layout /
# .slide_master attribute isn't available across python-pptx versions.
class _SlideLayoutWrapper:
    def __init__(self, part):
        self.part = part
        self.element = part._element
        # Walk to master via the SLIDE_MASTER relationship.
        self.slide_master = None
        for rel in part.rels.values():
            if rel.reltype == RT.SLIDE_MASTER:
                from pptx.parts.slide import SlideMasterPart
                tp = rel.target_part
                if isinstance(tp, SlideMasterPart):
                    self.slide_master = (tp.slide_master if hasattr(tp, "slide_master") else _SlideMasterWrapper(tp))


class _SlideMasterWrapper:
    def __init__(self, part):
        self.part = part
        self.element = part._element

    @property
    def slide_layouts(self):
        return []  # placeholder; clone path doesn't iterate target's master layouts


def _open_source(path: str | Path) -> Presentation:
    key = str(Path(path).resolve())
    pres = _SRC_CACHE.get(key)
    if pres is None:
        pres = Presentation(key)
        _SRC_CACHE[key] = pres
    return pres


# ---------------------------------------------------------------------------
# Byte / hash dedup helpers
# ---------------------------------------------------------------------------

def _sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:16]


def _xml_bytes(elem) -> bytes:
    """Canonical serialization for hashing."""
    return etree.tostring(elem, encoding="utf-8")


# Dedup state per target deck (carried across clone_slide calls).
class _CloneState:
    def __init__(self, target_pres: Presentation):
        self.target = target_pres
        self.layout_by_xmlhash: dict[str, object] = {}
        self.image_by_bytehash: dict[str, object] = {}
        self.chart_by_xmlhash: dict[str, object] = {}

        # Pre-populate dedup with target's existing parts so we don't re-add.
        for layout in target_pres.slide_layouts:
            try:
                h = _sha1_bytes(_xml_bytes(layout.element))
                self.layout_by_xmlhash[h] = layout
            except Exception:
                pass

    def get_or_clone_layout(self, src_layout, scale_xy: tuple[float, float] = (1.0, 1.0)) -> object:
        h = _sha1_bytes(_xml_bytes(src_layout.element)) + f"|s={scale_xy[0]:.6f},{scale_xy[1]:.6f}"
        if h in self.layout_by_xmlhash:
            return self.layout_by_xmlhash[h]
        new_layout = self._clone_layout_part(src_layout, scale_xy)
        self.layout_by_xmlhash[h] = new_layout
        return new_layout

    def _clone_layout_part(self, src_layout, scale_xy: tuple[float, float] = (1.0, 1.0)):
        """Copy a SlideLayout part into target. Re-uses master if possible."""
        # Clone the master first (and re-use if the same master was already cloned).
        src_master = src_layout.slide_master
        master_h = _sha1_bytes(_xml_bytes(src_master.element)) + f"|s={scale_xy[0]:.6f},{scale_xy[1]:.6f}"
        new_master = self.layout_by_xmlhash.get(master_h)
        if new_master is None or not hasattr(new_master, "slide_layouts"):
            new_master = self._clone_master_part(src_master, scale_xy)
            self.layout_by_xmlhash[master_h] = new_master

        from pptx.parts.slide import SlideLayoutPart
        from pptx.oxml.ns import qn

        target_pkg = self.target.part.package
        # Compute a unique partname by scanning existing parts in package, not
        # just self.target.slide_layouts (which may not be re-iterable mid-clone).
        existing_layouts = [str(p.partname) for p in target_pkg.iter_parts()
                            if str(p.partname).startswith("/ppt/slideLayouts/slideLayout")]
        # Find next available number
        n = 1
        while True:
            partname_str = f"/ppt/slideLayouts/slideLayout{n}.xml"
            if partname_str not in existing_layouts:
                break
            n += 1
        partname = PackURI(partname_str)
        layout_xml = copy.deepcopy(src_layout.element)
        # Cross-canvas scale layout shapes too — otherwise inherited
        # placeholders / background graphics stay at source-canvas coords.
        sx, sy = scale_xy
        if sx != 1.0 or sy != 1.0:
            _scale_emu_attrs_in_tree(layout_xml, sx, sy)
        new_layout_part = SlideLayoutPart(
            partname, CT.PML_SLIDE_LAYOUT, target_pkg, layout_xml
        )
        new_layout_part.relate_to(new_master.part, RT.SLIDE_MASTER)
        rid_map = self._copy_part_relationships(src_layout.part, new_layout_part)

        # v4.4 bug fix: after copying image/chart parts, rIds get renumbered by
        # python-pptx (insertion order, not preserving src rIds). Remap r:id /
        # r:embed / r:link in the cloned layout XML so decorative pics, charts,
        # etc. point to the right target part. (Bug symptom: layout's big bg
        # image ref'd by rId2 in SRC swapped with small logo's rId3 in DRAFT
        # → logo blown up to background size.)
        if rid_map:
            ns_r = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
            for elem in layout_xml.iter():
                for attr in (f"{ns_r}id", f"{ns_r}embed", f"{ns_r}link"):
                    old = elem.get(attr)
                    if old and old in rid_map:
                        elem.set(attr, rid_map[old])

        master_xml = new_master.element
        sldLayoutIdLst = master_xml.find(qn("p:sldLayoutIdLst"))
        if sldLayoutIdLst is None:
            sldLayoutIdLst = etree.SubElement(master_xml, qn("p:sldLayoutIdLst"))
        existing_ids = [int(e.get("id", "0")) for e in sldLayoutIdLst.findall(qn("p:sldLayoutId"))]
        new_id = max(existing_ids + [2147483648]) + 1
        new_rid = new_master.part.relate_to(new_layout_part, RT.SLIDE_LAYOUT)
        new_entry = etree.SubElement(sldLayoutIdLst, qn("p:sldLayoutId"))
        new_entry.set("id", str(new_id))
        new_entry.set(qn("r:id"), new_rid)

        return new_layout_part.slide_layout if hasattr(new_layout_part, "slide_layout") else _SlideLayoutWrapper(new_layout_part)

    def _clone_master_part(self, src_master, scale_xy: tuple[float, float] = (1.0, 1.0)):
        """Copy the master (theme + master XML) into target."""
        from pptx.parts.slide import SlideMasterPart
        from pptx.opc.package import Part as OpcPart

        target_pkg = self.target.part.package
        existing_masters = [str(p.partname) for p in target_pkg.iter_parts()
                             if str(p.partname).startswith("/ppt/slideMasters/slideMaster")]
        n = 1
        while True:
            master_partname_str = f"/ppt/slideMasters/slideMaster{n}.xml"
            if master_partname_str not in existing_masters:
                break
            n += 1
        master_partname = PackURI(master_partname_str)
        master_xml = copy.deepcopy(src_master.element)
        sx, sy = scale_xy
        if sx != 1.0 or sy != 1.0:
            _scale_emu_attrs_in_tree(master_xml, sx, sy)
        new_master_part = SlideMasterPart(
            master_partname, CT.PML_SLIDE_MASTER, target_pkg, master_xml
        )

        # Clone theme — pick unique theme number too
        existing_themes = [str(p.partname) for p in target_pkg.iter_parts()
                           if str(p.partname).startswith("/ppt/theme/theme")]
        for rel in src_master.part.rels.values():
            if rel.reltype == RT.THEME:
                src_theme_part = rel.target_part
                tn = 1
                while True:
                    theme_pn_str = f"/ppt/theme/theme{tn}.xml"
                    if theme_pn_str not in existing_themes:
                        break
                    tn += 1
                theme_partname = PackURI(theme_pn_str)
                new_theme_part = OpcPart(
                    theme_partname, CT.OFC_THEME, target_pkg, src_theme_part.blob
                )
                new_master_part.relate_to(new_theme_part, RT.THEME)
                break

        master_rid_map = self._copy_part_relationships(src_master.part, new_master_part)

        # v4.4 bug fix: same as layout — remap rIds in master XML so decorative
        # images on master (logos, watermarks) don't get swapped with theme/chart rIds.
        if master_rid_map:
            ns_r = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
            for elem in master_xml.iter():
                for attr in (f"{ns_r}id", f"{ns_r}embed", f"{ns_r}link"):
                    old = elem.get(attr)
                    if old and old in master_rid_map:
                        elem.set(attr, master_rid_map[old])

        from pptx.oxml.ns import qn
        pres_xml = self.target.part._element
        sldMasterIdLst = pres_xml.find(qn("p:sldMasterIdLst"))
        if sldMasterIdLst is None:
            sldMasterIdLst = etree.SubElement(pres_xml, qn("p:sldMasterIdLst"))
        existing_ids = [int(e.get("id", "0")) for e in sldMasterIdLst.findall(qn("p:sldMasterId"))]
        new_id = max(existing_ids + [2147483648]) + 1
        new_rid = self.target.part.relate_to(new_master_part, RT.SLIDE_MASTER)
        new_entry = etree.SubElement(sldMasterIdLst, qn("p:sldMasterId"))
        new_entry.set("id", str(new_id))
        new_entry.set(qn("r:id"), new_rid)

        return new_master_part.slide_master if hasattr(new_master_part, "slide_master") else _SlideMasterWrapper(new_master_part)

    def _copy_part_relationships(self, src_part, target_part) -> dict:
        """Walk relationships on src_part, copy referenced parts into target_part.

        Returns dict mapping src_rId → new_rId.
        """
        rid_map: dict[str, str] = {}
        for rel in list(src_part.rels.values()):
            if rel.is_external:
                # External relationships (hyperlinks) — preserve target URL.
                new_rid = target_part.relate_to(rel.target_ref, rel.reltype, is_external=True)
                rid_map[rel.rId] = new_rid
                continue
            src_target_part = rel.target_part
            reltype = rel.reltype
            if reltype == RT.IMAGE:
                new_part = self._get_or_clone_image(src_target_part)
            elif reltype == RT.CHART:
                new_part = self._clone_chart(src_target_part)
            elif reltype in (RT.SLIDE_LAYOUT, RT.SLIDE_MASTER, RT.THEME):
                # Skip — handled by higher-level layout/master clone
                continue
            elif reltype == RT.NOTES_SLIDE:
                # Skip — we overwrite notes via Slide.notes_slide later, and
                # cloning the source's notesSlide as a generic Part breaks
                # python-pptx's Slide.notes_slide accessor (it expects a
                # NotesSlidePart, not a generic Part).
                continue
            else:
                # Generic part copy (oleObject, embedded, custom XML, etc.)
                new_part = self._clone_generic_part(src_target_part)
            new_rid = target_part.relate_to(new_part, reltype)
            rid_map[rel.rId] = new_rid
        return rid_map

    def _get_or_clone_image(self, src_image_part):
        from pptx.parts.image import ImagePart
        h = _sha1_bytes(src_image_part.blob)
        cached = self.image_by_bytehash.get(h)
        if cached is not None:
            return cached
        target_pkg = self.target.part.package
        ext = Path(str(src_image_part.partname)).suffix or ".png"
        partname = PackURI(f"/ppt/media/image_{h}{ext}")
        new_part = ImagePart(partname, src_image_part.content_type, target_pkg, src_image_part.blob)
        self.image_by_bytehash[h] = new_part
        return new_part

    def _clone_chart(self, src_chart_part):
        from pptx.parts.chart import ChartPart
        target_pkg = self.target.part.package
        h = _sha1_bytes(_xml_bytes(src_chart_part._element))
        cached = self.chart_by_xmlhash.get(h)
        if cached is not None:
            return cached
        existing = [p for p in target_pkg.iter_parts() if str(p.partname).startswith("/ppt/charts/")]
        partname = PackURI(f"/ppt/charts/chart{len(existing)+1}.xml")
        new_part = ChartPart(
            partname, src_chart_part.content_type,
            target_pkg, copy.deepcopy(src_chart_part._element),
        )
        self._copy_part_relationships(src_chart_part, new_part)
        self.chart_by_xmlhash[h] = new_part
        return new_part

    def _clone_generic_part(self, src_part):
        target_pkg = self.target.part.package
        src_pn = str(src_part.partname)
        # Avoid partname collisions — append a suffix when target already
        # has a part at the same path (notesSlideN.xml / tagN.xml etc.)
        existing = {str(p.partname) for p in target_pkg.iter_parts()}
        partname_str = src_pn
        if partname_str in existing:
            from pathlib import PurePosixPath
            base = PurePosixPath(src_pn)
            stem = base.stem
            suffix = base.suffix or ""
            parent = base.parent
            n = 1
            while True:
                cand = f"{parent}/{stem}_{n}{suffix}"
                if cand not in existing:
                    partname_str = cand
                    break
                n += 1
        partname = PackURI(partname_str)
        return Part(partname, src_part.content_type, target_pkg, src_part.blob)


# ---------------------------------------------------------------------------
# Public API: clone_slide
# ---------------------------------------------------------------------------

def _scale_emu_attrs_in_tree(elem, scale_x: float, scale_y: float) -> None:
    """In-place scale every dimension that lives inside a cloned slide /
    layout / master XML tree so that pasting cross-canvas content keeps the
    SAME visual proportions as the source page.

    What gets scaled:
      • EMU positioning — <a:off>, <a:ext>, <a:chOff>, <a:chExt>
      • EMU text-frame insets — <a:bodyPr lIns/rIns/tIns/bIns>
      • EMU paragraph indents — marL / marR / indent on <a:pPr>,
        <a:defPPr>, and <a:lvl1pPr> … <a:lvl9pPr>
      • Font size (1/100 pt) — sz on <a:rPr>, <a:endParaRPr>, <a:defRPr>,
        plus bullet size <a:buSzPts val="...">
      • Line-spacing <a:spcPts val="..."> on <a:spcBef>/<a:spcAft> (1/100 pt)

    When ratio is preserved (which is always the case here — all three
    deck sizes we encounter are 16:9), we use the geometric mean of
    scale_x/scale_y as the uniform "text scale" so a 0.75× canvas paste
    produces 0.75× font sizes, paragraph margins keep their relative
    position to shapes, etc. — matching what PowerPoint's "Ensure Fit"
    paste does.
    """
    if abs(scale_x - 1.0) < 1e-6 and abs(scale_y - 1.0) < 1e-6:
        return
    a_ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    pos_tags = {f"{a_ns}off", f"{a_ns}ext", f"{a_ns}chOff", f"{a_ns}chExt"}
    bodyPr_tag = f"{a_ns}bodyPr"
    pPr_tags = {f"{a_ns}pPr", f"{a_ns}defPPr"}
    level_ppr_prefix = f"{a_ns}lvl"
    rpr_tags = {f"{a_ns}rPr", f"{a_ns}endParaRPr", f"{a_ns}defRPr"}
    spc_tags = {f"{a_ns}spcBef", f"{a_ns}spcAft"}
    buSzPts_tag = f"{a_ns}buSzPts"
    spcPts_tag = f"{a_ns}spcPts"

    # Uniform text scale — geometric mean is a tiny bit more tolerant of
    # 9144000×5148071 vs 9144000×5143500 rounding than scale_x alone.
    uniform = (scale_x * scale_y) ** 0.5

    def _scale_attr(node, attr, factor, *, min_value: int | None = None):
        v = node.get(attr)
        if v is None:
            return
        try:
            new_val = int(float(v) * factor)
            if min_value is not None and new_val < min_value:
                new_val = min_value
            node.set(attr, str(new_val))
        except (ValueError, TypeError):
            pass

    for sub in elem.iter():
        tag = sub.tag

        if tag in pos_tags:
            _scale_attr(sub, "x", scale_x)
            _scale_attr(sub, "y", scale_y)
            _scale_attr(sub, "cx", scale_x)
            _scale_attr(sub, "cy", scale_y)
            continue

        if tag == bodyPr_tag:
            _scale_attr(sub, "lIns", scale_x)
            _scale_attr(sub, "rIns", scale_x)
            _scale_attr(sub, "tIns", scale_y)
            _scale_attr(sub, "bIns", scale_y)
            continue

        # Paragraph margins / indent (EMU, x-axis)
        is_level_pPr = (
            tag.startswith(level_ppr_prefix)
            and tag.endswith("pPr")
            and len(tag) == len(level_ppr_prefix) + len("XpPr")  # lvl[1-9]pPr
        )
        if tag in pPr_tags or is_level_pPr:
            _scale_attr(sub, "marL", scale_x)
            _scale_attr(sub, "marR", scale_x)
            _scale_attr(sub, "indent", scale_x)
            # font size also lives on <a:defRPr> children — handled by next branch.
            # Some pPr/lvlXpPr also expose defTabSz (EMU, x-axis)
            _scale_attr(sub, "defTabSz", scale_x)
            continue

        # Font size on run properties (1/100 pt). Keep minimum 100 (=1pt)
        # to avoid producing illegal sz="0".
        if tag in rpr_tags:
            _scale_attr(sub, "sz", uniform, min_value=100)
            continue

        # Bullet absolute size (1/100 pt)
        if tag == buSzPts_tag:
            _scale_attr(sub, "val", uniform, min_value=100)
            continue

        # Line-spacing absolute (a:spcBef / a:spcAft → contain a:spcPts val=...)
        if tag == spcPts_tag:
            _scale_attr(sub, "val", uniform, min_value=0)
            continue


def _read_sldSz(pres: Presentation) -> tuple[int, int] | None:
    from pptx.oxml.ns import qn
    el = pres.part._element.find(qn("p:sldSz"))
    if el is None:
        return None
    try:
        return int(el.get("cx") or 0), int(el.get("cy") or 0)
    except (TypeError, ValueError):
        return None


def clone_slide(target_pres: Presentation, src_pres: Presentation,
                src_slide_index_1based: int, state: _CloneState | None = None):
    """Clone a single slide from src_pres into target_pres. Returns new Slide.

    If src_pres.sldSz != target_pres.sldSz, all positioning EMU values inside
    the cloned spTree are rescaled by (target_cx / src_cx, target_cy / src_cy)
    — this is what PowerPoint's UI does when you paste a slide from a
    differently-sized deck. Without it, e.g. a 12192000-wide slide pasted into
    a 9144000-wide deck overflows the right edge by 33%.
    """
    if state is None:
        state = _CloneState(target_pres)

    src_slides = list(src_pres.slides)
    if not (1 <= src_slide_index_1based <= len(src_slides)):
        raise IndexError(f"src slide {src_slide_index_1based} out of range (have {len(src_slides)})")
    src_slide = src_slides[src_slide_index_1based - 1]

    # Cross-canvas scale factor (applied to slide spTree AND layout/master).
    src_size = _read_sldSz(src_pres)
    tgt_size = _read_sldSz(target_pres)
    if src_size and tgt_size and src_size != tgt_size and src_size[0] > 0 and src_size[1] > 0:
        scale_xy = (tgt_size[0] / src_size[0], tgt_size[1] / src_size[1])
    else:
        scale_xy = (1.0, 1.0)

    # 1. Ensure layout is present in target — scale it if cross-canvas.
    new_layout = state.get_or_clone_layout(src_slide.slide_layout, scale_xy)

    # 2. Add a new slide using the (just-cloned) layout. python-pptx auto-fills
    #    spTree from the layout placeholders — we'll then wholesale replace it
    #    with the source's spTree.
    new_slide = target_pres.slides.add_slide(new_layout)

    # 3. Replace the body of the new slide with the source's full XML.
    from pptx.oxml.ns import qn

    src_root = copy.deepcopy(src_slide.element)
    target_root = new_slide.element

    # 3a. Cross-canvas rescale (P8): apply same scale to slide's own spTree.
    if scale_xy != (1.0, 1.0):
        _scale_emu_attrs_in_tree(src_root, scale_xy[0], scale_xy[1])

    # 3b. WHOLESALE replace target_root's contents with src_root's. Previously
    # we only swapped <p:cSld> children — that dropped <p:timing> (animations,
    # often 20-30 KB), <p:transition>, <p:clrMapOvr>, <p:extLst>, AND <p:sld>
    # attributes like `show="false"`. This produced visually identical first
    # frames but lost animations and hidden-slide flags.
    #
    # Strategy: keep the target_root *element identity* (lxml refs that
    # python-pptx and the slide part hold), but clear its attribs+children
    # and clone everything from src_root.
    for k in list(target_root.attrib.keys()):
        del target_root.attrib[k]
    for k, v in src_root.attrib.items():
        target_root.set(k, v)
    for child in list(target_root):
        target_root.remove(child)
    for child in src_root:
        target_root.append(copy.deepcopy(child))

    # 4. Copy rels (images / charts / hyperlinks) and remap rIds in the cloned XML.
    rid_map = state._copy_part_relationships(src_slide.part, new_slide.part)

    # Rewrite rId references across the ENTIRE cloned slide tree — timing,
    # transition, extLst can also reference embedded media (sounds, videos).
    if rid_map:
        ns_r = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
        for elem in target_root.iter():
            for attr in (f"{ns_r}id", f"{ns_r}embed", f"{ns_r}link"):
                old_rid = elem.get(attr)
                if old_rid and old_rid in rid_map:
                    elem.set(attr, rid_map[old_rid])

    # 5. Strip namespace declarations the source didn't use. python-pptx's
    # default slide template declares xmlns:r unconditionally; if the source
    # slide had no rId references, our copy would carry a 78-byte xmlns:r
    # decl that the source lacks, breaking byte-for-byte equivalence.
    etree.cleanup_namespaces(target_root)

    return new_slide


# ---------------------------------------------------------------------------
# Public API: build_deck_from_clone_plan
# ---------------------------------------------------------------------------

def _apply_text_edits(slide, *, target_title: str | None = None,
                       target_claim: str | None = None,
                       key_points: list | None = None) -> dict:
    """Apply v30 partial_rewrite text edits to a freshly cloned slide.

    Strategy (heuristic, no LLM):
    - **Title**: locate a title-like placeholder (ph type=title/ctrTitle or
      any placeholder holding the largest font-size text in the top third
      of the slide) → replace its text with `target_title`
    - **Primary content**: locate the biggest text-holding shape below the
      title (largest shape area with non-empty text_frame that isn't the
      title) → replace with `target_claim` as first paragraph, then each
      `key_points` entry as subsequent paragraphs, preserving the original
      shape's first paragraph run-level style (font/size/color).

    Returns {'title_replaced': bool, 'content_replaced': bool, 'reason': str}
    """
    from pptx.util import Emu
    from pptx.enum.text import PP_ALIGN

    result = {"title_replaced": False, "content_replaced": False, "reason": ""}

    # ---- find title placeholder ----
    title_shape = None
    try:
        # Preferred: use python-pptx placeholder API
        for ph in slide.placeholders:
            pt = getattr(ph.placeholder_format, "idx", None)
            ptype = getattr(ph.placeholder_format, "type", None)
            # 13 = title, 0 = title (idx varies by layout)
            if ptype is not None and str(ptype).lower() in ("title (13)", "title", "ctrtitle", "centered_title (1)", "centered_title"):
                title_shape = ph
                break
            if pt == 0:
                title_shape = ph
                break
    except Exception:
        pass

    if title_shape is None:
        # Fallback: shape with largest font in top 1/3 of slide
        _slide_h = None
        try:
            _slide_h = slide.part.package.presentation_part.presentation.slide_height
        except Exception:
            pass
        best = None
        best_score = -1
        for shp in slide.shapes:
            if not shp.has_text_frame:
                continue
            top = getattr(shp, "top", None)
            if top is None or (_slide_h and top > _slide_h / 2):
                continue
            # score by max font size in first paragraph
            max_sz = 0
            try:
                for p in shp.text_frame.paragraphs[:1]:
                    for r in p.runs:
                        sz = getattr(r.font, "size", None)
                        if sz is not None:
                            max_sz = max(max_sz, int(sz))
            except Exception:
                pass
            if max_sz > best_score:
                best_score = max_sz
                best = shp
        title_shape = best

    if title_shape is not None and target_title:
        try:
            _replace_shape_text(title_shape, [target_title])
            result["title_replaced"] = True
        except Exception as exc:
            result["reason"] += f"title replace failed: {exc}; "

    # ---- find primary content shape ----
    content_shape = None
    best_area = -1
    for shp in slide.shapes:
        if shp is title_shape or not shp.has_text_frame:
            continue
        try:
            area = int(shp.width or 0) * int(shp.height or 0)
        except Exception:
            area = 0
        # Skip near-empty text frames
        if not (shp.text_frame.text or "").strip():
            continue
        if area > best_area:
            best_area = area
            content_shape = shp

    if content_shape is not None:
        lines: list[str] = []
        if target_claim:
            lines.append(target_claim)
        if key_points:
            for kp in (key_points or []):
                if isinstance(kp, str):
                    lines.append(kp)
                elif isinstance(kp, dict):
                    _t = kp.get("text") or kp.get("point") or kp.get("bullet")
                    if _t:
                        lines.append(_t)
        if lines:
            try:
                _replace_shape_text(content_shape, lines)
                result["content_replaced"] = True
            except Exception as exc:
                result["reason"] += f"content replace failed: {exc}; "

    return result


def _replace_shape_text(shape, paragraphs: list[str]) -> None:
    """Replace all text in a shape's text_frame with the given paragraphs,
    preserving the first run's font style (family/size/color/bold) from the
    shape's first paragraph as the template for every new paragraph."""
    from pptx.util import Pt
    tf = shape.text_frame
    # Snapshot the first run's font style as template (if present)
    tmpl_font = {}
    try:
        first_p = tf.paragraphs[0]
        first_run = first_p.runs[0] if first_p.runs else None
        if first_run is not None:
            f = first_run.font
            tmpl_font = {
                "name": getattr(f, "name", None),
                "size": getattr(f, "size", None),
                "bold": getattr(f, "bold", None),
                "italic": getattr(f, "italic", None),
            }
            try:
                if f.color and f.color.type is not None:
                    tmpl_font["color_rgb"] = f.color.rgb
            except Exception:
                pass
    except Exception:
        pass

    # Clear text_frame — remove all paragraphs except one, clear its runs
    # (python-pptx doesn't expose "clear all"; we manipulate the XML)
    from pptx.oxml.ns import qn
    txBody = tf._txBody
    for p in list(txBody.findall(qn("a:p"))):
        txBody.remove(p)

    # Now add fresh paragraphs
    for i, text in enumerate(paragraphs):
        if not text:
            continue
        p = tf.add_paragraph()
        run = p.add_run()
        run.text = text
        # Apply template font style
        try:
            if tmpl_font.get("name"):
                run.font.name = tmpl_font["name"]
            if tmpl_font.get("size"):
                run.font.size = tmpl_font["size"]
            if tmpl_font.get("bold") is not None:
                run.font.bold = tmpl_font["bold"]
            if tmpl_font.get("italic") is not None:
                run.font.italic = tmpl_font["italic"]
            if tmpl_font.get("color_rgb"):
                run.font.color.rgb = tmpl_font["color_rgb"]
        except Exception:
            pass


def build_deck_from_clone_plan(
    plan_slides: list[dict],
    out_pptx: Path,
    *,
    section_titles: list[str] | None = None,
    gap_renderer: Callable[[Presentation, dict], None] | None = None,
    agenda_renderer: Callable[[Presentation, list[str], int], None] | None = None,
    base_template: str | Path | None = None,
) -> dict:
    """Iterate over draft-assembly-plan slides and produce out_pptx.

    plan_slides items support draft_action ∈ {direct_slide_reuse,
    fixed_agenda, placeholder, new_slide_placeholder}.
    """
    out_pptx = Path(out_pptx)
    out_pptx.parent.mkdir(parents=True, exist_ok=True)

    # Start from base_template if given (so canvas size + brand fonts come
    # from a known good seed). Otherwise blank Presentation.
    target = Presentation(str(base_template)) if base_template and Path(base_template).exists() else Presentation()
    # Drop any starter slides the template ships with.
    while len(target.slides) > 0:
        rId = target.slides._sldIdLst[0].rId
        target.part.drop_rel(rId)
        del target.slides._sldIdLst[0]

    state = _CloneState(target)

    summary = {"total": len(plan_slides), "cloned": 0, "agenda": 0,
               "placeholder": 0, "partial_rewrite": 0, "errors": []}

    section_titles = section_titles or []

    for spec in plan_slides:
        action = spec.get("draft_action") or spec.get("draft_action_kind") or ""
        try:
            if action in ("direct_slide_reuse", "copy_source_slide_as_is"):
                src_path = spec.get("source_pptx_path")
                src_idx = spec.get("source_slide_index")
                if not src_path or not src_idx:
                    raise ValueError(f"slide {spec.get('slide_index')} missing source_pptx_path / source_slide_index")
                src_pres = _open_source(src_path)
                clone_slide(target, src_pres, int(src_idx), state)
                summary["cloned"] += 1
            elif action in ("partial_slide_reuse", "partial_rewrite"):
                # v30: byte-clone the source, then overwrite title + primary
                # content with target_title / target_claim / key_points.
                src_path = spec.get("source_pptx_path")
                src_idx = spec.get("source_slide_index")
                if not src_path or not src_idx:
                    raise ValueError(f"slide {spec.get('slide_index')} missing source_pptx_path / source_slide_index")
                src_pres = _open_source(src_path)
                clone_slide(target, src_pres, int(src_idx), state)
                # The newly cloned slide is the last one on target.
                new_slide = target.slides[-1]
                edit_result = _apply_text_edits(
                    new_slide,
                    target_title=spec.get("target_title") or "",
                    target_claim=spec.get("target_claim") or "",
                    key_points=spec.get("key_points") or [],
                )
                summary["partial_rewrite"] += 1
                summary.setdefault("partial_rewrite_details", []).append({
                    "slide_index": spec.get("slide_index"),
                    **edit_result,
                })
            elif action == "fixed_agenda":
                if agenda_renderer is None:
                    raise NotImplementedError("agenda_renderer not provided")
                agenda_renderer(target, section_titles, int(spec.get("active_section_index") or 0))
                summary["agenda"] += 1
            elif action in ("placeholder", "new_slide_placeholder", "new_slide"):
                if gap_renderer is None:
                    raise NotImplementedError("gap_renderer not provided")
                gap_renderer(target, spec.get("gap_card") or spec)
                summary["placeholder"] += 1
            else:
                raise ValueError(f"unknown draft_action: {action!r}")
        except Exception as exc:
            summary["errors"].append({
                "slide_index": spec.get("slide_index"),
                "draft_action": action,
                "error": str(exc),
            })

    target.save(str(out_pptx))
    summary["ok"] = not summary["errors"]
    summary["out_path"] = str(out_pptx)
    return summary
