"""
S3 图表推荐引擎 - M2-05
字段组合 → 图表类型映射（借鉴 LIDA）
无 LLM 也能出完整看板（最终兜底）
"""
import yaml
import os
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import re


class FieldType(Enum):
    """字段类型"""
    DATE = "date"
    NUMBER = "number"
    CATEGORY = "category"
    GEO = "geo"
    TEXT = "text"


@dataclass
class ChartRecommendation:
    """图表推荐结果"""
    chart_type: str
    title: str
    x_field: Optional[str] = None
    y_field: Optional[str] = None
    category_field: Optional[str] = None
    value_field: Optional[str] = None
    config: Dict[str, Any] = None
    priority: int = 0
    rule_name: str = ""
    reason: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "chart_type": self.chart_type,
            "title": self.title,
            "x_field": self.x_field,
            "y_field": self.y_field,
            "category_field": self.category_field,
            "value_field": self.value_field,
            "config": self.config or {},
            "priority": self.priority,
            "rule_name": self.rule_name,
            "reason": self.reason
        }


class FieldAnalyzer:
    """字段分析器"""
    
    # 关键词到字段类型的映射
    KEYWORD_PATTERNS = {
        FieldType.DATE: [r"日期?", r"时间", r"年月?", r"day", r"date", r"time"],
        FieldType.NUMBER: [r"金额", r"额", r"率", r"数", r"值", r"量", r"价格", r"total", r"amount", r"count", r"num", r"balance"],
        FieldType.GEO: [r"地区", r"省份?", r"城市", r"区", r"地址", r"geo", r"region", r"province", r"city"],
        FieldType.CATEGORY: [r"类型", r"类别", r"种类", r"方式", r"状态", r"类型", r"type", r"category", r"status"]
    }
    
    @staticmethod
    def infer_field_type(field_name: str, sample_values: Optional[List] = None) -> FieldType:
        """推断字段类型"""
        field_lower = field_name.lower()
        
        # 关键词匹配
        for ftype, patterns in FieldAnalyzer.KEYWORD_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, field_lower, re.IGNORECASE):
                    return ftype
        
        # 默认值
        return FieldType.TEXT
    
    @staticmethod
    def analyze_fields(fields: List[str], sample_data: Optional[List[Dict]] = None) -> Dict[str, FieldType]:
        """分析所有字段类型"""
        return {
            f: FieldAnalyzer.infer_field_type(f, sample_data[0].get(f) if sample_data else None)
            for f in fields
        }


