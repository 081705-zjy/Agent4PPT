/**
 * pi SDK 多 agent chain demo
 * ---------------------------------------------
 * 演示"零造轮子、纯编排"：
 *   - agent loop / 工具执行 / 记忆 / 上下文压缩 全部由 SDK 内建
 *   - 我们只写:  1) 每个 agent 的角色(系统提示词)  2) chain 编排逻辑
 *
 * 流程(你 ppt-agent 流水线的缩影):
 *   researcher  -> 收集要点
 *   outliner    -> 基于要点产出大纲 (吃上一步输出)
 *   slideWriter -> 基于大纲写 3 页幻灯片文案 (吃上一步输出)
 *
 * 运行:
 *   cd pi-sdk-demo
 *   npx tsx chain-demo.ts "介绍 RAG 检索增强生成"
 */

import {
	createAgentSession,
	DefaultResourceLoader,
	getAgentDir,
	ModelRuntime,
	resolveCliModel,
	SessionManager,
} from "@earendil-works/pi-coding-agent";
import { ProxyAgent, setGlobalDispatcher } from "undici";

// ---- 0. 让底层 undici fetch 走系统代理 (undici 默认不读 HTTPS_PROXY) ----
// pi CLI 内部已处理代理; SDK 直连时若端点需代理, 需自己注入 dispatcher。
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy || process.env.ALL_PROXY || process.env.all_proxy;
if (proxy) {
	setGlobalDispatcher(new ProxyAgent(proxy));
	console.error(`[demo] 已启用代理: ${proxy}`);
}

const CWD = process.cwd();
const AGENT_DIR = getAgentDir();

// ---- 1. 选模型 (SDK 统一处理鉴权: models.json / auth.json / 环境变量) ----
// 用与 CLI 一致的解析器, 能正确拿到自定义 provider(infini) 的 baseUrl/apiKey
const modelRuntime = await ModelRuntime.create();
const resolved = resolveCliModel({ cliModel: "infini/claude-opus-4-8", modelRuntime });
if (resolved.error) throw new Error(resolved.error);
const model = resolved.model;
if (!model) throw new Error("模型不可用，请检查 ~/.pi/agent/models.json");

// ---- 2. 定义一个可复用的 "跑一个 agent" 函数 ----
// 注意: 我们没写 agent loop / 没写工具调度 / 没写记忆管理。
// createAgentSession() 返回的就是一个完整能干活的 agent。
type StageResult = { name: string; output: string };

async function runAgent(name: string, systemPrompt: string, task: string): Promise<StageResult> {
	// resourceLoader 用来覆盖系统提示词 = 给这个 agent 设定"角色/人格"
	const loader = new DefaultResourceLoader({
		cwd: CWD,
		agentDir: AGENT_DIR,
		systemPromptOverride: () => systemPrompt,
	});
	await loader.reload();

	const { session } = await createAgentSession({
		model,
		modelRuntime,
		thinkingLevel: "off",
		// 这个 demo 不需要文件/命令能力, 关掉内置工具让它纯文本产出
		noTools: "all",
		resourceLoader: loader,
		// 每个 agent 独立、临时的上下文窗口 (记忆隔离)
		sessionManager: SessionManager.inMemory(),
	});

	let output = "";
	let errMsg = "";
	// 订阅事件拿流式输出 — 这是 SDK 暴露 agent 内部过程的方式
	const unsub = session.subscribe((e) => {
		if (e.type === "message_update" && e.assistantMessageEvent.type === "text_delta") {
			const d = e.assistantMessageEvent.delta;
			output += d;
			process.stdout.write(d);
		}
		if (e.type === "message_end" && e.message?.role === "assistant") {
			if (e.message.errorMessage) errMsg = e.message.errorMessage;
			// 兜底: 若没收到流式 delta, 从最终消息里取文本
			if (!output) {
				for (const p of e.message.content ?? []) {
					if (p.type === "text") output += p.text;
				}
			}
		}
	});

	process.stdout.write(`\n\n=== [${name}] 开始 ===\n`);
	await session.prompt(task); // ← 一句话触发完整 agent 运行(内部可能多轮)
	unsub();
	session.dispose();
	if (errMsg) process.stdout.write(`\n[!! ${name} 错误] ${errMsg}\n`);
	return { name, output: output.trim() };
}

// ---- 3. chain 编排: 你自己的业务逻辑, 后一步吃前一步输出 ----
const topic = process.argv[2] ?? "介绍向量数据库";

const researcher = await runAgent(
	"researcher",
	"你是资料研究员。围绕给定主题，用简洁中文列出 4-6 个最关键的要点，每点一行，不要展开。",
	`主题: ${topic}`,
);

const outliner = await runAgent(
	"outliner",
	"你是 PPT 大纲设计师。根据给定要点，产出一个 3 页幻灯片的大纲，每页给出标题 + 该页要讲的 bullet。",
	`请基于以下要点做大纲:\n\n${researcher.output}`,
);

const slideWriter = await runAgent(
	"slideWriter",
	"你是幻灯片文案。根据大纲，为每一页写出最终的标题和 2-3 条精炼 bullet 文案，直接可放进 PPT。",
	`请基于以下大纲写文案:\n\n${outliner.output}`,
);

// ---- 4. 汇总 ----
console.log("\n\n========== chain 完成 ==========");
for (const r of [researcher, outliner, slideWriter]) {
	console.log(`\n--- ${r.name} 输出 ---\n${r.output}`);
}
