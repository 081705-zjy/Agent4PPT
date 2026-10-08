"""Claude-driven brief generator for the template library (Phase A.2).

Pipeline per deck:

    deck_brief       → 1 call  (deck-level overview)
    section_split    → 1 call  (boundaries)
    for each section:
        section_brief → 1 call (section-level narrative)
        slide_brief   → 1 call (per-slide brief, 1 call covers the whole section)
    enhance          → 1 call PER SLIDE (v20 fields: 页在section中的作用 /
                                          视觉文本层次 / alternate_claims / layout_tag)

Total per deck: 2 + 2N + M calls (N = section count, M = slide count).
Model: claude-opus-4-8 (user choice — brief quality > cost).

Within ONE deck: stages 1-4 are sequential; stage 5 (enhance) fans out
across the deck's slides with a bounded per-deck pool
(ENHANCE_MAX_PARALLEL_PER_DECK).

Across decks: fully independent, batch driver
`generate_briefs_for_decks(...)` uses a top-level pool
(DEFAULT_MAX_DECK_CONCURRENCY, default 6).

Each call has 3 retries with exponential backoff. If a call still fails,
the whole deck is marked `分析状态: failed` and we **do not** fall back
to heuristic — caller decides to skip or re-run.

The output is three lists of Chinese-keyed dicts ready to feed into
`library_tree.write_deck_tree(decks_root, deck, sections, slides)`.
"""
from __future__ import annotations
import concurrent.futures
import copy
import json
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable

from . import claude_cli
from .models import ROOT


BRIEF_MODEL = "claude-opus-4-8"
MAX_RETRIES = 3
BASE_BACKOFF = 2.0   # seconds; doubled each retry: 2, 4, 8

# Default cap on concurrent decks in the batch driver. Claude CLI calls are
# IO-bound (subprocess → API), so threads work fine. Don't crank this too
# high or the API will rate-limit.
DEFAULT_MAX_DECK_CONCURRENCY = 6

DECK_BRIEF_SKILL = "skills/resources_library/material/deck_brief.md"
SECTION_SPLIT_SKILL = "skills/resources_library/material/section_split.md"
SECTION_BRIEF_SKILL = "skills/resources_library/material/section_brief.md"
SLIDE_BRIEF_SKILL = "skills/resources_library/material/slide_brief.md"
# v20 enhance: 4 fields (页在section中的作用 / 视觉文本层次 / alternate_claims / layout_tag)
# added AFTER slide_brief in a single follow-up call per slide, so base
# slide_brief.md stays simple. Merged into slides_zh before write_deck_tree.
SLIDE_BRIEF_ENHANCE_SKILL = "skills/resources_library/material/slide_brief_enhance.md"
ENHANCE_FIELDS = ("页在section中的作用", "视觉文本层次", "alternate_claims", "layout_tag")
ENHANCE_TIMEOUT = 180
ENHANCE_MAX_PARALLEL_PER_DECK = 8

# Source-side (user-uploaded materials) equivalents. When called with non-empty
# project_context, library_brief routes to these copies so all source analysis
# skills sit together under skills/sources/.
PROJECT_DECK_BRIEF_SKILL = "skills/sources/ppt_deck_brief.md"
PROJECT_SECTION_SPLIT_SKILL = "skills/sources/ppt_section_split.md"
PROJECT_SECTION_BRIEF_SKILL = "skills/sources/ppt_section_brief.md"
PROJECT_SLIDE_BRIEF_SKILL = "skills/sources/ppt_slide_brief.md"

# Per-call timeout (seconds). Section/slide briefs may need longer with
# large sections, but opus generally finishes in <60s for these schemas.
DECK_BRIEF_TIMEOUT = 240
SECTION_SPLIT_TIMEOUT = 300
SECTION_BRIEF_TIMEOUT = 240
SLIDE_BRIEF_TIMEOUT = 360


class BriefGenerationError(RuntimeError):
    """Raised when a brief call fails after MAX_RETRIES with no fallback."""

    def __init__(self, stage: str, deck_id: str, last_error: str, raw_excerpt: str = ""):
        super().__init__(f"[{stage}] deck={deck_id} failed after {MAX_RETRIES} retries: {last_error}")
        self.stage = stage
        self.deck_id = deck_id
        self.last_error = last_error
        self.raw_excerpt = raw_excerpt


# --------------------------------------------------------------------------
# Low-level: a single retried Claude JSON call
# --------------------------------------------------------------------------

