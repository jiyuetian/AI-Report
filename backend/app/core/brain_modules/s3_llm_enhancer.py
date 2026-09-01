"""
S3 LLM推荐 + Schema自愈 - M2-06
LLM输出配置JSON → Schema校验 → 失败重试≤2 → 降级规则引擎
粒度校验（宏观指标禁行级展开）
"""
import json
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from jsonschema import validate, ValidationError, Draft7Validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm_gateway import llm_chat
from app.core.brain_modules.s3_chart_engine import S3ChartEngine, ChartRecommendation


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
        previous_error: Optional[str] = None
    ) -> str:
        """构建LLM Prompt"""
        
        error_section = ""
        if previous_error:
            error_section = f"""
【上次生成错误】
{previous_error}

请修正以上错误，重新生成配置。
"""
        
        prompt = f"""你是一位数据可视化专家。请根据以下信息生成图表配置：

【数据主题】
{theme}

【字段列表】
{', '.join(fields)}

【数据粒度】
{grain} ({'宏观指标' if grain == 'macro' else '汇总数据' if grain == 'aggregate' else '明细数据'})

【分析目标】
{json.dumps(goals, ensure_ascii=False, indent=2)}

【约束条件】
1. 生成5个图表配置
2. 图表类型必须是以下之一：kpi, line, bar, pie, scatter, table
3. 字段必须从上面的字段列表中选择
4. 标题简洁明了（不超过20字）
5. {"宏观粒度禁止生成分页明细表" if grain == "macro" else ""}

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
        
        return prompt
    
    async def generate_with_self_healing(
        self,
        db: AsyncSession,
        theme: str,
        fields: List[str],
        goals: List[Dict],
        grain: str = "detail"
    ) -> Dict[str, Any]:
        """
        生成图表配置（带Schema自愈）
        
        流程：
        1. LLM生成 → Schema校验 → 通过则返回
        2. 失败 → 回写错误 → 重试（最多2次）
        3. 仍失败 → 降级规则引擎
        """
        
        last_error = None
        
        for attempt in range(self.MAX_RETRIES + 1):
            print(f"[S3-LLM] 生成尝试 {attempt + 1}/{self.MAX_RETRIES + 1}")
            
            # 构建Prompt（带错误回写）
            prompt = self._build_prompt(theme, fields, goals, grain, last_error)
            
            # 调用LLM
            response = await llm_chat(
                prompt=prompt,
                json_mode=True,
                user_id="s3_llm_enhancer"
            )
            
            if not response.success or not response.response_json:
                last_error = f"LLM调用失败: {response.error}"
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
        
        # 全部重试失败，降级到规则引擎
        print(f"[S3-LLM] LLM生成失败，降级到规则引擎")
        
        rule_result = self.rule_engine.generate_dashboard_config(fields, grain)
        
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
        prompt = f"""请优化以下图表配置的标题和描述：

【数据主题】
{theme}

【原始图表配置】
{json.dumps([c.to_dict() for c in rule_charts], ensure_ascii=False, indent=2)}

【优化要求】
1. 标题更业务化（避免技术术语）
2. 添加配置项使图表更美观
3. 保持chart_type不变
4. 字段必须在{fields}中选择

输出格式：与输入相同的JSON数组"""
        
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
    grain: str = "detail"
) -> Dict[str, Any]:
    """
    便捷函数：LLM生成图表（带自愈）
    """
    enhancer = S3LLMEnhancer()
    return await enhancer.generate_with_self_healing(db, theme, fields, goals, grain)


def validate_chart_grain(chart_config: Dict, grain: str) -> Tuple[bool, str]:
    """便捷函数：校验图表粒度"""
    return GrainChecker.check_chart_grain(chart_config, grain)