class S3ChartEngine:
    """
    S3 图表推荐引擎
    
    核心功能：
    1. 读取 YAML 规则文件
    2. 字段匹配 → 图表推荐
    3. 粒度限制检查
    4. 兜底生成（无 LLM）
    """
    
    def __init__(self, rules_file: Optional[str] = None):
        self.rules_file = rules_file or os.path.join(
            os.path.dirname(__file__), "s3_chart_rules.yaml"
        )
        self.rules = []
        self.fallback = {}
        self.grain_constraints = {}
        self.chart_constraints = {}
        self._load_rules()
    
    def _load_rules(self):
        """加载 YAML 规则"""
        try:
            with open(self.rules_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            self.rules = data.get("rules", [])
            self.fallback = data.get("fallback", {})
            self.grain_constraints = data.get("grain_constraints", {})
            self.chart_constraints = data.get("chart_constraints", {})
            
            print(f"[S3] 加载 {len(self.rules)} 条图表规则")
        except Exception as e:
            print(f"[S3] 规则加载失败: {e}，使用默认规则")
            self._load_default_rules()
    
    def _load_default_rules(self):
        """加载默认规则"""
        self.rules = [
            {
                "name": "时间趋势",
                "priority": 90,
                "condition": {"field_types": ["date", "number"]},
                "chart": {"type": "line", "title": "趋势分析"}
            },
            {
                "name": "分类对比",
                "priority": 80,
                "condition": {"field_types": ["category", "number"]},
                "chart": {"type": "bar", "title": "对比分析"}
            },
            {
                "name": "占比分布",
                "priority": 70,
                "condition": {"field_types": ["category", "number"]},
                "chart": {"type": "pie", "title": "占比分析"}
            }
        ]
        self.fallback = {
            "default_charts": [
                {"type": "bar", "title": "数据对比"},
                {"type": "pie", "title": "结构分布"},
                {"type": "table", "title": "数据明细"}
            ]
        }
    
    def _match_rule(self, rule: Dict, field_types: Dict[str, FieldType], grain: str) -> Optional[ChartRecommendation]:
        """匹配单条规则"""
        condition = rule.get("condition", {})
        
        # 检查粒度限制
        if grain in self.grain_constraints:
            forbidden = self.grain_constraints[grain].get("forbidden", [])
            chart_type = rule.get("chart", {}).get("type", "")
            if chart_type in forbidden:
                return None
        
        # 检查字段类型
        required_types = condition.get("field_types", [])
        
        # 统计各类型字段数
        type_counts = {}
        for ft in field_types.values():
            type_counts[ft.value] = type_counts.get(ft.value, 0) + 1
        
        # 检查是否满足条件
        for req_type in required_types:
            if type_counts.get(req_type, 0) == 0:
                return None
        
        # 特殊条件检查
        if "date_count" in condition:
            if type_counts.get("date", 0) != condition["date_count"]:
                return None
        
        if "number_count" in condition:
            n_count = type_counts.get("number", 0)
            cond = condition["number_count"]
            if isinstance(cond, int):
                if n_count != cond:
                    return None
            elif isinstance(cond, dict):
                if cond.get("min") and n_count < cond["min"]:
                    return None
                if cond.get("max") and n_count > cond["max"]:
                    return None
        
        # 匹配成功，构建推荐
        chart_config = rule.get("chart", {})
        chart_type = chart_config.get("type", "bar")
        
        # 自动填充字段
        date_fields = [f for f, t in field_types.items() if t == FieldType.DATE]
        number_fields = [f for f, t in field_types.items() if t == FieldType.NUMBER]
        category_fields = [f for f, t in field_types.items() if t == FieldType.CATEGORY]
        geo_fields = [f for f, t in field_types.items() if t == FieldType.GEO]
        
        title = chart_config.get("title", "图表")
        title = title.replace("{date_field}", date_fields[0] if date_fields else "日期")
        title = title.replace("{number_field}", number_fields[0] if number_fields else "数值")
        title = title.replace("{category_field}", category_fields[0] if category_fields else "类别")
        title = title.replace("{geo_field}", geo_fields[0] if geo_fields else "地区")
        
        config = chart_config.get("config", {}).copy()
        
        # 填充config中的字段占位符
        for key, value in config.items():
            if isinstance(value, str):
                if date_fields:
                    value = value.replace("{date_field}", date_fields[0])
                if number_fields:
                    value = value.replace("{number_field}", number_fields[0])
                    value = value.replace("{number_field1}", number_fields[0])
                    if len(number_fields) > 1:
                        value = value.replace("{number_field2}", number_fields[1])
                if category_fields:
                    value = value.replace("{category_field}", category_fields[0])
                if geo_fields:
                    value = value.replace("{geo_field}", geo_fields[0])
                config[key] = value
        
        return ChartRecommendation(
            chart_type=chart_type,
            title=title,
            x_field=date_fields[0] if date_fields else (category_fields[0] if category_fields else None),
            y_field=number_fields[0] if number_fields else None,
            category_field=category_fields[0] if category_fields else None,
            value_field=number_fields[0] if number_fields else None,
            config=config,
            priority=rule.get("priority", 0),
            rule_name=rule.get("name", ""),
            reason=f"匹配规则: {rule.get('name', '')}"
        )
    
    def recommend_charts(
        self,
        fields: List[str],
        grain: str = "detail",
        sample_data: Optional[List[Dict]] = None,
        max_charts: int = 5
    ) -> List[ChartRecommendation]:
        """
        推荐图表
        
        Args:
            fields: 字段列表
            grain: 数据粒度 (detail/aggregate/macro)
            sample_data: 样本数据
            max_charts: 最大推荐数
        
        Returns:
            图表推荐列表
        """
        # 分析字段类型
        field_types = FieldAnalyzer.analyze_fields(fields, sample_data)
        
        print(f"[S3] 字段分析: {field_types}")
        
        # 按优先级排序匹配规则
        recommendations = []
        
        for rule in sorted(self.rules, key=lambda x: x.get("priority", 0), reverse=True):
            rec = self._match_rule(rule, field_types, grain)
            if rec:
                # 去重检查
                existing_types = [r.chart_type for r in recommendations]
                if rec.chart_type not in existing_types or len(recommendations) < 3:
                    recommendations.append(rec)
                
                if len(recommendations) >= max_charts:
                    break
        
        # 如果推荐不足，使用兜底
        if len(recommendations) < max_charts:
            recommendations = self._apply_fallback(
                recommendations, field_types, grain, max_charts
            )
        
        return recommendations[:max_charts]
    
    def _apply_fallback(
        self,
        existing: List[ChartRecommendation],
        field_types: Dict[str, FieldType],
        grain: str,
        max_charts: int
    ) -> List[ChartRecommendation]:
        """应用兜底规则"""
        result = existing.copy()
        
        # 检查已有类型
        existing_types = {r.chart_type for r in result}
        
        # 兜底配置
        fallback_charts = self.fallback.get("default_charts", [])
        
        for fb in fallback_charts:
            if len(result) >= max_charts:
                break
            
            chart_type = fb.get("type", "bar")
            
            # 检查粒度限制
            if grain in self.grain_constraints:
                forbidden = self.grain_constraints[grain].get("forbidden", [])
                if chart_type in forbidden:
                    continue
            
            # 检查是否已存在
            if chart_type in existing_types:
                continue
            
            # 自动填充字段
            date_fields = [f for f, t in field_types.items() if t == FieldType.DATE]
            number_fields = [f for f, t in field_types.items() if t == FieldType.NUMBER]
            category_fields = [f for f, t in field_types.items() if t == FieldType.CATEGORY]
            
            title = fb.get("title", "图表")
            
            rec = ChartRecommendation(
                chart_type=chart_type,
                title=title,
                x_field=date_fields[0] if date_fields else (category_fields[0] if category_fields else None),
                y_field=number_fields[0] if number_fields else None,
                priority=fb.get("priority", 0),
                rule_name="fallback",
                reason="兜底规则"
            )
            
            result.append(rec)
            existing_types.add(chart_type)
        
        return result
    
    def generate_dashboard_config(
        self,
        fields: List[str],
        grain: str = "detail",
        sample_data: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        生成完整看板配置（5个图表）
        
        断 LLM 时 01 表仍出：
        - KPI卡
        - 趋势图
        - 对比图
        - 分布图
        - 明细表
        """
        recommendations = self.recommend_charts(fields, grain, sample_data, max_charts=5)
        
        # 确保覆盖五种类型
        required_types = {"kpi", "line", "bar", "pie", "table"}
        existing_types = {r.chart_type for r in recommendations}
        
        # 如果缺少必要类型，强制添加
        for req_type in required_types - existing_types:
            if req_type == "kpi":
                recommendations.insert(0, ChartRecommendation(
                    chart_type="kpi",
                    title="关键指标",
                    priority=100,
                    rule_name="fallback_kpi",
                    reason="强制兜底KPI"
                ))
            elif req_type == "line":
                recommendations.append(ChartRecommendation(
                    chart_type="line",
                    title="趋势分析",
                    priority=50,
                    rule_name="fallback_line",
                    reason="强制兜底趋势"
                ))
            elif req_type == "bar":
                recommendations.append(ChartRecommendation(
                    chart_type="bar",
                    title="对比分析",
                    priority=40,
                    rule_name="fallback_bar",
                    reason="强制兜底对比"
                ))
            elif req_type == "pie":
                recommendations.append(ChartRecommendation(
                    chart_type="pie",
                    title="占比分布",
                    priority=30,
                    rule_name="fallback_pie",
                    reason="强制兜底分布"
                ))
            elif req_type == "table":
                recommendations.append(ChartRecommendation(
                    chart_type="table",
                    title="数据明细",
                    priority=10,
                    rule_name="fallback_table",
                    reason="强制兜底明细"
                ))
        
        # 截取前5个
        recommendations = recommendations[:5]
        
        return {
            "success": True,
            "grain": grain,
            "field_count": len(fields),
            "chart_count": len(recommendations),
            "charts": [r.to_dict() for r in recommendations],
            "generated_by": "rule_engine",
            "llm_used": False
        }


# 便捷函数
def recommend_charts(
    fields: List[str],
    grain: str = "detail",
    sample_data: Optional[List[Dict]] = None
) -> List[Dict]:
    """便捷图表推荐函数"""
    engine = S3ChartEngine()
    recommendations = engine.recommend_charts(fields, grain, sample_data)
    return [r.to_dict() for r in recommendations]


def generate_dashboard(
    fields: List[str],
    grain: str = "detail",
    sample_data: Optional[List[Dict]] = None
) -> Dict:
    """便捷看板生成函数"""
    engine = S3ChartEngine()
    return engine.generate_dashboard_config(fields, grain, sample_data)