def _claude_json_with_retry(
    *,
    stage: str,
    deck_id: str,
    skill: str,
    prompt: str,
    timeout: int,
    validator: callable,
    add_dirs: list[str] | None = None,
) -> dict:
    """Call Claude with the given skill, parse JSON, validate. Retry up to
    MAX_RETRIES; raise BriefGenerationError on final failure.

    `validator(data) -> str | None`: returns an error message if data is
    bad (so we can retry with a stronger prompt), or None if good.

    `add_dirs`: extra dirs Claude may Read (enables vision when the prompt
    asks the model to Read image files inside these dirs).
    """
    last_error = "no attempt made"
    last_raw = ""
    for attempt in range(1, MAX_RETRIES + 1):
        # On retries, prefix a corrective note. Claude has no memory between
        # calls so we restate the constraint inline.
        effective_prompt = prompt
        if attempt > 1:
            corrective = (
                f"PREVIOUS ATTEMPT FAILED: {last_error}\n"
                "STRICT RULES (re-read carefully):\n"
                "  • Output starts with `{` and ends with `}`. NOTHING else — no markdown fence, "
                "no prose before, no characters after the final `}`.\n"
                "  • All keys must be present and use the exact Chinese names from the schema.\n"
                "  • Quote every string with `\"`. Escape internal `\"` as `\\\"` and `\\` as `\\\\`.\n"
                "  • Lists must be valid JSON arrays even when empty (`[]`). No trailing commas.\n"
                "  • Match all required schema lengths exactly (e.g., `页面画像[]` length must equal "
                "input slide count).\n"
                "  • If the skill requires reading PNG files via Read tool, you MUST invoke Read on each provided png_path.\n"
            )
            effective_prompt = f"{corrective}\n---\n\n{prompt}"
        result = claude_cli.call_claude_json(
            effective_prompt,
            skill=[skill],
            model=BRIEF_MODEL,
            timeout=timeout,
            add_dirs=add_dirs,
        )
        if not result.get("ok"):
            last_error = result.get("error") or "unknown CLI error"
            last_raw = result.get("raw_excerpt") or ""
            print(f"  [{stage}/{deck_id}] attempt {attempt}/{MAX_RETRIES} CLI error: {last_error[:200]}", flush=True)
        else:
            data = result["data"]
            err = validator(data)
            if err is None:
                return data
            last_error = f"schema validation: {err}"
            last_raw = json.dumps(data, ensure_ascii=False)[:600]
            print(f"  [{stage}/{deck_id}] attempt {attempt}/{MAX_RETRIES} validation: {err[:200]}", flush=True)
        if attempt < MAX_RETRIES:
            time.sleep(BASE_BACKOFF * (2 ** (attempt - 1)))
    raise BriefGenerationError(stage, deck_id, last_error, last_raw)


# --------------------------------------------------------------------------
# Validators (one per skill)
# --------------------------------------------------------------------------

def _validate_deck_brief(data: Any) -> str | None:
    if not isinstance(data, dict):
        return "deck brief is not a JSON object"
    required = ["标题", "主题标签", "目标受众", "报告类型", "适用场景",
                "论述总结", "论述弧线", "适合复用场景", "不适合复用场景"]
    missing = [k for k in required if k not in data]
    if missing:
        return f"missing required keys: {missing}"
    if not isinstance(data.get("主题标签"), list):
        return "主题标签 must be a list"
    if not isinstance(data.get("论述弧线"), list):
        return "论述弧线 must be a list"
    if not isinstance(data.get("适合复用场景"), list):
        return "适合复用场景 must be a list"
    if not isinstance(data.get("不适合复用场景"), list):
        return "不适合复用场景 must be a list"
    return None


def _validate_section_split(data: Any, total_pages: int) -> str | None:
    if not isinstance(data, dict):
        return "section split is not a JSON object"
    splits = data.get("章节切分")
    if not isinstance(splits, list) or not splits:
        return "章节切分 must be a non-empty list"
    expected_idx = 1
    expected_start = 1
    for i, s in enumerate(splits):
        if not isinstance(s, dict):
            return f"章节切分[{i}] is not an object"
        for k in ["章节序号", "章节角色", "标题", "起始页", "结束页", "切分原因"]:
            if k not in s:
                return f"章节切分[{i}] missing {k}"
        if s["章节序号"] != expected_idx:
            return f"章节切分[{i}] 章节序号 must be {expected_idx}, got {s['章节序号']}"
        try:
            start, end = int(s["起始页"]), int(s["结束页"])
        except (TypeError, ValueError):
            return f"章节切分[{i}] 起始页/结束页 not int"
        if start != expected_start:
            return f"章节切分[{i}] expected 起始页={expected_start}, got {start}"
        if end < start:
            return f"章节切分[{i}] 结束页({end}) < 起始页({start})"
        expected_idx += 1
        expected_start = end + 1
    last_end = int(splits[-1]["结束页"])
    if last_end != total_pages:
        return f"last 章节 结束页={last_end} != 总页数={total_pages}"
    return None


def _validate_section_brief(data: Any, expected_relations_count: int) -> str | None:
    if not isinstance(data, dict):
        return "section brief is not a JSON object"
    required = ["章节叙事", "在deck中的位置", "页间关系",
                "适合复用场景", "不适合复用场景"]
    missing = [k for k in required if k not in data]
    if missing:
        return f"missing keys: {missing}"
    relations = data.get("页间关系")
    if not isinstance(relations, list):
        return "页间关系 must be a list"
    if len(relations) != expected_relations_count:
        return f"页间关系 length={len(relations)}, expected={expected_relations_count}"
    return None


def _validate_slide_briefs(data: Any, expected_indices: list[int]) -> str | None:
    if not isinstance(data, dict):
        return "slide brief is not a JSON object"
    portraits = data.get("页面画像")
    if not isinstance(portraits, list):
        return "页面画像 must be a list"
    if len(portraits) != len(expected_indices):
        return f"页面画像 length={len(portraits)}, expected={len(expected_indices)}"
    for i, (got, expect) in enumerate(zip(portraits, expected_indices)):
        if not isinstance(got, dict):
            return f"页面画像[{i}] is not an object"
        if got.get("页序号") != expect:
            return f"页面画像[{i}] 页序号={got.get('页序号')}, expected={expect}"
        for k in ["标题", "核心论断", "本页讲什么", "关键文字", "视觉骨架",
                  "适合复用场景", "不适合复用场景"]:
            if k not in got:
                return f"页面画像[{i}] missing {k}"
    return None


# --------------------------------------------------------------------------
# Per-stage skill calls
# --------------------------------------------------------------------------

