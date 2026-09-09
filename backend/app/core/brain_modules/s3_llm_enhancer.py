"""
S3 LLM推荐 + Schema自愈 - M2-06
LLM输出配置JSON → Schema校验 → 失败重试≤2 → 降级规则引擎
粒度校验（宏观指标禁行级展开）
"""
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from jsonschema import validate, ValidationError, Draft7Validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm_gateway import llm_chat
from app.core.prompt_loader import load_prompt
from app.core.brain_modules.s3_chart_engine_v2 import S3ChartEngine, ChartRecommendation, FieldAnalyzer, FieldType
from app.core.brain_modules.schema_enricher import build_semantics


# 业务主题 → 建议优先分析的维度（"主题-维度"联动：让模型贴合业务场景选维度，而非瞎选）
# 避免"客户画像却只统计单位性质/失信占比"这类思路偏离
THEME_DIMENSION_HINTS = [
    ("客户画像|客群画像|用户画像|画像",
     "客户画像场景（直接引用下述原始字段名，禁止构造不存在的字段）：\n"
     "  - 婚姻状况 → 饼图/柱状做婚姻分布\n"
     "  - 单位所属行业、单位性质 → 柱状/占比做行业与单位性质分布\n"
     "  - 借款人年龄 → 柱状按取值分组展示年龄分布（x 直接用字段'借款人年龄'）\n"
     "  - 失信人员、黑名单人员 → 占比 KPI 或饼图\n"
     "  - 历史逾期次数 → 柱状做风险分层分布\n"
     "至少覆盖婚姻、行业、年龄三类中的两类，且用【字段列表】中的原名。"),
    ("担保|贷款|信贷|借据|房贷", "信贷/担保场景：围绕风险与结构 —— 按地区/抵押物类型/贷款类型做占比与对比，趋势用时间字段，重点输出金额KPI与逾期等风险指标。"),
    ("违约|逾期|风险分层|不良", "风险分析：有且能分层的字段（如历史逾期次数、风险等级）优先做风险分层分布，再叠加地区/行业维度看风险集中度。"),
]

# 兜底通用建议
_DEFAULT_DIM_HINT = "优先选择低基数枚举字段（地区/状态/类型/性质/行业等）做分布与对比，数值字段做指标汇总或分桶分组；避免用同一对字段重复出多个图，尽量覆盖不同分析维度。"


def _theme_dimension_hint(theme: str) -> str:
    """根据主题返回业务维度建议"""
    if not theme:
        return _DEFAULT_DIM_HINT
    for kw, hint in THEME_DIMENSION_HINTS:
        if re.search(kw, theme, re.IGNORECASE):
            return hint
    return _DEFAULT_DIM_HINT


@dataclass
class LLMChartConfig:
    """LLM输出的图表配置"""
    chart_type: str
    title: str
    x_field: Optional[str] = None
    y_field: Optional[str] = None
    category_field: Optional[str] = None
    value_field: Optional[str] = None
    config: Dict[str, Any] = None
    reason: str = ""


# JSON Schema 定义（用于校验LLM输出）
CHART_CONFIG_SCHEMA = {
    "type": "object",
    "required": ["chart_type", "title"],
    "properties": {
        "chart_type": {
            "type": "string",
            "enum": ["kpi", "line", "bar", "pie", "scatter", "table", "map", "heatmap"]
        },
        "title": {
            "type": "string",
            "minLength": 1,
            "maxLength": 100
        },
        "x_field": {"type": ["string", "null"]},
        "y_field": {"type": ["string", "null"]},
        "category_field": {"type": ["string", "null"]},
        "value_field": {"type": ["string", "null"]},
        "config": {
            "type": "object",
            "additionalProperties": True
        },
        "reason": {"type": "string"}
    },
    "additionalProperties": False
}

DASHBOARD_CONFIG_SCHEMA = {
    "type": "object",
    "required": ["charts"],
    "properties": {
        "charts": {
            "type": "array",
            "minItems": 1,
            "maxItems": 10,
            "items": CHART_CONFIG_SCHEMA
        },
        "layout": {
            "type": "object",
            "properties": {
                "columns": {"type": "integer", "minimum": 1, "maximum": 4}
            }
        }
    }
}


