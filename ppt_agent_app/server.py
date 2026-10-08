from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def _load_env_local() -> None:
    """Load repo-local .env.local for direct `python -m ppt_agent_app.server` runs.

    scripts/start-app.sh already sources this file. Keeping the fallback here prevents
    direct server starts from silently losing search/fetch API keys.
    """
    env_path = Path(__file__).resolve().parents[1] / ".env.local"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_local()

from . import services
from .models import ROOT, project_dir, read_json


def _default_project_context() -> dict:
    projects_dir = ROOT / "projects"
    fallback_answers = {
        "topic": "",
        "slide_count": "15",
        "language": "zh",
        "audience": "",
        "scenario": "",
        "duration_minutes": "80",
        "style": "",
        "story_style": "",
        "user_outline": "",
        "required_sources": "",
        "forbidden_sources": "",
        "direct_slide_reuse_policy": "",
        "reuse_policy": "",
        "citation_policy": "",
    }
    fallback = {"project_id": "dai-llm-inference-onboarding", "answers": fallback_answers}
    candidates = []
    if projects_dir.exists():
        for path in projects_dir.iterdir():
            state_path = path / "app-state.json"
            if path.is_dir() and state_path.exists():
                try:
                    candidates.append((state_path.stat().st_mtime_ns, path.name, state_path))
                except OSError:
                    continue
    if not candidates:
        return fallback
    _, project_id, state_path = max(candidates, key=lambda item: item[0])
    state = read_json(state_path, {})
    answers = state.get("answers") if isinstance(state, dict) else {}
    merged = dict(fallback_answers)
    if isinstance(answers, dict):
        merged.update({key: value for key, value in answers.items() if value is not None})
    return {"project_id": project_id, "answers": merged}


def _render_index_html() -> str:
    context = _default_project_context()
    answers = context.get("answers") if isinstance(context.get("answers"), dict) else {}

    def attr(name: str) -> str:
        return html.escape(str(answers.get(name) or ""), quote=True)

    replacements = {
        "__DEFAULT_PROJECT_CONTEXT_JSON__": json.dumps(context, ensure_ascii=False),
        "__DEFAULT_PROJECT_ID__": html.escape(str(context.get("project_id") or ""), quote=True),
        "__DEFAULT_TOPIC__": attr("topic"),
        "__DEFAULT_SLIDE_COUNT__": attr("slide_count"),
        "__DEFAULT_AUDIENCE__": attr("audience"),
        "__DEFAULT_SCENARIO__": attr("scenario"),
        "__DEFAULT_DURATION_MINUTES__": attr("duration_minutes"),
        "__DEFAULT_STYLE__": attr("style"),
        "__DEFAULT_STORY_STYLE__": attr("story_style"),
        "__DEFAULT_USER_OUTLINE__": html.escape(str(answers.get("user_outline") or ""), quote=False),
        "__DEFAULT_REQUIRED_SOURCES__": html.escape(str(answers.get("required_sources") or ""), quote=False),
        "__DEFAULT_FORBIDDEN_SOURCES__": html.escape(str(answers.get("forbidden_sources") or ""), quote=False),
        "__DEFAULT_DIRECT_SLIDE_REUSE_POLICY__": attr("direct_slide_reuse_policy"),
        "__DEFAULT_REUSE_POLICY__": attr("reuse_policy"),
        "__DEFAULT_CITATION_POLICY__": attr("citation_policy"),
    }
    page = INDEX_HTML
    for key, value in replacements.items():
        page = page.replace(key, value)
    return page


