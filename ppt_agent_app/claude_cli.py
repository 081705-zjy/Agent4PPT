"""Generic Claude CLI wrapper for stage handlers.

Reuses the headless `claude -p` mode (stdin prompt + skill as system-prompt
append) that template_library.deep_analyze validated. All W2-W6 stages that
need a model call should go through `call_claude_json` so we have one place to
tune timeout/cache/error behavior.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

from .models import ROOT


CLI_PATH_DEFAULT = "/home/zjy/.npm-global/bin/claude"
MODEL_DEFAULT = "claude-opus-4-7"
TIMEOUT_DEFAULT = 240

# 上游 API 瞬时错误(400/429/5xx/网关)的 stdout 签名 —— CLI 会把这类错误当作正常输出打到
# stdout, 但 rc=1。对这些情况做退避重试, 避免 stage 因一次瞬时抖动就 fallback。
_TRANSIENT_STDOUT_PATTERNS = (
    "API Error: 400",
    "API Error: 429",
    "API Error: 500",
    "API Error: 502",
    "API Error: 503",
    "API Error: 504",
    "模型服务调用失败",
    "rate_limit",
    "overloaded",
    "upstream connect error",
    "gateway",
    "temporarily unavailable",
    "socket connection was closed unexpectedly",
    "connection was closed unexpectedly",
    "Decompression error: ZlibError",
    "Failed to parse JSON",
)

_RETRY_BACKOFFS_SECONDS = (5, 15)  # 首次失败后 5s 重试; 再失败 15s 重试; 总共 3 次尝试


def _is_transient_cli_failure(rc: int, stdout: str, stderr: str) -> bool:
    """判定 CLI 一次调用是否属于瞬时错误 (值得重试)."""
    if rc == 0:
        return False
    # v30 fix: rc≠0 且 stdout+stderr 都空 → 视为瞬时错误 (CLI 静默失败,
    # 常见于 subprocess.communicate() 大 payload 场景或 CLI 内部崩溃).
    # 手动 CLI 重跑通常能 rc=0.
    if not (stdout or "").strip() and not (stderr or "").strip():
        return True
    blob = ((stdout or "") + "\n" + (stderr or "")).lower()
    return any(pat.lower() in blob for pat in _TRANSIENT_STDOUT_PATTERNS)


def _run_cli(cmd: list[str], prompt: str, timeout: int) -> tuple[int, str, str, str | None]:
    """Run claude CLI with transient-error retry.

    Returns (returncode, stdout, stderr, terminal_error).
    terminal_error is set only for non-retryable early failures
    (FileNotFoundError / TimeoutExpired) — otherwise it's None even on rc!=0.
    """
    total_attempts = 1 + len(_RETRY_BACKOFFS_SECONDS)
    last_rc, last_out, last_err = 1, "", ""
    for attempt in range(total_attempts):
        try:
            proc = subprocess.run(cmd, input=prompt, capture_output=True,
                                  text=True, timeout=timeout)
        except FileNotFoundError as exc:
            return 127, "", "", f"claude CLI not found at {cmd[0]}: {exc}"
        except subprocess.TimeoutExpired:
            # timeout: 也算瞬时, 但只在还有 attempt 时重试
            last_rc, last_out, last_err = 124, "", f"timeout after {timeout}s"
            if attempt < total_attempts - 1:
                sleep_s = _RETRY_BACKOFFS_SECONDS[attempt]
                print(f"[claude_cli] timeout after {timeout}s (attempt {attempt+1}/{total_attempts}); "
                      f"backoff {sleep_s}s then retry", flush=True)
                time.sleep(sleep_s)
                continue
            return last_rc, last_out, last_err, f"timeout after {timeout}s"

        last_rc = proc.returncode
        last_out = proc.stdout or ""
        last_err = proc.stderr or ""
        if last_rc == 0:
            return last_rc, last_out, last_err, None
        if not _is_transient_cli_failure(last_rc, last_out, last_err):
            return last_rc, last_out, last_err, None
        if attempt < total_attempts - 1:
            sleep_s = _RETRY_BACKOFFS_SECONDS[attempt]
            print(f"[claude_cli] transient upstream error "
                  f"(rc={last_rc}, stdout_head={last_out[:80]!r}); "
                  f"attempt {attempt+1}/{total_attempts}, backoff {sleep_s}s then retry",
                  flush=True)
            time.sleep(sleep_s)
    return last_rc, last_out, last_err, None


def _load_skill_text(skill_paths: list[str] | str | None) -> str:
    if not skill_paths:
        return ""
    if isinstance(skill_paths, str):
        skill_paths = [skill_paths]
    chunks: list[str] = []
    for rel in skill_paths:
        path = ROOT / str(rel)
        if path.exists():
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n\n".join(chunks)


def _strip_code_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)
    return raw.strip()


def _extract_first_json_object(raw: str) -> str:
    """Return the substring covering the first balanced JSON object / array
    found in ``raw``. Useful when the model emits a valid JSON followed by
    stray prose / a second object — json.loads alone raises "Extra data".

    Falls back to the original string if no balanced object is found.
    """
    s = raw.lstrip()
    if not s:
        return raw
    # Find first { or [
    start_obj = s.find("{")
    start_arr = s.find("[")
    if start_obj == -1 and start_arr == -1:
        return raw
    if start_arr == -1 or (start_obj != -1 and start_obj < start_arr):
        start, open_ch, close_ch = start_obj, "{", "}"
    else:
        start, open_ch, close_ch = start_arr, "[", "]"
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return raw


def call_claude_json(
    prompt: str,
    *,
    skill: list[str] | str | None = None,
    model: str = MODEL_DEFAULT,
    cli_path: str = CLI_PATH_DEFAULT,
    timeout: int = TIMEOUT_DEFAULT,
    add_dirs: list[str] | None = None,
    allowed_tools: list[str] | None = None,
) -> dict:
    """Run `claude -p` with the prompt fed via stdin and parse stdout as JSON.

    Returns ``{"ok": True, "data": <parsed>}`` on success, otherwise
    ``{"ok": False, "error": "...", "raw_excerpt": "..."}``.

    瞬时上游错误 (400/429/5xx/中文"模型服务调用失败") 由 _run_cli 自动退避重试 2 次。

    Vision / file access:
        add_dirs: extra directories the model may access via built-in tools
            (Read/Grep/...). Enables vision analysis when the prompt asks it
            to Read image files under those dirs.
        allowed_tools: which tools to whitelist. When add_dirs is passed and
            allowed_tools is None, defaults to ["Read"] so the model can only
            read (no shell/edit).
    """
    skill_text = _load_skill_text(skill)
    cmd = [
        cli_path,
        "-p",
        "--model", model,
        "--output-format", "text",
        "--permission-mode", "bypassPermissions",
    ]
    if add_dirs:
        for d in add_dirs:
            cmd.extend(["--add-dir", d])
        tools = allowed_tools if allowed_tools is not None else ["Read"]
        if tools:
            cmd.extend(["--allowedTools", ",".join(tools)])
    if skill_text:
        cmd.extend(["--append-system-prompt", skill_text])
    rc, stdout, stderr, terminal_err = _run_cli(cmd, prompt, timeout)
    if terminal_err:
        return {"ok": False, "error": terminal_err}
    if rc != 0:
        return {
            "ok": False,
            "error": f"cli rc={rc}: {(stderr or '')[:400]}",
            "raw_excerpt": (stdout or "")[:400],
        }
    raw = _strip_code_fence(stdout or "")
    if not raw:
        return {"ok": False, "error": "empty stdout from claude"}
    try:
        return {"ok": True, "data": json.loads(raw)}
    except json.JSONDecodeError:
        # Retry with first balanced JSON object — handles cases where the
        # model output trailing prose / a duplicate object.
        candidate = _extract_first_json_object(raw)
        try:
            return {"ok": True, "data": json.loads(candidate)}
        except json.JSONDecodeError as exc:
            return {"ok": False, "error": f"json decode: {exc}", "raw_excerpt": raw[:600]}


def call_claude_text(
    prompt: str,
    *,
    skill: list[str] | str | None = None,
    model: str = MODEL_DEFAULT,
    cli_path: str = CLI_PATH_DEFAULT,
    timeout: int = TIMEOUT_DEFAULT,
) -> dict:
    """Variant that returns raw text instead of parsing JSON."""
    skill_text = _load_skill_text(skill)
    cmd = [
        cli_path,
        "-p",
        "--model", model,
        "--output-format", "text",
        "--permission-mode", "bypassPermissions",
    ]
    if skill_text:
        cmd.extend(["--append-system-prompt", skill_text])
    rc, stdout, stderr, terminal_err = _run_cli(cmd, prompt, timeout)
    if terminal_err:
        return {"ok": False, "error": terminal_err}
    if rc != 0:
        return {"ok": False, "error": f"cli rc={rc}: {(stderr or '')[:400]}",
                "raw_excerpt": (stdout or "")[:400]}
    return {"ok": True, "text": (stdout or "").strip()}


def call_claude_with_tools(
    prompt: str,
    *,
    allowed_tools: list[str],
    skill: list[str] | str | None = None,
    parse_json: bool = True,
    model: str = MODEL_DEFAULT,
    cli_path: str = CLI_PATH_DEFAULT,
    timeout: int = TIMEOUT_DEFAULT,
) -> dict:
    """Run claude -p with built-in tools enabled (WebSearch, WebFetch, etc.).

    When parse_json=True, the model's final stdout is parsed as JSON; tool calls
    happen inside the model loop and don't leak to stdout. Pass allowed_tools
    like ["WebSearch", "WebFetch"] to scope what the model may invoke.
    """
    skill_text = _load_skill_text(skill)
    cmd = [
        cli_path,
        "-p",
        "--model", model,
        "--output-format", "text",
        "--permission-mode", "bypassPermissions",
        "--allowedTools", ",".join(allowed_tools),
    ]
    if skill_text:
        cmd.extend(["--append-system-prompt", skill_text])
    rc, stdout, stderr, terminal_err = _run_cli(cmd, prompt, timeout)
    if terminal_err:
        return {"ok": False, "error": terminal_err}
    if rc != 0:
        return {
            "ok": False,
            "error": f"cli rc={rc}: {(stderr or '')[:400]}",
            "raw_excerpt": (stdout or "")[:400],
        }
    raw = _strip_code_fence(stdout or "")
    if not parse_json:
        return {"ok": True, "text": raw}
    if not raw:
        return {"ok": False, "error": "empty stdout from claude"}
    try:
        return {"ok": True, "data": json.loads(raw)}
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"json decode: {exc}", "raw_excerpt": raw[:600]}


def call_with_retry(
    fn,
    *,
    attempts: int = 2,
    accept=lambda outcome: bool((outcome or {}).get("ok")),
):
    """Re-run ``fn()`` up to ``attempts`` times until ``accept(outcome)`` is True.

    Returns ``(outcome, attempts_used)``. The last outcome is returned even on
    failure so the caller can log details.
    """
    last = None
    for i in range(1, attempts + 1):
        last = fn()
        if accept(last):
            return last, i
    return last, attempts


def skill_paths_for_agent(agent_name: str) -> list[str]:
    """Resolve the skill files an agent declares in config/agents.json."""
    from . import skill_runtime

    cfg = skill_runtime.get_agent(agent_name) or {}
    skills = cfg.get("skills") or []
    return [str(p) for p in skills if p]