def _slide_overview_for_deck_brief(slide: dict, png_dir: Path | None = None) -> dict:
    """Compact per-slide payload used in deck_brief input. ≤3 text samples.

    v30.3: if png_dir is passed, add png_path so deck_brief can Read strategic
    slides (cover, agenda, chapter dividers, closing) to nail down deck-level
    topic tags + narrative arc.
    """
    idx = slide.get("index")
    entry = {
        "页序号": idx,
        "页面角色": slide.get("pageType"),
        "标题": (slide.get("textSamples") or [""])[0][:80] if slide.get("textSamples") else "",
        "关键文字": [t[:120] for t in (slide.get("textSamples") or [])[:3]],
        "shape_count": slide.get("shapeCount"),
        "image_count": len(slide.get("imageAssets") or []),
    }
    if png_dir is not None and idx is not None:
        png = png_dir / f"slide_{idx:02d}.png"
        if png.exists():
            entry["png_path"] = str(png.resolve())
    return entry


def _slide_overview_for_section_split(slide: dict, png_dir: Path | None = None) -> dict:
    """Slightly richer per-slide payload for section_split (more text samples).

    v30.2: if png_dir is passed, add png_path so section_split can Read PNG to
    detect agenda-family pages (main agenda vs section-progress indicator).
    """
    idx = slide.get("index")
    entry = {
        "页序号": idx,
        "页面角色": slide.get("pageType"),
        "标题": (slide.get("textSamples") or [""])[0][:120] if slide.get("textSamples") else "",
        "关键文字": [t[:200] for t in (slide.get("textSamples") or [])[:6]],
    }
    if png_dir is not None and idx is not None:
        png = png_dir / f"slide_{idx:02d}.png"
        if png.exists():
            entry["png_path"] = str(png.resolve())
    return entry


def _slide_overview_for_slide_brief(slide: dict, prev_role: str | None,
                                     next_role: str | None,
                                     png_dir: Path | None = None) -> dict:
    """Full per-slide payload for slide_brief (all text samples).

    If `png_dir` is passed, add `png_path` field pointing to the rendered slide
    PNG (built by svg_to_png). Enables vision-based analysis.
    """
    idx = slide.get("index")
    entry = {
        "页序号": idx,
        "页面角色": slide.get("pageType"),
        "原始标题": (slide.get("textSamples") or [""])[0][:120] if slide.get("textSamples") else "",
        "关键文字": [t[:300] for t in (slide.get("textSamples") or [])[:10]],
        "shape_count": slide.get("shapeCount"),
        "image_count": len(slide.get("imageAssets") or []),
        "上页角色": prev_role,
        "下页角色": next_role,
    }
    if png_dir is not None and idx is not None:
        png = png_dir / f"slide_{idx:02d}.png"
        if png.exists():
            entry["png_path"] = str(png.resolve())
    return entry


def call_deck_brief(deck_id: str, source_pptx: str, slides_meta: list[dict],
                    slide_size: list[int] | None,
                    project_context: dict | None = None,
                    png_dir: Path | None = None) -> dict:
    """v30.3 vision: if png_dir is passed, deck_brief can Read strategic slide PNGs
    (cover, agenda, chapter dividers, closing) to nail topic tags + narrative arc."""
    payload = {
        "源文件": source_pptx,
        "deck标识": deck_id,
        "总页数": len(slides_meta),
        "画布尺寸": slide_size,
        "页面概览": [_slide_overview_for_deck_brief(s, png_dir=png_dir)
                     for s in slides_meta],
    }
    if project_context:
        payload["项目上下文"] = project_context
    skill = PROJECT_DECK_BRIEF_SKILL if project_context else DECK_BRIEF_SKILL
    prompt = json.dumps(payload, ensure_ascii=False)
    add_dirs = [str(png_dir.resolve())] if png_dir else None
    return _claude_json_with_retry(
        stage="deck_brief",
        deck_id=deck_id,
        skill=skill,
        prompt=prompt,
        timeout=DECK_BRIEF_TIMEOUT,
        validator=_validate_deck_brief,
        add_dirs=add_dirs,
    )


def call_section_split(deck_id: str, deck_brief: dict, slides_meta: list[dict],
                       project_context: dict | None = None,
                       png_dir: Path | None = None) -> list[dict]:
    """Split deck into sections. v30.2 vision: if png_dir is passed, section_split
    receives png_path per slide and Reads them to distinguish main agenda vs
    section-progress indicator (both look identical text-wise)."""
    payload = {
        "deck标识": deck_id,
        "deck标题": deck_brief.get("标题"),
        "总页数": len(slides_meta),
        "deck论述总结": deck_brief.get("论述总结"),
        "页面列表": [_slide_overview_for_section_split(s, png_dir=png_dir)
                     for s in slides_meta],
    }
    if project_context:
        payload["项目上下文"] = project_context
    skill = PROJECT_SECTION_SPLIT_SKILL if project_context else SECTION_SPLIT_SKILL
    prompt = json.dumps(payload, ensure_ascii=False)
    add_dirs = [str(png_dir.resolve())] if png_dir else None
    data = _claude_json_with_retry(
        stage="section_split",
        deck_id=deck_id,
        skill=skill,
        prompt=prompt,
        timeout=SECTION_SPLIT_TIMEOUT,
        validator=lambda d: _validate_section_split(d, len(slides_meta)),
        add_dirs=add_dirs,
    )
    return data["章节切分"]


