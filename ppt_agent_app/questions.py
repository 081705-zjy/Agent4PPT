from __future__ import annotations


QUESTION_SCHEMA = [
    {
        "id": "topic",
        "label": "主题",
        "required": True,
        "prompt": "这份 PPT 的主题是什么？",
    },
    {
        "id": "audience",
        "label": "受众",
        "required": True,
        "prompt": "主要给谁看？例如技术管理者、架构师、客户、投资人。",
    },
    {
        "id": "scenario",
        "label": "场景",
        "required": True,
        "prompt": "使用场景是什么？例如立项汇报、技术评审、客户交流、课程培训。",
    },
    {
        "id": "slide_count",
        "label": "页数",
        "required": True,
        "prompt": "希望生成多少页？",
        "default": "10",
    },
    {
        "id": "duration_minutes",
        "label": "时长",
        "required": False,
        "prompt": "汇报时长大约多少分钟？",
        "default": "10",
    },
    {
        "id": "language",
        "label": "语言",
        "required": True,
        "prompt": "输出语言是什么？",
        "default": "zh",
    },
    {
        "id": "style",
        "label": "风格",
        "required": False,
        "prompt": "叙事和视觉风格是什么？",
        "default": "专业技术汇报，偏架构分析和方案设计",
    },
    {
        "id": "story_style",
        "label": "叙事逻辑",
        "required": False,
        "prompt": "整体叙述逻辑偏哪种？例如问题-方案-验证-路线图。",
        "default": "背景 -> 问题 -> 机制 -> 架构 -> 路线图 -> 风险与建议",
    },
    {
        "id": "user_outline",
        "label": "用户大纲",
        "required": False,
        "prompt": "如果你已有大纲、章节结构或逐页标题，请直接粘贴。该大纲优先级最高。",
        "default": "",
    },
    {
        "id": "required_sources",
        "label": "必须复用资料",
        "required": False,
        "prompt": "哪些 PPT、图片、表格或资料必须优先复用？可写文件名或描述。",
        "default": "",
    },
    {
        "id": "forbidden_sources",
        "label": "禁止复用资料",
        "required": False,
        "prompt": "哪些资料不能复用、不能展示或需要避免过细描述？",
        "default": "",
    },
    {
        "id": "direct_slide_reuse_policy",
        "label": "整页复用策略",
        "required": False,
        "prompt": "是否允许草稿阶段直接复制整页 PPT？",
        "default": "允许草稿阶段直接复制整页，最终版需语义审计和统一风格",
    },
    {
        "id": "reuse_policy",
        "label": "复用策略",
        "required": False,
        "prompt": "是否优先复用已有 PPT/图片/文字/叙事逻辑？",
        "default": "激进复用：优先复用已有 PPT 的叙事、页面、图片、表格和图解，缺口再检索或生成",
    },
    {
        "id": "citation_policy",
        "label": "引用策略",
        "required": False,
        "prompt": "是否需要每页引用来源？",
        "default": "关键事实和外部资料需要引用",
    },
]


def completion(answers: dict) -> dict:
    required = [q["id"] for q in QUESTION_SCHEMA if q.get("required")]
    missing = [k for k in required if not str(answers.get(k, "")).strip()]
    answered = [q["id"] for q in QUESTION_SCHEMA if str(answers.get(q["id"], "")).strip()]
    return {
        "required_missing": missing,
        "answered_count": len(answered),
        "total_count": len(QUESTION_SCHEMA),
        "ready_to_generate": not missing,
    }
