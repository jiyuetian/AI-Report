"""
派生指标注册表（night15-16 Task H：派生指标完整版）

目标：用「确定性业务指标注册表」替代 derived_metric_service 的「跨列反推」思路，
显式定义 14 个业务指标（财务 5 / 风控 4 / 业务 3 / 其他 2）的名称、计算公式、
字段映射（含中文/英文别名）、数据来源，支持实时计算 + 轻量缓存 + 对比/趋势/解释。

设计约束（与 Task G 一致）：
- 纯计算，不碰任何 DB；数据由调用方显式以 dict 形式提供（字段→数值），
  满足红线④「不碰生产 DuckDB」。AI 查询时由调用层负责把字段值解析好再传入。
- 计算是确定性事实（非 LLM 猜），必须可验证；除零/缺字段一律返回明确 error，诚实不编造。
- 缓存为进程内轻量 LRU（容量上限 + TTL），仅加速重复查询，不影响正确性。

使用：
    from app.core.metric_registry import MetricRegistry, METRIC_REGISTRY
    res = METRIC_REGISTRY.calculate("gross_margin", {"收入": 1000, "成本": 600})
    res = METRIC_REGISTRY.calculate("gross_margin", {...}, operation="explain")
    # 对比：多期字段值
    res = METRIC_REGISTRY.calculate("不良率", {"periods":[{"period":"Q1","values":{"不良金额":50,"总贷款余额":1000}}, ...]}, operation="compare")
    # 趋势：历史序列 + 预测 horizon
    res = METRIC_REGISTRY.calculate("客户增长率", {"history":[{"period":"1月","values":{...}}, ...], "horizon":3}, operation="trend")
"""

from typing import Dict, Any, Optional, List
import time


class BaseMetric:
    """指标基类。子类只填类属性 + 实现 _compute（返回数值或 None）。"""

    key: str = ""                  # 英文唯一键
    name_zh: str = ""              # 中文名
    category: str = "other"        # financial / risk / business / other
    formula_zh: str = ""           # 中文公式（展示用）
    formula_expr: str = ""         # 表达式（展示用）
    unit: str = "%"                # 展示单位（比率类 %；交易量等用具体单位）
    aggregation: str = "ratio"      # ratio（比率，安全聚合 avg）/ sum（合计）/ value（单值）
    data_source: str = ""          # 数据来源说明
    description: str = ""           # 指标含义说明
    required_fields: List[str] = []  # 规范字段名（canonical）
    field_aliases: Dict[str, List[str]] = {}  # 规范字段 → 别名（中文/英文/snake）

    def _get(self, data: Dict[str, Any], name: str) -> float:
        """在 data 里按规范名或任意别名解析数值（大小写/空白不敏感）。"""
        candidates = [name] + list(self.field_aliases.get(name, []))
        # 精确匹配
        for c in candidates:
            if c in data and data[c] is not None:
                return float(data[c])
        # 大小写/空白不敏感匹配
        low = {str(k).strip().lower(): k for k in data if k is not None}
        for c in candidates:
            k = str(c).strip().lower()
            if k in low:
                v = data[low[k]]
                if v is not None:
                    return float(v)
        raise KeyError(name)

    def _compute(self, v: Dict[str, float]) -> Optional[float]:
        """由各指标实现：返回数值；除零/非法返回 None。"""
        raise NotImplementedError

    def calculate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """单期计算。返回统一结构；缺字段/除零 → success=False + 明确 error。"""
        resolved: Dict[str, float] = {}
        for f in self.required_fields:
            try:
                resolved[f] = self._get(data, f)
            except KeyError:
                return {
                    "success": False,
                    "metric": self.key,
                    "name": self.name_zh,
                    "error": f"缺少必需字段「{f}」或其别名（已配置别名：{self.field_aliases.get(f, [])}）",
                    "missing_field": f,
                }
        try:
            val = self._compute(resolved)
        except ZeroDivisionError:
            denom = self._denominator_field()
            return {
                "success": False,
                "metric": self.key,
                "name": self.name_zh,
                "error": f"计算「{self.name_zh}」时分母字段为 0，无法计算（公式：{self.formula_zh}）",
                "div_by_zero": denom,
            }
        if val is None or not _is_finite(val):
            return {
                "success": False,
                "metric": self.key,
                "name": self.name_zh,
                "error": f"计算「{self.name_zh}」结果非法（None/NaN/Inf），无法返回",
            }
        return {
            "success": True,
            "metric": self.key,
            "name": self.name_zh,
            "category": self.category,
            "value": round(val, 2),
            "raw_value": val,
            "unit": self.unit,
            "formula": self.formula_zh,
            "formula_expr": self.formula_expr,
            "fields": resolved,
            "aggregation": self.aggregation,
            "data_source": self.data_source,
            "explanation": self.explain(),
        }

    def _denominator_field(self) -> Optional[str]:
        """子类可覆写：返回公式的分母字段（用于除零报错定位）。默认 None。"""
        return None

    def explain(self) -> Dict[str, Any]:
        """结构化解释：公式、字段（含别名）、数据来源、含义。"""
        fields_desc = []
        for f in self.required_fields:
            fields_desc.append({
                "field": f,
                "aliases": self.field_aliases.get(f, []),
                "role": "分母" if f == self._denominator_field() else "分子/输入",
            })
        return {
            "metric": self.key,
            "name": self.name_zh,
            "category": self.category,
            "formula": self.formula_zh,
            "formula_expr": self.formula_expr,
            "unit": self.unit,
            "aggregation": self.aggregation,
            "data_source": self.data_source,
            "description": self.description,
            "fields": fields_desc,
        }


