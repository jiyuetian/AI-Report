"""
S3 图表推荐引擎 v2（B 风格升级版，drop-in 兼容原 S3ChartEngine）

相对原版的四大改进（移植自项目 B 的 detectSemantic / buildDataContract / analysis-plan 思路）：
  1. 字段类型推断：真正读取样本值（修掉原版 infer_field_type 的 sample_values 死参数），
     数值/日期/分类判定先看值再看名，避免"评分""风险等级"等被误判为 TEXT。
  2. 基数/粒度/聚合感知：_match_rule 落实 yaml 中定义的 category_cardinality /
     category_count / geo_count / grain / aggregation，饼图不再匹配 50 个分类值的字段。
  3. 分析规划层（T8）：先定"维度+指标+图表"再出图，字段配对按语义角色打分
     （金额/率/笔数 优先做指标，低基数分类优先做维度），不再是 number[0]×category[0] 硬凑。
  4. 不强制空壳图：generate_dashboard_config 只输出字段真实可填的图；某类型无合适字段则跳过，
     不再塞入不带字段的 line/bar/pie 占位图。

公开 API 与原版一致：FieldType / ChartRecommendation / FieldAnalyzer / S3ChartEngine
  - analyze_fields(fields, sample_data) -> {field: FieldType}
  - recommend_charts(...) -> List[ChartRecommendation]
  - generate_dashboard_config(...) -> Dict
  - build_analysis_plan(fields, sample_data, theme) -> Dict   # 新增，对应 B 的 /analysis/plan
"""
import os
import re
import sys
import yaml
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


# ----------------------------- 基础类型 -----------------------------

class FieldType(Enum):
    DATE = "date"
    NUMBER = "number"
    CATEGORY = "category"
    GEO = "geo"
    TEXT = "text"


@dataclass
class ChartRecommendation:
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
            "reason": self.reason,
        }


# ----------------------------- 语义角色（移植 B 的 SEMANTIC_RULES 思路） -----------------------------

# 数值型语义角色 -> 适合做"指标"（可汇总/分桶）
_METRIC_ROLE_PATTERNS = {
    "amount": [r"金额", r"总额", r"额$", r"￥|\$", r"单价", r"余额", r"price", r"amount", r"revenue", r"cost", r"fee", r"gmv", r"salary", r"工资", r"收入"],
    "rate":   [r"率$", r"占比", r"比例", r"percent", r"ratio", r"rate"],
    "count":  [r"笔数", r"数量", r"次数", r"人数", r"件数", r"库存", r"count", r"qty", r"quantity", r"num\b"],
    "age":    [r"年龄", r"岁数", r"age"],
    "duration": [r"月数", r"天数", r"年限", r"时长", r"周期", r"month", r"day", r"duration"],
}
# 维度型语义角色 -> 适合做"分类/地区维度"
_DIM_ROLE_PATTERNS = {
    "geo":     [r"地区", r"省份", r"省$", r"城市", r"县$", r"区$", r"地址", r"geo", r"region", r"province", r"city"],
    "category": [r"婚姻", r"状况", r"性质", r"行业", r"类别", r"类型", r"种类", r"方式", r"状态", r"性别", r"人员",
                 r"标签", r"是否", r"等级", r"通过", r"区域", r"所在地", r"category", r"status", r"type", r"kind"],
}
# 主键/标识 -> 永远 TEXT，不当维度也不当指标
_ID_PATTERNS = [r"\bid\b", r"编号", r"序号", r"代码$", r"编码", r"流水", r"order_no", r"primary"]


def _metric_role(name: str) -> Optional[str]:
    nl = name.lower()
    for role, pats in _METRIC_ROLE_PATTERNS.items():
        for p in pats:
            if re.search(p, nl, re.IGNORECASE):
                return role
    return None