class SchemaValidator:
    """Schema校验器"""
    
    def __init__(self):
        self.chart_validator = Draft7Validator(CHART_CONFIG_SCHEMA)
        self.dashboard_validator = Draft7Validator(DASHBOARD_CONFIG_SCHEMA)
    
    def validate_chart_config(self, config: Dict) -> Tuple[bool, List[str]]:
        """
        校验单个图表配置
        
        Returns:
            (是否通过, 错误列表)
        """
        errors = []
        for error in self.chart_validator.iter_errors(config):
            errors.append(f"{error.message} at {list(error.path)}")
        return len(errors) == 0, errors
    
    def validate_dashboard_config(self, config: Dict) -> Tuple[bool, List[str]]:
        """校验看板配置"""
        errors = []
        for error in self.dashboard_validator.iter_errors(config):
            errors.append(f"{error.message} at {list(error.path)}")
        return len(errors) == 0, errors
    
    def validate_grain_compatibility(
        self,
        config: Dict,
        grain: str,
        available_fields: List[str]
    ) -> Tuple[bool, str]:
        """
        校验粒度兼容性
        
        规则：
        - macro粒度：禁止行级展开（table图表且page_size>0视为明细）
        - 所有字段必须在available_fields中
        """
        chart_type = config.get("chart_type", "")
        chart_config = config.get("config", {})
        
        # 宏观粒度检查
        if grain == "macro":
            # 禁止明细表
            if chart_type == "table":
                page_size = chart_config.get("page_size", 20)
                if page_size > 0:
                    return False, "宏观粒度禁止行级明细表（请使用聚合表或关闭分页）"
        
        # 字段存在性检查
        fields_to_check = [
            config.get("x_field"),
            config.get("y_field"),
            config.get("category_field"),
            config.get("value_field")
        ]
        
        for field in fields_to_check:
            if field and field not in available_fields:
                return False, f"字段 '{field}' 不存在于数据集中"
        
        return True, ""