def _is_finite(x: float) -> bool:
    return x == x and x not in (float("inf"), float("-inf"))


# =========================================================================
# 财务指标（5）
# =========================================================================

class ROIMetric(BaseMetric):
    key = "roi"
    name_zh = "投资回报率(ROI)"
    category = "financial"
    formula_zh = "ROI = (收益 − 成本) ÷ 成本 × 100%"
    formula_expr = "(revenue - cost) / cost * 100"
    unit = "%"
    aggregation = "ratio"
    data_source = "财务数据集（收益/成本科目）"
    description = "衡量投资获利能力：净收益相对投入成本的比例，越高越好。"
    required_fields = ["revenue", "cost"]
    field_aliases = {
        "revenue": ["收益", "收入", "revenue", "income", "profit_revenue"],
        "cost": ["成本", "cost", "expense", "total_cost"],
    }

    def _compute(self, v):
        return (v["revenue"] - v["cost"]) / v["cost"] * 100

    def _denominator_field(self):
        return "cost"


class ROEMetric(BaseMetric):
    key = "roe"
    name_zh = "净资产收益率(ROE)"
    category = "financial"
    formula_zh = "ROE = 净利润 ÷ 净资产 × 100%"
    formula_expr = "net_profit / equity * 100"
    unit = "%"
    aggregation = "ratio"
    data_source = "财务数据集（利润表 + 权益表）"
    description = "衡量股东投入资本的回报水平，反映企业自有资本获利能力。"
    required_fields = ["net_profit", "equity"]
    field_aliases = {
        "net_profit": ["净利润", "net_profit", "np"],
        "equity": ["净资产", "equity", "net_assets", "owners_equity"],
    }

    def _compute(self, v):
        return v["net_profit"] / v["equity"] * 100

    def _denominator_field(self):
        return "equity"


class GrossMarginMetric(BaseMetric):
    key = "gross_margin"
    name_zh = "毛利率"
    category = "financial"
    formula_zh = "毛利率 = (收入 − 成本) ÷ 收入 × 100%"
    formula_expr = "(revenue - cost) / revenue * 100"
    unit = "%"
    aggregation = "ratio"
    data_source = "财务数据集（收入/成本科目）"
    description = "反映产品或服务本身的盈利空间，扣除期间费用前的毛利水平。"
    required_fields = ["revenue", "cost"]
    field_aliases = {
        "revenue": ["收入", "营收", "revenue", "income", "sales"],
        "cost": ["成本", "cost", "cogs", "total_cost"],
    }

    def _compute(self, v):
        return (v["revenue"] - v["cost"]) / v["revenue"] * 100

    def _denominator_field(self):
        return "revenue"