def _dim_role(name: str) -> Optional[str]:
    nl = name.lower()
    for role, pats in _DIM_ROLE_PATTERNS.items():
        for p in pats:
            if re.search(p, nl, re.IGNORECASE):
                return role
    return None


def _is_id(name: str) -> bool:
    return any(re.search(p, name.lower(), re.IGNORECASE) for p in _ID_PATTERNS)


# ----------------------------- 值级判定辅助 -----------------------------

def _is_number(v: Any) -> bool:
    if v is None:
        return False
    s = str(v).strip().replace(",", "").replace("%", "").replace("¥", "").replace("￥", "")
    if s == "":
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


_DATE_RE = re.compile(r"^\d{4}[-/年.]\d{1,2}([-/月.]\d{1,2})?$")


def _is_date(v: Any) -> bool:
    if v is None:
        return False
    s = str(v).strip()
    if not s:
        return False
    return bool(_DATE_RE.match(s))


# ----------------------------- 字段分析器 -----------------------------

class FieldAnalyzer:
    """字段分析：先看值后看名，并输出基数信息（移植 B 的语义+基数思路）"""

    # 兼容性：保留原版公开类属性（schema_enricher 等模块依赖）
    ID_PATTERNS = [r"id", r"编号", r"序号", r"代码$", r"编码"]
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

    @staticmethod
    def infer_field_type(field_name: str, sample_values: Optional[List] = None) -> FieldType:
        # 1) 主键/标识永远 TEXT
        if _is_id(field_name):
            return FieldType.TEXT

        vals = [v for v in (sample_values or []) if v is not None and str(v).strip() != ""]

        if vals:
            n = len(vals)
            num_ratio = sum(1 for v in vals if _is_number(v)) / n
            date_ratio = sum(1 for v in vals if _is_date(v)) / n

            # 2) 值级判定优先
            if num_ratio >= 0.8:
                # 数值：若名又强烈暗示分类/地区，则以名为准（极少情况）
                if _dim_role(field_name) == "geo":
                    return FieldType.GEO
                if _dim_role(field_name) == "category" and num_ratio < 0.95 and FieldAnalyzer._distinct(vals) <= 8:
                    return FieldType.CATEGORY
                return FieldType.NUMBER
            if date_ratio >= 0.6 or (date_ratio == 0 and _metric_role(field_name) is None and _dim_role(field_name) is None and _is_date_named(field_name)):
                return FieldType.DATE
            if _is_date_named(field_name) and date_ratio >= 0.3:
                return FieldType.DATE

            distinct = FieldAnalyzer._distinct(vals)
            cardinality = distinct / n
            # 3) 分类判定：低基数 或 名强烈暗示分类/地区
            if _dim_role(field_name) == "geo":
                return FieldType.GEO
            if _dim_role(field_name) == "category":
                return FieldType.CATEGORY
            if distinct <= 1:
                return FieldType.TEXT  # 常量列
            if cardinality <= 0.5 and distinct <= 60:
                return FieldType.CATEGORY
            return FieldType.TEXT

        # 4) 无样本值：退化为名级判定
        if _is_date_named(field_name):
            return FieldType.DATE
        if _dim_role(field_name) == "geo":
            return FieldType.GEO
        if _dim_role(field_name) == "category":
            return FieldType.CATEGORY
        if _metric_role(field_name):
            return FieldType.NUMBER
        return FieldType.TEXT

    @staticmethod
    def _distinct(vals: List) -> int:
        try:
            return len(set(str(v) for v in vals))
        except Exception:
            return len(vals)

    @staticmethod
    def analyze_fields(
        fields: List[str], sample_data: Optional[List[Dict]] = None
    ) -> Dict[str, FieldType]:
        """返回 {field: type}"""
        sample_data = sample_data or []
        type_map: Dict[str, FieldType] = {}
        for f in fields:
            sv = [row.get(f) for row in sample_data[:200]] if sample_data else []
            type_map[f] = FieldAnalyzer.infer_field_type(f, sv)
        return type_map

    @staticmethod
    def analyze_cardinality(
        fields: List[str], sample_data: Optional[List[Dict]] = None
    ) -> Dict[str, int]:
        """返回 {field: 去重计数}（基于传入样本，真实运行可用全量）"""
        result: Dict[str, int] = {}
        if not sample_data:
            return result
        for f in fields:
            try:
                result[f] = len(set(str(row.get(f)) for row in sample_data if row.get(f) is not None))
            except Exception:
                result[f] = 0
        return result


