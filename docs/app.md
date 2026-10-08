# ppt-agent App

`ppt_agent_app` is the local software layer on top of the existing ppt-agent generation
engine. It provides a browser UI and JSON API for interactive PPT generation.

## Start

```bash
bash scripts/start-app.sh
```

Default URL:

```text
http://127.0.0.1:8765
```

Optional environment overrides:

```bash
PPT_AGENT_HOST=127.0.0.1 PPT_AGENT_PORT=8765 bash scripts/start-app.sh
```

Local secrets can be stored in `.env.local`:

```bash
cp .env.example .env.local
# edit .env.local locally, then start the app
bash scripts/start-app.sh
```

`.env.local` is ignored by git. Do not paste API keys into chat or commit them.

## User Flow

1. Open the browser URL.
2. Enter topic, project ID, slide count, and language.
3. Save interaction answers: audience, scenario, style, story logic, reuse policy, citation policy.
4. Put reusable material into the project folder when needed:
   - `projects/<project-id>/templates/` for `.pptx` or `.json` templates
   - `projects/<project-id>/sources/` for `.md`, `.txt`, `.csv`, `.json` materials
   - `projects/<project-id>/assets/` for reusable images/assets
5. Click resource scan.
6. Run research/search when the deck needs papers, reports, links, or current facts.
7. Click generate PPT.
8. Inspect quality results and open/download `deck.pptx`.

## API

Create a project:

```bash
curl -sS -X POST http://127.0.0.1:8765/api/projects \
  -H 'content-type: application/json' \
  -d '{"topic":"端侧存储优化以及异构存储架构","project_id":"edge-storage","slide_count":"10","language":"zh"}'
```

Save interaction answers:

```bash
curl -sS -X POST http://127.0.0.1:8765/api/projects/edge-storage/answers \
  -H 'content-type: application/json' \
  -d '{"audience":"技术管理者、系统架构师","scenario":"技术方案汇报"}'
```

Scan project resources:

```bash
curl -sS -X POST http://127.0.0.1:8765/api/projects/edge-storage/resources \
  -H 'content-type: application/json' -d '{}'
```

Run research/search:

```bash
curl -sS -X POST http://127.0.0.1:8765/api/projects/edge-storage/research \
  -H 'content-type: application/json' \
  -d '{"research_depth":"deep"}'
```

Generate:

```bash
curl -sS -X POST http://127.0.0.1:8765/api/projects/edge-storage/generate \
  -H 'content-type: application/json' -d '{}'
```

Generate asynchronously:

```bash
curl -sS -X POST http://127.0.0.1:8765/api/projects/edge-storage/generate \
  -H 'content-type: application/json' -d '{"async":true,"research_depth":"deep"}'
curl -sS http://127.0.0.1:8765/api/jobs/<job_id>
```

Download outputs:

```text
GET /api/projects/edge-storage/files/deck.pptx
GET /api/projects/edge-storage/files/research.md
GET /api/projects/edge-storage/files/citations.json
GET /api/projects/edge-storage/files/run-manifest.json
```

Inspect model/tool routing:

```text
GET /api/model-routes
GET /api/providers/health
GET /api/tools/health
GET /api/routes/resolve?type=model&stage=outline
GET /api/routes/resolve?type=tool&tool=web_search
```

The browser UI has the same check as the "查看模型路由" button. It returns the
actual provider bound to each stage, not only a descriptive label.

Check whether the configured research adapter can run:

```text
GET /api/research-health
```

## Research Adapters

The app exposes a software API boundary for search and fetch. It does not hard-code a
single provider.

By default, the app uses the independent search adapter in
`scripts/lib/search_adapter.py`. Configure one provider in `.env.local`:

```text
ENABLE_EXTERNAL_WEBSEARCH=true
SEARCH_PROVIDER=tavily        # or serper
TAVILY_API_KEY=...
SERPER_API_KEY=...
WEBSEARCH_TIMEOUT=20
WEBSEARCH_MAX_RESULTS=5
WEBFETCH_TIMEOUT=30
TAVILY_EXTRACT_DEPTH=basic
```

`search_adapter.search_web(query, max_results)` returns normalized `title`, `url`,
`snippet`, and `source` fields. Provider failures return an empty result list and are
logged instead of failing the whole PPT generation.

For URL body extraction, `scripts/lib/extract_adapter.py` calls Tavily Extract first
and falls back to `http_fetch` if extraction fails. It returns normalized `url`,
`content`, `source`, `ok`, and `error` fields.

