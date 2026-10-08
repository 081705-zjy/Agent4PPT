"""Library tree writer (Phase A.1).

Renders deck / section / slide profile data into the new directory tree
layout described in /home/zjy/.claude/plans/refactored-twirling-truffle.md:

    decks/<deck-stem>/
        deck.md
        deck.json
        section_NN_<slug>/
            section.md
            section.json
            slide_NN.md
            slide_NN.json

This is a pure write-side helper. It does NOT call Claude. It accepts
"final" deck/section/slide dicts (Chinese-keyed schema) and just
serializes them. Phase A.2 (library_brief.py) is where Claude generates
these dicts.

**Schema is Chinese-keyed** (user decision — Claude generates Chinese
content more accurately when keys are Chinese). Mapping from legacy
heuristic profile keys (English) to the new schema lives in
`from_heuristic_*` helpers below.
"""
from __future__ import annotations
import json
import re
import shutil
import unicodedata
from pathlib import Path


# --------------------------------------------------------------------------
# Filename / slug helpers
# --------------------------------------------------------------------------

# Characters that break on Windows / mac / various tools — replace with `-`.
_UNSAFE_CHAR_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Collapse runs of whitespace only — preserve `_` and `-` from source filenames.
_WS_RUN_RE = re.compile(r"\s+")
# Collapse runs of consecutive dashes that result from substitution.
_DASH_RUN_RE = re.compile(r"-{2,}")


def safe_dirname(text: str, *, max_len: int = 60) -> str:
    """Sanitize an arbitrary string into a filesystem-safe directory name.

    CJK characters are kept. Only the few Windows-illegal chars and control
    codepoints are stripped. Whitespace runs collapse to single dashes.
    Underscores and existing dashes from the source name are preserved.
    """
    s = unicodedata.normalize("NFC", text or "").strip()
    s = _UNSAFE_CHAR_RE.sub("-", s)
    s = _WS_RUN_RE.sub("-", s)
    s = _DASH_RUN_RE.sub("-", s).strip("-")
    if len(s) > max_len:
        s = s[:max_len].rstrip("-_")
    return s or "untitled"


def deck_dirname(source_pptx_path: str | Path, sha1: str | None = None) -> str:
    """Deck directory name.

    Historically = stem of source .pptx. Collision-prone when two source pptx
    share the same stem across scenarios. Pass `sha1` (full file SHA1) to
    append `.<sha8>` for collision resistance.
    """
    stem = safe_dirname(Path(str(source_pptx_path)).stem)
    if sha1:
        return f"{stem}.{sha1[:8]}"
    return stem


def section_dirname(section_index: int, section_title: str) -> str:
    """Section directory name = section_NN_<slug>."""
    slug = safe_dirname(section_title or f"section-{section_index}", max_len=50)
    return f"section_{section_index:02d}_{slug}"


def slide_filename_stem(slide_index: int) -> str:
    """slide file stem = slide_NN (1-based)."""
    return f"slide_{slide_index:02d}"


# --------------------------------------------------------------------------
# YAML frontmatter renderer
# --------------------------------------------------------------------------