class NetMarginMetric(BaseMetric):
    key = "net_margin"
    name_zh = "净利率"
    category = "financial"
    formula_zh = "净利率 = 净利润 ÷ 收入 × 100%"
    formula_expr = "net_profit / revenue * 100"
    unit = "%"
    aggregation = "ratio"
    data_source = "财务数据集（利润表）"
    description = "扣除全部成本费用后的最终盈利能力，反映收入转化为净利润的效率。"
    required_fields = ["net_profit", "revenue"]
    field_aliases = {
        "net_profit": ["净利润", "net_profit", "np"],
        "revenue": ["收入", "营收", "revenue", "income", "sales"],
    }

    def _compute(self, v):
        return v["net_profit"] / v["revenue"] * 100

    def _denominator_field(self):
        return "revenue"


class EbitdaMarginMetric(BaseMetric):
    key = "ebitda_margin"
    name_zh = "EBITDA利润率"
    category = "financial"
    formula_zh = "EBITDA利润率 = EBITDA ÷ 收入 × 100%"
    formula_expr = "ebitda / revenue * 100"
    unit = "%"
    aggregation = "ratio"
    data_source = "财务数据集（息税折旧摊销前利润口径）"
    description = "剔除资本结构/税负/折旧影响的经营性盈利水平，便于跨企业可比。"
    required_fields = ["ebitda", "revenue"]
    field_aliases = {
        "ebitda": ["ebitda", "EBITDA", "息税折旧摊销前利润"],
        "revenue": ["收入", "营收", "revenue", "income", "sales"],
    }

    def _compute(self, v):
        return v["ebitda"] / v["revenue"] * 100

    def _denominator_field(self):
        return "revenue"


# =========================================================================
# 风控指标（4）
# =========================================================================

class NonPerformingRateMetric(BaseMetric):
    key = "non_performing_rate"
    name_zh = "不良率"
    category = "risk"
    formula_zh = "不良率 = 不良金额 ÷ 总贷款余额 × 100%"
    formula_expr = "npl_amount / loan_balance * 100"
    unit = "%"
    aggregation = "ratio"
    data_source = "风控资产表（贷款台账）"
    description = "反映信贷资产质量：不良贷款占总贷款余额的比例，越低越好。"
    required_fields = ["npl_amount", "loan_balance"]
    field_aliases = {
        "npl_amount": ["不良金额", "npl_amount", "npl", "bad_loan_amount"],
        "loan_balance": ["总贷款余额", "贷款余额", "loan_balance", "total_loan_balance"],
    }

    def _compute(self, v):
        return v["npl_amount"] / v["loan_balance"] * 100

    def _denominator_field(self):
        return "loan_balance"


class ProvisionCoverageMetric(BaseMetric):
    key = "provision_coverage"
    name_zh = "拨备覆盖率"
    category = "risk"
    formula_zh = "拨备覆盖率 = 拨备余额 ÷ 不良金额 × 100%"
    formula_expr = "provision_balance / npl_amount * 100"
    unit = "%"
    aggregation = "ratio"
    data_source = "风控资产表（拨备计提）"
    description = "反映对不良贷款的损失缓冲能力，越高抗风险能力越强（监管有下限要求）。"
    required_fields = ["provision_balance", "npl_amount"]
    field_aliases = {
        "provision_balance": ["拨备余额", "provision_balance", "provision"],
        "npl_amount": ["不良金额", "npl_amount", "npl", "bad_loan_amount"],
    }

    def _compute(self, v):
        return v["provision_balance"] / v["npl_amount"] * 100

    def _denominator_field(self):

        return "npl_amount"


class CapitalAdequacyMetric(BaseMetric):
    key = "capital_adequacy"
    name_zh = "资本充足率"
    category = "risk"
    formula_zh = "资本充足率 = (核心资本 + 附属资本) ÷ 风险加权资产 × 100%"
    formula_expr = "(tier1_capital + tier2_capital) / rwa * 100"
    unit = "%"
    aggregation = "ratio"
    data_source = "风控资本表（资本充足率报表）"
    description = "反映机构以资本抵御风险的能力，监管核心红线指标（商业银行≥10.5% 等）。"
    required_fields = ["tier1_capital", "tier2_capital", "rwa"]
    field_aliases = {
        "tier1_capital": ["核心资本", "tier1_capital", "core_capital", "一级资本"],
        "tier2_capital": ["附属资本", "tier2_capital", "supplementary_capital", "二级资本"],
        "rwa": ["风险加权资产", "rwa", "risk_weighted_assets"],
    }

    def _compute(self, v):
        return (v["tier1_capital"] + v["tier2_capital"]) / v["rwa"] * 100

    def _denominator_field(self):
        return "rwa"