def call_section_brief(deck_id: str, deck_brief: dict, section_split_entry: dict,
                       section_slides: list[dict], total_pages: int,
                       project_context: dict | None = None,
                       png_dir: Path | None = None) -> dict:
    """v30.3 vision: if png_dir is passed, section_brief Reads each slide's PNG
    to correctly synthesize 章节叙事 + 页间关系 (avoids 'two lines vs three
    contents' misclassification like ant slide 15)."""
    payload = {
        "所属deck标题": deck_brief.get("标题"),
        "deck论述总结": deck_brief.get("论述总结"),
        "章节序号": section_split_entry.get("章节序号"),
        "章节角色": section_split_entry.get("章节角色"),
        "章节标题": section_split_entry.get("标题"),
        "起始页": section_split_entry.get("起始页"),
        "结束页": section_split_entry.get("结束页"),
        "总页数": total_pages,
        "章节内页面": [_slide_overview_for_section_split(s, png_dir=png_dir)
                       for s in section_slides],
    }
    if project_context:
        payload["项目上下文"] = project_context
    skill = PROJECT_SECTION_BRIEF_SKILL if project_context else SECTION_BRIEF_SKILL
    prompt = json.dumps(payload, ensure_ascii=False)
    expected_rel = max(0, len(section_slides) - 1)
    add_dirs = [str(png_dir.resolve())] if png_dir else None
    return _claude_json_with_retry(
        stage="section_brief",
        deck_id=deck_id,
        skill=skill,
        prompt=prompt,
        timeout=SECTION_BRIEF_TIMEOUT,
        validator=lambda d: _validate_section_brief(d, expected_rel),
        add_dirs=add_dirs,
    )


def call_slide_brief(deck_id: str, deck_brief: dict, section_split_entry: dict,
                     section_brief: dict, section_slides: list[dict],
                     all_slides_by_idx: dict[int, dict],
                     project_context: dict | None = None,
                     png_dir: Path | None = None) -> list[dict]:
    """Run slide_brief on a complete section. Returns list[dict] of length
    == len(section_slides), in the same order.

    `png_dir`: if passed (e.g. imports/<deck_id>/pngs/), slide_brief runs in
    vision mode — each slide's PNG is included in the payload and Claude is
    told to Read them before writing brief.
    """
    if not section_slides:
        return []
    expected_indices = [s.get("index") for s in section_slides]
    enriched: list[dict] = []
    for i, s in enumerate(section_slides):
        prev_role = None
        next_role = None
        idx = s.get("index")
        if idx and idx > 1:
            prev = all_slides_by_idx.get(idx - 1)
            if prev:
                prev_role = prev.get("pageType")
        if idx and (idx + 1) in all_slides_by_idx:
            next_role = all_slides_by_idx[idx + 1].get("pageType")
        enriched.append(_slide_overview_for_slide_brief(s, prev_role, next_role,
                                                        png_dir=png_dir))

    payload = {
        "所属deck标题": deck_brief.get("标题"),
        "所属章节序号": section_split_entry.get("章节序号"),
        "所属章节标题": section_split_entry.get("标题"),
        "所属章节叙事": section_brief.get("章节叙事"),
        "章节起始页": section_split_entry.get("起始页"),
        "章节结束页": section_split_entry.get("结束页"),
        "章节内全部页面": enriched,
    }
    if project_context:
        payload["项目上下文"] = project_context
    skill = PROJECT_SLIDE_BRIEF_SKILL if project_context else SLIDE_BRIEF_SKILL
    prompt = json.dumps(payload, ensure_ascii=False)
    add_dirs = [str(png_dir.resolve())] if png_dir else None
    data = _claude_json_with_retry(
        stage="slide_brief",
        deck_id=deck_id,
        skill=skill,
        prompt=prompt,
        timeout=SLIDE_BRIEF_TIMEOUT,
        validator=lambda d: _validate_slide_briefs(d, expected_indices),
        add_dirs=add_dirs,
    )
    return data["页面画像"]


# --------------------------------------------------------------------------
# v20 enhance step — augment freshly-built slide briefs with 4 more fields.
# Runs as step 5 inside generate_deck_full_brief (after slide_brief). Batches
# concurrent calls PER DECK (small pool, 8) so total load stays reasonable
# even under outer deck-level fan-out.
# --------------------------------------------------------------------------

def _validate_enhance(data: Any) -> str | None:
    if not isinstance(data, dict):
        return "enhance output is not a JSON object"
    missing = [k for k in ENHANCE_FIELDS if k not in data]
    if missing:
        return f"missing enhance keys: {missing}"
    return None


def _section_role_context(section_slides: list[dict]) -> list[str]:
    """Return ordered `页面角色` list for a section's slides (used as prompt ctx)."""
    return [str(s.get("页面角色") or "?") for s in section_slides]


def _enhance_one_slide_call(*, deck_id: str, deck_title: str, section_title: str,
                             section_role_ctx: list[str], slide_pos_in_section: int,
                             slide_zh: dict,
                             png_dir: Path | None = None) -> dict | None:
    """Call enhance skill for ONE slide. Returns the 4-field dict, or None on
    hard failure (already retried MAX_RETRIES times inside).

    `png_dir`: if set, resolves slide's png_path and passes as add_dir so the
    enhance skill can Read the rendered PNG.
    """
    payload = {
        "slide_id": slide_zh.get("页标识"),
        "所属deck标题": deck_title,
        "所属章节标题": section_title,
        "该 section 内所有页角色顺序": section_role_ctx,
        "本页原始位置": slide_pos_in_section,
        "本页原始关键文字": slide_zh.get("关键文字") or [],
        "旧brief": {
            "页序号": slide_zh.get("页序号"),
            "标题": slide_zh.get("标题"),
            "核心论断": slide_zh.get("核心论断"),
            "本页讲什么": slide_zh.get("本页讲什么"),
            "关键文字": slide_zh.get("关键文字"),
            "视觉骨架": slide_zh.get("视觉骨架"),
            "页面角色": slide_zh.get("页面角色"),
        },
    }
    add_dirs = None
    if png_dir is not None:
        idx = slide_zh.get("页序号")
        if idx is not None:
            png = png_dir / f"slide_{idx:02d}.png"
            if png.exists():
                payload["png_path"] = str(png.resolve())
                add_dirs = [str(png_dir.resolve())]
    prompt = (
        "Enhance slide brief with 4 new v20 fields per the slide_brief_enhance skill. "
        "Return strict JSON only.\n\nINPUT:\n" + json.dumps(payload, ensure_ascii=False)
    )
    try:
        return _claude_json_with_retry(
            stage="slide_brief_enhance", deck_id=deck_id,
            skill=SLIDE_BRIEF_ENHANCE_SKILL, prompt=prompt,
            timeout=ENHANCE_TIMEOUT, validator=_validate_enhance,
            add_dirs=add_dirs,
        )
    except BriefGenerationError as exc:
        _safe_print(f"  [enhance/{deck_id}] slide {slide_zh.get('页序号')} FAILED: {exc}")
        return None