The app also exposes `/api/research-health` for an explicit connection check. During
normal `/research` and `/generate` calls, failed search/fetch attempts are returned as
warnings; citations are not fabricated.

Do not write API keys into repository code. Put search provider keys in `.env.local`.
`/api/research-health` reports whether `TAVILY_API_KEY` / `SERPER_API_KEY` are present,
but it never returns secret values.

Legacy CLI adapters are still possible only when explicitly requested:

```text
PPT_AGENT_SEARCH_CMD="your-search-cli --json {query}"
PPT_AGENT_FETCH_CMD="your-fetch-cli --text {url}"
```

Search output may be JSON (`results`, `items`, `sources`, or a list) or text lines:

```text
url | title | snippet
```

The research API writes:

- `research-results.json`: raw normalized search/fetch results
- `citations.json`: normalized source IDs for UI and slide citation planning
- `research.md`: pipeline-compatible research artifact when sources exist

When no adapter or local source exists, the app records a warning and does not fabricate
citations.

## Model And Tool Routing

The app separates model routing from tool routing. Models handle reasoning, planning,
writing, review, and code repair. Tools handle external actions such as web search,
web fetch, local resource search, rendering, and validation.

The current default model routes are:

```text
intake              -> codex_cli
task_understanding  -> claude_cli fallback: codex_cli
outline             -> claude_cli fallback: codex_cli
slide_rewrite       -> claude_cli fallback: codex_cli
research_summary    -> claude_cli fallback: codex_cli
citation_check      -> codex_cli
template_style      -> codex_cli
review              -> codex_cli
revision_router     -> codex_cli
code_repair         -> codex_cli
pipeline_debug      -> codex_cli
test_runner         -> codex_cli
render_fix          -> codex_cli
```

The current default tool routes are:

```text
web_search            -> search_adapter
web_fetch             -> extract_adapter fallback: http_fetch
web_extract           -> extract_adapter fallback: http_fetch
local_resource_search -> resource_index
ppt_render            -> native_svg
validation            -> native_svg
```

`codex_cli` is intentionally routed to engineering tasks such as `code_repair`,
`pipeline_debug`, `test_runner`, and `render_fix`, and as a fallback for model writing
where configured.

Keys are never hard-coded in the provider registry. Put secrets in `.env.local` or your
shell environment. `/api/model-routes` reports only boolean presence for required env
vars, never the secret value.

Every model or tool call appends one JSON line to:

```text
projects/<project-id>/route-log.jsonl
```

Model-stage calls also write:

```text
projects/<project-id>/model-runs/<stage>.json
projects/<project-id>/model-runs/<stage>.md
```

Research writes a machine-readable audit:

```text
projects/<project-id>/research-audit.json
```

To switch a stage to another provider, add a provider object under `providers` and point
the stage in `model_routes` to that provider id. For research tools, define tool
providers and tool routes instead of model routes:

```json
{
  "tool_providers": {
    "my_search_provider": {
      "kind": "cli",
      "label": "My Search Provider",
      "command": "my-search-cli",
      "capabilities": ["web_search"]
    }
  },
  "tool_routes": {
    "web_search": {
      "primary": "my_search_provider",
      "fallback": ["search_adapter"]
    }
  }
}
```

## Quality Gate

A generated deck is acceptable only when the API returns:

- `deck_quality_pass: "true"`
- `render_mode: "real"`
- `assets_ok: "true"`
- `speaker_notes_ok: "true"`
- `transitions_ok: "true"`
- `aggregate_editable_ratio` at or above config `min_editable_ratio`

The app never edits validation files to force success. `RENDER` reads V2 artifacts and
writes `structural-validation.md`, `render-audit.json`, and `run-manifest.json`.

## Implementation Boundary

- `ppt_agent_app/server.py` exposes the UI and API.
- `ppt_agent_app/services.py` owns project services and quality APIs.
- `ppt_agent_app/stage_runner.py` executes the V2 stage graph.
- `ppt_agent_app/questions.py` owns the intake questionnaire.
- `ppt_agent_app/resources.py` scans reusable project resources.
- `ppt_agent_app/research.py` wraps pluggable web-search/web-fetch commands and citations.
- `ppt_agent_app/jobs.py` provides in-process async job status for long deck generation.
- `ppt_agent_app/template_library.py` compiles and queries `templates/`.
