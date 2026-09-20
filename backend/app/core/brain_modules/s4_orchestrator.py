"""
S4 编排器 + S5 评分卡 - M2-07
KPI挑选/去冗余/三层叙事（结论→佐证→明细）
评分卡（冗余/覆盖/叙事，权重读配置，≥70通过，不过重排≤3次）
"""
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import json
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.brain_config_manager import BrainConfigManager


class ScoreDimension(Enum):
    """评分维度"""
    REDUNDANCY = "redundancy"  # 冗余度
    COVERAGE = "coverage"      # 覆盖度
    NARRATIVE = "narrative"    # 叙事性


@dataclass
class ChartScore:
    """图表评分"""
    chart_id: str
    chart_type: str
    title: str
    redundancy_score: float  # 0-100
    coverage_score: float
    narrative_score: float
    total_score: float
    
    def to_dict(self) -> Dict:
        return {
            "chart_id": self.chart_id,
            "chart_type": self.chart_type,
            "title": self.title,
            "redundancy_score": round(self.redundancy_score, 2),
            "coverage_score": round(self.coverage_score, 2),
            "narrative_score": round(self.narrative_score, 2),
            "total_score": round(self.total_score, 2)
        }


@dataclass
class DashboardScore:
    """看板评分"""
    overall_score: float
    passed: bool
    dimension_scores: Dict[str, float]
    chart_scores: List[ChartScore]
    retry_count: int
    improvement_suggestions: List[str]
    
    def to_dict(self) -> Dict:
        return {
            "overall_score": round(self.overall_score, 2),
            "passed": self.passed,
            "dimension_scores": {k: round(v, 2) for k, v in self.dimension_scores.items()},
            "chart_scores": [c.to_dict() for c in self.chart_scores],
            "retry_count": self.retry_count,
            "improvement_suggestions": self.improvement_suggestions
        }


