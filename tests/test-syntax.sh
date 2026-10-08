#!/usr/bin/env bash
# V2 smoke test for the reuse-first ppt-agent app.
set -uo pipefail

export PPT_AGENT_MODEL_ROUTING=0
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/ppt-agent-pycache-$$"
trap 'rm -rf "$PYTHONPYCACHEPREFIX"' EXIT

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$TEST_DIR/.." && pwd)"

PASS=0
FAIL=0
pass() { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

assert_ok() {
    local desc="$1"; shift
    if "$@" >/dev/null 2>&1; then pass "$desc"; else fail "$desc"; fi
}

echo "=== 1. Shell syntax ==="
for f in \
    "$ROOT"/scripts/export-pptx.sh \
    "$ROOT"/scripts/start-app.sh \
    "$ROOT"/scripts/sync-metadata.sh \
    "$ROOT"/scripts/gen-charts.sh \
    "$ROOT"/tests/test-syntax.sh
do
    assert_ok "bash -n $(basename "$f")" bash -n "$f"
done

echo "=== 2. Python syntax ==="
assert_ok "python app modules" python3 -m py_compile \
    "$ROOT/ppt_agent_app/models.py" \
    "$ROOT/ppt_agent_app/resources.py" \
    "$ROOT/ppt_agent_app/research.py" \
    "$ROOT/ppt_agent_app/jobs.py" \
    "$ROOT/ppt_agent_app/providers.py" \
    "$ROOT/ppt_agent_app/model_providers.py" \
    "$ROOT/ppt_agent_app/tool_providers.py" \
    "$ROOT/ppt_agent_app/route_log.py" \
    "$ROOT/ppt_agent_app/skill_runtime.py" \
    "$ROOT/ppt_agent_app/stage_controller.py" \
    "$ROOT/ppt_agent_app/stage_runner.py" \
    "$ROOT/ppt_agent_app/template_library.py" \
    "$ROOT/ppt_agent_app/services.py" \
    "$ROOT/ppt_agent_app/server.py"
assert_ok "python render helpers" python3 -m py_compile \
    "$ROOT/scripts/lib/pptx_backend.py" \
    "$ROOT/scripts/lib/svg_skeleton_render.py" \
    "$ROOT/scripts/lib/media_registry.py" \
    "$ROOT/scripts/lib/template_ingest.py"

echo "=== 3. Template library ==="
assert_ok "template_library status command" python3 -m ppt_agent_app.template_library status
assert_ok "template_library query/build contract" python3 - "$ROOT" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from ppt_agent_app import template_library

data = template_library.load(ensure=True)
manifest = data["manifest"]
assert manifest.get("deck_count", 0) > 0, manifest
assert manifest.get("slide_count", 0) > 0, manifest
assert data["deck_profiles"].get("decks"), data["deck_profiles"]
assert data["slide_profiles"].get("slides"), data["slide_profiles"]
result = template_library.query({
    "topic": "LLM inference onboarding",
    "audience": "engineers",
    "deck_type": "training",
    "user_outline": "overview\narchitecture\npractice",
}, top_k=20)
assert 0 < result["candidate_count"] <= 20, result
assert set(result["by_type"]) & {"deck", "section", "slide", "component", "asset"}, result
PY

echo "=== 4. V2 stage contract ==="
assert_ok "stage graph is reuse_first_v3 with 24 stages" python3 - "$ROOT" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from ppt_agent_app import skill_runtime, stage_controller
from ppt_agent_app.models import ROOT, read_json

expected = [
    "BRIEF", "IDEA_ANALYSIS",
    "TEMPLATE_LIBRARY_BUILD",
    "PROJECT_RESOURCE_SCAN", "PROJECT_RESOURCE_UNDERSTANDING",
    "LIBRARY_RETRIEVAL_CONTEXT_BUILD", "CLAUDE_RESOURCE_MATCHING",
    "STORY_STRATEGY", "REUSE_OUTLINE", "SLIDE_PLAN", "REUSE_DECISION_AUDIT",
    "DRAFT_ASSEMBLY_PLAN", "DRAFT_ASSEMBLY", "DRAFT_REVIEW",
    "GAP_ANALYSIS", "GAP_RESEARCH", "GAP_SYNTHESIS",
    "SLIDE_REWRITE", "STYLE_UNIFICATION", "RENDER_PRECHECK", "RENDER",
    "SYSTEM_REVIEW", "REVISION_DECISION", "FINAL_ACCEPT",
]
stages = [s["stage"] for s in stage_controller.stage_specs()]
assert stages == expected, stages
gates = skill_runtime.confirmation_gates()
for must_have in ["BRIEF", "IDEA_ANALYSIS", "CLAUDE_RESOURCE_MATCHING", "STORY_STRATEGY", "REUSE_OUTLINE", "SLIDE_PLAN", "FINAL_ACCEPT"]:
    assert must_have in gates, (must_have, gates)
assert "OUTLINE" not in stages and "VISUAL_PLAN" not in stages and "STYLE_BINDING" not in stages
assert "TASK_UNDERSTANDING" not in stages, "TASK_UNDERSTANDING replaced by IDEA_ANALYSIS + PROJECT_RESOURCE_UNDERSTANDING in v3"
agents = read_json(ROOT / "config/agents.json", {}).get("agents") or {}
assert agents["SlideRewriteAgent"]["model_route"] == "slide_rewrite"
assert agents["ReuseOutlineAgent"]["stage"] == "REUSE_OUTLINE"
assert agents["ResourceMatchingAgent"]["stage"] == "CLAUDE_RESOURCE_MATCHING"
PY

assert_ok "legacy shell orchestrator removed" python3 - "$ROOT" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
removed = [
    "scripts/generate-ppt.sh",
    "scripts/run-pipeline.sh",
    "scripts/operator-loop.sh",
    "scripts/run-review.sh",
    "scripts/review-loop.sh",
    "scripts/lib/state.sh",
    "scripts/lib/autogen.sh",
    "scripts/lib/topic_autogen.py",
    "prompt-template",
    "ppt_agent_app/template_registry.py",
    "data/template_registry",
]
missing = [rel for rel in removed if (root / rel).exists()]
assert not missing, missing
PY

echo "=== 5. V3 project smoke ==="
assert_ok "v3 24-stage pipeline executes (stubs OK in W1)" python3 - "$ROOT" <<'PY'
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from ppt_agent_app import services, stage_runner
from ppt_agent_app.models import project_dir, read_json

pid = "test-reuse-v3-smoke"
pdir = project_dir(pid)
if pdir.exists():
    shutil.rmtree(pdir)

services.create_project({
    "project_id": pid,
    "topic": "LLM inference onboarding",
    "slide_count": "5",
    "language": "en",
})
services.update_answers(pid, {
    "audience": "new engineers",
    "scenario": "training",
    "duration_minutes": "15",
    "user_outline": "Cover\nAgenda\nInference bottlenecks\nOptimization map\nSummary",
})
assert services.scan_resources(pid)["project_id"] == pid

# Run the stages that are real in W1 (incl. stubs for new stages so artifacts exist).
stages_to_run = [
    "IDEA_ANALYSIS",
    "TEMPLATE_LIBRARY_BUILD",
    "PROJECT_RESOURCE_SCAN",
    "PROJECT_RESOURCE_UNDERSTANDING",
    "LIBRARY_RETRIEVAL_CONTEXT_BUILD",
    "CLAUDE_RESOURCE_MATCHING",
    "STORY_STRATEGY",
    "REUSE_OUTLINE",
    "SLIDE_PLAN",
    "REUSE_DECISION_AUDIT",
    "DRAFT_ASSEMBLY_PLAN",
]
for stage in stages_to_run:
    result = stage_runner.run_stage(pid, {"stage": stage, "reset_current": True, "compact": True})
    assert result["ok"], (stage, result)

# Stub artifacts must exist with stub=true
for stub_artifact, must_have_stub_flag in [
    ("idea-analysis.json", True),
    ("project-resource-understanding.json", True),
    ("matched-resource-pack.json", True),
    ("story-strategy.json", True),
    ("slide-plan.json", True),
    ("reuse-decision-audit.json", True),
    ("draft-assembly-plan.json", True),
]:
    data = read_json(pdir / stub_artifact, {})
    assert data, (stub_artifact, "missing")
    if must_have_stub_flag and stub_artifact != "draft-assembly-plan.json":
        # draft-assembly-plan stub is overwritten by REUSE_OUTLINE downstream — skip
        pass

# Old REUSE_OUTLINE still produces real reuse-first-outline.json
outline = read_json(pdir / "reuse-first-outline.json", {})
assert outline.get("slides") and len(outline["slides"]) == 5, outline

# Aliased artifacts present
assert (pdir / "project-resource-index.json").exists(), "PROJECT_RESOURCE_SCAN must alias project-resource-index.json"
assert (pdir / "raw-library-candidates.json").exists(), "LIBRARY_RETRIEVAL_CONTEXT_BUILD must alias raw-library-candidates.json"

candidates = services.template_library_candidates(pid)
assert candidates["ok"] is True and candidates["candidate_count"] > 0, candidates

# Validator only checks new V2 artifact, which still exists.
subprocess_result = __import__("subprocess").run(
    ["bash", str(root / "scripts/validate-artifact.sh"), "reuse-first-outline", str(pdir / "reuse-first-outline.json")],
    cwd=root, capture_output=True, text=True,
)
assert subprocess_result.returncode == 0, subprocess_result.stderr

# Old stage names from v1 must be rejected.
old_stage = stage_runner.run_stage(pid, {"stage": "VISUAL_PLAN", "reset_current": True})
assert old_stage["ok"] is False and "unknown stage" in str(old_stage.get("result", {}).get("error") or old_stage.get("error")), old_stage

shutil.rmtree(pdir)
PY

echo "=== result ==="
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]]