def _yaml_scalar(v) -> str:
    """Render a YAML scalar with minimal quoting (byte-stable across pyyaml versions)."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    needs_quote = (
        s == ""
        or s.lstrip() != s
        or s.rstrip() != s
        or any(ch in s for ch in ":#&*!|>'\"%@`")
        or s.lower() in {"true", "false", "null", "yes", "no", "on", "off"}
        or (re.match(r"^[-\d]", s) is not None and not s.isalpha())
    )
    if "\n" in s:
        lines = s.split("\n")
        return "|\n" + "\n".join("  " + ln for ln in lines)
    if needs_quote:
        esc = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{esc}"'
    return s


def _yaml_render(d: dict, indent: int = 0) -> list[str]:
    pad = "  " * indent
    out: list[str] = []
    for k, v in d.items():
        if isinstance(v, dict):
            out.append(f"{pad}{k}:")
            if v:
                out.extend(_yaml_render(v, indent + 1))
            else:
                out[-1] += " {}"
        elif isinstance(v, list):
            if not v:
                out.append(f"{pad}{k}: []")
            elif all(isinstance(x, (str, int, float, bool)) or x is None for x in v):
                items = ", ".join(_yaml_scalar(x) for x in v)
                out.append(f"{pad}{k}: [{items}]")
            else:
                out.append(f"{pad}{k}:")
                for item in v:
                    if isinstance(item, dict):
                        sub = _yaml_render(item, indent + 1)
                        if sub:
                            sub[0] = pad + "  - " + sub[0].lstrip()
                            for i in range(1, len(sub)):
                                sub[i] = pad + "    " + sub[i].lstrip()
                        out.extend(sub)
                    else:
                        out.append(f"{pad}  - {_yaml_scalar(item)}")
        else:
            out.append(f"{pad}{k}: {_yaml_scalar(v)}")
    return out


def yaml_frontmatter(d: dict) -> str:
    body = "\n".join(_yaml_render(d))
    return f"---\n{body}\n---\n"


# --------------------------------------------------------------------------
# Markdown body renderers (Chinese-keyed schema)
# --------------------------------------------------------------------------

def render_deck_md(deck: dict, sections: list[dict]) -> str:
    title = deck.get("标题") or Path(deck.get("源文件", "untitled")).stem
    arc = deck.get("论述弧线") or []
    transferable = deck.get("适合复用场景") or []
    avoid = deck.get("不适合复用场景") or []
    summary = deck.get("论述总结") or ""

    lines = [f"# {title}", ""]

    lines.append("## 整篇 deck 的论述弧线")
    if isinstance(arc, list) and arc:
        lines.append(" → ".join(str(x) for x in arc))
    else:
        lines.append(summary or "_(brief 待 Claude 生成)_")
    lines.append("")

    lines.append("## section 之间的逻辑关系")
    if sections:
        for s in sections:
            idx = s.get("章节序号")
            title_s = s.get("标题") or s.get("章节角色") or "(untitled)"
            narr = s.get("章节叙事") or "_(brief 待生成)_"
            lines.append(f"{idx}. **{title_s}** — {narr}")
    else:
        lines.append("_(未识别 section)_")
    lines.append("")

    lines.append("## 适合复用的场景")
    if transferable:
        for t in transferable:
            lines.append(f"- {t}")
    else:
        lines.append("_(brief 待生成)_")
    lines.append("")

    lines.append("## 不适合复用的场景")
    if avoid:
        for a in avoid:
            lines.append(f"- {a}")
    else:
        lines.append("_(brief 待生成)_")
    lines.append("")

    return "\n".join(lines)


def render_section_md(section: dict, slides_in_section: list[dict]) -> str:
    title = section.get("标题") or section.get("章节角色") or f"section-{section.get('章节序号')}"
    idx = section.get("章节序号")
    transferable = section.get("适合复用场景") or []
    avoid = section.get("不适合复用场景") or []
    relations = section.get("页间关系") or []
    position = section.get("在deck中的位置") or f"页码范围 = {section.get('页码范围') or []}"

    lines = [f"# section {idx}: {title}", ""]

    lines.append("## 在 deck 中的位置")
    lines.append(position)
    lines.append("")

    lines.append("## 章内 slide 间的关系")
    if relations:
        for r in relations:
            lines.append(f"- {r}")
    elif slides_in_section:
        for sl in slides_in_section:
            ix = sl.get("页序号")
            t = sl.get("标题") or sl.get("核心论断") or "(no title)"
            lines.append(f"- slide {ix}: {t}")
    else:
        lines.append("_(no slides)_")
    lines.append("")

    lines.append("## 整章可复用的场景")
    if transferable:
        for t in transferable:
            lines.append(f"- {t}")
    else:
        lines.append("_(brief 待生成)_")
    lines.append("")

    lines.append("## 不适合复用的场景")
    if avoid:
        for a in avoid:
            lines.append(f"- {a}")
    else:
        lines.append("_(brief 待生成)_")
    lines.append("")

    return "\n".join(lines)


def render_slide_md(slide: dict) -> str:
    idx = slide.get("页序号")
    title = slide.get("标题") or "(no title)"
    claim = slide.get("核心论断") or ""
    explains = slide.get("本页讲什么") or ""
    samples = slide.get("关键文字") or []
    visuals = slide.get("视觉骨架") or []
    transferable = slide.get("适合复用场景") or []
    avoid = slide.get("不适合复用场景") or []

    lines = [f"# slide {idx}: {title}", ""]

    if claim:
        lines.append(f"**核心论断**: {claim}")
        lines.append("")

    lines.append("## 本页讲什么")
    lines.append(explains or "_(brief 待 Claude 生成)_")
    lines.append("")

    if samples:
        lines.append("## 关键文字片段")
        for s in samples[:10]:
            s_clean = (s or "").strip().replace("\n", " ")
            if s_clean:
                lines.append(f"- {s_clean[:200]}")
        lines.append("")

    if visuals:
        lines.append("## 视觉骨架")
        for v in (visuals if isinstance(visuals, list) else [visuals]):
            lines.append(f"- {v}")
        lines.append("")

    if transferable:
        lines.append("## 可复用到")
        for t in transferable:
            lines.append(f"- {t}")
        lines.append("")

    if avoid:
        lines.append("## 不适合复用的场景")
        for a in avoid:
            lines.append(f"- {a}")
        lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------
# Heuristic → Chinese-keyed schema conversion (one-time migration helper)
# --------------------------------------------------------------------------

def from_heuristic_deck(deck: dict) -> dict:
    """Convert a legacy heuristic deck-profile row to the Chinese-keyed schema."""
    src = deck.get("source_path") or deck.get("source_pptx") or ""
    return {
        "deck标识": deck.get("deck_id") or "",
        "源文件": src,
        "源哈希": deck.get("file_sha1"),
        "标题": Path(src).stem if src else (deck.get("topic") or deck.get("deck_id")),
        "总页数": deck.get("slide_count"),
        "章节数": deck.get("section_count"),
        "主题标签": [],
        "目标受众": deck.get("audience"),
        "报告类型": deck.get("deck_type") or deck.get("template_type"),
        "适用场景": deck.get("scenario"),
        "论述弧线": deck.get("narrative_arc") or [],
        "论述总结": deck.get("topic_summary") or "",
        "适合复用场景": [],
        "不适合复用场景": [],
        "分析状态": "heuristic",
    }


def from_heuristic_section(section: dict) -> dict:
    return {
        "章节标识": section.get("section_id") or "",
        "deck标识": section.get("deck_id") or "",
        "章节序号": section.get("section_index"),
        "章节角色": section.get("role"),
        "标题": section.get("role") or f"section-{section.get('section_index')}",
        "章节叙事": section.get("summary") or section.get("narrative_function") or "",
        "页码范围": None,
        "页数": len(section.get("slide_ids") or []),
        "页ID列表": [],
        "页间关系": [],
        "适合复用场景": section.get("transferable_to") or [],
        "不适合复用场景": section.get("do_not_reuse_when") or [],
        "在deck中的位置": "",
        "分析状态": "heuristic",
    }


def from_heuristic_slide(slide: dict, source_pptx: str) -> dict:
    return {
        "页标识": slide.get("slide_id") or "",
        "所属章节": slide.get("section_id") or "",
        "deck标识": slide.get("deck_id") or "",
        "页序号": slide.get("slide_index"),
        "源文件": source_pptx,
        "页面角色": slide.get("slide_role") or slide.get("role"),
        "标题": slide.get("title"),
        "核心论断": slide.get("claim"),
        "本页讲什么": slide.get("what_this_slide_explains") or "",
        "关键文字": slide.get("text_samples") or [],
        "视觉骨架": slide.get("salient_visuals") or [],
        "资源ID列表": slide.get("asset_ids") or [],
        "适合复用场景": slide.get("transferable_to") or [],
        "不适合复用场景": slide.get("do_not_reuse_when") or [],
        "上页角色": None,
        "下页角色": None,
        "分析状态": "heuristic",
    }


# --------------------------------------------------------------------------
# Tree writer (entry point)
# --------------------------------------------------------------------------

def write_deck_tree(
    decks_root: Path,
    deck: dict,
    sections: list[dict],
    slides: list[dict],
) -> dict:
    """Materialize one deck as a directory tree under decks_root.

    All three input dicts MUST be in the Chinese-keyed schema. Use the
    `from_heuristic_*` helpers above to convert legacy English-key data.
    """
    decks_root = Path(decks_root)

    src = deck.get("源文件") or ""
    sha1 = deck.get("源哈希") or deck.get("文件SHA1") or None
    deck_dir_name = deck_dirname(src, sha1=sha1) if src else safe_dirname(deck.get("deck标识", "untitled"))
    deck_dir = decks_root / deck_dir_name
    deck_dir.mkdir(parents=True, exist_ok=True)

    # Phase fix-2026-06-28: clean stale section_*/ dirs left over from
    # previous library_brief runs with different section_split outputs.
    # Bug observed: 49% of section dirs in material/ were stale (230/468),
    # because re-runs of section_split create new section_NN_<slug>/ dirs
    # without removing the old ones. Move stale to .stale_sections/ within
    # deck_dir for safekeeping (reversible) instead of rmtree.
    stale_holding = deck_dir / ".stale_sections"
    for existing in list(deck_dir.iterdir()):
        if existing.is_dir() and existing.name.startswith("section_"):
            stale_holding.mkdir(exist_ok=True)
            target = stale_holding / existing.name
            if target.exists():
                shutil.rmtree(target)
            existing.rename(target)

    slides_by_section: dict[str, list[dict]] = {}
    for s in slides:
        sid = s.get("所属章节") or ""
        slides_by_section.setdefault(sid, []).append(s)
    for v in slides_by_section.values():
        v.sort(key=lambda x: x.get("页序号") or 0)

    deck_fm = {
        "deck标识": deck.get("deck标识") or deck_dir_name,
        "目录名": deck_dir_name,
        "源文件": src,
        "源哈希": deck.get("源哈希"),
        "画布尺寸": deck.get("画布尺寸"),
        "标题": deck.get("标题"),
        "总页数": deck.get("总页数") or len(slides),
        "章节数": deck.get("章节数") or len(sections),
        "章节列表": [
            section_dirname(s.get("章节序号"), s.get("标题") or s.get("章节角色") or "")
            for s in sorted(sections, key=lambda x: x.get("章节序号") or 0)
        ],
        "主题标签": deck.get("主题标签") or [],
        "目标受众": deck.get("目标受众"),
        "报告类型": deck.get("报告类型"),
        "适用场景": deck.get("适用场景"),
        "论述总结": deck.get("论述总结"),
        "论述弧线": deck.get("论述弧线") or [],
        "适合复用场景": deck.get("适合复用场景") or [],
        "不适合复用场景": deck.get("不适合复用场景") or [],
        "分析状态": deck.get("分析状态") or "heuristic",
    }
    deck_md = yaml_frontmatter(deck_fm) + "\n" + render_deck_md(deck, sections)
    (deck_dir / "deck.md").write_text(deck_md, encoding="utf-8")
    (deck_dir / "deck.json").write_text(
        json.dumps(deck_fm, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    written_sections: list[str] = []
    written_slides: list[str] = []
    for s in sorted(sections, key=lambda x: x.get("章节序号") or 0):
        sec_idx = s.get("章节序号")
        sec_title = s.get("标题") or s.get("章节角色") or f"section-{sec_idx}"
        sec_dir = deck_dir / section_dirname(sec_idx, sec_title)
        sec_dir.mkdir(exist_ok=True)
        sec_slides = slides_by_section.get(s.get("章节标识"), [])

        sec_fm = {
            "章节标识": s.get("章节标识"),
            "所属deck": deck_fm["deck标识"],
            "章节序号": sec_idx,
            "章节角色": s.get("章节角色"),
            "标题": sec_title,
            "页码范围": [
                sec_slides[0].get("页序号") if sec_slides else None,
                sec_slides[-1].get("页序号") if sec_slides else None,
            ] if sec_slides else None,
            "页数": len(sec_slides),
            "页ID列表": [f"slide_{x.get('页序号'):02d}" for x in sec_slides if x.get("页序号")],
            "章节叙事": s.get("章节叙事"),
            "页间关系": s.get("页间关系") or [],
            "适合复用场景": s.get("适合复用场景") or [],
            "不适合复用场景": s.get("不适合复用场景") or [],
            "在deck中的位置": s.get("在deck中的位置") or "",
            "分析状态": s.get("分析状态") or "heuristic",
        }
        sec_md = yaml_frontmatter(sec_fm) + "\n" + render_section_md(s, sec_slides)
        (sec_dir / "section.md").write_text(sec_md, encoding="utf-8")
        (sec_dir / "section.json").write_text(
            json.dumps(sec_fm, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        written_sections.append(sec_dir.name)

        for sl in sec_slides:
            sl_idx = sl.get("页序号")
            slide_fm = {
                "页标识": sl.get("页标识"),
                "所属章节": sec_fm["章节标识"],
                "所属deck": deck_fm["deck标识"],
                "页序号": sl_idx,
                "源文件": src,
                "页面角色": sl.get("页面角色"),
                "标题": sl.get("标题"),
                "核心论断": sl.get("核心论断"),
                "本页讲什么": sl.get("本页讲什么"),
                "关键文字": sl.get("关键文字") or [],
                "视觉骨架": sl.get("视觉骨架") or [],
                "资源ID列表": sl.get("资源ID列表") or [],
                "适合复用场景": sl.get("适合复用场景") or [],
                "不适合复用场景": sl.get("不适合复用场景") or [],
                # v20 enhance fields (populated by library_brief step 5; else None/empty)
                "页在section中的作用": sl.get("页在section中的作用"),
                "视觉文本层次": sl.get("视觉文本层次") or [],
                "alternate_claims": sl.get("alternate_claims") or [],
                "layout_tag": sl.get("layout_tag"),
                # v30.5 structural subtype (populated by
                # ppt_agent_app.tools.classify_structural_subtype as a
                # post-process step; may be None on first write)
                "细分角色": sl.get("细分角色"),
                "上页角色": sl.get("上页角色"),
                "下页角色": sl.get("下页角色"),
                "分析状态": sl.get("分析状态") or "heuristic",
            }
            slide_md = yaml_frontmatter(slide_fm) + "\n" + render_slide_md(slide_fm)
            stem = slide_filename_stem(sl_idx)
            (sec_dir / f"{stem}.md").write_text(slide_md, encoding="utf-8")
            (sec_dir / f"{stem}.json").write_text(
                json.dumps(slide_fm, ensure_ascii=False, indent=2), encoding="utf-8",
            )
            written_slides.append(f"{sec_dir.name}/{stem}")

    return {
        "deck_dir": str(deck_dir),
        "sections_written": len(written_sections),
        "slides_written": len(written_slides),
        "sections": written_sections,
    }


# --------------------------------------------------------------------------
# decks-index.json — global lightweight index over all decks in the library
# --------------------------------------------------------------------------

def write_decks_index(decks_root: Path) -> dict:
    """Walk `decks/` and emit a global 28-entry index keyed by deck_id.

    The index is the FIRST thing LayeredRetrieval loads (~50 KB) before
    deciding which deck.md files to actually read. Keep each entry small.

    Returns the index dict (also written to `decks/../decks-index.json`).
    """
    decks_root = Path(decks_root)
    entries: list[dict] = []
    for deck_dir in sorted(decks_root.iterdir(), key=lambda p: p.name):
        if not deck_dir.is_dir():
            continue
        deck_json = deck_dir / "deck.json"
        if not deck_json.exists():
            continue
        try:
            d = json.loads(deck_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        entries.append({
            "deck标识": d.get("deck标识"),
            "目录名": d.get("目录名") or deck_dir.name,
            "标题": d.get("标题"),
            "源文件": d.get("源文件"),
            "总页数": d.get("总页数"),
            "章节数": d.get("章节数"),
            "画布尺寸": d.get("画布尺寸"),
            "主题标签": d.get("主题标签") or [],
            "目标受众": d.get("目标受众"),
            "报告类型": d.get("报告类型"),
            "适用场景": d.get("适用场景"),
            "适合复用场景": d.get("适合复用场景") or [],
            "不适合复用场景": d.get("不适合复用场景") or [],
            "分析状态": d.get("分析状态") or "unknown",
        })

    index = {
        "schema_version": "tree-v1",
        "deck_count": len(entries),
        "decks": entries,
    }
    out_path = decks_root.parent / "decks-index.json"
    out_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


# --------------------------------------------------------------------------
# CLI for prototype testing
# --------------------------------------------------------------------------

def _cli_smoke_test():
    import sys
    repo = Path(__file__).resolve().parents[1]
    decks = json.loads((repo / "data/resources_library/material/deck-profiles.json").read_text())["decks"]
    sections = json.loads((repo / "data/resources_library/material/section-profiles.json").read_text())["sections"]
    slides = json.loads((repo / "data/resources_library/material/slide-profiles.json").read_text())["slides"]

    needle = sys.argv[1] if len(sys.argv) > 1 else "戴国浩-高效大模型推理技术与应用"
    deck = next((d for d in decks if needle in d.get("source_path", "")), None)
    if deck is None:
        print(f"no deck matching needle={needle!r}")
        sys.exit(2)
    deck_id = deck["deck_id"]
    deck_sections = [s for s in sections if s["deck_id"] == deck_id]
    deck_slides = [s for s in slides if s["deck_id"] == deck_id]

    deck_zh = from_heuristic_deck(deck)
    sections_zh = [from_heuristic_section(s) for s in deck_sections]
    slides_zh = [from_heuristic_slide(s, deck_zh["源文件"]) for s in deck_slides]

    out_root = Path("/tmp/library-prototype/decks")
    if out_root.parent.exists():
        import shutil
        shutil.rmtree(out_root.parent)
    out_root.mkdir(parents=True)
    summary = write_deck_tree(out_root, deck_zh, sections_zh, slides_zh)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _cli_smoke_test()