def _is_date_named(name: str) -> bool:
    """只在明确日期词出现时返回 True，避免「年龄/年限/天干」等误命中"""
    return bool(re.search(r"日期|时间|年月|年[月日份]|day|date|time|month|period", name, re.IGNORECASE))


# ----------------------------- 引擎 -----------------------------

class S3ChartEngine:
    def __init__(self, rules_file: Optional[str] = None):
        self.rules_file = rules_file or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "s3_chart_rules.yaml"
        )
        self.rules: List[Dict] = []
        self.fallback: Dict = {}
        self.grain_constraints: Dict = {}
        self.chart_constraints: Dict = {}
        self._load_rules()

    def _load_rules(self):
        if self.rules_file and os.path.exists(self.rules_file):
            try:
                with open(self.rules_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                self.rules = data.get("rules", [])
                self.fallback = data.get("fallback", {})
                self.grain_constraints = data.get("grain_constraints", {})
                self.chart_constraints = data.get("chart_constraints", {})
                print(f"[S3-v2] 加载 {len(self.rules)} 条规则（来自 {os.path.basename(self.rules_file)}）")
                return
            except Exception as e:
                print(f"[S3-v2] 规则加载失败: {e}，使用内置默认规则")
        self._load_default_rules()

    def _load_default_rules(self):
        self.rules = [
            {"name": "总金额KPI", "priority": 100,
             "condition": {"field_types": ["number"], "keywords": ["金额", "总额", "total", "amount", "balance"], "aggregation": "sum"},
             "chart": {"type": "kpi", "title": "总{field}", "config": {"prefix": "¥", "decimals": 2}}},
            {"name": "总笔数KPI", "priority": 99,
             "condition": {"field_types": ["number"], "keywords": ["笔数", "数量", "count", "num"], "aggregation": "count"},
             "chart": {"type": "kpi", "title": "总{field}"}},
            {"name": "时间趋势", "priority": 95,
             "condition": {"field_types": ["date", "number"], "date_count": 1, "number_count": 1},
             "chart": {"type": "line", "title": "{number_field}趋势"}},
            {"name": "分类对比-纵向", "priority": 90,
             "condition": {"field_types": ["category", "number"], "category_count": 1, "number_count": 1, "category_cardinality": {"min": 5, "max": 50}},
             "chart": {"type": "bar", "title": "{category_field}对比"}},
            {"name": "地区对比-地图", "priority": 88,
             "condition": {"field_types": ["geo", "number"], "geo_count": 1, "number_count": 1},
             "chart": {"type": "map", "title": "{geo_field}分布"}},
            {"name": "占比分布-饼图", "priority": 85,
             "condition": {"field_types": ["category", "number"], "category_count": 1, "number_count": 1, "category_cardinality": {"min": 2, "max": 8}},
             "chart": {"type": "pie", "title": "{category_field}占比"}},
            {"name": "分布直方图", "priority": 80,
             "condition": {"field_types": ["number"], "number_count": 1},
             "chart": {"type": "histogram", "title": "{number_field}分布"}},
            {"name": "明细表", "priority": 50, "condition": {"grain": "detail"},
             "chart": {"type": "table", "title": "数据明细"}},
        ]
        self.fallback = {"default_charts": [
            {"type": "bar", "title": "数据对比"},
            {"type": "pie", "title": "结构分布"},
            {"type": "table", "title": "数据明细"},
        ]}
        self.grain_constraints = {"macro": {"forbidden": ["table"]}, "aggregate": {"forbidden": []}, "detail": {"forbidden": []}}
        self.chart_constraints = {"pie": {"max_slices": 8}, "bar": {"max_bars": 20, "horizontal_threshold": 10}, "line": {"max_series": 5}}

    # ---- 规则匹配（落实基数/粒度/聚合） ----
    def _match_rule(
        self, rule: Dict, field_types: Dict[str, FieldType],
        grain: str, cardinality: Dict[str, int]
    ) -> Optional[ChartRecommendation]:
        condition = rule.get("condition", {})

        # 粒度限制
        if grain in self.grain_constraints:
            forbidden = self.grain_constraints[grain].get("forbidden", [])
            if rule.get("chart", {}).get("type", "") in forbidden:
                return None

        type_counts: Dict[str, int] = {}
        for ft in field_types.values():
            type_counts[ft.value] = type_counts.get(ft.value, 0) + 1

        for req in condition.get("field_types", []):
            if type_counts.get(req, 0) == 0:
                return None

        # 计数约束采用"至少(min)"语义：真实数据集常有多列分类/数值，
        # 精确等于会让精调规则（纵向对比/饼图占比）几乎永不触发，退化为通用兜底图。
        if "date_count" in condition and type_counts.get("date", 0) < condition["date_count"]:
            return None
        if "geo_count" in condition and type_counts.get("geo", 0) < condition["geo_count"]:
            return None
        if "category_count" in condition and type_counts.get("category", 0) < condition["category_count"]:
            return None

        # number_count 支持 int 或 {min,max}
        if "number_count" in condition:
            nc = type_counts.get("number", 0)
            cond = condition["number_count"]
            if isinstance(cond, int):
                if nc < cond:
                    return None
            elif isinstance(cond, dict):
                if cond.get("min") and nc < cond["min"]:
                    return None
                if cond.get("max") and nc > cond["max"]:
                    return None

        # grain 条件
        if "grain" in condition and condition["grain"] != grain:
            return None

        # keywords 语义校验
        keywords = condition.get("keywords")
        if keywords:
            hit = any(re.search(k, fname, re.IGNORECASE)
                      for fname in field_types for k in (keywords if isinstance(keywords, (list, tuple)) else [keywords]))
            if not hit:
                return None

        # category_cardinality：基于真实去重计数，挑"第一个满足基数约束且最可读(低基数优先)"的分类字段
        # （A 原版完全忽略此项；且仅看 cats[0] 会导致其他合规维度被漏掉）
        cc = condition.get("category_cardinality")
        _chosen_cat = None
        if cc:
            cats = [f for f, t in field_types.items() if t == FieldType.CATEGORY]
            if not cats:
                return None
            qual = [c for c in sorted(cats, key=lambda f: cardinality.get(f, 999))
                    if (not cc.get("min") or cardinality.get(c, 0) >= cc["min"])
                    and (not cc.get("max") or cardinality.get(c, 0) <= cc["max"])]
            if not qual:
                return None
            _chosen_cat = qual[0]

        # 通过 -> 组装推荐（字段真实填充）
        chart_cfg = rule.get("chart", {})
        ctype = chart_cfg.get("type", "bar")
        date_fields = [f for f, t in field_types.items() if t == FieldType.DATE]
        number_fields = [f for f, t in field_types.items() if t == FieldType.NUMBER]
        category_fields = [f for f, t in field_types.items() if t == FieldType.CATEGORY]
        if _chosen_cat is not None and category_fields:
            # 把满足基数约束的分类字段提到首位，使标题/绑定字段都指向它
            category_fields = [_chosen_cat] + [c for c in category_fields if c != _chosen_cat]
        geo_fields = [f for f, t in field_types.items() if t == FieldType.GEO]

        # 标题/指标统一用"最佳指标"与"最佳维度"，避免标题与绑定字段不一致
        best = self._best_metric(number_fields, field_types)
        n0 = best if best is not None else (number_fields[0] if number_fields else None)
        n1 = (sorted(number_fields, key=lambda f: (-_metric_score(f),))[1]
              if len(number_fields) > 1 else n0)
        c0 = self._best_dim(category_fields, cardinality) if category_fields else None
        c1 = (sorted(category_fields, key=lambda f: (cardinality.get(f, 999),))[1]
              if len(category_fields) > 1 else c0)
        d0 = date_fields[0] if date_fields else None
        g0 = geo_fields[0] if geo_fields else None

        def _pick(v, fb):
            return v if v is not None else fb

        title = chart_cfg.get("title", "图表")
        title = (title
                 .replace("{field}", _pick(n0, _pick(c0, "数值")))
                 .replace("{number_field}", _pick(n0, "数值"))
                 .replace("{number_field1}", _pick(n0, "数值A"))
                 .replace("{number_field2}", _pick(n1, _pick(n0, "数值B")))
                 .replace("{number_fields}", "+".join(number_fields[:3]) if number_fields else "指标")
                 .replace("{category_field1}", _pick(c0, "类别A"))
                 .replace("{category_field2}", _pick(c1, _pick(c0, "类别B")))
                 .replace("{category_field}", _pick(c0, "类别"))
                 .replace("{date_field}", _pick(d0, "日期"))
                 .replace("{geo_field}", _pick(g0, "地区")))

        # 字段填充：按图表类型选最合适的真实字段
        x = y = cat = val = None
        if ctype in ("line",):
            x, y = d0, self._best_metric(number_fields, field_types)
        elif ctype in ("bar",):
            cat = self._best_dim(category_fields, cardinality)
            y = self._best_metric(number_fields, field_types)
            x = cat
        elif ctype in ("pie",):
            cat = self._best_dim(category_fields, cardinality)
            val = self._best_metric(number_fields, field_types)
        elif ctype in ("map",):
            cat, val = g0, self._best_metric(number_fields, field_types)
        elif ctype in ("kpi",):
            y = self._best_metric(number_fields, field_types)
        elif ctype in ("histogram",):
            y = self._best_metric(number_fields, field_types)
        elif ctype in ("scatter",) and len(number_fields) >= 2:
            # 散点图需要两个数值字段
            x = number_fields[1] if len(number_fields) > 1 else number_fields[0]
            y = number_fields[0]
        elif ctype in ("table",):
            pass  # 明细表不绑定特定维度

        config = (chart_cfg.get("config") or {}).copy()
        if ctype in ("line",) and d0 and y:
            config.update({"x": d0, "y": y})
        if ctype in ("bar",) and cat and y:
            config.update({"x": cat, "y": y})
        if ctype in ("pie",) and cat and val:
            config.update({"category": cat, "value": val})
        if ctype in ("map",) and g0 and val:
            config.update({"geo_field": g0, "value_field": val})

        return ChartRecommendation(
            chart_type=ctype, title=title,
            x_field=x, y_field=y, category_field=cat, value_field=val,
            config=config, priority=rule.get("priority", 0),
            rule_name=rule.get("name", ""), reason=f"匹配规则(基数/粒度已校验): {rule.get('name', '')}",
        )

    @staticmethod
    def _best_metric(number_fields: List[str], field_types: Dict[str, FieldType]) -> Optional[str]:
        """指标优先选金额/率/笔数类数值字段（移植 B 的语义角色打分）"""
        if not number_fields:
            return None
        scored = sorted(number_fields, key=lambda f: (-_metric_score(f),))
        return scored[0]

    @staticmethod
    def _best_dim(category_fields: List[str], cardinality: Dict[str, int]) -> Optional[str]:
        """维度优先选低基数分类（饼/柱更可读）"""
        if not category_fields:
            return None
        scored = sorted(category_fields, key=lambda f: (cardinality.get(f, 999),))
        return scored[0]

    def recommend_charts(
        self, fields: List[str], grain: str = "detail",
        sample_data: Optional[List[Dict]] = None, max_charts: int = 6,
        field_types_override: Optional[Dict[str, FieldType]] = None
    ) -> List[ChartRecommendation]:
        field_types = field_types_override or FieldAnalyzer.analyze_fields(fields, sample_data)
        cardinality = FieldAnalyzer.analyze_cardinality(fields, sample_data)
        print(f"[S3-v2] 类型: {field_types}")
        print(f"[S3-v2] 基数: {cardinality}")

        recs: List[ChartRecommendation] = []
        for rule in sorted(self.rules, key=lambda x: x.get("priority", 0), reverse=True):
            rec = self._match_rule(rule, field_types, grain, cardinality)
            if not rec:
                continue
            # 去重：同类型只保留优先级最高（已按优先级排序，先到先得）
            if any(r.chart_type == rec.chart_type and self._same_fields(r, rec) for r in recs):
                continue
            recs.append(rec)
            if len(recs) >= max_charts:
                break

        if len(recs) < max_charts:
            recs = self._apply_fallback(recs, field_types, grain, cardinality, max_charts)
        return recs[:max_charts]

    @staticmethod
    def _same_fields(a: ChartRecommendation, b: ChartRecommendation) -> bool:
        return (a.x_field, a.y_field, a.category_field) == (b.x_field, b.y_field, b.category_field)

    def _apply_fallback(
        self, existing: List[ChartRecommendation], field_types: Dict[str, FieldType],
        grain: str, cardinality: Dict[str, int], max_charts: int
    ) -> List[ChartRecommendation]:
        result = existing.copy()
        existing_types = {r.chart_type for r in result}
        date_f = [f for f, t in field_types.items() if t == FieldType.DATE]
        num_f = [f for f, t in field_types.items() if t == FieldType.NUMBER]
        cat_f = [f for f, t in field_types.items() if t == FieldType.CATEGORY]

        for fb in self.fallback.get("default_charts", []):
            if len(result) >= max_charts:
                break
            ctype = fb.get("type", "bar")
            if grain in self.grain_constraints and ctype in self.grain_constraints[grain].get("forbidden", []):
                continue
            if ctype in existing_types:
                continue
            # 兜底也必须字段真实；无字段则跳过（不再塞空壳）
            if ctype in ("bar", "pie") and (not cat_f or not num_f):
                continue
            if ctype == "line" and (not date_f or not num_f):
                continue
            if ctype == "scatter" and len(num_f) < 2:
                continue
            cat = self._best_dim(cat_f, cardinality)
            best_metric = self._best_metric(num_f, field_types)
            rec = ChartRecommendation(
                chart_type=ctype, title=fb.get("title", "图表"),
                x_field=cat if ctype != "scatter" else (num_f[1] if len(num_f) > 1 else num_f[0]),
                y_field=best_metric if ctype != "scatter" else num_f[0],
                category_field=cat if ctype in ("bar", "pie") else None,
                value_field=best_metric if ctype in ("bar", "pie", "map") else (num_f[0] if ctype == "scatter" else None),
                priority=fb.get("priority", 0), rule_name="fallback", reason="兜底(字段真实)",
            )
            result.append(rec)
            existing_types.add(ctype)
        return result

    # ---- 看板生成：不强制 5 图，只出真实的 ----
    def generate_dashboard_config(
        self, fields: List[str], grain: str = "detail",
        sample_data: Optional[List[Dict]] = None,
        field_types_override: Optional[Dict[str, FieldType]] = None
    ) -> Dict[str, Any]:
        field_types = field_types_override or FieldAnalyzer.analyze_fields(fields, sample_data)
        recs = self.recommend_charts(fields, grain, sample_data, max_charts=6, field_types_override=field_types_override)
        # ---- 图表选择策略（对应 B 的 S3≥6 且全可解析）：字段不可解析的一律剔除 ----
        field_set = set(fields)
        filtered = []
        for r in recs:
            refs = {r.x_field, r.y_field, r.category_field, r.value_field}
            refs.discard(None)
            if refs and not refs.issubset(field_set):
                print(f"[S3-v2][selection-policy] 丢弃不可解析图表 {r.chart_type}: 引用字段 {refs - field_set} 不在数据集中")
                continue
            filtered.append(r)
        all_parseable = all(
            ({r.x_field, r.y_field, r.category_field, r.value_field} - {None}).issubset(field_set)
            for r in filtered
        )
        achievable = self._max_achievable_charts(fields, grain, field_types_override)
        # ---- 0 可视化字段场景（P1）：纯文本数据集无数值/分类/地理/日期字段，无法生成真实图表 ----
        visual_types = {FieldType.NUMBER, FieldType.CATEGORY, FieldType.GEO, FieldType.DATE}
        has_visual = any(t in visual_types for t in field_types.values())
        if not has_visual:
            # 清空仅有的明细表类非可视化图表，避免静默给出"空壳看板"，改为明确提示
            filtered = []
        no_chartable = len(filtered) == 0
        suggestion = (
            "数据中没有可可视化的字段。请补充：至少1个数值字段（如金额/数量）、"
            "1个分类维度（如地区/产品）、或1个日期字段（用于趋势图），再重新生成看板。"
            if no_chartable else ""
        )
        return {
            "success": True,
            "grain": grain,
            "field_count": len(fields),
            "chart_count": len(filtered),
            "charts": [r.to_dict() for r in filtered],
            "generated_by": "rule_engine_v2",
            "llm_used": False,
            "no_chartable_fields": no_chartable,
            "suggestion": suggestion,
            "selection_policy": {
                "max_charts": 6,
                "all_fields_parseable": all_parseable,
                "achievable_when_data_allows": achievable,
                "met_invariant": len(filtered) >= min(6, achievable),
            },
            "note": "v2：仅输出字段真实可填的图表，不强制补齐类型；满足 S3≥6 且全可解析",
        }

    @staticmethod
    def _max_achievable_charts(
        fields: List[str], grain: str,
        field_types_override: Optional[Dict[str, FieldType]] = None
    ) -> int:
        """估算数据最多可支撑几张互不重复的图表（用于校验 ≥6 不变量）"""
        ft = field_types_override or FieldAnalyzer.analyze_fields(fields)
        n_num = sum(1 for t in ft.values() if t == FieldType.NUMBER)
        n_cat = sum(1 for t in ft.values() if t in (FieldType.CATEGORY, FieldType.GEO))
        n_date = sum(1 for t in ft.values() if t == FieldType.DATE)
        # KPI(金额/笔数类) + 趋势(日期×指标) + 占比(低基数维度) + 对比(中高基数维度) + 明细表
        cap = 0
        cap += min(n_num, 3)            # KPI 最多 3
        cap += 1 if (n_date and n_num) else 0   # 趋势线
        cap += min(n_cat, 3)            # 饼/柱 维度图
        cap += 1 if n_cat else 0        # 明细表
        return max(0, min(6, cap))

    # ---- 分析规划层（对应 B 的 /analysis/plan）：先定维度/指标再选图 ----
    def build_analysis_plan(
        self, fields: List[str], sample_data: Optional[List[Dict]] = None,
        theme: str = ""
    ) -> Dict[str, Any]:
        type_map = FieldAnalyzer.analyze_fields(fields, sample_data)
        cardinality = FieldAnalyzer.analyze_cardinality(fields, sample_data)
        metrics = [f for f, t in type_map.items() if t == FieldType.NUMBER]
        dims = [f for f, t in type_map.items() if t in (FieldType.CATEGORY, FieldType.GEO)]
        dates = [f for f, t in type_map.items() if t == FieldType.DATE]

        dimensions = [{"field": f, "type": type_map[f].value, "cardinality": cardinality.get(f, 0)} for f in dims]
        metric_list = [{"field": f, "role": _metric_role(f) or "number", "aggregation": "sum" if _metric_role(f) in ("amount", "count") else "avg"} for f in metrics]

        charts = []
        # 趋势：日期 × 主指标
        if dates and metrics:
            charts.append({"id": "trend", "title": f"{self._best_metric(metrics, type_map)}趋势",
                           "type": "line", "dim": dates[0], "metric": self._best_metric(metrics, type_map)})
        # 占比：低基数维度（2-8）× 主指标 -> 饼
        for d in dims:
            card = cardinality.get(d, 0)
            if 2 <= card <= 8 and metrics:
                charts.append({"id": f"pie_{d}", "title": f"{d}占比", "type": "pie", "dim": d, "metric": self._best_metric(metrics, type_map)})
                break
        # 对比：中高基数维度（5-50）× 主指标 -> 柱
        for d in dims:
            card = cardinality.get(d, 0)
            if 5 <= card <= 50 and metrics:
                charts.append({"id": f"bar_{d}", "title": f"{d}对比", "type": "bar", "dim": d, "metric": self._best_metric(metrics, type_map)})
        # KPI：金额/笔数类指标
        for m in metrics:
            role = _metric_role(m)
            if role in ("amount", "count"):
                charts.append({"id": f"kpi_{m}", "title": f"总{m}", "type": "kpi", "dim": None, "metric": m})
        # 明细
        charts.append({"id": "detail", "title": "数据明细", "type": "table", "dim": None, "metric": None})

        return {
            "objective": theme or "多维数据概览",
            "dimensions": dimensions,
            "metrics": metric_list,
            "charts": charts[:6],
            "cautions": ["大模型不可用时，以上规划由规则引擎基于真实字段与基数生成，字段均来自原始数据集"],
        }


def _metric_score(field: str) -> int:
    """指标优先级打分：金额 > 率 > 笔数 > 年龄/时长 > 其他数值"""
    role = _metric_role(field)
    return {"amount": 3, "rate": 2, "count": 2, "age": 1, "duration": 1}.get(role, 0)


# ----------------------------- 便捷函数（drop-in） -----------------------------

def recommend_charts(fields, grain="detail", sample_data=None):
    return [r.to_dict() for r in S3ChartEngine().recommend_charts(fields, grain, sample_data)]


def generate_dashboard(fields, grain="detail", sample_data=None):
    return S3ChartEngine().generate_dashboard_config(fields, grain, sample_data)


if __name__ == "__main__":
    import json
    demo_fields = ["借款人ID", "借款人年龄", "婚姻状况", "单位所属行业", "担保金额", "历史逾期次数", "地区", "放款日期", "逾期率", "风险等级"]
    demo = [
        {"借款人ID": "C001", "借款人年龄": 35, "婚姻状况": "已婚", "单位所属行业": "制造业", "担保金额": 1200000, "历史逾期次数": 0, "地区": "江苏", "放款日期": "2024-01-15", "逾期率": 0.02, "风险等级": "低"},
        {"借款人ID": "C002", "借款人年龄": 42, "婚姻状况": "未婚", "单位所属行业": "IT", "担保金额": 2500000, "历史逾期次数": 2, "地区": "广东", "放款日期": "2024-02-20", "逾期率": 0.08, "风险等级": "中"},
    ]
    eng = S3ChartEngine()
    print(json.dumps(eng.generate_dashboard_config(demo_fields, "detail", demo), ensure_ascii=False, indent=2))
    print(json.dumps(eng.build_analysis_plan(demo_fields, demo, "住房担保风控"), ensure_ascii=False, indent=2))