def enhance_slide_briefs_inline(deck_id: str, deck_title: str,
                                 sections_zh: list[dict],
                                 slides_zh: list[dict],
                                 png_dir: Path | None = None) -> int:
    """Fan-out enhance calls for every slide in this deck, merge results back
    into `slides_zh` in place. Returns count of slides successfully enhanced.

    Concurrency is scoped PER DECK to keep the outer batch driver in control.
    """
    if not slides_zh:
        return 0
    # Build section-lookup for role context
    slides_by_section: dict[str, list[dict]] = {}
    for s in slides_zh:
        slides_by_section.setdefault(s.get("所属章节") or "", []).append(s)
    sec_title_by_id = {s.get("章节标识"): s.get("标题") for s in sections_zh}
    for lst in slides_by_section.values():
        lst.sort(key=lambda x: x.get("页序号") or 0)

    tasks: list[tuple[dict, dict]] = []  # (slide_zh, kwargs)
    for section_id, section_slides in slides_by_section.items():
        role_ctx = _section_role_context(section_slides)
        section_title = sec_title_by_id.get(section_id) or ""
        for pos, sl in enumerate(section_slides, start=1):
            tasks.append((sl, dict(
                deck_id=deck_id, deck_title=deck_title,
                section_title=section_title, section_role_ctx=role_ctx,
                slide_pos_in_section=pos, slide_zh=sl,
                png_dir=png_dir,
            )))

    print(f"[brief/{deck_id}] step 5/5: enhance ({len(tasks)} slides, "
          f"pool={ENHANCE_MAX_PARALLEL_PER_DECK})", flush=True)
    ok_count = 0
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=ENHANCE_MAX_PARALLEL_PER_DECK
    ) as ex:
        futs = {ex.submit(_enhance_one_slide_call, **kw): sl for sl, kw in tasks}
        for fut in concurrent.futures.as_completed(futs):
            sl = futs[fut]
            data = fut.result()
            if data is None:
                continue
            for k in ENHANCE_FIELDS:
                sl[k] = data.get(k)
            ok_count += 1
    print(f"[brief/{deck_id}] step 5/5: enhance ok={ok_count}/{len(tasks)}", flush=True)
    return ok_count


# --------------------------------------------------------------------------
# Top-level orchestrator
# --------------------------------------------------------------------------

