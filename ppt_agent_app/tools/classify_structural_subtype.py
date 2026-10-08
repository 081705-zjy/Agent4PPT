"""Classify structural subtype for every slide in material/decks/.

Post-processes vision brief output to add a `细分角色` field:
  cover              — deck 封面
  toc_main           — 总览目录 (无高亮, 列所有 deck 章节)
  chapter_transition — 章间过渡骨架页 (合并 v30.5b 的 toc_progress + chapter_divider):
                        既包括"进度目录"版式(某章高亮), 也包括"PART XX + 大字标题 + 留白"版式,
                        功能上都是章节间的过渡骨架页
  toc_section        — 章内进度目录 (章内层次/框架 + 某项高亮)
  ending             — 结尾致谢
  content            — 普通内容页 (default)

设计说明 (v30.6): 合并 toc_progress 和 chapter_divider — 二者功能相同
(承担章节间过渡), 只是视觉呈现不同 (进度目录 vs PART 分隔)。

Runs in <10s per full corpus.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ppt_agent_app.models import ROOT

DECKS_DIR = ROOT / "data" / "resources_library" / "material" / "decks"

# ---------------------------------------------------------------------------
# Signal detection
# ---------------------------------------------------------------------------

# Signal that vision brief noticed a highlight/gray contrast — hallmark of
# progress-indicator page (as opposed to plain全览 目录)
HIGHLIGHT_KEYWORDS = (
    "高亮", "灰化", "灰显", "灰色", "灰化",
    "激活", "深色", "淡显", "浅色", "浅化",
    "highlight", "highlighted", "gray", "greyed", "greyed-out",
    "当前进度", "active",
)

# Signal that page discusses a **layered / hierarchical framework** (章内层次)
# rather than the top-level deck outline
HIERARCHY_KEYWORDS = (
    "层次", "N层框架", "三层框架", "四层框架", "五层框架", "六层框架",
    "两层框架", "分层框架", "分层结构", "架构层次", "架构分层",
    "hierarchy", "layered", "layers",
)

# v30.6c: Navigation semantic — 指令性移动信号 (真 toc_section 必须含此).
# 只有 "hierarchy + highlight + navigation semantic" 才判 toc_section;
# 只有 "hierarchy + highlight" 而无 navigation → framework 论证页 (content).
# 例:开题 p16 "应用/模型/系统三层次协同框架" — 有 hierarchy 有 highlight 但无
# navigation semantic (纯 framework 描述), 应判 content 而非 toc_section.
NAVIGATION_KEYWORDS = (
    "定位到", "定位于", "定位第", "定位当前",
    "进入", "切换到", "切入", "转入", "推进到", "推进至",
    "开篇", "开场", "总起", "章节 opener",
    "高亮当前", "高亮第", "高亮定位",
    "承上启下", "承接", "过渡",
    "本章聚焦", "本节聚焦", "本层聚焦", "本章切入",
    "目录", "contents", "agenda", "章节导航",
    "视觉 build 引导", "章节定位",
)

# Title keywords indicating a page IS a table-of-contents style page
TOC_TITLE_KEYWORDS = (
    "目录", "contents", "outline", "议程", "章节导航", "content 目录",
    "内容概要", "agenda", "chapter",
)

# v30.6d: toc_section title guard — 标题必须含明确 navigation / framework-layer
# 词, 否则不算 toc_section. 排除内容页 title 里"承接"这种巧合 nav 词.
# 例: SpeContext p26 "精度评测(长输入):KV 选择机制对比" 是 content page,
# 但 combined 里的"承接"曾误触发 toc_section — 加此 guard 后被排除.
TOC_SECTION_TITLE_KEYWORDS = (
    "目录", "contents", "outline", "议程", "agenda", "大纲",
    "导航", "定位", "进入", "切换", "转入", "推进", "切入",
    "层框架", "层次拆解", "层次回顾", "三层次", "四层次", "五层次",
    "六层次",
    "总览", "开场", "开篇", "总起",
    "chapter", "part ",
)

# v30.5b: real "章前分隔骨架页" signals — used to salvage the 40% of
# `chapter_candidate` slides that are genuine dividers (rest are mis-labeled
# content). Strict AND-of-signals required.
CHAPTER_DIVIDER_TITLE_KW = (
    "PART", "章节分隔", "章封面", "chapter", "第一章", "第二章", "第三章",
    "第四章", "第五章", "第六章", "第七章", "分节", "分隔页", "过渡页",
)
CHAPTER_DIVIDER_VISUAL_KW = (
    "留白", "分隔", "过渡", "大字标题", "章节标题", "极简", "空白",
    "版式骨架", "分节封面", "章封面",
)

# v30.6c: Strict ending validation. `ending_candidate` role from vision brief
# is unreliable — some content pages get mis-labeled ending. Real ending
# must contain thanks/致谢/Q&A/联系方式 signals in title or 关键文字.
REAL_ENDING_KEYWORDS = (
    "致谢", "谢谢", "感谢", "thanks", "thank you", "thank-you",
    "Q&A", "Q & A", "敬请指正", "敬请批评", "请批评指正",
    "联系方式", "contact", "邮箱", "email", "@",
    "作者信息", "作者署名", "author information",
    "招募", "招聘", "recruiting",
    "汇报结束", "汇报完毕", "汇报人",  # thanks page often signs汇报人
    "封底",
)

# Deck-level chapter enumeration signals (progress vs section)
DECK_CHAPTER_KEYWORDS = (
    "章节", "章 ", "第一章", "第二章", "第三章", "第四章", "第五章",
    "background", "motivation", "method", "result", "experiment", "conclusion",
    "研究背景", "研究思路", "研究成果", "研究方法", "研究内容",
    "五段", "四段", "三段", "六段",
    "part ", "PART ", "01", "02", "03", "04",
)


def _combine_text(slide: dict) -> str:
    """Concatenate fields that carry visual-layer semantics.

    v30.6b: also include `视觉骨架` (list of str) and `关键文字` because
    vision brief sometimes puts key structural hints there rather than
    in `视觉文本层次` (e.g., 机器之心 p16 has "居中蓝框标题带 / 留白封面版式"
    in `视觉骨架` and "PART 02" in `关键文字`).
    """
    parts = [slide.get("本页讲什么") or ""]
    for x in (slide.get("视觉文本层次") or []):
        if isinstance(x, dict):
            parts.append(str(x.get("位置") or ""))
            parts.append(str(x.get("内容") or ""))
        else:
            parts.append(str(x))
    for c in (slide.get("alternate_claims") or []):
        parts.append(str(c))
    # v30.6b additions:
    for v in (slide.get("视觉骨架") or []):
        parts.append(str(v))
    for k in (slide.get("关键文字") or []):
        parts.append(str(k))
    return " ".join(parts)


def _has_any(text: str, keywords) -> bool:
    lower = text.lower()
    return any(kw.lower() in lower or kw in text for kw in keywords)


def classify_slide_subtype(slide: dict, section_role: str,
                            is_deck_first_page: bool) -> str:
    """Return `细分角色 ∈ {cover, toc_main, chapter_transition, toc_section,
                            ending, content}`."""
    page_type = (slide.get("页面角色") or "").strip()
    title = (slide.get("标题") or "").strip()
    layout = (slide.get("layout_tag") or "").strip()

    # ---- cover ---------------------------------------------------
    if page_type == "cover_candidate":
        return "cover"
    # A+B fix: force page-1 of opening/cover section = cover even if
    # vision misclassified as content_candidate
    if is_deck_first_page and section_role in ("opening", "cover"):
        return "cover"

    # ---- ending (v30.6c: strict validation) ----------------------
    # Only accept ending_candidate role IF page has REAL_ENDING_KEYWORDS
    # (thanks / 致谢 / 联系方式 / Q&A). Otherwise it's a mis-labeled content
    # page (common vision brief error, e.g. 开题 p29/p74 were content pages
    # wrongly labeled ending_candidate).
    if page_type == "ending_candidate":
        combined_for_ending = " ".join([
            title,
            slide.get("核心论断") or "",
            slide.get("本页讲什么") or "",
            " ".join(slide.get("关键文字") or []),
        ])
        if _has_any(combined_for_ending, REAL_ENDING_KEYWORDS):
            return "ending"
        # else fall through to content

    # ---- toc family ----------------------------------------------
    combined = _combine_text(slide)
    has_highlight = _has_any(combined, HIGHLIGHT_KEYWORDS)
    has_hierarchy = _has_any(combined, HIERARCHY_KEYWORDS)
    has_navigation = _has_any(combined, NAVIGATION_KEYWORDS)
    title_is_toc = _has_any(title, TOC_TITLE_KEYWORDS)

    is_toc_role = page_type == "toc_candidate"
    is_toc_layout_bullet = layout == "bullet_list_conceptual"
    # v30.5b: let chapter_candidate enter TOC family if it looks like a toc
    is_chapter_role_toc_like = (page_type == "chapter_candidate"
                                 and (title_is_toc or has_highlight or has_hierarchy))

    # toc_section: 章内 层次 + 高亮 + navigation 语义 (v30.6c) + title guard (v30.6d)
    # 要求 title 也含 TOC_SECTION_TITLE_KEYWORDS, 排除 content title 里含"承接"
    # 等巧合 nav 词的误判 (SpeContext p26 "精度评测:KV 选择机制对比").
    title_hits_toc_section = _has_any(title, TOC_SECTION_TITLE_KEYWORDS)
    if has_hierarchy and has_highlight and has_navigation and title_hits_toc_section:
        return "toc_section"

    # toc_main / chapter_transition (v30.6: 合并 toc_progress 与 chapter_divider)
    if is_toc_role or title_is_toc or is_chapter_role_toc_like or (
            is_toc_layout_bullet and "目录" in combined):
        if has_highlight:
            return "chapter_transition"  # 进度目录版式的章间过渡
        else:
            return "toc_main"

    # chapter_transition — PART 分隔版式 或 chapter_candidate role + 短内容
    # v30.6b: check divider signals across ALL text fields (not just title):
    #   - title 里含 PART / 章节分隔 关键词  OR
    #   - 本页讲什么 / 关键文字 / 视觉骨架 里含 divider 关键词
    #   - 关键文字 ≤ 3 项 (短内容 = 分隔骨架特征)
    #   - page_type ∈ chapter_candidate / content_candidate
    # 当 page_type == chapter_candidate, 放松要求 (只要有 short + any divider signal)
    keyword_count = len(slide.get("关键文字") or [])
    title_hits_divider = any(kw in title for kw in CHAPTER_DIVIDER_TITLE_KW)
    combined_hits_divider = _has_any(combined, CHAPTER_DIVIDER_TITLE_KW)
    visual_hits_divider = _has_any(combined, CHAPTER_DIVIDER_VISUAL_KW)
    is_short_content = keyword_count <= 3
    is_chapter_role = page_type == "chapter_candidate"

    # 严格模式 (page_type=content_candidate 需要 3 个 AND)
    strict_match = (title_hits_divider and visual_hits_divider and is_short_content
                     and page_type == "content_candidate")
    # 宽松模式 (page_type=chapter_candidate 只要短内容 + 任一 divider 信号)
    lax_match = (is_chapter_role and is_short_content
                  and (title_hits_divider or combined_hits_divider or visual_hits_divider))

    if strict_match or lax_match:
        return "chapter_transition"

    return "content"


# ---------------------------------------------------------------------------
# Corpus walk + write-back
# ---------------------------------------------------------------------------

def _update_slide_md_frontmatter(md_path: Path, subtype: str) -> None:
    """Insert or update `细分角色: <subtype>` in slide.md YAML frontmatter."""
    if not md_path.exists():
        return
    text = md_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return
    end = text.find("\n---", 3)
    if end < 0:
        return
    fm = text[4:end]
    body = text[end:]
    if re.search(r"^细分角色\s*:", fm, flags=re.MULTILINE):
        fm = re.sub(r"^细分角色\s*:.*$", f"细分角色: {subtype}", fm, count=1,
                    flags=re.MULTILINE)
    else:
        # append before closing ---
        fm = fm.rstrip() + f"\n细分角色: {subtype}"
    md_path.write_text(f"---\n{fm}\n---{body[4:] if body.startswith('----') else body}",
                       encoding="utf-8")


def process_deck(deck_dir: Path, *, dry_run: bool = False) -> dict:
    """Compute 细分角色 for every slide in this deck; write back JSON + md."""
    deck_json_path = deck_dir / "deck.json"
    if not deck_json_path.exists():
        return {"deck": deck_dir.name, "error": "no deck.json"}
    deck = json.loads(deck_json_path.read_text(encoding="utf-8"))
    section_list = deck.get("章节列表") or []

    counts: dict[str, int] = {}
    changed = 0
    total = 0

    # v30.6c: 2-pass — first collect all (idx, slide_json_path, subtype),
    # then find LAST real ending; downgrade everything after → content.
    provisional: list[tuple[int, Path, dict, str]] = []  # (page_idx, path, slide_data, subtype)

    for sname in section_list:
        sec_dir = deck_dir / sname
        sec_json = sec_dir / "section.json"
        if not sec_json.exists():
            continue
        sec = json.loads(sec_json.read_text(encoding="utf-8"))
        sec_role = (sec.get("章节角色") or "").strip()

        for slide_json in sorted(sec_dir.glob("slide_*.json")):
            total += 1
            sl = json.loads(slide_json.read_text(encoding="utf-8"))
            is_first_of_deck = sl.get("页序号") == 1
            subtype = classify_slide_subtype(sl, sec_role, is_first_of_deck)
            provisional.append((sl.get("页序号") or 0, slide_json, sl, subtype))

    # Sort by absolute page index
    provisional.sort(key=lambda x: x[0])

    # Find LAST ending index → everything after downgrades to content
    # (post-appendix rule: after true ending, all pages are 附录/补充, not
    # part of deck logic → treat as content).
    last_ending_idx = -1
    for i, (_, _, _, sub) in enumerate(provisional):
        if sub == "ending":
            last_ending_idx = i

    for i, (page_idx, slide_json, sl, subtype) in enumerate(provisional):
        if last_ending_idx >= 0 and i > last_ending_idx:
            subtype = "content"  # post-ending appendix pages
        counts[subtype] = counts.get(subtype, 0) + 1
        if sl.get("细分角色") == subtype:
            continue
        changed += 1
        if not dry_run:
            sl["细分角色"] = subtype
            slide_json.write_text(
                json.dumps(sl, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            md_path = slide_json.with_suffix(".md")
            _update_slide_md_frontmatter(md_path, subtype)

    return {
        "deck": deck_dir.name,
        "total": total,
        "changed": changed,
        "counts": counts,
    }


def run(*, dry_run: bool = False, only: list[str] | None = None) -> dict:
    if not DECKS_DIR.exists():
        return {"error": f"no decks dir: {DECKS_DIR}"}

    all_counts: dict[str, int] = {}
    total_changed = 0
    total_slides = 0
    results = []

    deck_dirs = sorted([d for d in DECKS_DIR.iterdir()
                       if d.is_dir() and (d / "deck.json").exists()])
    if only:
        keep = set(only)
        deck_dirs = [d for d in deck_dirs if d.name in keep]

    for deck_dir in deck_dirs:
        r = process_deck(deck_dir, dry_run=dry_run)
        results.append(r)
        total_slides += r.get("total", 0)
        total_changed += r.get("changed", 0)
        for k, v in (r.get("counts") or {}).items():
            all_counts[k] = all_counts.get(k, 0) + v

    print(f"\n=== summary ({'DRY RUN' if dry_run else 'WRITTEN'}) ===")
    print(f"decks processed: {len(results)}")
    print(f"total slides:    {total_slides}")
    print(f"changed slides:  {total_changed}")
    print(f"\n细分角色 distribution:")
    for k in ("cover", "toc_main", "chapter_transition", "toc_section",
              "ending", "content"):
        n = all_counts.get(k, 0)
        pct = 100 * n / total_slides if total_slides else 0
        print(f"  {k:<20s}: {n:>4d}  ({pct:>5.1f}%)")

    return {
        "decks": len(results),
        "total_slides": total_slides,
        "changed": total_changed,
        "distribution": all_counts,
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    dry_run = "--dry-run" in argv
    only: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--only" and i + 1 < len(argv):
            only.append(argv[i + 1]); i += 2; continue
        i += 1
    run(dry_run=dry_run, only=only or None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
