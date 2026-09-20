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
    # 中文业务字段语义：兄弟姐妹——"婚姻状况/单位性质/单位所属行业/失信人员"都应是类别字段，
    # "借款人年龄/公积金缴存月数/收入负债比/历史逾期次数/职业稳定性(连续工作年限)"都应是数值字段。
    # 顺序敏感：先精确(数值)再语义归类；ID/编号类强制文本，避免被当数值。
    KEYWORD_PATTERNS = {
        FieldType.NUMBER: [r"金额", r"总额", r"额$", r"￥|\$", r"率", r"比$", r"月数", r"天数", r"次数",
                          r"数量", r"笔数", r"人数", r"年龄", r"年限", r"余额", r"占比", r"价格",
                          r"total", r"amount", r"count", r"num\b", r"value", r"balance"],
        FieldType.CATEGORY: [r"婚姻", r"状况", r"性质", r"行业", r"类别", r"类型", r"种类", r"方式",
                           r"状态", r"性别", r"人员", r"标签", r"是否", r"通过", r"区域", r"所在地",
                           r"省份?", r"城市", r"type", r"category", r"status"],
        FieldType.GEO: [r"地区", r"省份", r"省$", r"城市", r"县$", r"区$", r"地址", r"geo", r"region",
                       r"province", r"city"],
        FieldType.DATE: [r"日期", r"时间", r"年月", r"day", r"date", r"time"],
    }

    # 强制文本标识：主键/唯一标识类字段永远不是分析数值或分类维度
    ID_PATTERNS = [r"id", r"编号", r"序号", r"代码$", r"编码"]

    @staticmethod
    def infer_field_type(field_name: str, sample_values: Optional[List] = None) -> FieldType:
        """推断字段类型 —— 样本值优先，关键词次之"""
        field_lower = field_name.lower()

        # 强制文本（ID/编号类）
        for pat in FieldAnalyzer.ID_PATTERNS:
            if re.search(pat, field_lower, re.IGNORECASE):
                return FieldType.TEXT

        # ── 优先级1：样本值分析 ──────────────────────────────────────
        if sample_values and len(sample_values) > 0:
            non_null = [v for v in sample_values if v is not None and str(v).strip() != ""]
            if non_null:
                # 尝试解析为日期
                date_count = 0
                for v in non_null[:20]:
                    s = str(v).strip()
                    if re.match(r'^\d{4}[-/年]\d{1,2}[-/年]\d{1,2}', s) or \
                       re.match(r'^\d{4}年\d{1,2}月\d{1,2}日?', s) or \
                       re.match(r'^\d{4}-\d{2}-\d{2}', s):
                        date_count += 1
                if date_count >= len(non_null) * 0.5:
                    return FieldType.DATE

                # 尝试解析为数字
                num_count = 0
                for v in non_null[:20]:
                    s = str(v).replace(',', '').replace('￥', '').replace('$', '').replace(' ', '').strip()
                    try:
                        float(s)
                        num_count += 1
                    except ValueError:
                        pass
                if num_count >= len(non_null) * 0.5:
                    return FieldType.NUMBER

                # 基数判断：低基数 → CATEGORY，高基数 → TEXT
                distinct_vals = set(str(v) for v in non_null[:100])
                total = len(non_null)
                if total > 0 and len(distinct_vals) / total < 0.5 and len(distinct_vals) <= 50:
                    return FieldType.CATEGORY

        # ── 优先级2：关键词匹配（样本值缺失时的兜底）──────────────────
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
    
    def _match_rule(self, rule: Dict, field_types: Dict[str, FieldType], grain: str,
                    sample_data: Optional[List[Dict]] = None) -> Optional[ChartRecommendation]:
        """匹配单条规则"""
        condition = rule.get("condition", {})

        # 检查粒度限制
        if grain in self.grain_constraints:
            forbidden = self.grain_constraints[grain].get("forbidden", [])
            chart_type = rule.get("chart", {}).get("type", "")
            if chart_type in forbidden:
                return None

        # 统计各类型字段数
        type_counts = {}
        for ft in field_types.values():
            type_counts[ft.value] = type_counts.get(ft.value, 0) + 1

        # 检查字段类型数量
        required_types = condition.get("field_types", [])
        for req_type in required_types:
            if type_counts.get(req_type, 0) == 0:
                return None

        # ── cardinality 约束（样本值分析）─────────────────────────────
        if sample_data:
            for cond_key, cond_val in condition.items():
                if cond_key == "category_cardinality":
                    cat_fields = [f for f, t in field_types.items() if t in (FieldType.CATEGORY, FieldType.GEO)]
                    for cf in cat_fields:
                        vals = [row.get(cf) for row in sample_data if cf in row]
                        distinct = set(str(v) for v in vals if v is not None)
                        if cond_val.get("max") and len(distinct) > cond_val["max"]:
                            print(f"[S3] 规则跳过: {cf} 基数={len(distinct)} > max={cond_val['max']}")
                            return None
                        if cond_val.get("min") and len(distinct) < cond_val["min"]:
                            return None

        # ── 其他计数约束 ──────────────────────────────────────────────
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

        if "category_count" in condition:
            c_count = type_counts.get("category", 0) + type_counts.get("geo", 0)
            cond = condition["category_count"]
            if isinstance(cond, int):
                if c_count != cond:
                    return None
            elif isinstance(cond, dict):
                if cond.get("min") and c_count < cond["min"]:
                    return None
                if cond.get("max") and c_count > cond["max"]:
                    return None

        # keywords 语义条件校验
        keywords = condition.get("keywords")
        if keywords:
            hit = any(
                re.search(k, fname, re.IGNORECASE)
                for fname in field_types
                for k in (keywords if isinstance(keywords, (list, tuple)) else [keywords])
            )
            if not hit:
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
        # 完备的占位符替换：{field}/{number_field}/{number_field1}/{number_field2}
        # /{number_fields}/{category_field}/{category_field1}/{category_field2}/{date_field}/{geo_field}
        # 否则标题会残留未替换的占位符（如"总{field}""{number_field1} vs {number_field2}"）
        n0 = number_fields[0] if number_fields else None
        n1 = number_fields[1] if len(number_fields) > 1 else n0
        c0 = category_fields[0] if category_fields else None
        c1 = category_fields[1] if len(category_fields) > 1 else c0
        d0 = date_fields[0] if date_fields else None
        g0 = geo_fields[0] if geo_fields else None
        def _pick(v, fallback):
            return v if v is not None else fallback
        title = title.replace("{field}", _pick(n0, _pick(c0, "数值")))
        title = title.replace("{number_field}", _pick(n0, "数值"))
        title = title.replace("{number_field1}", _pick(n0, "数值A"))
        title = title.replace("{number_field2}", _pick(n1, _pick(n0, "数值B")))
        title = title.replace("{number_fields}", "+".join(number_fields[:3]) if number_fields else "指标")
        title = title.replace("{category_field1}", _pick(c0, "类别A"))
        title = title.replace("{category_field2}", _pick(c1, _pick(c0, "类别B")))
        title = title.replace("{category_field}", _pick(c0, "类别"))
        title = title.replace("{date_field}", _pick(d0, "日期"))
        title = title.replace("{geo_field}", _pick(g0, "地区"))
        
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
        max_charts: int = 5,
        field_types_override: Optional[Dict[str, FieldType]] = None
    ) -> List[ChartRecommendation]:
        """
        推荐图表
        
        Args:
            fields: 字段列表
            grain: 数据粒度 (detail/aggregate/macro)
            sample_data: 样本数据
            max_charts: 最大推荐数
            field_types_override: AI 语义标注融合后的字段类型，覆盖规则推断（默认为 None 用规则）
        
        Returns:
            图表推荐列表
        """
        # 分析字段类型：优先用 AI+规则 融合结果（down-grade 场景也能享受 AI 识别能力）
        field_types = field_types_override or FieldAnalyzer.analyze_fields(fields, sample_data)
        
        print(f"[S3] 字段分析: {field_types}")
        
        # 按优先级排序匹配规则
        recommendations = []

        for rule in sorted(self.rules, key=lambda x: x.get("priority", 0), reverse=True):
            rec = self._match_rule(rule, field_types, grain, sample_data)
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

            # 多分类维度时，让 bar/pie 轮流采用不同 category，避免所有图都只用同一个维度；
            # 无分类字段则退回日期/时间维度
            cat = (category_fields[len(result) % len(category_fields)]
                   if category_fields
                   else (date_fields[0] if date_fields else None))
            rec = ChartRecommendation(
                chart_type=chart_type,
                title=title,
                x_field=cat,
                y_field=number_fields[0] if number_fields else None,
                category_field=cat,
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
        sample_data: Optional[List[Dict]] = None,
        field_types_override: Optional[Dict[str, FieldType]] = None
    ) -> Dict[str, Any]:
        """
        生成看板配置 —— 按数据实际能力出图，不再硬塞固定数量

        field_types_override: AI+规则融合的字段类型（默认 None 用纯规则推断）
        """
        recommendations = self.recommend_charts(
            fields, grain, sample_data, max_charts=6,
            field_types_override=field_types_override
        )

        # 不再强制补到5张，按实际匹配结果返回
        # 但至少保证有一张明细表（数据可追溯）
        has_table = any(r.chart_type == "table" for r in recommendations)
        if not has_table and len(recommendations) > 0:
            n0 = fields[0] if fields else None
            recommendations.append(ChartRecommendation(
                chart_type="table",
                title=f"数据明细（前20行）",
                x_field=n0,
                y_field=n0,
                priority=10,
                rule_name="fallback_table",
                reason="自动补充分明细表"
            ))

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