def generate_deck_full_brief(
    *,
    deck_id: str,
    source_pptx: str,
    file_sha1: str | None,
    slide_size: list[int] | None,
    slides_meta: list[dict],
    project_context: dict | None = None,
) -> tuple[dict, list[dict], list[dict]]:
    """Run the 4-skill pipeline for ONE deck.

    `slides_meta` is the imports manifest's `slides[]` (sorted by index).
    Each item has at minimum: index, pageType, textSamples, shapeCount,
    imageAssets, slidePath.

    `project_context` (optional): when this deck is being analyzed in the
    context of a specific project (sources/ upload), pass the project's
    `{项目主题, 项目主题标签, 项目章节}`. The skill then additionally
    outputs `本项目相关性评分` + `适合本项目章节`. For global library
    builds, leave this None.

    Returns Chinese-keyed `(deck_zh, sections_zh, slides_zh)` ready for
    `library_tree.write_deck_tree`. Raises BriefGenerationError on any
    stage's final failure (no fallback).
    """
    if not slides_meta:
        raise BriefGenerationError("setup", deck_id, "empty slides_meta", "")

    slides_meta = sorted(slides_meta, key=lambda x: x.get("index") or 0)
    all_slides_by_idx = {s.get("index"): s for s in slides_meta if s.get("index")}
    total_pages = len(slides_meta)

    # v30 vision: locate PNG dir (built by svg_to_png upstream). If absent,
    # skip vision (brief still runs text-only). Log a warning so user notices.
    png_dir_candidate = ROOT / "data" / "resources_library" / "material" / "imports" / deck_id / "pngs"
    png_dir = png_dir_candidate if png_dir_candidate.exists() else None
    if png_dir is None:
        _safe_print(f"[brief/{deck_id}] WARN: no pngs/ dir found — running text-only "
                    f"(run `preprocess svg-to-png` first for vision)")

    vision_note = " [vision]" if png_dir else ""
    print(f"[brief/{deck_id}] step 1/5: deck_brief{vision_note}", flush=True)
    deck_brief = call_deck_brief(deck_id, source_pptx, slides_meta, slide_size,
                                 project_context=project_context,
                                 png_dir=png_dir)

    print(f"[brief/{deck_id}] step 2/5: section_split{vision_note}", flush=True)
    splits = call_section_split(deck_id, deck_brief, slides_meta,
                                project_context=project_context,
                                png_dir=png_dir)

    print(f"[brief/{deck_id}] step 3/5: section_briefs ({len(splits)} sections){vision_note}", flush=True)
    sections_zh: list[dict] = []
    slides_zh: list[dict] = []
    for split_entry in splits:
        sec_idx = split_entry["章节序号"]
        start_p = int(split_entry["起始页"])
        end_p = int(split_entry["结束页"])
        section_slides = [s for s in slides_meta
                          if start_p <= (s.get("index") or 0) <= end_p]
        sec_brief = call_section_brief(deck_id, deck_brief, split_entry,
                                       section_slides, total_pages,
                                       project_context=project_context,
                                       png_dir=png_dir)

        # --- per-section slide briefs (1 Claude call covers the whole section) ---
        print(f"[brief/{deck_id}] step 4/5: slide_brief sec.{sec_idx} "
              f"({len(section_slides)} slides){vision_note}", flush=True)
        slide_briefs = call_slide_brief(deck_id, deck_brief, split_entry, sec_brief,
                                        section_slides, all_slides_by_idx,
                                        project_context=project_context,
                                        png_dir=png_dir)

        # ---- compose Chinese-keyed records ----
        section_id = f"{deck_id}.sec.{sec_idx:02d}"
        sec_zh = {
            "章节标识": section_id,
            "deck标识": deck_id,
            "章节序号": sec_idx,
            "章节角色": split_entry.get("章节角色"),
            "标题": split_entry.get("标题"),
            "章节叙事": sec_brief.get("章节叙事"),
            "页码范围": [start_p, end_p],
            "页数": len(section_slides),
            "页ID列表": [f"slide_{s.get('index'):02d}" for s in section_slides],
            "页间关系": sec_brief.get("页间关系") or [],
            "适合复用场景": sec_brief.get("适合复用场景") or [],
            "不适合复用场景": sec_brief.get("不适合复用场景") or [],
            "在deck中的位置": sec_brief.get("在deck中的位置") or "",
            "切分原因": split_entry.get("切分原因"),
            "分析状态": BRIEF_MODEL,
        }
        sections_zh.append(sec_zh)

        for raw, brief in zip(section_slides, slide_briefs):
            sl_idx = raw.get("index")
            slide_id = f"{deck_id}.slide_{sl_idx:02d}"
            slides_zh.append({
                "页标识": slide_id,
                "所属章节": section_id,
                "deck标识": deck_id,
                "页序号": sl_idx,
                "源文件": source_pptx,
                "页面角色": brief.get("页面角色") or raw.get("pageType"),
                "标题": brief.get("标题"),
                "核心论断": brief.get("核心论断"),
                "本页讲什么": brief.get("本页讲什么"),
                "关键文字": brief.get("关键文字") or [],
                "视觉骨架": brief.get("视觉骨架") or [],
                "资源ID列表": [f"{deck_id}.slide_{sl_idx:02d}.asset.{i+1:02d}"
                               for i, _ in enumerate(raw.get("imageAssets") or [])],
                "适合复用场景": brief.get("适合复用场景") or [],
                "不适合复用场景": brief.get("不适合复用场景") or [],
                "上页角色": brief.get("上页角色"),
                "下页角色": brief.get("下页角色"),
                "分析状态": BRIEF_MODEL,
            })

    # ---- step 5: v20 enhance (in-place merge of 4 new fields into slides_zh) ----
    enhance_slide_briefs_inline(deck_id, deck_brief.get("标题") or "",
                                sections_zh, slides_zh,
                                png_dir=png_dir)

    # ---- compose deck-level Chinese-keyed record ----
    deck_zh = {
        "deck标识": deck_id,
        "源文件": source_pptx,
        "源哈希": file_sha1,
        "标题": deck_brief.get("标题"),
        "总页数": total_pages,
        "章节数": len(splits),
        "画布尺寸": slide_size,
        "主题标签": deck_brief.get("主题标签") or [],
        "目标受众": deck_brief.get("目标受众"),
        "报告类型": deck_brief.get("报告类型"),
        "适用场景": deck_brief.get("适用场景"),
        "论述弧线": deck_brief.get("论述弧线") or [],
        "论述总结": deck_brief.get("论述总结"),
        "适合复用场景": deck_brief.get("适合复用场景") or [],
        "不适合复用场景": deck_brief.get("不适合复用场景") or [],
        "分析状态": BRIEF_MODEL,
    }
    return deck_zh, sections_zh, slides_zh


# --------------------------------------------------------------------------
# Batch driver — parallelize across decks
# --------------------------------------------------------------------------

_print_lock = threading.Lock()


def _safe_print(msg: str) -> None:
    """Threadsafe print so parallel deck logs don't interleave mid-line."""
    with _print_lock:
        print(msg, flush=True)


