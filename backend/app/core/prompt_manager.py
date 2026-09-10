"""Prompt 中心引擎
将文件化提示词（core/prompts/*.md）升级为可管理/可版本化/可启停的配置中心。

架构遵循「代码/文件是种子，DB 是运行时覆盖层」：
- prompts/*.md  = 内置种子（"恢复默认"的来源），也是给人读的权威文案
- prompts 表   = 管理员在"管理中心 → Prompt 中心"编辑的覆盖内容 + 版本/启停
- 运行时        = prompt_loader.load_prompt ——> 本引擎：启用覆盖 → 文件 → 内置默认

内存缓存 _OVERRIDES 由 admin API 维护；服务启动时从 DB 初始化（单进程部署下生效）。
"""
import threading
from typing import Dict, Optional

from app.core.prompt_loader import _read_prompt_file

# --------------------------------------------------------------------------
# 板块元数据：按「基础→治理→分析→表达→安全」分层（参考《Prompt 中心策略手册》），
# key = 对应 prompts/*.md 的文件前缀（即 load_prompt 的 slug），与真实数据加工步骤一一对应。
# 所有板块均有对应提示词文件且被 AI 节点消费（system/accuracy 作为全局护栏注入 S3 图表生成）。
# --------------------------------------------------------------------------
PROMPT_GROUPS: list = [
    # ── 层1 基础 · 始终生效（全局护栏，最高优先级） ──
    {
        "key": "system",
        "title": "全局系统提示",
        "category": "基础 · 始终生效",
        "description": "定义 AI 人设（资深数据分析师）与人机协作契约：先理解目标→校验数据→再生成图表；工具与输出契约；禁止臆造字段与数字。",
    },
    {
        "key": "accuracy",
        "title": "数据准确性红线",
        "category": "基础 · 始终生效",
        "description": "最高优先级铁律：每个数字/字段必须来自字段实测、逐字一致，严禁臆造字段，不确定须声明置信度。冲突时以此为准。",
    },
    # ── 层2 治理 · 数据加工 ──
    {
        "key": "schema_enricher",
        "title": "字段语义标注",
        "category": "治理 · 字段标准化",
        "description": "Node-6 SchemaEnricher：识别中文字段的语义类型（分类/数值/文本/标识），供下游聚合与图表选型。",
    },
    {
        "key": "ai_quality_checker",
        "title": "AI 质检补充",
        "category": "治理 · 数据清洗",
        "description": "在规则引擎扫描之后，由 LLM 补充业务语义层面的数据质量问题（业务单元口径、不可能组合等），输出结构化 JSON。",
    },
    # ── 层3 分析生成 · 六层血缘链路 ──
    {
        "key": "s1_theme_detector",
        "title": "主题识别",
        "category": "分析 · S1",
        "description": "S1：从数据集字段识别业务主题（担保风控/客户画像等），输出主题标签与置信度。",
    },
    {
        "key": "s2_goal_generator",
        "title": "分析目标生成",
        "category": "分析 · S2",
        "description": "S2：基于主题与维度生成分析目标（趋势/对比/分布/预警/画像等），约束为合法 JSON。",
    },
    {
        "key": "s3_llm_main",
        "title": "图表生成 · LLM 主生成",
        "category": "分析 · S3",
        "description": "S3：由 LLM 依据目标推荐图表（图表类型/维度/指标），受规则矩阵约束并给出来源依据。",
    },
    {
        "key": "s3_rule_chart_enhance",
        "title": "图表生成 · 规则补充",
        "category": "分析 · S3",
        "description": "S3：对多分类/多指标场景做规则化补充，确保图表均匀分布、避免拥挤在一对维度上。",
    },
    # ── 层4 表达 · 对话交互 ──
    {
        "key": "intent_classifier",
        "title": "意图分类器",
        "category": "表达 · 对话交互",
        "description": "把用户在 AI 对话/血缘问答中的自然语言指令归类为受支持的动作（新增图表/改标题/导出等）。",
    },
    {
        "key": "ai_assistant_spec",
        "title": "AI 助手规范",
        "category": "表达 · 对话交互",
        "description": "AI 对话助手的角色与回答规范：给办公用户输出简洁、可执行、可溯源的 BI 助理答案。",
    },
    # ── 层4 表达 · 报告生成（接管期新增，对齐「AI 节点必须走受管 prompt」契约） ──
    {
        "key": "executive_summary",
        "title": "执行摘要生成（结构化数据）",
        "category": "表达 · 报告生成",
        "description": "报告第2章执行摘要：基于数据集主题与统计信息（字段/类型/基数/空值率/极值/聚合值），生成 3–5 条带数值的结论，禁止臆造。",
    },
    {
        "key": "executive_summary_doc",
        "title": "执行摘要生成（文档/文本）",
        "category": "表达 · 报告生成",
        "description": "文档型报告第2章执行摘要：仅基于源文件文本节选生成摘要，不得编造或推断。",
    },
]

_ORDER = [g["key"] for g in PROMPT_GROUPS]
_GROUPS_BY_KEY: Dict[str, dict] = {g["key"]: g for g in PROMPT_GROUPS}

# 内存覆盖缓存：key -> {content, enabled, version, is_builtin, remark, updated_by}
_OVERRIDES: Dict[str, dict] = {}
_LOCK = threading.Lock()


def all_groups() -> list:
    """按定义顺序返回全部板块元数据"""
    return list(PROMPT_GROUPS)


def get_group_meta(key: str) -> Optional[dict]:
    return _GROUPS_BY_KEY.get(key)


def is_valid_key(key: str) -> bool:
    return key in _GROUPS_BY_KEY


def seed_content(key: str) -> str:
    """内置种子文案 = prompts/{key}.md；文件缺失返回空串"""
    return _read_prompt_file(key) or ""


def get_override(key: str) -> Optional[dict]:
    with _LOCK:
        o = _OVERRIDES.get(key)
        return dict(o) if o else None


def is_customized(key: str) -> bool:
    """是否有启用中的自定义覆盖"""
    o = _OVERRIDES.get(key)
    return bool(o and o.get("content"))


def set_override(key: str, content: str, enabled: bool, version: int,
                 is_builtin: bool, remark: str, updated_by: str) -> None:
    """应用覆盖（编辑保存后由 admin API 调用）"""
    with _LOCK:
        _OVERRIDES[key] = {
            "content": content,
            "enabled": enabled,
            "version": version,
            "is_builtin": is_builtin,
            "remark": remark,
            "updated_by": updated_by,
        }


def clear_override(key: str) -> None:
    """清除覆盖（恢复默认后由 admin API 调用）"""
    with _LOCK:
        _OVERRIDES.pop(key, None)


def loaded_prompt(key: str, default: str, **kwargs) -> str:
    """
    取板块生效提示词（供 prompt_loader.load_prompt 委托）：
    启用中的覆盖 → prompts/{key}.md 种子 → 内置默认。再对 {token} 占位符做字面替换。
    """
    content: Optional[str] = None
    o = get_override(key)
    if o and o.get("content") and o.get("enabled"):
        content = o["content"]
    else:
        content = _read_prompt_file(key)
    if not content:
        content = default
    for k, v in kwargs.items():
        content = content.replace("{" + k + "}", str(v))
    return content