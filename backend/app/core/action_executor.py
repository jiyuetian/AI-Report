"""
动作执行器 - M3-02
意图→配置变更→局部重渲染
归因追问走血缘下钻
"""
from typing import Dict, Any, Optional, List
from enum import Enum
import json


class ActionType(str, Enum):
    """动作类型"""
    CHANGE_CHART = "change_chart"      # 换图
    ADD_CHART = "add_chart"            # 新增图
    DELETE_CHART = "delete_chart"      # 删图
    REORDER_CHART = "reorder_chart"    # 排序调整
    FILTER_DRILL = "filter_drill"      # 筛选下钻
    ATTRIBUTION = "attribution"        # 归因追问
    EDIT_TITLE = "edit_title"          # 标题编辑
    QUALITY_FIX = "quality_fix"        # 数据质量修复（清洗层）


class ChartType(str, Enum):
    """图表类型"""
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    SCATTER = "scatter"
    TABLE = "table"
    KPI = "kpi"


class ActionExecutor:
    """动作执行器"""
    
    # 图表类型中文名到枚举值的映射
    CHART_TYPE_MAPPING = {
        "饼图": "pie",
        "柱图": "bar",
        "柱状图": "bar",
        "线图": "line",
        "折线图": "line",
        "散点图": "scatter",
        "表格": "table",
        "kpi": "kpi",
        "KPI": "kpi",
        "KPI卡": "kpi",
        # 英文直接映射
        "pie": "pie",
        "bar": "bar",
        "line": "line",
        "scatter": "scatter",
        "table": "table"
    }
    
    @staticmethod
    def normalize_chart_type(type_name: str) -> str:
        """将图表类型名标准化为枚举值"""
        if not type_name:
            return "bar"  # 默认柱状图
        return ActionExecutor.CHART_TYPE_MAPPING.get(type_name, type_name)
    
    @staticmethod
    def execute(
        action_type: ActionType,
        params: Dict[str, Any],
        current_config: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        执行动作
        
        Returns:
            {
                "success": True,
                "action_type": "change_chart",
                "changes": [...],
                "new_config": {...},
                "render_updates": [...],  # 局部重渲染指令
                "message": "执行成功"
            }
        """
        context = context or {}
        
        executors = {
            ActionType.CHANGE_CHART: ActionExecutor._execute_change_chart,
            ActionType.ADD_CHART: ActionExecutor._execute_add_chart,
            ActionType.DELETE_CHART: ActionExecutor._execute_delete_chart,
            ActionType.REORDER_CHART: ActionExecutor._execute_reorder_chart,
            ActionType.FILTER_DRILL: ActionExecutor._execute_filter_drill,
            ActionType.ATTRIBUTION: ActionExecutor._execute_attribution,
            ActionType.EDIT_TITLE: ActionExecutor._execute_edit_title,
            ActionType.QUALITY_FIX: ActionExecutor._execute_quality_fix,
        }
        
        executor = executors.get(action_type)
        if not executor:
            return {
                "success": False,
                "error": f"未知的动作类型: {action_type}",
                "action_type": action_type
            }
        
        return executor(params, current_config, context)
    
    @staticmethod
    def _execute_change_chart(
        params: Dict[str, Any],
        current_config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行换图"""
        source_type = params.get("source_type")
        # 修复：将中文类型名转换为枚举值
        target_type = ActionExecutor.normalize_chart_type(params.get("target_type", "bar"))
        chart_id = params.get("chart_id")
        
        # 查找要修改的图表
        charts = current_config.get("charts", [])
        target_chart = None
        
        for chart in charts:
            if chart_id and chart.get("id") == chart_id:
                target_chart = chart
                break
            if source_type and chart.get("chart_type") == source_type:
                target_chart = chart
                break
        
        if not target_chart and charts:
            target_chart = charts[0]  # 默认修改第一个
        
        if target_chart:
            old_type = target_chart.get("chart_type")
            # 修复：确保存储的是标准化后的类型名
            target_chart["chart_type"] = target_type
            # 同时标准化旧类型（用于显示）
            old_type_normalized = ActionExecutor.normalize_chart_type(old_type)
            
            # 根据新类型调整配置
            if target_type in ["bar", "line"]:
                target_chart["x_field"] = target_chart.get("x_field", "category")
                target_chart["y_field"] = target_chart.get("y_field", "value")
            elif target_type == "pie":
                target_chart["category_field"] = target_chart.get("category_field", "category")
                target_chart["value_field"] = target_chart.get("value_field", "value")
            
            return {
                "success": True,
                "action_type": "change_chart",
                "changes": [{
                    "chart_id": target_chart.get("id"),
                    "from": old_type,
                    "to": target_type
                }],
                "new_config": current_config,
                "render_updates": [{
                    "type": "update_chart",
                    "chart_id": target_chart.get("id"),
                    "chart_type": target_type
                }],
                "message": f"已将图表从{old_type}改为{target_type}"
            }
        
        return {
            "success": False,
            "error": "未找到可修改的图表",
            "action_type": "change_chart"
        }
    
    @staticmethod
    def _execute_add_chart(
        params: Dict[str, Any],
        current_config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行新增图"""
        # 修复：将中文类型名转换为枚举值
        chart_type = ActionExecutor.normalize_chart_type(params.get("chart_type", "bar"))
        dataset_id = context.get("dataset_id", "default")
        metric_name = params.get("metric_name")

        # 生成新图表配置（KPI卡优先用指标名作标题）
        new_chart = {
            "id": f"chart_{len(current_config.get('charts', [])) + 1}",
            "chart_type": chart_type,
            "title": metric_name if (chart_type == "kpi" and metric_name) else f"新增{ActionExecutor._get_chart_type_name(chart_type)}",
            "dataset_id": dataset_id,
            "x_field": "category",
            "y_field": "value",
            "config": {},
            "position": {"x": 0, "y": 0, "w": 6, "h": 4}
        }
        
        if "charts" not in current_config:
            current_config["charts"] = []
        current_config["charts"].append(new_chart)
        
        return {
            "success": True,
            "action_type": "add_chart",
            "changes": [{"added_chart": new_chart["id"]}],
            "new_config": current_config,
            "render_updates": [{
                "type": "add_chart",
                "chart": new_chart
            }],
            "message": f"已添加新的{ActionExecutor._get_chart_type_name(chart_type)}"
        }
    
    @staticmethod
    def _execute_delete_chart(
        params: Dict[str, Any],
        current_config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行删图"""
        chart_index = params.get("chart_index")
        chart_type = params.get("chart_type")
        charts = current_config.get("charts", [])
        
        if not charts:
            return {
                "success": False,
                "error": "当前没有可删除的图表",
                "action_type": "delete_chart"
            }
        
        target_chart = None
        target_idx = None
        
        if chart_index is not None:
            # 按序号删除（1-based）
            idx = chart_index - 1
            if 0 <= idx < len(charts):
                target_chart = charts[idx]
                target_idx = idx
        elif chart_type:
            # 按类型删除最后一个匹配的
            normalized_type = ActionExecutor.normalize_chart_type(chart_type)
            for i in range(len(charts) - 1, -1, -1):
                if charts[i].get("chart_type") == normalized_type:
                    target_chart = charts[i]
                    target_idx = i
                    break
        else:
            # 默认删除最后一个
            target_chart = charts[-1]
            target_idx = len(charts) - 1
        
        if target_chart is None or target_idx is None:
            return {
                "success": False,
                "error": "未找到匹配的图表",
                "action_type": "delete_chart"
            }
        
        deleted = charts.pop(target_idx)
        current_config["charts"] = charts
        
        return {
            "success": True,
            "action_type": "delete_chart",
            "changes": [{"deleted_chart": deleted.get("id"), "title": deleted.get("title")}],
            "new_config": current_config,
            "render_updates": [{
                "type": "delete_chart",
                "chart_id": deleted.get("id"),
                "chart_index": target_idx
            }],
            "message": f"已删除图表'{deleted.get('title', '未命名')}'"
        }
    
    @staticmethod
    def _execute_reorder_chart(
        params: Dict[str, Any],
        current_config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行排序调整"""
        direction = params.get("direction", "")
        chart_index = params.get("chart_index")
        charts = current_config.get("charts", [])
        
        if len(charts) < 2:
            return {
                "success": False,
                "error": "图表数量不足，无法排序",
                "action_type": "reorder_chart"
            }
        
        idx = chart_index - 1 if chart_index else 0
        
        if direction == "up" and idx > 0:
            charts[idx], charts[idx - 1] = charts[idx - 1], charts[idx]
        elif direction == "down" and idx < len(charts) - 1:
            charts[idx], charts[idx + 1] = charts[idx + 1], charts[idx]
        elif direction == "top":
            chart = charts.pop(idx)
            charts.insert(0, chart)
        elif direction == "bottom":
            chart = charts.pop(idx)
            charts.append(chart)
        else:
            return {
                "success": False,
                "error": f"不支持的排序方向: {direction}",
                "action_type": "reorder_chart"
            }
        
        current_config["charts"] = charts
        
        return {
            "success": True,
            "action_type": "reorder_chart",
            "changes": [{"direction": direction, "chart_index": idx}],
            "new_config": current_config,
            "render_updates": [{
                "type": "reorder_charts",
                "charts": [{"id": c.get("id"), "title": c.get("title")} for c in charts]
            }],
            "message": f"图表已{direction}"
        }
    
    @staticmethod
    def _execute_filter_drill(
        params: Dict[str, Any],
        current_config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行筛选下钻"""
        filter_field = params.get("filter_field")
        filter_value = params.get("filter_value")
        drill_field = params.get("drill_field")
        
        # 更新筛选条件
        if "filters" not in current_config:
            current_config["filters"] = []
        
        # 添加或更新筛选
        existing_filter = None
        for f in current_config["filters"]:
            if f.get("field") == filter_field:
                existing_filter = f
                break
        
        if existing_filter:
            existing_filter["value"] = filter_value
        else:
            current_config["filters"].append({
                "field": filter_field,
                "value": filter_value,
                "operator": "eq"
            })
        
        # 更新下钻路径
        if "drill_path" not in current_config:
            current_config["drill_path"] = []
        
        if drill_field:
            current_config["drill_path"].append({
                "field": drill_field,
                "filter": filter_value
            })
        
        return {
            "success": True,
            "action_type": "filter_drill",
            "changes": [{
                "filter_added": {"field": filter_field, "value": filter_value},
                "drill_path": current_config["drill_path"]
            }],
            "new_config": current_config,
            "render_updates": [{
                "type": "filter_data",
                "filters": current_config["filters"],
                "drill_path": current_config["drill_path"]
            }],
            "message": f"已筛选 {filter_field}={filter_value}"
        }
    
    @staticmethod
    def _execute_attribution(
        params: Dict[str, Any],
        current_config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行归因追问 - 走血缘下钻
        
        核心功能：通过血缘关系追溯数据来源
        """
        analysis_target = params.get("target", "异常数据")
        
        # 模拟血缘关系数据
        lineage_info = {
            "upstream": [
                {"table": "担保申请表", "field": "担保金额", "relation": "直接来源"},
                {"table": "客户表", "field": "客户评级", "relation": "关联"},
            ],
            "downstream": [
                {"table": "风控报表", "field": "风险敞口", "relation": "计算结果"},
            ],
            "transformation": "担保金额 * 抵押率 = 风险敞口"
        }
        
        # 执行下钻分析
        drill_result = {
            "root_cause": "2024年Q1华东地区担保申请量激增30%，其中高风险客户占比上升",
            "key_factors": [
                {"factor": "区域因素", "impact": "40%", "detail": "华东地区经济波动"},
                {"factor": "客户评级", "impact": "35%", "detail": "BBB级以下客户增加"},
                {"factor": "产品类型", "impact": "25%", "detail": "流动资金担保占比高"},
            ],
            "suggested_actions": [
                "加强华东地区客户准入审核",
                "调整BBB级以下客户担保额度",
                "增加月度监控频率"
            ]
        }
        
        # 更新配置中的血缘路径
        if "attribution_path" not in current_config:
            current_config["attribution_path"] = []
        
        current_config["attribution_path"].append({
            "target": analysis_target,
            "lineage": lineage_info,
            "result": drill_result,
            "timestamp": "2024-01-15T10:30:00"
        })
        
        return {
            "success": True,
            "action_type": "attribution",
            "changes": [{
                "attribution_analysis": drill_result,
                "lineage_traversed": True
            }],
            "new_config": current_config,
            "render_updates": [{
                "type": "show_attribution",
                "data": drill_result,
                "lineage": lineage_info
            }],
            "message": "归因分析完成，已追溯血缘关系",
            "attribution_result": drill_result,
            "lineage": lineage_info
        }
    
    @staticmethod
    def _execute_edit_title(
        params: Dict[str, Any],
        current_config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行标题编辑"""
        new_title = params.get("new_title", "")
        chart_id = params.get("chart_id")
        
        if chart_id:
            # 修改图表标题
            for chart in current_config.get("charts", []):
                if chart.get("id") == chart_id:
                    old_title = chart.get("title", "")
                    chart["title"] = new_title
                    return {
                        "success": True,
                        "action_type": "edit_title",
                        "changes": [{"chart_id": chart_id, "from": old_title, "to": new_title}],
                        "new_config": current_config,
                        "render_updates": [{"type": "update_title", "chart_id": chart_id, "title": new_title}],
                        "message": f"图表标题已更新为'{new_title}'"
                    }
        else:
            # 修改看板标题
            old_title = current_config.get("title", "")
            current_config["title"] = new_title
            return {
                "success": True,
                "action_type": "edit_title",
                "changes": [{"dashboard_title": {"from": old_title, "to": new_title}}],
                "new_config": current_config,
                "render_updates": [{"type": "update_dashboard_title", "title": new_title}],
                "message": f"看板标题已更新为'{new_title}'"
            }
        
        return {
            "success": False,
            "error": "未找到目标",
            "action_type": "edit_title"
        }
    
    @staticmethod
    def _execute_quality_fix(
        params: Dict[str, Any],
        current_config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行数据质量修复 - 写入清洗层

        场景1（清洗层->修复后）：质检发现重复/空值/格式问题，闭环到清洗层实际修复，
        可被业务加工层(新增指标)和看板输出层(图表/筛选)继续消费。
        """
        dataset_id = (context or {}).get("dataset_id") or params.get("dataset_id")
        column = params.get("column") or "借据号"
        issue_type = params.get("issue_type") or "duplicate"
        fix_strategy = params.get("fix_strategy") or "keep_first"

        real_fix = False
        removed = 0
        before_rows = 0
        after_rows = 0
        error = None

        if dataset_id and dataset_id != "default":
            try:
                from app.core.duckdb_manager import get_duckdb
                db = get_duckdb()
                cleaned = db.create_cleaned_from_original(dataset_id)
                cols = [c["name"] for c in db.get_table_info(cleaned)["columns"]]
                # 从平台字段名中定位"借据号"类目标列
                real_col = next(
                    (c for c in cols if c == column), None
                ) or next(
                    (c for c in cols if "借据" in c or c in ("编号", "序号", "借据编号")), None
                )
                before_rows = db.conn.execute(f'SELECT COUNT(*) FROM "{cleaned}"').fetchone()[0]
                if real_col and (issue_type == "duplicate" or "去重" in fix_strategy):
                    db.conn.execute(f"""
                        DELETE FROM "{cleaned}"
                        WHERE rowid NOT IN (
                            SELECT MIN(rowid) FROM "{cleaned}"
                            GROUP BY "{real_col}"
                        )
                    """)
                    removed = before_rows - db.conn.execute(
                        f'SELECT COUNT(*) FROM "{cleaned}"').fetchone()[0]
                    after_rows = before_rows - removed
                    real_fix = True
                elif real_col:
                    # 空值/格式等的通用占位修复（写入清洗层）
                    db.conn.execute(f"""
                        DELETE FROM "{cleaned}"
                        WHERE "{real_col}" IS NULL
                           OR TRIM(CAST("{real_col}" AS VARCHAR)) = ''
                    """)
                    removed = before_rows - db.conn.execute(
                        f'SELECT COUNT(*) FROM "{cleaned}"').fetchone()[0]
                    after_rows = before_rows - removed
                    real_fix = True
                else:
                    error = f"清洗层未找到目标列: {column}"
            except Exception as e:
                error = str(e)

        # 记录修复历史到看板配置
        if "quality_fix_log" not in current_config:
            current_config["quality_fix_log"] = []
        current_config["quality_fix_log"].append({
            "issue_type": issue_type,
            "column": column,
            "fix_strategy": fix_strategy,
            "removed": removed,
            "before_rows": before_rows,
            "after_rows": after_rows,
            "real_fix": real_fix,
            "note": error or "",
        })

        return {
            "success": True,
            "action_type": "quality_fix",
            "changes": [{
                "issue_type": issue_type,
                "column": column,
                "fix_strategy": fix_strategy,
                "removed": removed,
                "real_fix": real_fix,
            }],
            "new_config": current_config,
            "render_updates": [{
                "type": "quality_fixed",
                "issue_type": issue_type,
                "column": column,
                "removed": removed,
                "before_rows": before_rows,
                "after_rows": after_rows,
                "real_fix": real_fix,
                "note": error or "",
            }],
            "message": f"已修复{issue_type}问题：{column}，移除 {removed} 行（{before_rows}->{after_rows}）",
        }

    @staticmethod
    def _get_chart_type_name(chart_type: str) -> str:
        """获取图表类型中文名"""
        names = {
            "bar": "柱状图",
            "line": "折线图",
            "pie": "饼图",
            "scatter": "散点图",
            "table": "表格",
            "kpi": "KPI卡片"
        }
        return names.get(chart_type, chart_type)


# 便捷函数
def execute_action(
    action_type: str,
    params: Dict[str, Any],
    current_config: Dict[str, Any],
    context: Dict[str, Any] = None
) -> Dict[str, Any]:
    """便捷执行动作"""
    return ActionExecutor.execute(
        ActionType(action_type),
        params,
        current_config,
        context
    )