class LiquidityRatioMetric(BaseMetric):
    key = "liquidity_ratio"
    name_zh = "流动性比率"
    category = "risk"
    formula_zh = "流动性比率 = 流动资产 ÷ 流动负债 × 100%"
    formula_expr = "current_assets / current_liabilities * 100"
    unit = "%"
    aggregation = "ratio"
    data_source = "风控流动性表（资产负债期限结构）"
    description = "反映短期偿债能力：流动资产覆盖流动负债的程度，监管通常≥25%。"
    required_fields = ["current_assets", "current_liabilities"]
    field_aliases = {
        "current_assets": ["流动资产", "current_assets", "ca"],
        "current_liabilities": ["流动负债", "current_liabilities", "cl"],
    }

    def _compute(self, v):
        return v["current_assets"] / v["current_liabilities"] * 100

    def _denominator_field(self):
        return "current_liabilities"


# =========================================================================
# 业务指标（3）
# =========================================================================

class CustomerGrowthRateMetric(BaseMetric):
    key = "customer_growth_rate"
    name_zh = "客户增长率"
    category = "business"
    formula_zh = "客户增长率 = (本期客户数 − 上期客户数) ÷ 上期客户数 × 100%"
    formula_expr = "(customers_current - customers_prev) / customers_prev * 100"
    unit = "%"
    aggregation = "ratio"
    data_source = "业务数据集（客户主表，按周期统计）"
    description = "反映客户规模扩张速度，是业务增长的核心先行指标。"
    required_fields = ["customers_current", "customers_prev"]
    field_aliases = {
        "customers_current": ["本期客户数", "客户数", "customers_current", "cur_customers"],
        "customers_prev": ["上期客户数", "customers_prev", "prev_customers"],
    }

    def _compute(self, v):
        return (v["customers_current"] - v["customers_prev"]) / v["customers_prev"] * 100

    def _denominator_field(self):
        return "customers_prev"


class TransactionVolumeMetric(BaseMetric):
    key = "transaction_volume"
    name_zh = "交易量"
    category = "business"
    formula_zh = "交易量 = 本期交易总额（合计）"
    formula_expr = "sum(transaction_amount)"
    unit = "元"
    aggregation = "sum"
    data_source = "业务数据集（交易流水表，按周期汇总）"
    description = "周期内交易总金额，衡量业务规模与活跃度（非比率，安全聚合为求和）。"
    required_fields = ["transaction_amount"]
    field_aliases = {
        "transaction_amount": ["交易总额", "transaction_amount", "total_amount", "gmv"],
    }

    def _compute(self, v):
        return v["transaction_amount"]


class AvgOrderValueMetric(BaseMetric):
    key = "avg_order_value"
    name_zh = "客单价"
    category = "business"
    formula_zh = "客单价 = 交易总额 ÷ 交易笔数"
    formula_expr = "transaction_amount / transaction_count"
    unit = "元"
    aggregation = "value"
    data_source = "业务数据集（交易流水表）"
    description = "单笔交易平均金额，反映客户消费水平与变现效率。"
    required_fields = ["transaction_amount", "transaction_count"]
    field_aliases = {
        "transaction_amount": ["交易总额", "transaction_amount", "total_amount", "gmv"],
        "transaction_count": ["交易笔数", "transaction_count", "order_count", "orders"],
    }

    def _compute(self, v):
        return v["transaction_amount"] / v["transaction_count"]

    def _denominator_field(self):
        return "transaction_count"


# =========================================================================
# 其他指标（2）
# =========================================================================

class RepurchaseRateMetric(BaseMetric):
    key = "repurchase_rate"
    name_zh = "复购率"
    category = "other"
    formula_zh = "复购率 = 回头客数量 ÷ 总客户数 × 100%"
    formula_expr = "repeat_customers / total_customers * 100"
    unit = "%"
    aggregation = "ratio"
    data_source = "业务数据集（客户行为表）"
    description = "反映客户忠诚度与留存质量：周期内产生复购的客户占比。"
    required_fields = ["repeat_customers", "total_customers"]
    field_aliases = {
        "repeat_customers": ["回头客数量", "复购客户", "repeat_customers", "returning_customers"],
        "total_customers": ["总客户数", "total_customers", "all_customers"],
    }

    def _compute(self, v):
        return v["repeat_customers"] / v["total_customers"] * 100

    def _denominator_field(self):
        return "total_customers"