class S3LLMEnhancer:
    """
    S3 LLM增强器 + Schema自愈
    
    流程：
    1. 调用LLM生成图表配置JSON
    2. Schema校验
    3. 失败则回写错误信息，重试（最多2次）
    4. 仍失败则降级到规则引擎
    5. 粒度兼容性检查
    """
    
    MAX_RETRIES = 2
    
    def __init__(self):
        self.validator = SchemaValidator()
        self.rule_engine = S3ChartEngine()
    
    def _build_prompt(
        self,
        theme: str,
        fields: List[str],
        goals: List[Dict],
        grain: str,
        previous_error: Optional[str] = None,
        semantics: Optional[Dict[str, Any]] = None
    ) -> str:
        """构建LLM Prompt"""

        error_section = ""
        if previous_error:
            error_section = f"""
【上次生成错误】
{previous_error}

请修正以上错误，重新生成配置。
"""

        # 字段语义标注（优先用 AI+规则 融合结果，比纯规则更懂中文业务字段）
        # - 规则无法识别的"婚姻状况/单位所属行业/职业稳定性"等，AI 能标成分类/数值
        field_types = semantics.get("type_map", {}) if semantics else FieldAnalyzer.analyze_fields(fields)
        meta = semantics.get("meta", {}) if semantics else {}
        type_label = {
            FieldType.DATE: "日期/趋势横轴",
            FieldType.NUMBER: "数值/指标(可汇总或分桶)",
            FieldType.CATEGORY: "分类维度(适合做分布/对比/占比)",
            FieldType.GEO: "地区维度(适合地图/地区对比)",
            FieldType.TEXT: "文本标识(一般不宜作分析维度)",
        }

        def _desc(f: str) -> str:
            t = field_types.get(f, FieldType.TEXT)
            base = type_label.get(t, "文本")
            m = meta.get(f, {})
            role = m.get("business_role") or ""
            hint = m.get("chart_hint") or ""
            parts = [base]
            if role:
                parts.append(role)
            if hint:
                parts.append(f"建议:{hint}")
            return "，".join(parts) if len(parts) > 1 else base

        fields_desc = "\n".join(f"  - {f}（{_desc(f)}）" for f in fields)
        # 主题→维度业务建议
        dim_hint = _theme_dimension_hint(theme)

        # 粒度标签与宏观禁则（外置模板使用）
        grain_with_label = f"{grain} ({'宏观指标' if grain == 'macro' else '汇总数据' if grain == 'aggregate' else '明细数据'})"
        grain_rule = "宏观粒度禁止生成分页明细表" if grain == "macro" else "无（按粒度选择合适图表）"
        goals_str = json.dumps(goals, ensure_ascii=False, indent=2)

        default_prompt = f"""你是一位数据可视化专家。请根据以下信息生成图表配置：

【数据主题】
{theme}

【字段列表及类型（务必据此选择分析维度，不要逐客户堆明细）】
{fields_desc}

【业务场景维度建议】
{dim_hint}

【数据粒度】
{grain_with_label}

【分析目标】
{goals_str}

【约束条件】
1. 生成5个图表配置
2. 图表类型必须是以下之一：kpi, line, bar, pie, scatter, table
3. 字段必须从上面的字段列表中选择
4. 标题简洁明了（不超过20字）
5. 贴合【业务场景维度建议】，5个图尽量覆盖不同分析维度，不要反复用同一对字段
6. 所有 x_field/y_field/category_field/value_field 必须是【字段列表及类型】中存在的【确切原始字段名】；严禁臆造不存在字段（如'年龄_分桶'、'status_flag'），连续数值字段直接引用原字段名即可
7. {grain_rule}

{error_section}
【输出格式】
必须是有效的JSON，格式如下：
{{
    "charts": [
        {{
            "chart_type": "line",
            "title": "担保金额趋势",
            "x_field": "日期",
            "y_field": "担保金额",
            "config": {{}},
            "reason": "趋势分析需要折线图"
        }}
    ]
}}

请只输出JSON，不要其他文字。"""

        # 外置被控提示词优先（prompts/s3_llm_main.md），缺失回退内置默认
        main_prompt = load_prompt(
            "s3_llm_main",
            default_prompt,
            theme=theme,
            fields_desc=fields_desc,
            dim_hint=dim_hint,
            grain_with_label=grain_with_label,
            goals=goals_str,
            grain_rule=grain_rule,
            error_section=error_section,
        )
        # 全局护栏：Prompt 中心「system（全局系统提示）」+「accuracy（数据准确性红线）」作为前缀，始终生效
        # 管理员在管理中心编辑这两块即可实时影响图表生成遵守的红线，无需重启
        global_guard = load_prompt("system", "你是一名资深 BI 数据分析师。") \
            + "\n\n" + load_prompt("accuracy", "所有字段必须来自给定字段列表，严禁臆造。")
        return global_guard + "\n\n" + main_prompt
    
    async def generate_with_self_healing(
        self,
        db: AsyncSession,
        theme: str,
        fields: List[str],
        goals: List[Dict],
        grain: str = "detail",
        semantics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        生成图表配置（带Schema自愈 + 字段语义增强）
        
        流程：
        1. LLM生成 → Schema校验 → 通过则返回
        2. 失败 → 回写错误 → 重试（最多2次）
        3. 仍失败 → 降级规则引擎（同样使用 AI+规则 融合的类型，识别维度不退化）
        """
        
        # 字段语义增强：AI权威 + 规则保底，一次计算复用（prompt 与降级路径都受益）
        # 按数据集缓存，同一批字段只标一次；AI 不可用自动回退纯规则
        if semantics is None:
            semantics = await build_semantics(fields, theme)
            print(f"[S3-LLM] 字段语义增强: enriched={semantics.get('enriched')}")

        last_error = None
        
        for attempt in range(self.MAX_RETRIES + 1):
            print(f"[S3-LLM] 生成尝试 {attempt + 1}/{self.MAX_RETRIES + 1}")
            
            # 构建Prompt（带错误回写 + 语义标注）
            prompt = self._build_prompt(theme, fields, goals, grain, last_error, semantics)
            
            # 调用LLM
            response = await llm_chat(
                prompt=prompt,
                json_mode=True,
                user_id="s3_llm_enhancer"
            )

            # fallback_used=True 时明确走规则引擎降级，不再继续重试
            if response.fallback_used or not response.success or not response.response_json:
                last_error = response.error or f"LLM调用失败: {response.error}"
                print(f"[S3-LLM] {last_error}")
                continue
            
            llm_output = response.response_json
            
            # Schema校验
            is_valid, errors = self.validator.validate_dashboard_config(llm_output)
            
            if not is_valid:
                last_error = f"Schema校验失败: {'; '.join(errors)}"
                print(f"[S3-LLM] {last_error}")
                continue
            
            # 粒度兼容性检查
            charts = llm_output.get("charts", [])
            grain_errors = []
            
            for i, chart in enumerate(charts):
                is_compatible, error = self.validator.validate_grain_compatibility(
                    chart, grain, fields
                )
                if not is_compatible:
                    grain_errors.append(f"图表{i+1}: {error}")
            
            if grain_errors:
                last_error = f"粒度不兼容: {'; '.join(grain_errors)}"
                print(f"[S3-LLM] {last_error}")
                continue
            
            # 全部通过
            print(f"[S3-LLM] 生成成功（尝试{attempt + 1}次）")
            
            return {
                "success": True,
                "charts": charts,
                "generated_by": "llm",
                "llm_used": True,
                "retry_count": attempt,
                "self_healed": attempt > 0
            }
        
        # 全部重试失败，降级到规则引擎（带 AI+规则 融合的类型，识别维度不退化）
        print(f"[S3-LLM] LLM生成失败，降级到规则引擎")
        
        type_override = semantics.get("type_map") if semantics else None
        rule_result = self.rule_engine.generate_dashboard_config(
            fields, grain, field_types_override=type_override
        )
        
        return {
            "success": True,
            "charts": rule_result["charts"],
            "generated_by": "rule_engine",
            "llm_used": False,
            "retry_count": self.MAX_RETRIES,
            "fallback_reason": f"LLM生成失败: {last_error}",
            "self_healed": False
        }
    
    async def enhance_rule_based_charts(
        self,
        db: AsyncSession,
        rule_charts: List[ChartRecommendation],
        theme: str,
        fields: List[str],
        goals: List[Dict]
    ) -> List[Dict]:
        """
        增强规则生成的图表
        
        使用LLM优化标题和配置，但保持图表类型不变
        """
        # 外置被控提示词优先（prompts/s3_rule_chart_enhance.md），缺失回退内置默认
        default_prompt = f"""请优化以下图表配置的标题和描述：

【数据主题】
{theme}

【原始图表配置】
{raw_charts}

【优化要求】
1. 标题更业务化（避免技术术语）
2. 添加配置项使图表更美观
3. 保持chart_type不变
4. 字段必须在{fields}中选择

输出格式：与输入相同的JSON数组"""
        prompt = load_prompt(
            "s3_rule_chart_enhance",
            default_prompt,
            theme=theme,
            raw_charts=json.dumps([c.to_dict() for c in rule_charts], ensure_ascii=False, indent=2),
            fields=json.dumps(fields, ensure_ascii=False),
        )

        response = await llm_chat(
            prompt=prompt,
            json_mode=True,
            user_id="s3_llm_enhancer"
        )
        
        if response.success and response.response_json:
            # 校验
            if isinstance(response.response_json, list):
                return response.response_json
            elif isinstance(response.response_json, dict) and "charts" in response.response_json:
                return response.response_json["charts"]
        
        # 失败返回原始配置
        return [c.to_dict() for c in rule_charts]


class GrainChecker:
    """粒度检查器（用于前端拦截）"""
    
    @staticmethod
    def check_chart_grain(chart_config: Dict, grain: str) -> Tuple[bool, str]:
        """
        检查图表与粒度是否兼容
        
        Returns:
            (是否兼容, 错误信息)
        """
        chart_type = chart_config.get("chart_type", "")
        
        if grain == "macro":
            # 宏观粒度禁止
            if chart_type == "table":
                config = chart_config.get("config", {})
                if config.get("page_size", 20) > 0:
                    return False, "宏观指标不支持行级明细表（m-grain）"
            
            # 建议聚合图表
            if chart_type in ["scatter", "heatmap"]:
                return False, "宏观指标建议使用KPI/折线/柱状图"
        
        return True, ""
    
    @staticmethod
    def get_grain_recommendation(grain: str) -> List[str]:
        """获取粒度推荐的图表类型"""
        recommendations = {
            "macro": ["kpi", "line", "bar", "pie"],
            "aggregate": ["kpi", "line", "bar", "pie", "table"],
            "detail": ["kpi", "line", "bar", "pie", "scatter", "table", "heatmap"]
        }
        return recommendations.get(grain, recommendations["detail"])


# 便捷函数
async def generate_charts_with_llm(
    db: AsyncSession,
    theme: str,
    fields: List[str],
    goals: List[Dict],
    grain: str = "detail",
    semantics: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    便捷函数：LLM生成图表（带自愈 + 字段语义增强）
    """
    enhancer = S3LLMEnhancer()
    return await enhancer.generate_with_self_healing(db, theme, fields, goals, grain, semantics)


def validate_chart_grain(chart_config: Dict, grain: str) -> Tuple[bool, str]:
    """便捷函数：校验图表粒度"""
    return GrainChecker.check_chart_grain(chart_config, grain)