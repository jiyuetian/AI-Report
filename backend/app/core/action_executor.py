"""
动作执行器 - M3-02
意图→配置变更→局部重渲染
归因追问走血缘下钻
"""
from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime
import json
import uuid


class ActionType(str, Enum):
    """动作类型"""
    CHANGE_CHART = "change_chart"      # 换图
    ADD_CHART = "add_chart"            # 新增图
    DELETE_CHART = "delete_chart"      # 删图
    REORDER_CHART = "reorder_chart"    # 排序调整
    FILTER_DRILL = "filter_drill"      # 筛选下钻
    ATTRIBUTION = "attribution"        # 归因追问
    EDIT_TITLE = "edit_title"          # 标题编辑
    ADD_CONCLUSION = "add_conclusion"  # 追加结论（2026-09-18 新增：基于真实字段，禁止幻觉）
    QUALITY_FIX = "quality_fix"        # 数据质量修复（清洗层）
    CLARIFY = "clarify"                # 歧义/不可执行：向用户澄清，绝不猜测执行
    CHART_FIX = "chart_fix"            # 图表问题诊断+修复（空图/无数据，AI对话用）


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
            ActionType.ADD_CONCLUSION: ActionExecutor._execute_add_conclusion,
            ActionType.CLARIFY: ActionExecutor._execute_clarify,
            ActionType.QUALITY_FIX: ActionExecutor._execute_quality_fix,
            ActionType.CHART_FIX: ActionExecutor._execute_chart_fix,
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
        # 2026-09-18 修复："把地区分布 换成饼图"此前改的是第一张图（常误伤 KPI 卡）。
        # 现按标题关键词先精确定位，再退回类型匹配，最后兜底"第一张还不是目标类型的图"。
        title_kw = (params.get("title_keyword") or params.get("chart_title") or "").strip()

        # 查找要修改的图表
        charts = current_config.get("charts", [])
        target_chart = None

        if title_kw:
            target_chart = ActionExecutor._locate_chart(charts, {"chart_title": title_kw})
        if target_chart is None:
            for chart in charts:
                if chart_id and chart.get("id") == chart_id:
                    target_chart = chart
                    break
                if source_type and chart.get("chart_type") == source_type:
                    target_chart = chart
                    break
        if target_chart is None and charts:
            target_chart = next(
                (c for c in charts if c.get("chart_type") != target_type), None
            ) or charts[0]

        if target_chart:
            old_type = target_chart.get("chart_type")
            # 修复：确保存储的是标准化后的类型名
            target_chart["chart_type"] = target_type

            # 根据新类型调整配置（2026-09-18 修复：换图沿用原字段，不再写死 category/value，
            # 否则"柱图→饼图"后图表用不存在的 category 列取数，页面看起来"没变化/空白"）
            if target_type in ["bar", "line", "scatter"]:
                target_chart["x_field"] = (
                    target_chart.get("x_field")
                    or target_chart.get("category_field")
                    or "category"
                )
                target_chart["y_field"] = (
                    target_chart.get("y_field")
                    or target_chart.get("value_field")
                    or "value"
                )
            elif target_type == "pie":
                target_chart["category_field"] = (
                    target_chart.get("category_field")
                    or target_chart.get("x_field")
                    or "category"
                )
                target_chart["value_field"] = (
                    target_chart.get("value_field")
                    or target_chart.get("y_field")
                    or "value"
                )
            
            # 2026-09-18 新增：时间粒度（"按月聚合的折线图"）。
            # 若当前 x 轴不是时间/月份字段，而数据集里有，就切到时间字段，否则只标注粒度。
            time_grain = (params.get("time_grain") or "").strip()
            grain_applied = False
            if time_grain:
                target_chart["time_grain"] = time_grain
                xf = target_chart.get("x_field") or target_chart.get("category_field") or ""
                if not ActionExecutor._looks_like_time_field(xf):
                    cand = ActionExecutor._find_time_field(
                        (context or {}).get("dataset_info", {}).get("field_profiles") or []
                    )
                    if cand:
                        if target_chart.get("chart_type") == "pie":
                            target_chart["category_field"] = cand
                        else:
                            target_chart["x_field"] = cand
                        grain_applied = True
                else:
                    grain_applied = True

            msg = f"已将图表从{ActionExecutor._get_chart_type_name(old_type)}改为{ActionExecutor._get_chart_type_name(target_type)}"
            if grain_applied:
                msg += f"，并按{({'month':'月','day':'天','week':'周','quarter':'季度','year':'年'}).get(time_grain, time_grain)}聚合"

            return {
                "success": True,
                "action_type": "change_chart",
                "changes": [{
                    "chart_id": target_chart.get("id"),
                    "from": old_type,
                    "to": target_type,
                    "time_grain": time_grain or None,
                }],
                "new_config": current_config,
                "render_updates": [{
                    "type": "update_chart",
                    "chart_id": target_chart.get("id"),
                    "chart_type": target_type
                }],
                "message": msg
            }
        
        return {
            "success": False,
            "error": "未找到可修改的图表",
            "action_type": "change_chart"
        }
    
    @staticmethod
    def _is_numeric_field(fp) -> bool:
        ftype = (fp.get("type") or fp.get("dtype") or "").upper()
        return any(t in ftype for t in ("DECIMAL", "DOUBLE", "FLOAT", "INT", "BIGINT", "NUMERIC", "REAL", "NUMBER", "DEC"))

    @staticmethod
    def _build_chart(chart_type: str, title: str, dim: str, metric: str, dataset_id: str, seq: int, aggregation: str = None) -> Dict[str, Any]:
        """按图型把维度/指标字段映射到正确的 echarts 字段名（不再写死 category/value）。

        2026-09-22 N1-D2：aggregation 透传到 chart.config.aggregation，
        KPI 卡的 deriveKpi 据此走 AVG 而非默认 SUM（"平均值"必须真算均值）。
        """
        chart = {
            "id": f"chart_{seq}",
            "chart_type": chart_type,
            "title": title,
            "dataset_id": dataset_id,
            "config": {},
            "position": {"x": 0, "y": 0, "w": 6, "h": 4},
        }
        if chart_type == "pie":
            chart["category_field"] = dim
            chart["value_field"] = metric
        elif chart_type == "kpi":
            chart["y_field"] = metric
        elif chart_type == "scatter":
            # 散点图需两数值字段；维度非数值时回退用指标字段
            chart["x_field"] = dim if dim else metric
            chart["y_field"] = metric
        else:  # bar / line / table
            chart["x_field"] = dim
            chart["y_field"] = metric
        # N1-D2：聚合口径（avg/sum/max/min/count）写入 config，前端 deriveKpi 读取
        if aggregation:
            chart["config"]["aggregation"] = aggregation
        return chart

    @staticmethod
    def _execute_add_chart(
        params: Dict[str, Any],
        current_config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行新增图（支持 LLM/规则提取的多图，按真实字段生成，不再写死 category/value）"""
        dataset_id = context.get("dataset_id") or ""
        field_profiles = (context.get("dataset_info") or {}).get("field_profiles") or []

        def first_dim_metric():
            dim = ""
            metric = ""
            for fp in field_profiles:
                nm = fp.get("name") or fp.get("column") or ""
                if not nm:
                    continue
                if not ActionExecutor._is_numeric_field(fp) and not dim:
                    dim = nm
                if ActionExecutor._is_numeric_field(fp) and not metric:
                    metric = nm
            return dim, metric

        charts_spec = params.get("charts") or []
        existing = len(current_config.get("charts", []))
        limit = 50  # 与 feasibility 上限一致
        new_charts = []

        def _match_field(cand, role):
            """问题2 修复（Layer3）：把候选名（可能带「每个：」前缀或表述差异）解析成真实字段名。"""
            cand = (cand or "").strip()
            names = [fp.get("name") or fp.get("column") or "" for fp in field_profiles]
            if cand in names:
                return cand
            for fp in field_profiles:
                nm = fp.get("name") or fp.get("column") or ""
                if cand and (cand in nm or nm in cand):
                    return nm
            for fp in field_profiles:
                nm = fp.get("name") or fp.get("column") or ""
                if not nm:
                    continue
                if role == "metric" and ActionExecutor._is_numeric_field(fp):
                    return nm
                if role == "dim" and not ActionExecutor._is_numeric_field(fp):
                    return nm
            return ""

        if charts_spec:
            skipped = 0
            def _strict_match(cand, role):
                """2026-09-21 修复（1.5 垃圾图）：严格匹配真实字段，不做"首个字段"回退，
                避免把无关字段臆造成垃圾图。仅当候选名精确或子串命中真实字段才返回。"""
                cand = (cand or "").strip()
                names = [fp.get("name") or fp.get("column") or "" for fp in field_profiles]
                if cand in names:
                    return cand
                for nm in names:
                    if cand and (cand in nm or nm in cand):
                        return nm
                return ""
            for spec in charts_spec[:max(0, limit - existing)]:
                ct = ActionExecutor.normalize_chart_type(spec.get("chart_type", "bar"))
                title = (spec.get("title") or "").strip()
                metric_cand = spec.get("metric_field") or spec.get("metric_name") or title
                dim_cand = spec.get("dimension_field") or title
                metric = _strict_match(metric_cand, "metric")
                dim = _strict_match(dim_cand, "dim")
                # 2026-09-21 修复（1.5）：字段无法解析为真实字段时，跳过该图，
                # 绝不拿"第一个维度/指标"臆造无关的「新增bar」垃圾图。
                if not metric:
                    skipped += 1
                    continue
                if ct in ("pie", "bar", "line", "scatter", "table") and not dim:
                    # 维度图必须有真实维度字段；kpi 允许只给指标
                    skipped += 1
                    continue
                title = title or f"{dim or '数据'}分布"
                # N1-D3'：同标题+同图型已存在则跳过，避免纠正类重复指令叠加成翻倍卡片
                if any(c.get("title") == title and c.get("chart_type") == ct
                       for c in current_config.get("charts", [])):
                    skipped += 1
                    continue
                seq = existing + len(new_charts) + 1
                new_charts.append(ActionExecutor._build_chart(ct, title, dim, metric, dataset_id, seq, spec.get("aggregation")))
        else:
            # 兼容旧逻辑：单图，字段用 params 真实字段或画像兜底
            # M6-03：若请求中完全解析不出真实字段（如用户提到的字段在数据集里不存在），
            # 拒绝并给出明确提示，绝不臆造无关字段的图表。
            if not (params.get("dimension_field") or params.get("metric_field")
                    or params.get("value_field") or params.get("y_field")):
                return {
                    "success": False,
                    "error": "未能从数据中匹配到您提到的字段，请使用数据中的真实字段名（如维度字段或数值指标）再试。",
                    "action_type": "add_chart",
                }
            chart_type = ActionExecutor.normalize_chart_type(params.get("chart_type", "bar"))
            fd, fm = first_dim_metric()
            dim = params.get("dimension_field") or fd
            metric = params.get("metric_field") or params.get("value_field") or params.get("y_field") or fm
            metric_name = params.get("metric_name")
            title = metric_name if (chart_type == "kpi" and metric_name) else (
                params.get("title") or f"新增{ActionExecutor._get_chart_type_name(chart_type)}"
            )
            if existing < limit:
                seq = existing + 1
                new_charts.append(ActionExecutor._build_chart(chart_type, title, dim, metric, dataset_id, seq, params.get("aggregation")))

        if "charts" not in current_config:
            current_config["charts"] = []
        # 2026-09-18：id 必须唯一。老逻辑用 `chart_{len+1}`，删过图之后再新增会与已有图同 id，
        # 前端按 id 渲染就会出现"新增的图覆盖了已有图"。
        existing_ids = {c.get("id") for c in current_config["charts"]}
        for c in new_charts:
            while c["id"] in existing_ids:
                c["id"] = f"chart_{uuid.uuid4().hex[:8]}"
            existing_ids.add(c["id"])
            current_config["charts"].append(c)

        if not new_charts:
            # N1-D3'：若全因"已存在"被去重跳过（skipped>0），视为成功而非报错
            if skipped > 0:
                return {
                    "success": True,
                    "action_type": "add_chart",
                    "changes": [],
                    "new_config": current_config,
                    "render_updates": [],
                    "message": "这些图表已存在，未重复添加。",
                }
            return {
                "success": False,
                "error": "看板图表数已达上限(50)，无法继续新增",
                "action_type": "add_chart",
            }

        titles = "、".join(c["title"] for c in new_charts)
        skip_note = f"（{skipped} 个字段无法匹配真实数据，已跳过）" if skipped else ""
        return {
            "success": True,
            "action_type": "add_chart",
            "changes": [{"added_chart": c["id"]} for c in new_charts],
            "new_config": current_config,
            "render_updates": [{"type": "add_chart", "chart": c} for c in new_charts],
            "message": f"已添加 {len(new_charts)} 个图表：{titles}{skip_note}",
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
        title_keyword = (params.get("title_keyword") or "").strip()
        delete_all = bool(params.get("delete_all"))
        confirmed = bool(params.get("confirmed"))
        charts = current_config.get("charts", [])
        
        if not charts:
            return {
                "success": False,
                "error": "当前没有可删除的图表",
                "action_type": "delete_chart"
            }

        # 2026-09-18 修复：「删掉所有图」此前只删了最后一张还说"已删除"。
        # 现必须显式确认（用户二次确认或前端 override），否则给出后果提示，绝不擅自清空。
        if delete_all and not confirmed:
            return {
                "success": False,
                "action_type": "delete_chart",
                "requires_confirm": True,
                "error": (
                    f"你要求删除全部 {len(charts)} 张图："
                    + "、".join((c.get("title") or "未命名") for c in charts[:8])
                    + ("…" if len(charts) > 8 else "")
                    + "。删除后看板将为空且不可自动恢复（可用版本回退找回）。"
                      "请回复「确认删除全部图表」后再执行一次。"
                ),
                "new_config": current_config,
            }
        if delete_all and confirmed:
            removed = [{"deleted_chart": c.get("id"), "title": c.get("title")} for c in charts]
            current_config["charts"] = []
            return {
                "success": True,
                "action_type": "delete_chart",
                "changes": removed,
                "new_config": current_config,
                "render_updates": [{"type": "delete_chart", "chart_id": c["deleted_chart"]} for c in removed],
                "message": f"已删除全部 {len(removed)} 张图表",
            }
        
        target_chart = None
        target_idx = None
        
        if chart_index is not None:
            # 按序号删除（1-based）
            idx = chart_index - 1
            if 0 <= idx < len(charts):
                target_chart = charts[idx]
                target_idx = idx
        elif title_keyword:
            # 按标题关键词（包含匹配）删除最后一个匹配的
            for i in range(len(charts) - 1, -1, -1):
                title = (charts[i].get("title") or "")
                if title_keyword in title:
                    target_chart = charts[i]
                    target_idx = i
                    break
            # 2026-09-18 修复：关键词未命中时"回退按类型删"是误删源头
            # （用户说"删除转化率那张图"，实际删了另一张饼图）。
            # 现在只要用户给了定位线索却没命中，就明确报错并列出可选图表，绝不猜。
            if target_chart is None and chart_type:
                normalized_type = ActionExecutor.normalize_chart_type(chart_type)
                for i in range(len(charts) - 1, -1, -1):
                    if charts[i].get("chart_type") == normalized_type:
                        target_chart = charts[i]
                        target_idx = i
                        break
            if target_chart is None:
                return {
                    "success": False,
                    "action_type": "delete_chart",
                    "error": (
                        f"没有找到标题/类型匹配「{title_keyword or chart_type}」的图表，未做任何删除。"
                        "当前看板有："
                        + "、".join((c.get("title") or "未命名") for c in charts[:10])
                        + "。请说明具体是哪一张。"
                    ),
                    "new_config": current_config,
                }
        elif chart_type:
            # 按类型删除最后一个匹配的
            normalized_type = ActionExecutor.normalize_chart_type(chart_type)
            for i in range(len(charts) - 1, -1, -1):
                if charts[i].get("chart_type") == normalized_type:
                    target_chart = charts[i]
                    target_idx = i
                    break
            if target_chart is None:
                return {
                    "success": False,
                    "action_type": "delete_chart",
                    "error": f"没有类型为「{chart_type}」的图表，未做任何删除。当前图表："
                             + "、".join((c.get("title") or "未命名") for c in charts[:10]),
                    "new_config": current_config,
                }
        else:
            # 2026-09-18 修复：此前"默认删除最后一张"，用户没说删哪张就删错了。
            # 现在改为要求澄清。
            return {
                "success": False,
                "action_type": "delete_chart",
                "requires_clarify": True,
                "error": "请告诉我要删除哪一张（可用图名，如「删除转化率分布」；或序号，如「删除第2张」）。当前图表："
                         + "、".join((c.get("title") or "未命名") for c in charts[:10]),
                "new_config": current_config,
            }
        
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
    def _looks_like_time_field(name: str) -> bool:
        n = (name or "").lower()
        return any(k in n for k in ("日期", "时间", "月份", "年月", "date", "time", "month", "day", "year"))

    @staticmethod
    def _find_time_field(field_profiles) -> str:
        for fp in field_profiles or []:
            nm = fp.get("name") or fp.get("column") or ""
            if nm and ActionExecutor._looks_like_time_field(nm) and not ActionExecutor._is_numeric_field(fp):
                return nm
        return ""

    # ---------------- 追加结论（基于真实字段，禁止幻觉）----------------

    @staticmethod
    def _collect_real_facts(dataset_id: str, field_profiles, current_config) -> Dict[str, Any]:
        """从清洗层真实查询出可引用的事实（行数/合计/TopN），供结论生成使用。

        只返回查得出来的数字；查不出来的一律为 None，结论里就不出现——这是"不幻觉"的硬约束。
        """
        charts = (current_config or {}).get("charts") or []
        names = [(fp.get("name") or fp.get("column") or "") for fp in (field_profiles or [])]
        names = [n for n in names if n]

        dim = metric = ""
        for c in charts:
            if not dim:
                dim = (c.get("x_field") or c.get("category_field") or "").strip()
            if not metric:
                metric = (c.get("y_field") or c.get("value_field") or "").strip()
            if dim and metric:
                break

        facts: Dict[str, Any] = {
            "ok": False, "dataset_id": dataset_id, "fields": names,
            "dim": dim, "metric": metric, "row_count": None,
            "metric_sum": None, "metric_avg": None, "top": [],
        }
        if not dataset_id or dataset_id == "default":
            return facts
        try:
            from app.core.duckdb_manager import get_duckdb
            db = get_duckdb()
            tbl = f"ds_{dataset_id.replace('-', '_')}_cleaned"
            if not db.table_exists(tbl):
                tbl = f"ds_{dataset_id.replace('-', '_')}"
            if not db.table_exists(tbl):
                return facts
            cols = [c["name"] for c in db.get_table_info(tbl).get("columns", [])]
            facts["fields"] = cols or names
            facts["row_count"] = db.conn.execute(f'SELECT COUNT(*) FROM "{tbl}"').fetchone()[0]

            dim_ok = dim if dim in cols else ""
            metric_ok = metric if metric in cols else ""
            if not metric_ok:
                for fp in field_profiles or []:
                    nm = fp.get("name") or fp.get("column") or ""
                    if nm in cols and ActionExecutor._is_numeric_field(fp):
                        metric_ok = nm
                        break
            if not dim_ok:
                for fp in field_profiles or []:
                    nm = fp.get("name") or fp.get("column") or ""
                    if nm in cols and not ActionExecutor._is_numeric_field(fp):
                        dim_ok = nm
                        break
            facts["dim"], facts["metric"] = dim_ok, metric_ok

            if metric_ok:
                row = db.conn.execute(
                    f'SELECT SUM(TRY_CAST("{metric_ok}" AS DOUBLE)), AVG(TRY_CAST("{metric_ok}" AS DOUBLE)) FROM "{tbl}"'
                ).fetchone()
                if row:
                    facts["metric_sum"] = row[0]
                    facts["metric_avg"] = row[1]
            if dim_ok and metric_ok:
                rows = db.conn.execute(
                    f'SELECT "{dim_ok}", SUM(TRY_CAST("{metric_ok}" AS DOUBLE)) s FROM "{tbl}" '
                    f'GROUP BY 1 ORDER BY s DESC LIMIT 3'
                ).fetchall()
                facts["top"] = [(r[0], r[1]) for r in rows if r[0] is not None]
            facts["ok"] = True
        except Exception:
            pass
        return facts

    @staticmethod
    def _rule_conclusion(facts: Dict[str, Any]) -> str:
        """纯规则结论：只用查出来的真实数字，查不到就不写。"""
        parts = []
        rc = facts.get("row_count")
        if rc is not None:
            parts.append(f"本次分析覆盖 {rc} 条记录")
        dim, metric = facts.get("dim") or "", facts.get("metric") or ""
        if dim and metric:
            parts.append(f"按「{dim}」维度统计「{metric}」")
        s = facts.get("metric_sum")
        if s is not None:
            try:
                parts.append(f"{metric}合计 {round(float(s), 2):g}" if metric else f"合计 {round(float(s), 2):g}")
            except Exception:
                pass
        top = facts.get("top") or []
        if top and dim and metric:
            share = ""
            if s:
                try:
                    share = f"，占合计 {round(float(top[0][1]) / float(s) * 100, 1):g}%"
                except Exception:
                    share = ""
            try:
                v0 = f"{round(float(top[0][1]), 2):g}"
            except Exception:
                v0 = str(top[0][1])
            parts.append(f"{dim}中「{top[0][0]}」最高（{metric} {v0}{share}）")
            if len(top) > 1:
                parts.append("其后依次为 " + "、".join(str(t[0]) for t in top[1:]))
        if not parts:
            return ""
        return "；".join(parts) + "。以上结论均基于当前数据集实际字段计算，未引用数据之外的信息。"

    @staticmethod
    def _llm_polish_conclusion(facts: Dict[str, Any], rule_text: str, user_hint: str = "") -> tuple:
        """用 LLM 把事实润色成自然语言；输出必须通过 anti-hallucination 校验，否则丢弃。"""
        if not rule_text:
            return None, "no_facts"
        try:
            from app.core.llm_gateway import llm_chat
            import asyncio, concurrent.futures
            allowed = facts.get("fields") or []
            top_txt = "、".join(f"{a}={b}" for a, b in (facts.get("top") or []))
            prompt = (
                "你是BI分析师。只能使用下面【真实事实】中的字段名和数字写一句结论，"
                "严禁出现事实之外的字段名、严禁编造数字、严禁推测原因。\n"
                f"【真实事实】{rule_text}\n"
                f"【可用字段白名单】{allowed}\n"
                f"【Top明细】{top_txt}\n"
                f"【用户要求】{user_hint or '基于真实字段写一段结论'}\n"
                "只输出结论正文（不超过80字），不要解释、不要JSON。"
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                resp = ex.submit(lambda: asyncio.run(llm_chat(prompt, timeout=40))).result(timeout=45)
            text = (resp or "").strip()
            if not text:
                return None, "empty"
            # ---- anti-hallucination 校验 ----
            import re as _re
            # 1) 出现白名单之外的"《》/「」/引号包裹"的字段名 → 判幻觉
            for m in _re.findall(r"[《「『\"']([^》」』\"']{2,20})[》」』\"']", text):
                if m not in allowed and m not in (facts.get("dim") or "", facts.get("metric") or ""):
                    return None, f"hallucinated_field:{m}"
            # 2) 数字必须来自事实文本
            facts_nums = set(_re.findall(r"\d+(?:\.\d+)?", rule_text))
            nums = set(_re.findall(r"\d+(?:\.\d+)?", text))
            unknown = nums - facts_nums - {"1", "2", "3"}
            if unknown:
                return None, f"hallucinated_number:{sorted(unknown)[:3]}"
            return text, "llm"
        except Exception as e:
            return None, f"llm_error:{str(e)[:60]}"

    @staticmethod
    def _execute_add_conclusion(
        params: Dict[str, Any],
        current_config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """在末尾追加一段结论——正文必须基于真实字段的真实聚合值。"""
        dataset_id = (context or {}).get("dataset_id") or params.get("dataset_id") or ""
        field_profiles = (context.get("dataset_info") or {}).get("field_profiles") or []
        facts = ActionExecutor._collect_real_facts(dataset_id, field_profiles, current_config)
        # 2026-09-18：查不到真实数据就明确拒绝，绝不产出"看起来有道理但没算过"的结论。
        if not facts.get("ok"):
            return {
                "success": False,
                "action_type": "add_conclusion",
                "error": "无法生成结论：取不到当前数据集的真实聚合结果（数据集未就绪或清洗层无数据），为避免编造，已中止。",
                "new_config": current_config,
            }
        rule_text = ActionExecutor._rule_conclusion(facts)

        if not rule_text:
            return {
                "success": False,
                "action_type": "add_conclusion",
                "error": "无法生成结论：当前数据集取不到可聚合的真实字段（请确认数据集已上传并完成清洗）。",
                "new_config": current_config,
            }

        polished, source = ActionExecutor._llm_polish_conclusion(
            facts, rule_text, params.get("hint") or ""
        )
        text = polished or rule_text

        entry = {
            "text": text,
            "rule_text": rule_text,
            "source": "llm" if polished else "rule",
            "llm_reject_reason": None if polished else (source if source != "rule" else None),
            "based_on": {
                "dataset_id": dataset_id,
                "row_count": facts.get("row_count"),
                "dim": facts.get("dim"),
                "metric": facts.get("metric"),
                "top": facts.get("top"),
            },
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        if "conclusions" not in current_config:
            current_config["conclusions"] = []
        current_config["conclusions"].append(entry)
        # 兼容前端单结论展示
        current_config["conclusion_text"] = text

        return {
            "success": True,
            "action_type": "add_conclusion",
            "changes": [{"added_conclusion": entry}],
            "new_config": current_config,
            "render_updates": [{"type": "add_conclusion", "conclusion": entry}],
            "message": f"已在末尾追加结论（来源：{'AI 生成' if polished else '规则生成'}）：{text}",
            "conclusion_source": "llm" if polished else "rule",
        }

    @staticmethod
    def _execute_clarify(
        params: Dict[str, Any],
        current_config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """歧义/矛盾/不可执行：只澄清，不改配置（杜绝"瞎猜着改"）。"""
        return {
            "success": False,
            "action_type": "clarify",
            "requires_clarify": True,
            "reason": params.get("reason", "ambiguous"),
            "error": params.get("message") or "这条指令有歧义，请补充说明具体要改什么。",
            "options": params.get("options", []),
            "new_config": current_config,
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

        direction_names = {"up": "上移", "down": "下移", "top": "置顶", "bottom": "移至末尾"}
        return {
            "success": True,
            "action_type": "reorder_chart",
            "changes": [{"direction": direction, "chart_index": idx}],
            "new_config": current_config,
            "render_updates": [{
                "type": "reorder_charts",
                "charts": [{"id": c.get("id"), "title": c.get("title")} for c in charts]
            }],
            "message": f"图表已{direction_names.get(direction, direction)}"
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
        """归因追问 - 实查版（3.5 修复，2026-09-21）。

        演进史：
        - 最初：返回写死的假血缘（"华东地区担保申请量激增30%"）+ "已追溯血缘关系"话术，纯编造。
        - 2026-09-17：改为诚实罗列 3 条可能性 + "请先刷新看板页面"——不再编造，但仍未实查，
          用户等于被告知"你自己去试"，体验上就是"AI 只会说刷新试试"。
        - 本次：用 context 里的**真实字段画像** + 当前看板图表配置做实查，
          直接给出"这张图到底卡在哪"的结论（字段缺失 / 清洗置空 / 高缺失率 / 字段正常），
          无法实查时也明确说明原因，不再让用户盲试。
        """
        analysis_target = params.get("target", "异常数据")

        # 仅记录归因请求轨迹，不伪装成已完成的分析
        if "attribution_path" not in current_config:
            current_config["attribution_path"] = []
        current_config["attribution_path"].append({
            "target": analysis_target,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        })

        # ====== 实查 1：取真实字段画像（兼容两种 context 约定）======
        # 消息链路(chat.py:533)用 dataset_info.field_profiles；会话链路(chat.py:359)用顶层 field_profiles
        fps = (
            ((context or {}).get("dataset_info") or {}).get("field_profiles")
            or (context or {}).get("field_profiles")
            or []
        )
        # 归一化：真实数据列名常带首尾空格/全角空格（Excel 导出极常见），
        # 若不做归一化，" 抵押率 " 会被误判为 missing（假阴性）。
        def _norm(s: Any) -> str:
            return str(s or "").strip()

        def _squash(s: Any) -> str:
            """去掉所有半角/全角空格，用于兜底匹配。"""
            return _norm(s).replace(" ", "").replace("\u3000", "")

        def _lookup(field: Any) -> Optional[Dict[str, Any]]:
            """先精确匹配，再去空格匹配，最后大小写不敏感匹配。"""
            key = _norm(field)
            if not key:
                return None
            return (
                field_index.get(key)
                or field_index.get(_squash(key))
                or field_index.get(key.lower())
                or field_index.get(_squash(key).lower())
            )

        field_index: Dict[str, Dict[str, Any]] = {}
        field_names: List[str] = []  # 仅存原名，供对外话术计数/举例，避免别名污染
        for fp in fps:
            if not isinstance(fp, dict):
                continue
            name = _norm(fp.get("name") or fp.get("column"))
            if not name:
                continue
            field_names.append(name)
            field_index[name] = fp
            sq = _squash(name)
            if sq != name:
                field_index[sq] = fp
            low = name.lower()
            if low != name:
                field_index[low] = fp
                if _squash(low) != low:
                    field_index[_squash(low)] = fp

        charts = (current_config or {}).get("charts") or []

        # ====== 实查 2：定位与目标相关的图表 ======
        # 优先：标题或字段命中 target；否则退化为"字段有问题的那张图"；再否则取第一张非 KPI 图
        def _chart_fields(c: Dict[str, Any]) -> List[str]:
            keys = ("x_field", "y_field", "category_field", "value_field", "series_field")
            out: List[str] = []
            for k in keys:
                v = c.get(k)
                if v:
                    out.append(str(v))
            return out

        matched = None
        for c in charts:
            if not isinstance(c, dict):
                continue
            hay = str(c.get("title") or "") + "|" + "|".join(_chart_fields(c))
            if analysis_target and analysis_target in hay:
                matched = c
                break
        if matched is None:
            # 找字段缺失的那张（最可能是"无可绘制数据"的元凶）
            for c in charts:
                if not isinstance(c, dict):
                    continue
                if c.get("chart_type") == "kpi":
                    continue
                if any(_lookup(f) is None for f in _chart_fields(c)):
                    matched = c
                    break
        if matched is None:
            matched = next((c for c in charts if isinstance(c, dict) and c.get("chart_type") != "kpi"), None)

        # ====== 实查 3：逐字段判定 ======
        def _diagnose(field: str) -> str:
            # 与建索引时同一套归一化：精确 → 去空格 → 大小写不敏感
            fp = _lookup(field)
            if fp is None:
                return "missing"
            try:
                rate = float(fp.get("null_rate") or 0)
            except (TypeError, ValueError):
                rate = 0.0
            if rate >= 0.999:
                return "emptied"
            if rate >= 0.5:
                return "high_null"
            return "ok"

        checked: Dict[str, Any] = {}
        message = ""
        if not field_index:
            # 无法实查：说明原因，而不是让用户盲刷新
            message = (
                f"收到对「{analysis_target}」的归因请求。当前会话没有携带该数据集的字段画像"
                "（多文件看板或数据集未生成画像时会出现），因此我无法在这里实查字段是否存在——"
                "这也是我不直接说「刷新试试」的原因：没有依据的结论没有价值。\n"
                "请确认：① 打开看板时是否带上了 dataset；② 到「数据上传/质检」重新生成一次字段画像；"
                "③ 若字段来自另一份数据，先在主数据集里确认该列是否存在。"
            )
            checked = {"checkable": False, "reason": "no_field_profiles"}
        elif not charts:
            message = (
                f"收到对「{analysis_target}」的归因请求。已取到 {len(field_names)} 个真实字段，"
                "但当前看板没有图表配置，无法定位是哪张图有问题。请确认看板配置是否已保存。"
            )
            checked = {"checkable": True, "charts": 0}
        elif matched is None:
            message = (
                f"收到对「{analysis_target}」的归因请求。已实查 {len(field_names)} 个字段、"
                f"{len(charts)} 张图表，但未找到与该目标关联的图表。请指明具体图表名或字段名。"
            )
            checked = {"checkable": True, "charts": len(charts), "matched": None}
        else:
            fields = _chart_fields(matched)
            title = str(matched.get("title") or "未命名图表")
            verdicts = {f: _diagnose(f) for f in fields}
            checked = {
                "checkable": True,
                "chart": title,
                "fields": verdicts,
                "field_count": len(field_names),
            }

            if not fields:
                conclusion = "这张图没有配置任何字段（无 x/y/分类字段），所以取不到数据。"
                next_step = "请重新生成该图表，或在对话里直接说「按 <字段名> 画柱状图」让我重建。"
            else:
                miss = [f for f, v in verdicts.items() if v == "missing"]
                emptied = [f for f, v in verdicts.items() if v == "emptied"]
                highnull = [f for f, v in verdicts.items() if v == "high_null"]
                if miss:
                    sample = "、".join(field_names[:8])
                    conclusion = (
                        f"字段 {('、'.join(miss))} 不在主数据集的 {len(field_names)} 个字段里"
                        f"（现有字段如：{sample}）。多文件看板时该字段可能来自另一份数据。"
                    )
                    next_step = "到看板里按字段匹配到对应数据集；或告诉我正确的字段名，我按真实字段重建这张图。"
                elif emptied:
                    conclusion = f"字段 {('、'.join(emptied))} 存在，但空值率 100%（质检清洗后被置空）。"
                    next_step = "返回质检步骤撤销/调整该列的清洗规则，再重新取数。"
                elif highnull:
                    conclusion = f"字段 {('、'.join(highnull))} 存在但空值率偏高（>50%），可用数据点很少。"
                    next_step = "可先按该字段做缺失值处理（填充/删除），再重画。"
                else:
                    conclusion = f"字段 {('、'.join(fields))} 都存在于数据集且非空——字段层面没问题。"
                    next_step = "那更可能是图表配置/取数问题，建议重新生成看板；或告诉我目标，我按现有字段重建一张。"

            message = (
                f"收到对「{analysis_target}」的归因请求。需要说明：对话助手不能直接改已有图表，"
                f"所以我不说「刷新试试」，而是先实查给你结论。\n"
                f"已实查图表「{title}」：{conclusion}\n"
                f"下一步：{next_step}"
            )

        return {
            "success": True,
            "action_type": "attribution",
            "changes": [],
            "new_config": current_config,
            "render_updates": [],
            "message": message,
            # 3.5：把实查结论结构化回传，便于前端/日志追踪（不再是一句"请刷新"）
            "check_result": checked,
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
    def _locate_chart(charts: List[Dict[str, Any]], params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """在看板图表里定位用户说的那张图（按 id → 标题精确 → 标题包含）"""
        cid = params.get("chart_id")
        if cid:
            for c in charts:
                if c.get("id") == cid:
                    return c
        target = (params.get("chart_title") or params.get("title") or params.get("target") or "").strip()
        if not target:
            return None
        for c in charts:
            if (c.get("title") or "") == target:
                return c
        for c in charts:
            if target and target in (c.get("title") or ""):
                return c
        # 最后按字段模糊匹配
        for c in charts:
            for k in ("category_field", "x_field", "y_field", "value_field"):
                if target and target in str(c.get(k) or ""):
                    return c
        return None

    @staticmethod
    def _apply_chart_field_fix(
        dataset_id: str, column: str, strategy: str, fill_value: Any = None
    ) -> Dict[str, Any]:
        """在清洗层真实修复某个字段（图表取数读的就是清洗层，修完刷新即生效）"""
        from app.core.duckdb_manager import get_duckdb
        db = get_duckdb()
        cleaned = db.create_cleaned_from_original(dataset_id)
        cols = [c["name"] for c in db.get_table_info(cleaned).get("columns", [])]
        if column not in cols:
            return {"ok": False, "error": f"清洗层没有这一列：{column}"}

        before = db.conn.execute(f'SELECT COUNT(*) FROM "{cleaned}"').fetchone()[0]
        empty_cond = f'"{column}" IS NULL OR TRIM(CAST("{column}" AS VARCHAR)) = \'\''

        if strategy == "drop":
            db.conn.execute(f'DELETE FROM "{cleaned}" WHERE {empty_cond}')
            after = db.conn.execute(f'SELECT COUNT(*) FROM "{cleaned}"').fetchone()[0]
            return {"ok": True, "action": "drop", "before": before, "after": after,
                    "removed": before - after}

        if strategy in ("fill_constant", "fill_unknown", "fill_mode", "fill_median"):
            if strategy == "fill_median":
                row = db.conn.execute(
                    f'SELECT MEDIAN(TRY_CAST("{column}" AS DOUBLE)) FROM "{cleaned}"'
                ).fetchone()
                val = row[0] if row and row[0] is not None else 0
            elif strategy == "fill_mode":
                row = db.conn.execute(
                    f'SELECT "{column}", COUNT(*) c FROM "{cleaned}" WHERE NOT ({empty_cond}) '
                    f'GROUP BY 1 ORDER BY c DESC LIMIT 1'
                ).fetchone()
                val = row[0] if row else (fill_value if fill_value is not None else "未知")
            else:
                val = fill_value if fill_value is not None else "未知"
            try:
                db.conn.execute(
                    f'UPDATE "{cleaned}" SET "{column}" = ? WHERE {empty_cond}', [val]
                )
            except Exception:
                # 数值列塞字符串会失败 → 退化为 0
                val = 0
                db.conn.execute(
                    f'UPDATE "{cleaned}" SET "{column}" = ? WHERE {empty_cond}', [val]
                )
            filled = db.conn.execute(
                f'SELECT COUNT(*) FROM "{cleaned}" WHERE "{column}" IS NOT NULL'
            ).fetchone()[0]
            return {"ok": True, "action": strategy, "value": val, "filled": filled}

        return {"ok": False, "error": f"暂不支持的处理方式：{strategy}"}

    @staticmethod
    def _execute_chart_fix(
        params: Dict[str, Any],
        current_config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        图表问题诊断 + 修复（AI 对话用，真修复不是话术）

        - 未给 fix_strategy：诊断「图为什么是空的」，说清真实原因 + 给出可选处理方案让用户选
        - 给了 fix_strategy：在清洗层真实执行修复，并让前端刷新图表数据
        """
        charts = list((current_config or {}).get("charts") or [])
        chart = ActionExecutor._locate_chart(charts, params)
        if chart is None:
            names = "、".join([c.get("title") or "未命名" for c in charts[:8]])
            return {
                "success": False,
                "action_type": "chart_fix",
                "new_config": current_config,
                "render_updates": [],
                "message": f"没定位到你说的是哪张图。当前看板有：{names}。请告诉我是哪一张。",
            }

        title = chart.get("title") or "该图表"
        dataset_id = (
            chart.get("dataset_id")
            or (context or {}).get("dataset_id")
            or params.get("dataset_id")
        )
        need_fields = [
            chart.get(k) for k in ("category_field", "x_field", "y_field", "value_field")
            if chart.get(k)
        ]
        fix_strategy = (params.get("fix_strategy") or "").strip()

        # ---------- 诊断：到底为什么没数据 ----------
        cols: List[str] = []
        stats: Dict[str, Dict[str, int]] = {}
        if dataset_id and dataset_id != "default":
            try:
                from app.core.duckdb_manager import get_duckdb
                db = get_duckdb()
                tbl = f"ds_{dataset_id.replace('-', '_')}_cleaned"
                if not db.table_exists(tbl):
                    tbl = f"ds_{dataset_id.replace('-', '_')}"
                if db.table_exists(tbl):
                    cols = [c["name"] for c in db.get_table_info(tbl).get("columns", [])]
                    total = db.conn.execute(f'SELECT COUNT(*) FROM "{tbl}"').fetchone()[0]
                    for f in need_fields:
                        if f in cols:
                            try:
                                nulls = db.conn.execute(
                                    f'SELECT COUNT(*) FROM "{tbl}" WHERE "{f}" IS NULL '
                                    f"OR TRIM(CAST(\"{f}\" AS VARCHAR)) = ''"
                                ).fetchone()[0]
                                stats[f] = {"total": total, "nulls": nulls}
                            except Exception:
                                pass
            except Exception:
                pass

        missing = [f for f in need_fields if cols and f not in cols]
        all_null = [f for f, v in stats.items() if v["total"] and v["nulls"] >= v["total"]]
        part_null = [f for f, v in stats.items() if v["total"] and 0 < v["nulls"] < v["total"]]

        if missing:
            problem = (
                f"「{title}」要用字段「{'、'.join(missing)}」，"
                f"但这个字段不在它的来源数据集里——这是字段选错了，清洗数据修不好。"
            )
            options: List[Dict[str, Any]] = []
            advice = "请到质检页确认列名后重新生成看板；或告诉我改用哪个字段。"
        elif all_null:
            n = stats[all_null[0]]["total"]
            problem = (
                f"「{title}」的字段「{'、'.join(all_null)}」在全部 {n} 行里都是空值，"
                f"聚合后没有任何可画的数据。"
            )
            options = [
                {"strategy": "fill_constant", "label": "空值填成「未知」", "recommended": True,
                 "description": "保留所有行，把空值填成「未知」，图表就能画出来了"},
                {"strategy": "fill_mode", "label": "用出现最多的值填充",
                 "description": "该列无有效值时等价于填「未知」"},
                {"strategy": "drop", "label": "删除该字段为空的行",
                 "description": "整列都空的话删完仍是空的，不推荐"},
            ]
            advice = "你想用哪种方式？回复方案名（比如「填未知」），我就在清洗层执行并刷新图表。"
        elif part_null:
            v = stats[part_null[0]]
            problem = (
                f"「{title}」的字段「{'、'.join(part_null)}」有 {v['nulls']}/{v['total']} 行是空值，"
                f"会影响统计口径。"
            )
            options = [
                {"strategy": "fill_constant", "label": "空值填成「未知」", "recommended": True,
                 "description": "保留行数，空值单独作为一类参与统计"},
                {"strategy": "drop", "label": "删除这些空值行",
                 "description": "统计更干净，但总行数会减少"},
            ]
            advice = "选一种，我立刻执行并刷新图表。"
        else:
            problem = f"「{title}」取不到可绘制数据：来源数据集没有可用的行，或字段值无法聚合。"
            options = [
                {"strategy": "drop", "label": "删除空行后重试",
                 "description": "清理无效行再刷新"},
            ]
            advice = "也可以到质检页修复数据后重新生成看板。"

        # ---------- 用户还没选方案：把问题 + 选项抛回去 ----------
        if not fix_strategy:
            opt_text = ""
            if options:
                opt_text = "\n\n可选处理方案：\n" + "\n".join(
                    [f"{i + 1}. {o['label']}——{o['description']}"
                     + ("（推荐）" if o.get("recommended") else "")
                     for i, o in enumerate(options)]
                )
            return {
                "success": True,
                "action_type": "chart_fix",
                "changes": [],
                "new_config": current_config,
                "render_updates": [{
                    "type": "chart_fix_options",
                    "chart_title": title,
                    "dataset_id": dataset_id,
                    "problem": problem,
                    "options": options,
                }],
                "message": f"查到了原因：{problem}{opt_text}\n\n{advice}",
                "chart_fix_options": options,
                "problem": problem,
            }

        # ---------- 用户已选方案：真执行 ----------
        target_col = (all_null or part_null or need_fields or [None])[0]
        applied: Dict[str, Any] = {"ok": False, "error": "没有可处理的字段"}
        if target_col and dataset_id and dataset_id != "default":
            try:
                applied = ActionExecutor._apply_chart_field_fix(
                    dataset_id, target_col, fix_strategy, params.get("fill_value")
                )
            except Exception as e:
                applied = {"ok": False, "error": str(e)}

        if not applied.get("ok"):
            return {
                "success": False,
                "action_type": "chart_fix",
                "new_config": current_config,
                "render_updates": [],
                "message": f"修复没成功：{applied.get('error') or '未知原因'}。{advice}",
            }

        # 记录到看板配置，便于回溯
        log = current_config.setdefault("chart_fix_log", [])
        log.append({
            "chart_title": title, "dataset_id": dataset_id,
            "column": target_col, "strategy": fix_strategy, "result": applied,
        })

        if fix_strategy == "drop":
            summary = f"已删除「{target_col}」为空的行：{applied.get('before')} → {applied.get('after')} 行"
        else:
            summary = (f"已把「{target_col}」的空值填充为「{applied.get('value')}」，"
                       f"共处理 {applied.get('filled', 0)} 行")

        return {
            "success": True,
            "action_type": "chart_fix",
            "changes": [{"chart_title": title, "column": target_col,
                         "strategy": fix_strategy, "result": applied}],
            "new_config": current_config,
            "render_updates": [{
                "type": "chart_fixed",
                "chart_title": title,
                "dataset_id": dataset_id,
                "column": target_col,
                "strategy": fix_strategy,
                "result": applied,
            }],
            # 关键：让前端重新拉图表数据（清洗层已改，刷新即可见）
            "refresh_chart_data": True,
            "message": f"{summary}。图表「{title}」已按修复后的数据刷新。",
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