def generate_briefs_for_decks(
    deck_inputs: list[dict],
    *,
    decks_root: Path,
    max_concurrency: int = DEFAULT_MAX_DECK_CONCURRENCY,
    write_tree: bool = True,
    on_deck_done: Callable[[str, dict], None] | None = None,
) -> dict:
    """Run the 4-skill brief pipeline on each input deck IN PARALLEL.

    `deck_inputs` is a list of dicts with these keys:
        - deck_id (str)
        - source_pptx (str)
        - file_sha1 (str | None)
        - slide_size (list[int] | None)
        - slides_meta (list[dict])  — from imports/<deck_id>/manifest.json's slides[]

    Within one deck the 4 stages run sequentially (data dependencies);
    across decks we fan out to a thread pool of size `max_concurrency`.

    Returns a summary dict:
        {
          "ok": [deck_id, ...],
          "failed": [{"deck_id": ..., "error": ..., "stage": ...}, ...],
          "elapsed_seconds": float,
          "concurrency": int,
        }

    If `write_tree` is True, each successful deck's tree is materialized
    under `decks_root` immediately after its briefs complete.
    """
    from . import library_tree

    decks_root = Path(decks_root)
    decks_root.mkdir(parents=True, exist_ok=True)

    ok: list[str] = []
    failed: list[dict] = []
    t0 = time.time()

    def _process_one(inp: dict) -> dict:
        deck_id = inp["deck_id"]
        try:
            deck_zh, sections_zh, slides_zh = generate_deck_full_brief(
                deck_id=deck_id,
                source_pptx=inp["source_pptx"],
                file_sha1=inp.get("file_sha1"),
                slide_size=inp.get("slide_size"),
                slides_meta=inp["slides_meta"],
                project_context=inp.get("project_context"),
            )
        except BriefGenerationError as exc:
            _safe_print(f"[brief/FAIL] {deck_id}: stage={exc.stage} err={exc.last_error[:200]}")
            return {"deck_id": deck_id, "ok": False, "stage": exc.stage,
                    "error": exc.last_error}
        except Exception as exc:  # noqa: BLE001
            tb = traceback.format_exc(limit=4)
            _safe_print(f"[brief/CRASH] {deck_id}: {exc!r}\n{tb}")
            return {"deck_id": deck_id, "ok": False, "stage": "unknown",
                    "error": f"{type(exc).__name__}: {exc}"}

        if write_tree:
            try:
                summary = library_tree.write_deck_tree(decks_root, deck_zh, sections_zh, slides_zh)
                _safe_print(f"[brief/OK] {deck_id}: tree → {summary['deck_dir']} "
                            f"({summary['sections_written']} sec, {summary['slides_written']} slides)")
            except Exception as exc:  # noqa: BLE001
                tb = traceback.format_exc(limit=4)
                _safe_print(f"[brief/WRITE-FAIL] {deck_id}: {exc!r}\n{tb}")
                return {"deck_id": deck_id, "ok": False, "stage": "write_tree",
                        "error": f"{type(exc).__name__}: {exc}"}

        return {"deck_id": deck_id, "ok": True,
                "section_count": len(sections_zh),
                "slide_count": len(slides_zh)}

    n = len(deck_inputs)
    _safe_print(f"[brief] starting batch: {n} decks, concurrency={max_concurrency}, model={BRIEF_MODEL}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrency,
                                               thread_name_prefix="brief") as pool:
        futs = {pool.submit(_process_one, inp): inp["deck_id"] for inp in deck_inputs}
        done_count = 0
        for fut in concurrent.futures.as_completed(futs):
            deck_id = futs[fut]
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                _safe_print(f"[brief/POOL-CRASH] {deck_id}: {exc!r}")
                res = {"deck_id": deck_id, "ok": False, "stage": "pool",
                       "error": f"{type(exc).__name__}: {exc}"}
            done_count += 1
            if res["ok"]:
                ok.append(deck_id)
            else:
                failed.append(res)
            _safe_print(f"[brief/progress] {done_count}/{n} done "
                        f"(ok={len(ok)}, failed={len(failed)})")
            if on_deck_done:
                try:
                    on_deck_done(deck_id, res)
                except Exception:  # noqa: BLE001
                    pass

    elapsed = time.time() - t0
    summary = {
        "ok": ok,
        "failed": failed,
        "elapsed_seconds": elapsed,
        "concurrency": max_concurrency,
        "model": BRIEF_MODEL,
    }
    _safe_print(f"[brief] batch done in {elapsed:.1f}s: ok={len(ok)} failed={len(failed)}")
    return summary


def collect_deck_inputs_from_imports(
    deck_ids: list[str] | None = None,
    *,
    dedup_by_source: bool = True,
) -> list[dict]:
    """Read `data/resources_library/material/imports/<deck_id>/manifest.json` for each
    requested deck (or all imports if `deck_ids` is None) and build the
    input dict list for `generate_briefs_for_decks`.

    `dedup_by_source=True` (default): when multiple imports share the same
    source pptx path (e.g., legacy duplicates `tpl.topic.paper_share.<hash>`
    and `tpl.topic.论文分享.<hash>` after a scope rename), keep only one.
    Preference order: Chinese-named scope > English-named scope >
    earliest-by-deck_id (so `论文分享` wins over `paper_share`).
    """
    imports_root = ROOT / "data/resources_library/material/imports"
    if not imports_root.exists():
        raise FileNotFoundError(f"no imports dir: {imports_root}")

    lib_manifest_path = ROOT / "data/resources_library/material/manifest.json"
    if lib_manifest_path.exists():
        lib_manifest = json.loads(lib_manifest_path.read_text())
        sha_by_source = {f["path"]: f.get("sha1") for f in lib_manifest.get("files", [])}
    else:
        sha_by_source = {}

    if deck_ids is None:
        deck_ids = sorted(p.name for p in imports_root.iterdir() if p.is_dir())

    out: list[dict] = []
    for deck_id in deck_ids:
        imp_dir = imports_root / deck_id
        manifest_path = imp_dir / "manifest.json"
        if not manifest_path.exists():
            _safe_print(f"[brief/skip] {deck_id}: no imports manifest")
            continue
        m = json.loads(manifest_path.read_text())
        slides = m.get("slides") or []
        # `source` is `{pptx: <abs path>, name: <basename>}` in imports manifests
        src_raw = m.get("source")
        if isinstance(src_raw, dict):
            src_abs = src_raw.get("pptx") or ""
        else:
            src_abs = str(src_raw or "")
        # Relativize against repo root if possible — that's how the lib manifest
        # records `path:` for SHA1 lookups.
        try:
            source_pptx = str(Path(src_abs).resolve().relative_to(ROOT))
        except (ValueError, OSError):
            source_pptx = src_abs

        # slideSize: imports uses {width_emu, height_emu}, not {cx, cy}
        sld = m.get("slideSize") or {}
        if "cx" in sld:
            slide_size = [sld.get("cx"), sld.get("cy")]
        elif "width_emu" in sld:
            slide_size = [sld.get("width_emu"), sld.get("height_emu")]
        else:
            slide_size = None

        # Prefer sha1 from library manifest; fall back to computing it from
        # the source pptx directly (manifest is missing on partial rebuilds).
        file_sha1 = sha_by_source.get(source_pptx)
        if not file_sha1:
            try:
                pptx_abs = (ROOT / source_pptx) if not Path(source_pptx).is_absolute() else Path(source_pptx)
                if pptx_abs.exists():
                    import hashlib as _hashlib
                    _h = _hashlib.sha1()
                    with pptx_abs.open("rb") as _f:
                        for _chunk in iter(lambda: _f.read(8192), b""):
                            _h.update(_chunk)
                    file_sha1 = _h.hexdigest()
            except OSError:
                file_sha1 = None

        out.append({
            "deck_id": deck_id,
            "source_pptx": source_pptx,
            "file_sha1": file_sha1,
            "slide_size": slide_size,
            "slides_meta": slides,
        })

    if dedup_by_source:
        out = _dedup_by_source(out)
    return out


