"""
多模态视觉评估 - M3-05
基于规则的质量评估兜底，可扩展为LLM视觉评估
"""
from typing import Dict, Any, List, Optional


class VisualEvaluator:
    """视觉评估器 - 规则评估兜底"""
    
    @staticmethod
    def evaluate(config: Dict[str, Any]) -> Dict[str, Any]:
        """
        评估看板质量
        
        Returns:
            {
                "passed": True,
                "score": 85,
                "issues": [],
                "suggestions": []
            }
        """
        issues = []
        suggestions = []
        score = 100
        
        charts = config.get("charts", [])
        
        if not charts:
            return {
                "passed": False,
                "score": 0,
                "issues": [{"severity": "critical", "message": "看板没有图表"}],
                "suggestions": ["请添加至少一个图表"]
            }
        
        # 1. 检查图表数量
        if len(charts) > 10:
            issues.append({
                "severity": "warning",
                "message": f"图表数量过多({len(charts)}个)，建议不超过10个"
            })
            suggestions.append("删除部分图表或合并同类项")
            score -= 10
        
        if len(charts) < 2:
            issues.append({
                "severity": "info",
                "message": "图表数量较少，建议添加更多维度"
            })
            suggestions.append("添加趋势图或对比图丰富看板内容")
            score -= 5
        
        # 2. 检查图表类型多样性
        chart_types = set(c.get("chart_type") for c in charts if c.get("chart_type"))
        if len(chart_types) < 2:
            issues.append({
                "severity": "warning",
                "message": f"图表类型单一(仅{len(chart_types)}种)，建议混合使用"
            })
            suggestions.append("增加不同图表类型（如饼图、折线图）")
            score -= 10
        
        # 3. 检查饼图切片数
        for chart in charts:
            if chart.get("chart_type") == "pie":
                # 饼图切片数检查（如果有数据的话）
                pass
        
        # 4. 检查标题是否完整
        for chart in charts:
            if not chart.get("title"):
                issues.append({
                    "severity": "info",
                    "message": "存在未命名的图表"
                })
                suggestions.append("为所有图表添加标题")
                score -= 5
                break
        
        # 5. 检查KPI卡片数量
        kpi_count = sum(1 for c in charts if c.get("chart_type") == "kpi")
        if kpi_count > 6:
            issues.append({
                "severity": "warning",
                "message": f"KPI卡片过多({kpi_count}个)，建议精简"
            })
            suggestions.append("保留核心KPI，合并或删除冗余卡片")
            score -= 10
        
        return {
            "passed": score >= 60,
            "score": max(score, 0),
            "issues": issues,
            "suggestions": suggestions
        }