INDEX_HTML = r"""<!doctype html>
<meta charset="utf-8">
<title>ppt-agent app</title>
<style>
body{font-family:Arial,"Microsoft YaHei",sans-serif;margin:0;background:#f6f7f9;color:#151a1f}
header{background:#17324d;color:white;padding:16px 24px}
main{display:grid;grid-template-columns:330px 1fr;gap:20px;padding:20px}
section{background:white;border:1px solid #dde2e8;border-radius:8px;padding:16px}
label{display:block;margin:10px 0 4px;font-size:13px;color:#4b5563}
input,textarea,select{width:100%;box-sizing:border-box;padding:8px;border:1px solid #cbd5e1;border-radius:6px}
button{margin-top:12px;padding:9px 12px;border:0;border-radius:6px;background:#2e7d8a;color:white;cursor:pointer}
button.secondary{background:#64748b}
button.danger{background:#b42336}
button.step{width:100%;text-align:left;margin-top:8px}
button:disabled{opacity:.55;cursor:not-allowed}
a{color:#145c68}
pre{white-space:pre-wrap;background:#0f172a;color:#e2e8f0;padding:12px;border-radius:6px;max-height:360px;overflow:auto}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.status{font-weight:bold}
.wide{grid-column:1 / -1}
.workflow{border-top:1px solid #e5e7eb;margin-top:14px;padding-top:12px}
.workflow h4{margin:8px 0;color:#17324d}
.hint{font-size:12px;color:#64748b;line-height:1.5}
.button-row{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.plan-toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.plan-editor{font-family:Consolas,Monaco,monospace;min-height:360px;line-height:1.45}
.slide-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;margin-top:12px}
.slide-item{border:1px solid #dde2e8;border-radius:6px;padding:10px;background:#fbfcfd}
.slide-item h4{margin:0 0 6px;font-size:14px}
.slide-meta{font-size:12px;color:#64748b}
.component-card{border-left:4px solid #2e7d8a}
</style>
<header><h2>ppt-agent interactive app</h2></header>
<main>
<section>
  <h3>项目需求</h3>
  <label>主题</label><input id="topic" value="__DEFAULT_TOPIC__">
  <label>项目 ID</label><input id="project_id" value="__DEFAULT_PROJECT_ID__">
  <label>页数</label><input id="slide_count" value="__DEFAULT_SLIDE_COUNT__">
  <label>语言</label><select id="language"><option value="zh">中文</option><option value="en">English</option></select>
  <button onclick="createProject()">创建/载入项目</button>
  <div class="workflow">
    <h4>推荐流程</h4>
    <p class="hint">V2 复用优先流程：先查询层级模板库和 sources，拼草稿，再按 gap 改写和统一风格。</p>
    <button class="step secondary" onclick="confirmStage('BRIEF')">1. 确认需求</button>
    <button class="step" onclick="scanResources()">2. 扫描项目 sources/assets</button>
    <button class="step" onclick="runNamedStage('TEMPLATE_LIBRARY_BUILD')">3. 构建层级模板库</button>
    <button class="step" onclick="runNamedStage('TEMPLATE_LIBRARY_QUERY')">4. 查询模板库候选</button>
    <button class="step" onclick="runNamedStage('TASK_UNDERSTANDING')">5. 任务理解/资料边界</button>
    <button class="step" onclick="prepareModelPlan()">6. 生成复用优先大纲</button>
    <button class="step secondary" onclick="confirmStage('REUSE_OUTLINE')">7. 确认复用大纲</button>
    <button class="step" onclick="runNamedStage('DRAFT_ASSEMBLY')">8. 拼接草稿 PPT</button>
    <button class="step secondary" onclick="confirmStage('DRAFT_ASSEMBLY')">9. 确认草稿</button>
    <button class="step" onclick="runNamedStage('GAP_ANALYSIS')">10. 逐页 Gap 分析</button>
    <button class="step secondary" onclick="confirmStage('GAP_ANALYSIS')">11. 确认 Gap 计划</button>
    <button class="step" onclick="researchDeck()">12. 按 Gap 检索/补证据</button>
    <button class="step" onclick="runNamedStage('SLIDE_REWRITE')">13. 基于草稿改写页面</button>
    <button class="step" onclick="runNamedStage('STYLE_UNIFICATION')">14. 统一 basic 模板风格</button>
    <button class="step" onclick="runNamedStage('RENDER')">15. 渲染最终 PPT</button>
    <button class="step secondary" onclick="runNamedStage('REVIEW')">16. 评审结果</button>
  </div>
  <div class="workflow">
    <h4>状态与排查</h4>
    <button class="secondary" onclick="showStages()">阶段状态</button>
    <button class="secondary" onclick="showSlides()">每页状态</button>
    <button class="secondary" onclick="showTemplateLibraryCandidates()">层级模板候选</button>
    <button class="secondary" onclick="showRouteSummary()">实际调用汇总</button>
    <button class="secondary" onclick="showRouteLog()">路由日志</button>
    <button class="secondary" onclick="checkProviders()">模型路由</button>
    <button class="secondary" onclick="checkTools()">工具路由</button>
    <button class="secondary" onclick="checkAgents()">Agent/Skills</button>
    <button class="secondary" onclick="runUntilBlocked()">推进到下一确认点</button>
    <button class="secondary" onclick="confirmCurrent()">确认当前阶段</button>
    <button class="danger" onclick="debugWithCodex()">仅出错时：Codex 诊断</button>
    <button class="danger" onclick="autoRun()">高级：按 V2 流程自动推进</button>
  </div>
  <p>项目资料放入 <code>projects/&lt;project_id&gt;/sources/</code>；系统模板库来自仓库根目录 <code>templates/</code>。</p>
  <p id="downloads"></p>
</section>
<section>
  <h3>交互问题</h3>
  <div class="grid">
    <div><label>受众</label><input id="audience" value="__DEFAULT_AUDIENCE__"></div>
    <div><label>场景</label><input id="scenario" value="__DEFAULT_SCENARIO__"></div>
    <div><label>时长</label><input id="duration_minutes" value="__DEFAULT_DURATION_MINUTES__"></div>
    <div><label>风格</label><input id="style" value="__DEFAULT_STYLE__"></div>
  </div>
  <label>叙事逻辑</label><input id="story_style" value="__DEFAULT_STORY_STYLE__">
  <label>用户大纲（优先级最高）</label><textarea id="user_outline" rows="8">__DEFAULT_USER_OUTLINE__</textarea>
  <label>必须复用资料</label><textarea id="required_sources" rows="3">__DEFAULT_REQUIRED_SOURCES__</textarea>
  <label>禁止复用/敏感资料</label><textarea id="forbidden_sources" rows="3">__DEFAULT_FORBIDDEN_SOURCES__</textarea>
  <label>整页复用策略</label><input id="direct_slide_reuse_policy" value="__DEFAULT_DIRECT_SLIDE_REUSE_POLICY__">
  <label>复用策略</label><input id="reuse_policy" value="__DEFAULT_REUSE_POLICY__">
  <label>引用策略</label><input id="citation_policy" value="__DEFAULT_CITATION_POLICY__">
  <button onclick="saveAnswers()">保存回答</button>
</section>
<section>
  <h3>质量结果</h3>
  <pre id="quality">尚未生成</pre>
</section>
<section>
  <h3>日志 / 响应</h3>
  <pre id="log"></pre>
</section>
<section class="wide">
  <h3>检索结果预览</h3>
  <div id="research_summary" class="slide-list"></div>
</section>
<section class="wide">
  <h3>大纲 / 页面计划编辑区</h3>
  <div class="plan-toolbar">
    <button class="secondary" onclick="loadModelPlan()">载入计划</button>
    <button class="secondary" onclick="saveModelPlan()">保存修改</button>
    <button class="secondary" onclick="reviseSlide()">重写当前页</button>
    <button class="secondary" onclick="confirmStage('REUSE_OUTLINE')">确认复用大纲</button>
  </div>
  <div class="grid">
    <div><label>页码</label><input id="revise_slide_id" value="2"></div>
    <div><label>单页修改要求</label><input id="revise_instruction" value="把这一页改成更聚焦问题定义，减少泛泛背景"></div>
  </div>
  <textarea id="plan_editor" class="plan-editor"></textarea>
  <div id="slide_preview" class="slide-list"></div>
</section>
<section class="wide">
  <h3>层级模板库候选</h3>
  <p class="hint">这里展示从 templates/ 编译出的 deck/section/slide/component/asset 候选。候选不是最终批准复用，最终由复用大纲、草稿和 gap 审计决定。</p>
  <div class="plan-toolbar">
    <button class="secondary" onclick="runNamedStage('TEMPLATE_LIBRARY_BUILD')">构建层级模板库</button>
    <button class="secondary" onclick="runNamedStage('TEMPLATE_LIBRARY_QUERY')">查询当前项目候选</button>
    <button class="secondary" onclick="showTemplateLibraryCandidates()">载入候选摘要</button>
  </div>
  <div id="template_components" class="slide-list"></div>
</section>
<section class="wide">
  <h3>复用决策 / 血缘预览</h3>
  <p class="hint">这里显示模板候选、当前复用大纲选中的来源，以及最终 visual-plan 中的复用决策。V2 不再通过旧组件规划兜底。</p>
  <div class="plan-toolbar">
    <button class="secondary" onclick="showTemplateLibraryCandidates()">载入候选/决策</button>
    <button class="secondary" onclick="runNamedStage('REUSE_OUTLINE')">重跑复用大纲</button>
  </div>
  <div id="template_library_candidates" class="slide-list"></div>
</section>
</main>
<script>
const DEFAULT_PROJECT_CONTEXT = __DEFAULT_PROJECT_CONTEXT_JSON__;
let currentProject = DEFAULT_PROJECT_CONTEXT.project_id || "__DEFAULT_PROJECT_ID__";
let runningStageJobs = {};
let templateComponentsCache = [];
function val(id){return document.getElementById(id).value}
function setVal(id, value){
  const el = document.getElementById(id);
  if(el && value !== undefined && value !== null){ el.value = value; }
}
function hydrateAnswers(answers){
  if(!answers || typeof answers !== "object"){ return; }
  ["topic","audience","scenario","slide_count","duration_minutes","language","style","story_style","user_outline","required_sources","forbidden_sources","direct_slide_reuse_policy","reuse_policy","citation_policy"].forEach(id => setVal(id, answers[id]));
}
function hydrateProject(data){
  if(!data || typeof data !== "object"){ return; }
  currentProject = data.project_id || currentProject;
  setVal("project_id", currentProject);
  hydrateAnswers(data.answers || {});
  localStorage.setItem("ppt-agent:last-project", currentProject);
}
function show(data){
  const text = typeof data === "string" ? data : JSON.stringify(data,null,2);
  document.getElementById("log").textContent = text.length > 30000 ? text.slice(0,30000) + "\n\n...日志已截断，完整内容已写入项目文件。" : text;
}
function esc(value){
  return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}
function renderPlanPreview(plan){
  const slides = Array.isArray(plan?.slides) ? plan.slides : [];
  document.getElementById("slide_preview").innerHTML = slides.map(s => {
    const refs = Array.isArray(s.source_references) ? s.source_references.join(", ") : "";
    const bullets = Array.isArray(s.bullets) ? s.bullets.slice(0,3).join(" / ") : "";
    const claim = s.claim || s.key_message || bullets || "";
    const left = s.left_box?.heading ? `左框：${s.left_box.heading}` : "";
    const right = s.right_box?.heading ? `右框：${s.right_box.heading}` : "";
    const component = s.layout_contract?.component_id || "";
    const role = [s.story_role, s.layout_type, s.visual_type || s.kind].filter(Boolean).join(" · ");
    const formatMode = s.format_reference?.mode ? `格式：${s.format_reference.mode}` : "";
    const intent = s.visual_intent ? `表达意图：${s.visual_intent}` : "";
    return `<div class="slide-item"><h4>${esc(s.index || "")}. ${esc(s.title || "")}</h4><div class="slide-meta">${esc(s.section || "")} · ${esc(role)} · ${esc(component)} · ${esc(refs)}</div><p>${esc(claim)}</p><p class="hint">${esc([formatMode,intent,left,right].filter(Boolean).join(" / "))}</p></div>`;
  }).join("");
}
function renderResearchPreview(data){
  const research = data?.research || data || {};
  const audit = data?.research_audit || data?.audit || {};
  const citations = Array.isArray(data?.citations) ? data.citations : Array.isArray(research?.citations) ? research.citations : [];
  const results = Array.isArray(research?.results) ? research.results : [];
  const queries = Array.isArray(research?.queries) ? research.queries : [];
  const downloads = data?.downloads || {};
  const cards = [];
  cards.push(`<div class="slide-item"><h4>检索状态</h4><p>web_results_count: ${esc(research.web_results_count ?? audit.web_results_count ?? 0)}<br>local_fallback_count: ${esc(research.local_fallback_count ?? audit.local_fallback_count ?? 0)}<br>fetched_count: ${esc(research.fetched_count ?? audit.fetched_count ?? 0)}</p>${downloads.research ? `<p><a href="${esc(downloads.research)}">下载 research.md</a></p>` : ""}</div>`);
  if(queries.length){
    cards.push(`<div class="slide-item"><h4>Search Queries</h4><p>${queries.map(q=>esc(q)).join("<br>")}</p></div>`);
  }
  const sourceItems = results.length ? results : citations;
  sourceItems.slice(0,12).forEach((item, idx) => {
    const url = item.url || "";
    const title = item.title || item.id || `Source ${idx+1}`;
    const snippet = item.snippet || item.fetched_text || "";
    const provider = item.provider || "";
    cards.push(`<div class="slide-item"><h4>${esc(item.id || `S${idx+1}`)}. ${esc(title)}</h4><div class="slide-meta">${url ? `<a href="${esc(url)}" target="_blank">${esc(url)}</a>` : "no url"} · ${esc(provider)}</div><p>${esc(snippet).slice(0,360)}</p></div>`);
  });
  if(!sourceItems.length){
    cards.push(`<div class="slide-item"><h4>暂无来源</h4><p>请先运行“按 Gap 检索/补证据”。如果仍为空，请查看工具路由。</p></div>`);
  }
  document.getElementById("research_summary").innerHTML = cards.join("");
}
function renderTemplateComponents(data){
  const components = Array.isArray(data?.components) ? data.components : [];
  templateComponentsCache = components;
  const select = document.getElementById("component_select");
  if(select){
    select.innerHTML = components.map(c => `<option value="${esc(c.component_id || "")}">${esc(c.component_id || c.name || "")}</option>`).join("");
  }
  const summary = `<div class="slide-item component-card"><h4>${esc(data.template_name || data.template_id || "模板")}</h4><p>组件数：${esc(data.component_count || 0)}<br>ppt-master 源页组件：${esc(data.source_component_count || 0)}<br>状态：${esc(data.review_status || "unknown")}</p><p class="hint">${esc(data.review_instructions || "")}</p></div>`;
  const cards = components.map(c => {
    const slots = c.slots ? Object.keys(c.slots).slice(0,10).join(", ") : "";
    const imageSlots = Array.isArray(c.image_slots) ? c.image_slots.map(x=>x.asset || x.slot_role).join(", ") : "";
    const samples = Array.isArray(c.text_samples) ? c.text_samples.slice(0,3).join(" / ") : "";
    return `<div class="slide-item component-card"><h4>${esc(c.component_id || c.name || "")}</h4><div class="slide-meta">${esc(c.source || "")} · ${esc(c.page_type || "")} · ${esc(c.template_svg || "")}</div><p>槽位：${esc(slots || "无")}</p>${imageSlots ? `<p>图片槽：${esc(imageSlots)}</p>` : ""}${samples ? `<p class="hint">${esc(samples)}</p>` : ""}<p class="hint">需要确认：${esc(c.requires_user_review === false ? "否" : "是")}</p></div>`;
  });
  document.getElementById("template_components").innerHTML = summary + cards.join("");
}
function renderTemplateLibraryCandidates(data){
  const counts = data?.by_type || {};
  const units = Array.isArray(data?.units) ? data.units : [];
  const direct = Array.isArray(data?.direct_candidates) ? data.direct_candidates : [];
  const slideDecisions = Array.isArray(data?.visual_plan_reuse_decisions) ? data.visual_plan_reuse_decisions : [];
  const countText = Object.entries(counts).map(([k,v])=>`${k}: ${v}`).join("<br>");
  const cards = [];
  cards.push(`<div class="slide-item component-card"><h4>层级模板库总览</h4><p>候选对象：${esc(data?.candidate_count || data?.unit_count || 0)}<br>需模型语义审计：${esc(data?.audit_required_count || 0)}<br>可直接复用候选：${esc(data?.direct_candidate_count || 0)}</p><p class="hint">${countText}</p></div>`);
  direct.slice(0,12).forEach(u => {
    const objectType = u.object_type || u.unit_type || "";
    const objectId = u.object_id || u.unit_id || "";
    const source = u.source ? JSON.stringify(u.source) : [u.deck_id, u.slide_id].filter(Boolean).join(" / ");
    const text = u.text || u.what_it_teaches || "";
    cards.push(`<div class="slide-item"><h4>${esc(objectType)} · ${esc(objectId)}</h4><div class="slide-meta">${esc(source)} · score ${esc(u.score || "")}</div><p>${esc(text)}</p><p class="hint">audit: ${esc((u.audit_dimensions || []).join(", "))}</p></div>`);
  });
  if(slideDecisions.length){
    slideDecisions.forEach(s => {
      const image = s.image_decision || {};
      const decisions = Array.isArray(s.reuse_decisions) ? s.reuse_decisions : [];
      const rows = decisions.map(d => `${d.decision || "unknown"} · ${d.unit_type || ""} · ${d.unit_id || ""}<br><span class="hint">${esc(d.why_match || "")}</span>`).join("<br>");
      cards.push(`<div class="slide-item component-card"><h4>Slide ${esc(s.slide_index)} · ${esc(s.title || "")}</h4><p>direct_reuse: ${esc(s.direct_reuse_count || 0)}<br>image: ${esc(image.decision || "none")}</p><p class="hint">${rows || "visual-plan 尚未写入 reuse_decisions"}</p></div>`);
    });
  } else {
    cards.push(`<div class="slide-item"><h4>暂无逐页决策</h4><p>请先运行“生成复用优先大纲”和“基于草稿改写页面”。运行后这里会显示每页的复用来源、资源血缘和审计决策。</p></div>`);
  }
  document.getElementById("template_library_candidates").innerHTML = cards.join("");
  const compact = {candidate_count:data?.candidate_count || data?.unit_count,by_type:data?.by_type,audit_required_count:data?.audit_required_count,direct_candidate_count:data?.direct_candidate_count,visual_plan_quality_audit:data?.visual_plan_quality_audit};
  document.getElementById("quality").textContent = JSON.stringify(compact,null,2);
}
function applyComponentToPlan(){
  try {
    const slideId = Number(val("component_slide_id"));
    const componentId = val("component_select");
    const plan = JSON.parse(document.getElementById("plan_editor").value || "{}");
    const slides = Array.isArray(plan.slides) ? plan.slides : [];
    const slide = slides.find(s => Number(s.index) === slideId) || slides[slideId - 1];
    const component = templateComponentsCache.find(c => c.component_id === componentId) || {};
    if(!slide || !componentId){
      const data = {ok:false,error:"请先载入页面计划和模板组件，并选择有效页码/组件。"};
      document.getElementById("quality").textContent = JSON.stringify(data,null,2);
      show(data);
      return;
    }
    slide.layout_contract = slide.layout_contract || {};
    slide.layout_contract.component_id = componentId;
    slide.layout_contract.template_svg = component.template_svg || "";
    slide.layout_contract.source_slide_index = component.source_slide_index || null;
    slide.layout_contract.slots = component.slots ? Object.keys(component.slots) : [];
    if(componentId === "evidence_two_box.v1"){
      slide.visual_type = "evidence-two-box";
    }
    document.getElementById("plan_editor").value = JSON.stringify(plan,null,2);
    renderPlanPreview(plan);
    const data = {ok:true,slide:slideId,component_id:componentId,hint:"已写入编辑区；点击“保存修改”后生效。"};
    document.getElementById("quality").textContent = JSON.stringify(data,null,2);
    show(data);
  } catch(e) {
    const data = {ok:false,error:String(e)};
    document.getElementById("quality").textContent = JSON.stringify(data,null,2);
    show(data);
  }
}
async function api(path, body){
  show("请求中...");
  const res = await fetch(path,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body||{})});
  const data = await res.json(); show(data); return data;
}
function setQualityStatus(lines, details=null){
  const body = Array.isArray(lines) ? lines.filter(Boolean).join("\n") : String(lines || "");
  document.getElementById("quality").textContent = details ? `${body}\n\n${JSON.stringify(details,null,2)}` : body;
}
function jobStage(data, fallback=null){
  return data?.result?.stage || data?.result?.result?.stage || fallback || data?.kind || "任务";
}
function jobOk(data){
  return data.status === "succeeded" && data?.result?.ok !== false && data?.result?.result?.ok !== false;
}
function nextStageHint(stage, ok){
  if(!ok){ return "下一步：查看“日志 / 响应”和“实际调用汇总”，定位失败原因。"; }
  const hints = {
    RESOURCE_SCAN: "下一步：点击 3. 构建层级模板库。",
    TEMPLATE_LIBRARY_BUILD: "下一步：点击 4. 查询模板库候选。",
    TEMPLATE_LIBRARY_QUERY: "下一步：点击 5. 任务理解/资料边界。",
    TASK_UNDERSTANDING: "下一步：点击 6. 生成复用优先大纲。",
    REUSE_OUTLINE: "下一步：检查下方计划，确认复用大纲，然后点击 8. 拼接草稿 PPT。",
    DRAFT_ASSEMBLY: "下一步：下载/查看草稿，确认后点击 10. 逐页 Gap 分析。",
    GAP_ANALYSIS: "下一步：确认 Gap 计划，然后点击 12. 按 Gap 检索/补证据。",
    GAP_RESEARCH: "下一步：点击 13. 基于草稿改写页面。",
    SLIDE_REWRITE: "下一步：点击 14. 统一 basic 模板风格。",
    STYLE_UNIFICATION: "下一步：点击 15. 渲染最终 PPT。",
    RENDER: "下一步：检查下载链接和结构校验，然后点击 16. 评审结果。",
    REVIEW: "下一步：查看评审意见，决定是否修订或最终确认。"
  };
  return hints[stage] || "下一步：可以继续流程中的下一项。";
}
async function stageSummary(stage, jobId=null, ok=true, finished=""){
  try {
    const res = await fetch(`/api/projects/${currentProject}/stages`);
    const data = await res.json();
    const stages = Array.isArray(data.stages) ? data.stages : [];
    const item = stages.find(s => s.stage === stage) || {};
    const diag = item.diagnostics || data?.diagnostics?.[stage] || {};
    const artifacts = Array.isArray(item.output_artifacts) ? item.output_artifacts.join(", ") : "";
    const gaps = Array.isArray(diag.gaps) ? diag.gaps.slice(0,5) : [];
    const current = data.current_stage || stage;
    setQualityStatus([
      `${stage || "任务"} ${ok ? "已完成。" : "未成功。"}`,
      `当前阶段: ${current}`,
      item.status ? `阶段状态: ${item.status}` : "",
      item.artifact_status ? `产物状态: ${item.artifact_status}` : "",
      diag.provider ? `模型/工具 provider: ${diag.provider}` : "",
      diag.fallback_used ? "发生 fallback: true" : "",
      diag.error_type ? `错误类型: ${diag.error_type}` : "",
      diag.failed_artifact ? `失败产物: ${diag.failed_artifact}` : "",
      gaps.length ? `质量问题: ${JSON.stringify(gaps,null,2)}` : "",
      artifacts ? `产物文件: ${artifacts}` : "",
      nextStageHint(stage, ok),
      jobId ? `job_id: ${jobId}` : "",
      finished
    ]);
  } catch(e) {
    setQualityStatus([
      `${stage || "任务"} ${ok ? "已完成。" : "未成功。"}`,
      nextStageHint(stage, ok),
      jobId ? `job_id: ${jobId}` : "",
      finished
    ]);
  }
}
function rememberRunningJob(stage, jobId){
  if(!stage || !jobId){ return; }
  runningStageJobs[stage] = jobId;
  try {
    localStorage.setItem(`ppt-agent:${currentProject}:job:${stage}`, jobId);
  } catch(e) {}
}
function forgetRunningJob(stage){
  if(!stage){ return; }
  delete runningStageJobs[stage];
  try {
    localStorage.removeItem(`ppt-agent:${currentProject}:job:${stage}`);
  } catch(e) {}
}
function renderJobRunning(stage, jobId, data=null){
  setQualityStatus([
    `${stage || "任务"} 正在后台运行，当前阶段尚未结束。`,
    `job_id: ${jobId}`,
    data?.started_at ? `开始时间: ${data.started_at}` : "",
    `最近检查: ${new Date().toLocaleTimeString()}`
  ]);
}
function resumeRunningJobs(){
  try {
    const prefix = `ppt-agent:${currentProject}:job:`;
    for(let i=0;i<localStorage.length;i++){
      const key = localStorage.key(i);
      if(!key || !key.startsWith(prefix)){ continue; }
      const stage = key.slice(prefix.length);
      const jobId = localStorage.getItem(key);
      if(jobId && !runningStageJobs[stage]){
        runningStageJobs[stage] = jobId;
        renderJobRunning(stage, jobId);
        pollJob(jobId, stage);
      }
    }
  } catch(e) {}
}
async function createProject(){
  currentProject = val("project_id");
  const data = await api("/api/projects",{topic:val("topic"),project_id:currentProject,slide_count:val("slide_count"),language:val("language")});
  if(data.loaded_existing){
    hydrateProject(data);
    resumeRunningJobs();
    return data;
  }
  hydrateProject(data);
  await saveAnswers();
  resumeRunningJobs();
  return data;
}
async function saveAnswers(){
  const data = await api(`/api/projects/${currentProject}/answers`,{
    topic:val("topic"),audience:val("audience"),scenario:val("scenario"),slide_count:val("slide_count"),
    duration_minutes:val("duration_minutes"),language:val("language"),style:val("style"),
    story_style:val("story_style"),user_outline:val("user_outline"),required_sources:val("required_sources"),
    forbidden_sources:val("forbidden_sources"),direct_slide_reuse_policy:val("direct_slide_reuse_policy"),
    reuse_policy:val("reuse_policy"),citation_policy:val("citation_policy")
  });
}
async function scanResources(){await runNamedStage("RESOURCE_SCAN")}
async function checkProviders(){
  const res = await fetch("/api/providers/health");
  const data = await res.json();
  document.getElementById("quality").textContent = JSON.stringify(data,null,2);
  show(data);
}
async function checkTools(){
  const res = await fetch("/api/tools/health");
  const data = await res.json();
  document.getElementById("quality").textContent = JSON.stringify(data,null,2);
  show(data);
}
async function checkAgents(){
  const res = await fetch("/api/agents");
  const data = await res.json();
  document.getElementById("quality").textContent = JSON.stringify(data,null,2);
  show(data);
}
async function checkResearch(){
  const controller = new AbortController();
  const timer = setTimeout(()=>controller.abort(), 20000);
  document.getElementById("quality").textContent = "正在检查 Claude 主链路与 Tavily/Serper 备选检索连接...";
  show("正在检查 Claude 主链路与 Tavily/Serper 备选检索连接...");
  try {
    const res = await fetch("/api/research-health",{signal:controller.signal});
    const data = await res.json();
    document.getElementById("quality").textContent = JSON.stringify(data,null,2);
    show(data);
  } catch(e) {
    const data = {ok:false,error:String(e),hint:"检查请求超时或 App 服务未响应；请确认使用的是新启动的 App 端口。"};
    document.getElementById("quality").textContent = JSON.stringify(data,null,2);
    show(data);
  } finally {
    clearTimeout(timer);
  }
}
async function researchDeck(){
  if(runningStageJobs.GAP_RESEARCH){
    renderJobRunning("GAP_RESEARCH", runningStageJobs.GAP_RESEARCH);
    pollJob(runningStageJobs.GAP_RESEARCH, "GAP_RESEARCH");
    return {job_id: runningStageJobs.GAP_RESEARCH, status:"running"};
  }
  const data = await api(`/api/projects/${currentProject}/run-stage`,{stage:"GAP_RESEARCH",research_depth:"deep",compact:true,async:true});
  if(data.job_id){
    rememberRunningJob("GAP_RESEARCH", data.job_id);
    renderJobRunning("GAP_RESEARCH", data.job_id, data);
    pollJob(data.job_id, "GAP_RESEARCH");
    return data;
  }
  return data;
}
async function showResearch(){
  const res = await fetch(`/api/projects/${currentProject}/research-summary`);
  const data = await res.json();
  renderResearchPreview(data);
  document.getElementById("quality").textContent = JSON.stringify({research_audit:data.research_audit,citations:data.citations,downloads:data.downloads},null,2);
  show(data.research || data);
}
async function prepareModelPlan(){
  if(runningStageJobs.REUSE_OUTLINE){
    renderJobRunning("REUSE_OUTLINE", runningStageJobs.REUSE_OUTLINE);
    pollJob(runningStageJobs.REUSE_OUTLINE, "REUSE_OUTLINE");
    return {job_id: runningStageJobs.REUSE_OUTLINE, status:"running"};
  }
  const data = await api(`/api/projects/${currentProject}/run-stage`,{stage:"REUSE_OUTLINE",compact:true,async:true});
  if(data.job_id){
    rememberRunningJob("REUSE_OUTLINE", data.job_id);
    setQualityStatus([
      "REUSE_OUTLINE 正在后台运行，当前阶段尚未结束。",
      "完成后会自动载入到下方“计划编辑区”。",
      `job_id: ${data.job_id}`,
      data.started_at ? `开始时间: ${data.started_at}` : ""
    ]);
    pollJob(data.job_id, "REUSE_OUTLINE");
    return data;
  }
  document.getElementById("quality").textContent = JSON.stringify(data,null,2);
}
async function loadModelPlan(){
  const res = await fetch(`/api/projects/${currentProject}/model-plan`);
  const data = await res.json();
  const plan = data.plan || {};
  document.getElementById("plan_editor").value = JSON.stringify(plan,null,2);
  renderPlanPreview(plan);
  if(!data.ok){
    document.getElementById("quality").textContent = "还没有可载入的复用大纲。请先点击左侧第 6 步“生成复用优先大纲”。\n" + JSON.stringify(data.gates||data,null,2);
  } else {
    document.getElementById("quality").textContent = JSON.stringify(data.gates||data,null,2);
  }
  show(data);
}
async function saveModelPlan(){
  try {
    const plan = JSON.parse(document.getElementById("plan_editor").value || "{}");
    const data = await api(`/api/projects/${currentProject}/model-plan-update`,{plan});
    if(data.ok){
      document.getElementById("plan_editor").value = JSON.stringify(data.plan,null,2);
      renderPlanPreview(data.plan);
    }
    document.getElementById("quality").textContent = JSON.stringify(data.gates||data,null,2);
  } catch(e) {
    const data = {ok:false,error:String(e)};
    document.getElementById("quality").textContent = JSON.stringify(data,null,2);
    show(data);
  }
}
async function reviseSlide(){
  try {
    const data = await api(`/api/projects/${currentProject}/slide-revise`,{
      slide_id:val("revise_slide_id"),
      instruction:val("revise_instruction")
    });
    if(data.ok){
      document.getElementById("plan_editor").value = JSON.stringify(data.plan,null,2);
      renderPlanPreview(data.plan);
    }
    document.getElementById("quality").textContent = JSON.stringify(data.gates||data,null,2);
  } catch(e) {
    const data = {ok:false,error:String(e)};
    document.getElementById("quality").textContent = JSON.stringify(data,null,2);
    show(data);
  }
}
async function runStageModel(stage){
  const data = await api(`/api/projects/${currentProject}/model-stage`,{stage});
  document.getElementById("quality").textContent = JSON.stringify(data,null,2);
}
async function runCurrentStage(){
  const data = await api(`/api/projects/${currentProject}/run-stage`,{});
  document.getElementById("quality").textContent = JSON.stringify(data,null,2);
  await showStages();
}
async function runNamedStage(stage){
  if(runningStageJobs[stage]){
    renderJobRunning(stage, runningStageJobs[stage]);
    pollJob(runningStageJobs[stage], stage);
    return {job_id: runningStageJobs[stage], status:"running"};
  }
  const data = await api(`/api/projects/${currentProject}/run-stage`,{stage,compact:true,async:true});
  if(data.job_id){
    rememberRunningJob(stage, data.job_id);
    renderJobRunning(stage, data.job_id, data);
    pollJob(data.job_id, stage);
    return data;
  }
  document.getElementById("quality").textContent = JSON.stringify(data.result || data,null,2);
  if(stage === "RENDER" && data.result){ renderQuality(data.result); }
  return data;
}
async function runUntilBlocked(){
  const data = await api(`/api/projects/${currentProject}/run-until-blocked`,{async:true,model_routed:true,research_depth:"light"});
  if(data.job_id){
    const stage = data.stage || data.current_stage || "自动推进";
    rememberRunningJob(stage, data.job_id);
    renderJobRunning(stage, data.job_id, data);
    pollJob(data.job_id, stage);
  }
  else {
    document.getElementById("quality").textContent = JSON.stringify(data,null,2);
    show(data);
  }
}
async function currentStage(){
  const res = await fetch(`/api/projects/${currentProject}/stages`);
  const data = await res.json();
  return data.current_stage;
}
async function confirmCurrent(){
  const stage = await currentStage();
  const data = await api(`/api/projects/${currentProject}/stages`,{stage,force:true});
  document.getElementById("quality").textContent = "已确认 "+stage+"\n"+JSON.stringify(data.gates||data,null,2);
  return data;
}
// One-click full run: advance, auto-confirm every human gate, until complete/escalation.
async function autoRun(){
  const opts = {model_routed:true, research_depth:"light", search_cmd:"true"};  // search_cmd:"true" => skip slow web search
  for(let i=0;i<40;i++){
    const data = await api(`/api/projects/${currentProject}/run-until-blocked`, opts);
    document.getElementById("log").textContent = JSON.stringify(data,null,2);
    const reason = data.stop_reason;
    if(reason === "human_gate_waiting"){
      const stage = data.stopped_stage || await currentStage();
      await api(`/api/projects/${currentProject}/stages`,{stage,force:true});
      document.getElementById("quality").textContent = "自动确认 "+stage+" … 继续";
      continue;
    }
    document.getElementById("quality").textContent = "结束: "+reason+"\n"+JSON.stringify(data.stage_state||data,null,2);
    if(reason === "complete" || reason === "escalated" || !reason){ await showRouteSummary(); }
    return data;
  }
}
async function debugWithCodex(){
  const data = await api(`/api/projects/${currentProject}/codex-debug`,{apply_fix:false});
  document.getElementById("quality").textContent = JSON.stringify(data,null,2);
}
async function showRouteLog(){
  const res = await fetch(`/api/projects/${currentProject}/route-log`);
  const data = await res.json();
  document.getElementById("quality").textContent = JSON.stringify(data,null,2);
  show(data);
}
async function showRouteSummary(){
  const res = await fetch(`/api/projects/${currentProject}/route-summary`);
  const data = await res.json();
  document.getElementById("quality").textContent = JSON.stringify(data,null,2);
  show(data);
}
async function showStages(){
  const res = await fetch(`/api/projects/${currentProject}/stages`);
  const data = await res.json();
  document.getElementById("quality").textContent = JSON.stringify(data,null,2);
  show(data);
}
async function showSlides(){
  const res = await fetch(`/api/projects/${currentProject}/slide-state`);
  const data = await res.json();
  document.getElementById("quality").textContent = JSON.stringify(data,null,2);
  show(data);
}
async function showTemplateComponents(){
  const res = await fetch(`/api/projects/${currentProject}/template-components`);
  const data = await res.json();
  renderTemplateComponents(data);
  document.getElementById("quality").textContent = JSON.stringify({template_name:data.template_name,component_count:data.component_count,source_component_count:data.source_component_count,review_status:data.review_status},null,2);
  show(data);
}
async function showTemplateLibraryCandidates(){
  const res = await fetch(`/api/projects/${currentProject}/template-library-candidates`);
  const data = await res.json();
  renderTemplateLibraryCandidates(data);
  show(data);
}
async function confirmStage(stage){
  const data = await api(`/api/projects/${currentProject}/stages`,{stage});
  document.getElementById("quality").textContent = JSON.stringify(data.gates||data,null,2);
}
async function generateDeck(){
  const data = await api(`/api/projects/${currentProject}/run-until-blocked`,{async:true,max_steps:20});
  if(data.job_id){
    rememberRunningJob("GENERATE", data.job_id);
    renderJobRunning("GENERATE", data.job_id, data);
    pollJob(data.job_id, "GENERATE");
  }
  else { renderQuality(data); }
}
function renderQuality(data){
  document.getElementById("quality").textContent = JSON.stringify(data.quality||data.result?.quality||data,null,2);
  const downloads = data.downloads || data.result?.downloads || {};
  document.getElementById("downloads").innerHTML = Object.entries(downloads).map(([k,v])=>`<a href="${v}">${k}</a>`).join(" · ");
}
async function pollJob(jobId, stageKey=null){
  for(let i=0;i<240;i++){
    const res = await fetch(`/api/jobs/${jobId}`);
    const data = await res.json();
    show(data);
    if(data.status !== "running"){
      if(stageKey){ forgetRunningJob(stageKey); }
      const stage = jobStage(data, stageKey);
      const ok = jobOk(data);
      const finished = data.finished_at ? `结束时间: ${data.finished_at}` : "";
      await stageSummary(stage, jobId, ok, finished);
      if(stage === "GAP_RESEARCH"){
        await showResearch();
        await stageSummary("GAP_RESEARCH", jobId, ok, finished);
      } else if(stage === "REUSE_OUTLINE"){
        await loadModelPlan();
        const hasPlan = !!document.getElementById("plan_editor").value && document.getElementById("plan_editor").value !== "{}";
        if(hasPlan){
          await stageSummary("REUSE_OUTLINE", jobId, ok, finished);
        } else {
          setQualityStatus([
            "REUSE_OUTLINE 未成功载入计划。",
            "下一步：查看“日志 / 响应”和“实际调用汇总”。",
            `job_id: ${jobId}`,
            finished
          ]);
        }
      } else if(stage === "RENDER" || stage === "GENERATE"){
        renderQuality(data);
        await stageSummary(stage, jobId, ok, finished);
      }
      return;
    }
    if(i === 0 || i % 3 === 0){
      renderJobRunning(stageKey || jobStage(data, stageKey), jobId, data);
    }
    await new Promise(r=>setTimeout(r,1000));
  }
  setQualityStatus([
    `${stageKey || "任务"} 仍在后台运行，前端已停止自动轮询。`,
    "下一步：点击“阶段状态”或再次点击当前阶段按钮刷新状态。",
    `job_id: ${jobId}`
  ]);
}
window.addEventListener("load", () => {
  hydrateProject(DEFAULT_PROJECT_CONTEXT);
  const queryProject = new URLSearchParams(window.location.search).get("project");
  currentProject = queryProject || DEFAULT_PROJECT_CONTEXT.project_id || val("project_id") || currentProject;
  setVal("project_id", currentProject);
  createProject().then(data => {
    show({loaded_project: currentProject, topic: val("topic"), next_step: "继续按左侧 V2 推荐流程推进：扫描 sources -> 构建/查询模板库 -> 任务理解 -> 复用大纲。", project: data});
    resumeRunningJobs();
  }).catch(err => {
    show({error: String(err), project_id: currentProject});
  });
  resumeRunningJobs();
});
</script>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body, content_type: str = "application/json") -> None:
        if isinstance(body, (dict, list)):
            raw = json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")
        elif isinstance(body, str):
            raw = body.encode("utf-8")
        else:
            raw = bytes(body)
        self.send_response(status)
        self.send_header("content-type", f"{content_type}; charset=utf-8")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_file(self, path) -> None:
        if not path.exists() or not path.is_file():
            self._send(404, {"error": "file not found"})
            return
        raw = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(raw)))
        self.send_header("content-disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(raw)

    def _json(self):
        n = int(self.headers.get("content-length", "0") or "0")
        if n <= 0:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def do_GET(self):
        try:
            path = urlparse(self.path).path
            parts = [p for p in path.split("/") if p]
            if path in ("/", "/index.html"):
                self._send(200, _render_index_html(), "text/html")
                return
            if path == "/api/projects":
                self._send(200, services.list_projects())
                return
            if path == "/api/model-routes":
                self._send(200, services.model_routes())
                return
            if path == "/api/providers/health":
                self._send(200, services.providers_health())
                return
            if path == "/api/tools/health":
                self._send(200, services.tools_health())
                return
            if path == "/api/agents":
                self._send(200, services.agents_status())
                return
            if path == "/api/routes/resolve":
                qs = parse_qs(urlparse(self.path).query)
                route_type = (qs.get("type") or ["model"])[0]
                name = (qs.get("stage") or qs.get("tool") or [""])[0]
                self._send(200, services.resolve_route(route_type, name))
                return
            if path == "/api/research-health":
                self._send(200, services.research_health())
                return
            if path == "/api/jobs":
                self._send(200, services.list_jobs())
                return
            if len(parts) == 3 and parts[:2] == ["api", "jobs"]:
                self._send(200, services.job_status(parts[2]))
                return
            if len(parts) == 3 and parts[:2] == ["api", "projects"]:
                self._send(200, services.get_project(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "research-summary":
                self._send(200, services.project_research_summary(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "route-log":
                self._send(200, services.route_logs(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "route-summary":
                self._send(200, services.route_summary(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "stages":
                self._send(200, services.stage_state(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "gates":
                self._send(200, services.gate_status(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "slide-state":
                self._send(200, services.slide_state(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "model-plan":
                self._send(200, services.get_model_routed_plan(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "template-components":
                self._send(200, services.template_components(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "template-library-candidates":
                self._send(200, services.template_library_candidates(parts[2]))
                return
            if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3] == "files":
                filename = parts[4]
                allowed = {
                    "deck.pptx": "deck.pptx",
                    "research.md": "research.md",
                    "citations.json": "citations.json",
                    "run-manifest.json": "run-manifest.json",
                    "model-routed-plan.json": "model-routed-plan.json",
                    "slide-state.json": "slide-state.json",
                    "codex-debug-report.md": "devops/codex-debug-report.md",
                }
                if filename not in allowed:
                    self._send(403, {"error": "file not downloadable"})
                    return
                self._send_file(project_dir(parts[2]) / allowed[filename])
                return
            self._send(404, {"error": "not found"})
        except FileNotFoundError as exc:
            self._send(404, {"error": f"project not found: {exc}"})
        except Exception as exc:
            self._send(500, {"error": str(exc)})

    def do_POST(self):
        path = urlparse(self.path).path
        parts = [p for p in path.split("/") if p]
        try:
            body = self._json()
            if path == "/api/projects":
                self._send(200, services.create_project(body))
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"]:
                project_id, action = parts[2], parts[3]
                if action == "answers":
                    self._send(200, services.update_answers(project_id, body))
                    return
                if action == "resources":
                    self._send(200, services.scan_resources(project_id))
                    return
                if action == "research":
                    self._send(200, services.run_research(project_id, body))
                    return
                if action == "generate":
                    if body.get("async"):
                        self._send(200, services.generate_async(project_id, body))
                    else:
                        self._send(200, services.generate(project_id, body))
                    return
                if action == "model-stage":
                    stage = str(body.get("stage") or "")
                    self._send(200, services.run_model_stage(project_id, stage, body))
                    return
                if action == "run-stage":
                    if body.get("async"):
                        self._send(200, services.run_stage_async(project_id, body))
                    else:
                        self._send(200, services.run_stage(project_id, body))
                    return
                if action == "run-until-blocked":
                    if body.get("async"):
                        self._send(200, services.run_until_blocked_async(project_id, body))
                    else:
                        self._send(200, services.run_until_blocked(project_id, body))
                    return
                if action == "model-plan":
                    self._send(200, services.prepare_model_routed_plan(project_id, body))
                    return
                if action == "model-plan-update":
                    self._send(200, services.update_model_routed_plan(project_id, body))
                    return
                if action == "slide-revise":
                    self._send(200, services.revise_slide_plan(project_id, body))
                    return
                if action == "codex-debug":
                    self._send(200, services.run_codex_debug(project_id, body))
                    return
                if action == "stages":
                    stage = str(body.get("stage") or "")
                    self._send(200, services.confirm_stage(project_id, stage, body))
                    return
                if action == "stage-artifact":
                    stage = str(body.get("stage") or "")
                    self._send(200, services.edit_stage_artifact(project_id, stage, body))
                    return
            self._send(404, {"error": "not found"})
        except FileNotFoundError as exc:
            self._send(404, {"error": f"project not found: {exc}"})
        except Exception as exc:
            self._send(500, {"error": str(exc)})

    def log_message(self, fmt, *args):
        print("[ppt-agent-app] " + fmt % args)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the local ppt-agent app.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"ppt-agent app: http://{args.host}:{args.port}")
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
