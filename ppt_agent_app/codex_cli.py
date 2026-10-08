"""Codex CLI wrapper — mirror of claude_cli for the REVIEW stage.

Uses `codex exec -o <outfile>` so the final agent message lands cleanly in a
file rather than being mixed with JSONL event stream. `--skip-git-repo-check`
keeps codex from refusing to run when invoked from a non-git location
(stage_runner runs from repo root so this is mostly defensive).

`skill` (list of md file paths) is inlined into the prompt header — codex has
no `--append-system-prompt` equivalent. This is a small token cost but keeps
the contract identical to claude_cli for the REVIEW orchestrator.

Multimodal: pass `images=[path, ...]` → each becomes a `-i path` flag.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .models import ROOT


CLI_PATH_DEFAULT = "/home/zjy/.npm-global/bin/codex"
MODEL_DEFAULT = "gpt-5.5"
TIMEOUT_DEFAULT = 600
RUNTIME_HOME = ROOT / ".codex-runtime"
CODEX_RUNTIME_FILES = ("config.toml", "installation_id", "version.json")


def _prepare_codex_runtime_env() -> dict:
    """Run nested Codex CLI from an isolated writable home.

    The PPT pipeline itself may run inside a Codex session. Inheriting that
    session's CODEX_* variables makes nested `codex exec` try to initialize the
    in-process app-server client and write PATH aliases under the outer session
    sandbox, which can fail with "Read-only file system". Copy only the small
    auth/config files needed by the CLI, then clear the outer session variables.
    """
    RUNTIME_HOME.mkdir(parents=True, exist_ok=True)
    source_home = Path(os.environ.get("PPT_AGENT_CODEX_SOURCE_HOME") or Path.home() / ".codex")
    for name in CODEX_RUNTIME_FILES:
        src = source_home / name
        dst = RUNTIME_HOME / name
        if not src.exists():
            continue
        try:
            if src.resolve() != dst.resolve():
                shutil.copy2(src, dst)
        except Exception:
            pass

    env = os.environ.copy()
    for key in list(env):
        if key.startswith("CODEX_"):
            env.pop(key, None)
    env.update({
        "HOME": str(RUNTIME_HOME),
        "CODEX_HOME": str(RUNTIME_HOME),
        "XDG_CONFIG_HOME": str(RUNTIME_HOME / "config"),
        "XDG_CACHE_HOME": str(RUNTIME_HOME / "cache"),
        "XDG_DATA_HOME": str(RUNTIME_HOME / "data"),
        "TMPDIR": env.get("TMPDIR") or "/tmp",
    })
    for key in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    return env


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
    """Return the substring covering the first balanced JSON object/array."""
    s = raw.lstrip()
    if not s:
        return raw
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


def call_codex_json(
    prompt: str,
    *,
    skill: list[str] | str | None = None,
    images: list[str] | None = None,
    model: str = MODEL_DEFAULT,
    cli_path: str = CLI_PATH_DEFAULT,
    timeout: int = TIMEOUT_DEFAULT,
) -> dict:
    """Run `codex exec` and parse the final agent message as JSON.

    Returns ``{"ok": True, "data": <parsed>}`` on success, otherwise
    ``{"ok": False, "error": "...", "raw_excerpt": "..."}``.
    """
    skill_text = _load_skill_text(skill)
    # Inline skill md as a header followed by the actual task prompt.
    if skill_text:
        full_prompt = (
            "=== SKILL INSTRUCTIONS (READ FIRST) ===\n"
            f"{skill_text}\n\n"
            "=== TASK ===\n"
            f"{prompt}\n\n"
            "Return JSON only. Do not write any files. Do not run shell commands."
        )
    else:
        full_prompt = prompt + "\n\nReturn JSON only."

    # Write last-message output to a temp file so we get clean final-message text
    # (without the JSONL event stream that goes to stdout).
    with tempfile.NamedTemporaryFile(mode="r", suffix=".txt", delete=False) as tf:
        out_path = tf.name

    cmd = [
        cli_path, "exec",
        "--sandbox", "read-only",
        "--skip-git-repo-check",
        "--ignore-rules",
        "--ephemeral",
        "-m", model,
        "-o", out_path,
    ]
    for img in images or []:
        cmd.extend(["-i", str(img)])
    # Pass long prompt via stdin (codex accepts `-` to read from stdin).
    cmd.append("-")

    try:
        proc = subprocess.run(cmd, input=full_prompt, capture_output=True,
                              text=True, timeout=timeout,
                              cwd=ROOT, env=_prepare_codex_runtime_env())
    except FileNotFoundError as exc:
        return {"ok": False, "error": f"codex CLI not found at {cli_path}: {exc}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout after {timeout}s"}

    try:
        raw = Path(out_path).read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        raw = ""
    finally:
        try:
            Path(out_path).unlink(missing_ok=True)
        except Exception:
            pass

    if proc.returncode != 0:
        return {
            "ok": False,
            "error": f"cli rc={proc.returncode}: {(proc.stderr or '')[:400]}",
            "raw_excerpt": (raw or proc.stdout or "")[:400],
        }
    raw = _strip_code_fence(raw or "")
    if not raw:
        return {"ok": False, "error": "empty output from codex",
                "raw_excerpt": (proc.stdout or "")[:400]}
    try:
        return {"ok": True, "data": json.loads(raw)}
    except json.JSONDecodeError:
        candidate = _extract_first_json_object(raw)
        try:
            return {"ok": True, "data": json.loads(candidate)}
        except json.JSONDecodeError as exc:
            return {"ok": False, "error": f"json decode: {exc}",
                    "raw_excerpt": raw[:600]}


def call_codex_text(
    prompt: str,
    *,
    skill: list[str] | str | None = None,
    images: list[str] | None = None,
    model: str = MODEL_DEFAULT,
    cli_path: str = CLI_PATH_DEFAULT,
    timeout: int = TIMEOUT_DEFAULT,
) -> dict:
    """Variant that returns the final agent message text without JSON parsing."""
    skill_text = _load_skill_text(skill)
    if skill_text:
        full_prompt = (
            "=== SKILL INSTRUCTIONS (READ FIRST) ===\n"
            f"{skill_text}\n\n"
            "=== TASK ===\n"
            f"{prompt}\n\n"
            "Do not write any files. Do not run shell commands."
        )
    else:
        full_prompt = prompt

    with tempfile.NamedTemporaryFile(mode="r", suffix=".txt", delete=False) as tf:
        out_path = tf.name

    cmd = [
        cli_path, "exec",
        "--sandbox", "read-only",
        "--skip-git-repo-check",
        "--ignore-rules",
        "--ephemeral",
        "-m", model,
        "-o", out_path,
    ]
    for img in images or []:
        cmd.extend(["-i", str(img)])
    cmd.append("-")

    try:
        proc = subprocess.run(cmd, input=full_prompt, capture_output=True,
                              text=True, timeout=timeout,
                              cwd=ROOT, env=_prepare_codex_runtime_env())
    except FileNotFoundError as exc:
        return {"ok": False, "error": f"codex CLI not found at {cli_path}: {exc}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout after {timeout}s"}

    try:
        text = Path(out_path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        text = ""
    finally:
        try:
            Path(out_path).unlink(missing_ok=True)
        except Exception:
            pass

    if proc.returncode != 0:
        return {
            "ok": False,
            "error": f"cli rc={proc.returncode}: {(proc.stderr or '')[:400]}",
            "raw_excerpt": (text or proc.stdout or "")[:400],
        }
    return {"ok": True, "text": text}