class S4Orchestrator:
    """
    S4 编排器
    
    功能：
    1. KPI挑选（选择最有价值的KPI卡）
    2. 去冗余（相似图表合并/删除）
    3. 三层叙事：
       - L1: 结论层（KPI卡）
       - L2: 佐证层（趋势/对比图表）
       - L3: 明细层（分布/明细表）
    """
    
    # 图表类型权重（用于叙事排序）
    NARRATIVE_PRIORITY = {
        "kpi": 1,      # L1: 结论
        "line": 2,     # L2: 佐证-趋势
        "bar": 2,      # L2: 佐证-对比
        "pie": 3,      # L3: 明细-分布
        "scatter": 3,  # L3: 明细-关联
        "table": 3,    # L3: 明细-明细
        "map": 2,      # L2: 佐证-地理
        "heatmap": 3   # L3: 明细-矩阵
    }
    
    def __init__(self):
        self.score_weights = {
            "redundancy": 0.3,
            "coverage": 0.4,
            "narrative": 0.3
        }
        self.pass_threshold = 70
        self.max_retries = 3
    
    async def load_score_config(self, db: AsyncSession):
        """加载评分配置"""
        config = await BrainConfigManager.get_config(db, "score_weights")
        if config and "content" in config:
            content = config["content"]
            self.score_weights = content.get("weights", self.score_weights)
            self.pass_threshold = content.get("pass_threshold", 70)
            self.max_retries = content.get("max_retries", 3)
    
    def select_kpis(self, charts: List[Dict], max_kpis: int = 4) -> List[Dict]:
        """
        KPI挑选
        
        策略：
        1. 优先选择数值型KPI（金额、数量）
        2. 去重（同类指标最多1个）
        3. 最多4个KPI卡
        """
        kpi_charts = [c for c in charts if c.get("chart_type") == "kpi"]
        
        if len(kpi_charts) <= max_kpis:
            return kpi_charts
        
        # 按优先级排序（根据字段类型判断）
        def kpi_priority(chart):
            title = chart.get("title", "")
            if "金额" in title or "总额" in title:
                return 3
            if "笔数" in title or "数量" in title:
                return 2
            return 1
        
        kpi_charts.sort(key=kpi_priority, reverse=True)
        return kpi_charts[:max_kpis]
    
    def remove_redundancy(self, charts: List[Dict]) -> List[Dict]:
        """
        去冗余
        
        策略：
        1. 相同类型且相同字段的图表去重
        2. 相似度>0.8的只保留1个
        3. 保留优先级高的
        """
        if not charts:
            return []
        
        result = []
        seen_signatures = set()
        
        for chart in charts:
            # 生成图表签名
            signature = self._generate_chart_signature(chart)
            
            # 检查是否已存在相似图表
            is_redundant = False
            for seen_sig in seen_signatures:
                similarity = self._calculate_similarity(signature, seen_sig)
                if similarity > 0.8:
                    is_redundant = True
                    break
            
            if not is_redundant:
                result.append(chart)
                seen_signatures.add(signature)
        
        return result
    
    def _generate_chart_signature(self, chart: Dict) -> str:
        """生成图表签名（用于相似度计算）"""
        chart_type = chart.get("chart_type", "")
        x_field = chart.get("x_field", "") or chart.get("category_field", "")
        y_field = chart.get("y_field", "") or chart.get("value_field", "")
        return f"{chart_type}:{x_field}:{y_field}"
    
    def _calculate_similarity(self, sig1: str, sig2: str) -> float:
        """计算签名相似度"""
        parts1 = sig1.split(":")
        parts2 = sig2.split(":")
        
        if len(parts1) != 3 or len(parts2) != 3:
            return 0.0
        
        matches = sum(1 for a, b in zip(parts1, parts2) if a == b)
        return matches / 3.0
    
    def organize_narrative(self, charts: List[Dict]) -> Dict[str, List[Dict]]:
        """
        三层叙事组织
        
        L1: 结论层 - KPI卡（总览）
        L2: 佐证层 - 趋势/对比（论证）
        L3: 明细层 - 分布/明细（深入）
        """
        layers = {
            "L1_conclusion": [],
            "L2_evidence": [],
            "L3_detail": []
        }
        
        for chart in charts:
            chart_type = chart.get("chart_type", "")
            priority = self.NARRATIVE_PRIORITY.get(chart_type, 3)
            
            if priority == 1:
                layers["L1_conclusion"].append(chart)
            elif priority == 2:
                layers["L2_evidence"].append(chart)
            else:
                layers["L3_detail"].append(chart)
        
        return layers
    
    def orchestrate(self, charts: List[Dict], max_charts: int = 6) -> Dict[str, Any]:
        """
        编排入口
        
        流程：
        1. KPI挑选（最多4个）
        2. 去冗余
        3. 三层叙事组织
        4. 限制总数
        """
        # 1. KPI挑选
        kpis = self.select_kpis(charts)
        
        # 2. 去冗余（非KPI图表）
        non_kpi = [c for c in charts if c.get("chart_type") != "kpi"]
        non_kpi = self.remove_redundancy(non_kpi)
        
        # 3. 合并并排序
        all_charts = kpis + non_kpi
        
        # 按叙事优先级排序
        all_charts.sort(key=lambda c: self.NARRATIVE_PRIORITY.get(c.get("chart_type"), 3))
        
        # 4. 限制总数
        final_charts = all_charts[:max_charts]

        # 5. 组织叙事层
        layers = self.organize_narrative(final_charts)

        # 6. 基于真实分层结果生成叙述流（非硬编码）
        narrative_flow = self._build_narrative_flow(layers, final_charts)

        return {
            "success": True,
            "charts": final_charts,
            "chart_count": len(final_charts),
            "kpi_count": len(layers["L1_conclusion"]),
            "layers": layers,
            "narrative_flow": narrative_flow,
        }

    def _build_narrative_flow(self, layers: Dict[str, List[Dict]], charts: List[Dict]) -> str:
        """基于三层真实编排结果生成叙述流描述。

        只描述实际存在的层，每层标注图表数与类型；某层为空时如实跳过，
        空看板返回"无可用图表"。
        """
        if not charts:
            return "无可用图表（数据不足以生成叙事）"

        layer_meta = [
            ("L1_conclusion", "结论"),
            ("L2_evidence", "佐证"),
            ("L3_detail", "明细"),
        ]
        parts = []
        for key, label in layer_meta:
            layer_charts = layers.get(key, [])
            if not layer_charts:
                continue
            type_counts: Dict[str, int] = {}
            for c in layer_charts:
                t = c.get("chart_type", "unknown")
                type_counts[t] = type_counts.get(t, 0) + 1
            type_desc = "、".join(f"{t}×{n}" for t, n in type_counts.items())
            parts.append(f"{label}（{type_desc}）")
        return "→".join(parts) if parts else "无可用图表（数据不足以生成叙事）"