class MarketShareMetric(BaseMetric):
    key = "market_share"
    name_zh = "市场份额"
    category = "other"
    formula_zh = "市场份额 = 本公司销售额 ÷ 行业总销售额 × 100%"
    formula_expr = "company_sales / industry_sales * 100"
    unit = "%"
    aggregation = "ratio"
    data_source = "业务数据集 + 行业公开/对标数据"
    description = "反映企业在行业中的竞争地位，本公司销售额占行业总盘子的比例。"
    required_fields = ["company_sales", "industry_sales"]
    field_aliases = {
        "company_sales": ["本公司销售额", "company_sales", "our_sales"],
        "industry_sales": ["行业总销售额", "industry_sales", "market_total"],
    }

    def _compute(self, v):
        return v["company_sales"] / v["industry_sales"] * 100

    def _denominator_field(self):
        return "industry_sales"


# =========================================================================
# 注册表
# =========================================================================

class MetricRegistry:
    """指标注册表：单期计算 / 对比 / 趋势 / 解释 + 轻量缓存。"""

    _CACHE_MAX = 128
    _CACHE_TTL = 60.0  # 秒

    def __init__(self):
        self._metrics: Dict[str, BaseMetric] = {}
        self._alias_map: Dict[str, str] = {}   # 小写别名/键 → 规范 key
        for _m in (
            ROIMetric(), ROEMetric(), GrossMarginMetric(), NetMarginMetric(), EbitdaMarginMetric(),
            NonPerformingRateMetric(), ProvisionCoverageMetric(), CapitalAdequacyMetric(), LiquidityRatioMetric(),
            CustomerGrowthRateMetric(), TransactionVolumeMetric(), AvgOrderValueMetric(),
            RepurchaseRateMetric(), MarketShareMetric(),
        ):
            self._metrics[_m.key] = _m
            self._alias_map[_m.key.lower()] = _m.key
            self._alias_map[_m.name_zh.lower()] = _m.key
            for _f in _m.required_fields:
                self._alias_map[_f.lower()] = _m.key
            for _al in _m.field_aliases.values():
                for _a in _al:
                    self._alias_map[_a.lower()] = _m.key
        self._cache: Dict[str, Any] = {}

    # ---- 解析 ----
    def resolve_key(self, name: str) -> Optional[str]:
        """把中文名/英文键/别名解析成规范 key。"""
        if name is None:
            return None
        return self._alias_map.get(str(name).strip().lower())

    def list_metrics(self) -> List[Dict[str, Any]]:
        """列出全部指标元信息（给前端/接口用）。"""
        out = []
        for _m in self._metrics.values():
            out.append({
                "key": _m.key,
                "name": _m.name_zh,
                "category": _m.category,
                "formula": _m.formula_zh,
                "formula_expr": _m.formula_expr,
                "unit": _m.unit,
                "aggregation": _m.aggregation,
                "data_source": _m.data_source,
                "description": _m.description,
                "fields": [
                    {"field": f, "aliases": _m.field_aliases.get(f, [])}
                    for f in _m.required_fields
                ],
            })
        return out

    def get_metric(self, name: str) -> Optional[BaseMetric]:
        key = self.resolve_key(name)
        return self._metrics.get(key) if key else None

    # ---- 缓存 ----
    def _cache_get(self, ck: str) -> Optional[Any]:
        item = self._cache.get(ck)
        if not item:
            return None
        ts, val = item
        if time.time() - ts > self._CACHE_TTL:
            self._cache.pop(ck, None)
            return None
        return val

    def _cache_set(self, ck: str, val: Any) -> None:
        if len(self._cache) >= self._CACHE_MAX:
            # 简单 FIFO 淘汰：弹最旧
            try:
                self._cache.pop(next(iter(self._cache)))
            except StopIteration:
                pass
        self._cache[ck] = (time.time(), val)

    # ---- 计算入口 ----
    def calculate(
        self,
        metric_name: str,
        data: Dict[str, Any],
        operation: str = "query",
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """统一计算入口。

        operation:
          - "query"  ：单期计算（data 为字段值 dict）
          - "explain"：仅返回公式/字段/来源说明
          - "compare"：多期对比（data["periods"]=[{period, values}]）
          - "trend"  ：历史趋势预测（data["history"]=[{period, values}] + data["horizon"]）
        """
        metric = self.get_metric(metric_name)
        if not metric:
            return {
                "success": False,
                "metric": metric_name,
                "error": f"未找到指标「{metric_name}」；可用指标：{list(self._metrics.keys())}",
            }
        if operation == "explain":
            return {"success": True, "operation": "explain", **metric.explain()}

        if operation == "compare":
            return self._compare(metric, data, use_cache)
        if operation == "trend":
            return self._trend(metric, data, use_cache)

        # query（默认）
        ck = f"q:{metric.key}:{_hash_data(data)}" if use_cache else None
        if ck:
            hit = self._cache_get(ck)
            if hit is not None:
                return hit
        res = metric.calculate(data)
        if ck and res.get("success"):
            self._cache_set(ck, res)
        return res

    def _compare(self, metric: BaseMetric, data: Dict[str, Any], use_cache: bool) -> Dict[str, Any]:
        periods = data.get("periods") or []
        if not periods:
            return {"success": False, "metric": metric.key, "error": "对比分析需提供 periods（[{period, values}]）"}
        series = []
        for p in periods:
            r = metric.calculate(p.get("values") or {})
            series.append({
                "period": p.get("period"),
                "success": r.get("success"),
                "value": r.get("value") if r.get("success") else None,
                "error": r.get("error"),
            })
        vals = [s["value"] for s in series if s["success"] and s["value"] is not None]
        delta_pct = None
        if len(vals) >= 2 and vals[0] != 0:
            delta_pct = round((vals[-1] - vals[0]) / abs(vals[0]) * 100, 2)
        return {
            "success": True,
            "operation": "compare",
            "metric": metric.key,
            "name": metric.name_zh,
            "unit": metric.unit,
            "formula": metric.formula_zh,
            "series": series,
            "delta_pct": delta_pct,
            "message": f"{metric.name_zh} 共对比 {len(periods)} 期，首尾变化 {delta_pct}%",
        }

    def _trend(self, metric: BaseMetric, data: Dict[str, Any], use_cache: bool) -> Dict[str, Any]:
        history = data.get("history") or []
        horizon = int(data.get("horizon") or 3)
        if len(history) < 2:
            return {"success": False, "metric": metric.key,
                    "error": "趋势预测需至少 2 期 history（[{period, values}]）"}
        hist_series = []
        for h in history:
            r = metric.calculate(h.get("values") or {})
            if not r.get("success"):
                return {"success": False, "metric": metric.key,
                        "error": f"历史期「{h.get('period')}」计算失败：{r.get('error')}"}
            hist_series.append({"period": h.get("period"), "value": r["value"]})
        # 最小二乘线性拟合（确定性、可解释）
        n = len(hist_series)
        xs = list(range(n))
        ys = [s["value"] for s in hist_series]
        mx = sum(xs) / n
        my = sum(ys) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        if sxx == 0:
            slope = 0.0
        else:
            slope = sxy / sxx
        intercept = my - slope * mx
        forecast = []
        for i in range(1, horizon + 1):
            idx = n - 1 + i
            fv = intercept + slope * idx
            forecast.append({
                "period": f"T+{i}",
                "value": round(fv, 2),
                "is_forecast": True,
            })
        return {
            "success": True,
            "operation": "trend",
            "metric": metric.key,
            "name": metric.name_zh,
            "unit": metric.unit,
            "formula": metric.formula_zh,
            "method": "linear_least_squares",
            "slope": round(slope, 4),
            "history": hist_series,
            "forecast": forecast,
            "message": f"{metric.name_zh} 线性最小二乘外推未来 {horizon} 期（斜率 {round(slope, 4)}）",
        }


def _hash_data(data: Dict[str, Any]) -> str:
    try:
        return str(hash(frozenset(((k, str(v)) for k, v in (data or {}).items())))
                   if isinstance(data, dict) else id(data))
    except Exception:
        return str(id(data))


# 全局单例（缓存随之保留在进程内）
METRIC_REGISTRY = MetricRegistry()