def _dedup_by_source(inputs: list[dict]) -> list[dict]:
    """Collapse multiple imports that share the same source pptx.

    Identity is decided by the trailing SHA1 in `deck_id` — same hash means
    the file content is identical (e.g., a deck registered under both
    `tpl.topic.paper_share.<hash>` and `tpl.topic.论文分享.<hash>` after a
    scope rename). When duplicates are present we prefer the one whose
    scope path uses Chinese names (more descriptive).
    """

    def _scope_score(deck_id: str) -> int:
        cjk = sum(1 for c in deck_id if "一" <= c <= "鿿")
        return cjk * 100 + len(deck_id)

    def _hash_key(deck_id: str) -> str:
        # deck_id is "tpl.<scope>.<scope>.<sha>" — trailing segment is the SHA.
        # Fall back to the whole id if it doesn't fit that shape.
        parts = (deck_id or "").rsplit(".", 1)
        return parts[-1] if len(parts) > 1 else deck_id

    by_hash: dict[str, dict] = {}
    dropped = 0
    for inp in inputs:
        h = _hash_key(inp["deck_id"])
        existing = by_hash.get(h)
        if existing is None:
            by_hash[h] = inp
            continue
        # tie-break: prefer the deck_id with the better (more CJK) scope
        if _scope_score(inp["deck_id"]) > _scope_score(existing["deck_id"]):
            _safe_print(f"[brief/dedup] keep {inp['deck_id']} drop {existing['deck_id']} (same hash {h})")
            by_hash[h] = inp
        else:
            _safe_print(f"[brief/dedup] keep {existing['deck_id']} drop {inp['deck_id']} (same hash {h})")
        dropped += 1

    if dropped:
        _safe_print(f"[brief/dedup] removed {dropped} duplicate import(s); {len(by_hash)} unique decks")
    return list(by_hash.values())


# --------------------------------------------------------------------------
# CLI smoke test (one deck only)
# --------------------------------------------------------------------------

def _cli_smoke():
    """Run brief generation on one or more decks.

    Usage:
        python3 -m ppt_agent_app.library_brief                       # default: 1 sample deck
        python3 -m ppt_agent_app.library_brief <deck_id>             # one specific deck
        python3 -m ppt_agent_app.library_brief --all                 # all decks, parallel
        python3 -m ppt_agent_app.library_brief --all -j 4            # 4-way parallel
        python3 -m ppt_agent_app.library_brief <id1> <id2> ... -j 2  # subset parallel
    """
    import sys

    args = sys.argv[1:]
    concurrency = DEFAULT_MAX_DECK_CONCURRENCY
    deck_ids: list[str] | None = None
    do_all = False

    i = 0
    rest: list[str] = []
    while i < len(args):
        a = args[i]
        if a == "-j" and i + 1 < len(args):
            concurrency = int(args[i + 1])
            i += 2
            continue
        if a in ("--all", "-a"):
            do_all = True
            i += 1
            continue
        rest.append(a)
        i += 1

    if do_all:
        deck_ids = None  # collect_deck_inputs handles None as "all"
        out_root = ROOT / "data/resources_library/material/decks"
    elif rest:
        deck_ids = rest
        out_root = ROOT / "data/resources_library/material/decks"
    else:
        # default: first deck under imports/ (for quick smoke test)
        imports_root = ROOT / "data/resources_library/material/imports"
        if imports_root.exists():
            first = sorted(p.name for p in imports_root.iterdir() if p.is_dir())
            deck_ids = [first[0]] if first else None
        else:
            deck_ids = None
        if not deck_ids:
            print("no imports found; run `preprocess import-all` first", file=sys.stderr)
            sys.exit(2)
        # write to /tmp so we don't clobber data/ during smoke testing
        out_root = Path("/tmp/library-brief-test/decks")

    inputs = collect_deck_inputs_from_imports(deck_ids)
    if not inputs:
        print("no deck inputs collected", file=sys.stderr)
        sys.exit(2)

    print(f"=== brief generation: {len(inputs)} deck(s), concurrency={concurrency} ===")
    for inp in inputs[:5]:
        print(f"  {inp['deck_id']:<55} slides={len(inp['slides_meta'])} src={inp['source_pptx']}")
    if len(inputs) > 5:
        print(f"  ... + {len(inputs)-5} more")

    summary = generate_briefs_for_decks(
        inputs,
        decks_root=out_root,
        max_concurrency=concurrency,
        write_tree=True,
    )

    print()
    print("=== summary ===")
    print(json.dumps({k: (v if not isinstance(v, list) or len(v) <= 5 else f"{len(v)} items")
                      for k, v in summary.items()}, ensure_ascii=False, indent=2))
    if summary["failed"]:
        print("\nfailed decks:")
        for f in summary["failed"][:10]:
            print(f"  {f['deck_id']} [{f.get('stage')}]: {(f.get('error') or '')[:200]}")


if __name__ == "__main__":
    _cli_smoke()