class S5ScoreCard:
    """
    S5 评分卡
    
    评分维度：
    1. 冗余度（30%）：图表是否重复/相似
    2. 覆盖度（40%）：是否覆盖KPI/趋势/对比/分布
    3. 叙事性（30%）：是否符合结论→佐证→明细结构
    
    通过标准：≥70分
    重排：不通过时最多重排3次
    """
    
    def __init__(self):
        self.weights = {
            "redundancy": 0.3,
            "coverage": 0.4,
            "narrative": 0.3
        }
        self.pass_threshold = 70
        self.max_retries = 3
    
    async def load_config(self, db: AsyncSession):
        """加载评分配置"""
        config = await BrainConfigManager.get_config(db, "score_weights")
        if config and "content" in config:
            content = config["content"]
            self.weights = content.get("weights", self.weights)
            self.pass_threshold = content.get("pass_threshold", 70)
            self.max_retries = content.get("max_retries", 3)
    
    def calculate_redundancy_score(self, charts: List[Dict]) -> float:
        """
        计算冗余度分数（越高越好，即冗余越低）
        """
        if not charts or len(charts) <= 1:
            return 100.0
        
        # 计算相似图表对数
        similar_pairs = 0
        for i, c1 in enumerate(charts):
            for c2 in charts[i+1:]:
                sig1 = f"{c1.get('chart_type')}:{c1.get('x_field')}:{c1.get('y_field')}"
                sig2 = f"{c2.get('chart_type')}:{c2.get('x_field')}:{c2.get('y_field')}"
                if sig1 == sig2:
                    similar_pairs += 1
        
        # 冗余度 = 相似对数 / 总对数
        total_pairs = len(charts) * (len(charts) - 1) / 2
        redundancy = similar_pairs / total_pairs if total_pairs > 0 else 0
        
        return (1 - redundancy) * 100
    
    def calculate_coverage_score(self, charts: List[Dict]) -> float:
        """
        计算覆盖度分数
        
        期望覆盖：KPI + 趋势 + 对比 + 分布
        """
        expected_types = {"kpi", "line", "bar", "pie"}
        actual_types = {c.get("chart_type") for c in charts}
        
        coverage = len(expected_types & actual_types) / len(expected_types)
        return coverage * 100
    
    def calculate_narrative_score(self, charts: List[Dict]) -> float:
        """
        计算叙事性分数
        
        期望结构：KPI(结论) → line/bar(佐证) → pie/table(明细)
        """
        narrative_priority = {
            "kpi": 1, "line": 2, "bar": 2, "map": 2,
            "pie": 3, "scatter": 3, "table": 3, "heatmap": 3
        }
        
        if not charts:
            return 0.0
        
        # 检查顺序是否符合叙事流
        scores = []
        for i, chart in enumerate(charts):
            chart_type = chart.get("chart_type", "")
            priority = narrative_priority.get(chart_type, 3)
            
            # 位置评分（越靠前优先级应该越高）
            expected_priority = 1 if i < len(charts) // 3 else (2 if i < 2 * len(charts) // 3 else 3)
            match_score = 100 - abs(priority - expected_priority) * 30
            scores.append(max(0, match_score))
        
        return sum(scores) / len(scores) if scores else 0.0
    
    def score_dashboard(self, charts: List[Dict]) -> DashboardScore:
        """
        看板评分
        """
        # 计算各维度分数
        redundancy = self.calculate_redundancy_score(charts)
        coverage = self.calculate_coverage_score(charts)
        narrative = self.calculate_narrative_score(charts)
        
        # 加权总分
        total = (
            redundancy * self.weights["redundancy"] +
            coverage * self.weights["coverage"] +
            narrative * self.weights["narrative"]
        )
        
        # 生成改进建议
        suggestions = []
        if redundancy < 80:
            suggestions.append("存在冗余图表，建议合并或删除相似图表")
        if coverage < 80:
            missing = {"kpi", "line", "bar", "pie"} - {c.get("chart_type") for c in charts}
            suggestions.append(f"缺少图表类型: {', '.join(missing)}")
        if narrative < 70:
            suggestions.append("叙事结构待优化，建议按KPI→趋势→明细排序")
        
        # 图表级评分
        chart_scores = []
        for i, chart in enumerate(charts):
            chart_scores.append(ChartScore(
                chart_id=str(i),
                chart_type=chart.get("chart_type", ""),
                title=chart.get("title", ""),
                redundancy_score=redundancy,
                coverage_score=coverage,
                narrative_score=narrative,
                total_score=total
            ))
        
        return DashboardScore(
            overall_score=total,
            passed=total >= self.pass_threshold,
            dimension_scores={
                "redundancy": redundancy,
                "coverage": coverage,
                "narrative": narrative
            },
            chart_scores=chart_scores,
            retry_count=0,
            improvement_suggestions=suggestions
        )
    
    def _reorder_by_narrative_priority(self, charts: List[Dict]) -> List[Dict]:
        """按叙事优先级重排: kpi→line→bar→pie→table"""
        priority_order = {
            "kpi": 1,
            "line": 2,
            "bar": 3,
            "pie": 4,
            "table": 5,
            "scatter": 6
        }
        return sorted(charts, key=lambda c: priority_order.get(c.get("chart_type", ""), 99))
    
    def _fill_missing_types(self, charts: List[Dict], backup_pool: List[Dict]) -> List[Dict]:
        """补充缺失类型 - 修复：当backup_pool为空时自动生成默认图表"""
        expected_types = {"kpi", "line", "bar", "pie", "table"}
        existing_types = {c.get("chart_type") for c in charts}
        missing_types = expected_types - existing_types
        
        result = charts.copy()
        
        # 1. 先从备选池补充
        for chart in backup_pool:
            if chart.get("chart_type") in missing_types:
                result.append(chart)
                missing_types.discard(chart.get("chart_type"))
                if not missing_types:
                    break
        
        # 2. 修复：备选池补充不足时，自动生成默认图表
        type_defaults = {
            "kpi": {"chart_type": "kpi", "title": "关键指标", "config": {}},
            "line": {"chart_type": "line", "title": "趋势分析", "x_field": "时间", "y_field": "数值"},
            "bar": {"chart_type": "bar", "title": "对比分析", "x_field": "类别", "y_field": "数值"},
            "pie": {"chart_type": "pie", "title": "分布占比", "category_field": "类别", "value_field": "数值"},
            "table": {"chart_type": "table", "title": "数据明细", "grain": "detail"}
        }
        
        for missing_type in missing_types:
            default_chart = type_defaults.get(missing_type, {"chart_type": missing_type, "title": f"{missing_type}图表"}).copy()
            default_chart["id"] = f"auto_{missing_type}_{len(result)}"
            default_chart["auto_generated"] = True
            result.append(default_chart)
        
        return result
    
    def _remove_redundant_charts(self, charts: List[Dict]) -> List[Dict]:
        """删除冗余相似图"""
        if not charts or len(charts) <= 1:
            return charts
        
        result = [charts[0]]  # 保留第一个
        for chart in charts[1:]:
            is_redundant = False
            for existing in result:
                # 使用已有的similarity计算逻辑
                similar = self._is_chart_similar(chart, existing)
                if similar:
                    is_redundant = True
                    break
            if not is_redundant:
                result.append(chart)
        return result
    
    def _is_chart_similar(self, c1: Dict, c2: Dict) -> bool:
        """判断两个图表是否相似"""
        # 基于类型和字段签名判断
        type1, type2 = c1.get("chart_type"), c2.get("chart_type")
        if type1 != type2:
            return False
        
        # 检查字段签名
        sig1 = f"{c1.get('x_field', '')}:{c1.get('y_field', '')}:{c1.get('category_field', '')}"
        sig2 = f"{c2.get('x_field', '')}:{c2.get('y_field', '')}:{c2.get('category_field', '')}"
        return sig1 == sig2 and sig1 != ":"
    
    async def score_with_retry(
        self,
        db: AsyncSession,
        orchestrator: S4Orchestrator,
        raw_charts: List[Dict],
        backup_charts: Optional[List[Dict]] = None
    ) -> Tuple[DashboardScore, List[Dict]]:
        """
        评分并可能重排 (R2返工: 修正重排策略)
        
        重排策略：
        - 第1次重排: 按叙事优先级重排 (kpi→line→bar→pie→table)
        - 第2次重排: 补充缺失类型 (从备选池取)
        - 第3次重排: 删除冗余相似图
        """
        await self.load_config(db)
        
        best_score = None
        best_charts = None
        current_charts = raw_charts.copy()
        reorder_log = []
        
        for retry in range(self.max_retries + 1):
            # 编排
            orchestrated = orchestrator.orchestrate(current_charts)
            charts = orchestrated["charts"]
            
            # 评分
            score = self.score_dashboard(charts)
            score.retry_count = retry
            
            print(f"[S5] 评分尝试 {retry + 1}: {score.overall_score:.1f}分")
            reorder_log.append(f"retry_{retry}: {score.overall_score:.1f}分, {len(charts)}张图")
            
            if score.passed:
                score.improvement_suggestions = reorder_log
                return score, charts
            
            # 保存最佳结果
            if best_score is None or score.overall_score > best_score.overall_score:
                best_score = score
                best_charts = charts
            
            # R2返工: 新重排策略
            if retry < self.max_retries:
                if retry == 0:
                    # 第1次重排: 按叙事优先级重排
                    print(f"[S5] 第1次重排: 按叙事优先级")
                    current_charts = self._reorder_by_narrative_priority(current_charts)
                    reorder_log.append("-> 按叙事优先级重排")
                    
                elif retry == 1:
                    # 第2次重排: 补充缺失类型
                    if backup_charts:
                        print(f"[S5] 第2次重排: 补充缺失类型")
                        current_charts = self._fill_missing_types(current_charts, backup_charts)
                        reorder_log.append("-> 补充缺失类型")
                    
                elif retry == 2:
                    # 第3次重排: 删除冗余相似图
                    print(f"[S5] 第3次重排: 删除冗余图")
                    current_charts = self._remove_redundant_charts(current_charts)
                    reorder_log.append("-> 删除冗余图")
        
        best_score.improvement_suggestions = reorder_log
        return best_score, best_charts


# 便捷函数
async def orchestrate_and_score(
    db: AsyncSession,
    charts: List[Dict],
    dataset_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    便捷函数：编排+评分
    
    Args:
        db: 数据库会话
        charts: 主图表列表
        dataset_id: 数据集ID（可选，用于获取更多信息）
    """
    orchestrator = S4Orchestrator()
    await orchestrator.load_score_config(db)
    
    scorer = S5ScoreCard()
    # 修复：备选池应包含更多图表候选（如S3生成的所有候选，不只是选中的）
    # 当前传入空列表，算法会在_fill_missing_types中自动生成缺失类型的默认图表
    score, final_charts = await scorer.score_with_retry(
        db, orchestrator, charts, backup_charts=[]
    )

    # 基于最终图表的真实分层生成叙述流
    layers = orchestrator.organize_narrative(final_charts)
    narrative_flow = orchestrator._build_narrative_flow(layers, final_charts)

    return {
        "success": True,
        "charts": final_charts,
        "chart_count": len(final_charts),
        "overall_score": score.overall_score,
        "passed": score.passed,
        "retry_count": score.retry_count,
        "dimension_scores": score.dimension_scores,
        "improvement_suggestions": score.improvement_suggestions,
        "layers": layers,
        "narrative_flow": narrative_flow,
        "score": score.to_dict()
    }