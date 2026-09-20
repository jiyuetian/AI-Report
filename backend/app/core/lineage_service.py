"""
血缘服务 - M4-01
六层血缘构建：原始数据层 → 字段标准化层 → 数据清洗层 → 业务加工层 → 聚合计算层 → 看板输出层
重算验证：误差=0
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete
import uuid
import json
import re

from app.models.lineage import LineageNode, LineageEdge
from app.models.file import File
from app.models.dataset import Dataset
from app.models.quality import QualityIssue, CleanRule
from app.models.chart import Chart
from app.models.dashboard import Dashboard


class LineageLevel(Enum):
    """血缘层级（对齐原型六列：①数据源→②数据表→③字段→④清洗规则→⑤计算逻辑→⑥指标/图表）"""
    SOURCE = "source"           # ① 数据源（文件）
    TABLE = "table"             # ② 数据表（贴源表 + 清洗表）
    FIELD = "field"             # ③ 字段（逐字段节点）
    CLEAN = "clean"             # ④ 清洗规则
    BUSINESS = "business"       # ⑤ 计算逻辑（口径 / 派生公式）
    AGG = "agg"                 # ⑤ 计算逻辑（聚合）
    CHART = "chart"             # ⑥ 指标 / 图表


@dataclass
class LineageNodeData:
    """血缘节点数据"""
    id: str
    node_type: str
    ref_id: str
    name: str
    description: str = ""
    logic_json: Dict = None
    quality_flag: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "node_type": self.node_type,
            "ref_id": self.ref_id,
            "name": self.name,
            "description": self.description,
            "logic_json": self.logic_json or {},
            "quality_flag": self.quality_flag
        }


@dataclass
class LineageEdgeData:
    """血缘边数据"""
    id: str
    source_id: str
    target_id: str
    transform_type: str
    description: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "transform_type": self.transform_type,
            "description": self.description
        }


class LineageService:
    """血缘服务"""
    
    @staticmethod
    async def build_lineage_for_dataset(
        db: AsyncSession,
        dataset_id: str,
        file_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        为数据集构建六层血缘（逐层连接，无跨层跳跃）
        
        层级关系：
        1. source (原始数据层) → 2. field (字段标准化层) → 3. clean (数据清洗层)
           → 4. business (业务加工层) → 5. agg (聚合计算层) → 6. chart (看板输出层)
        """
        nodes = []
        edges = []
        layer_nodes = {level.value: [] for level in LineageLevel}
        
        # 获取数据集信息
        result = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
        dataset = result.scalar_one_or_none()
        if not dataset:
            raise ValueError(f"数据集不存在: {dataset_id}")

        # 注意：本函数只做"内存构建"，不写库。删除旧节点由 save_lineage_to_db
        # 在保存时原子完成（先删后插）。此前这里曾先 delete+commit，导致只调用
        # build 不 save 的路径（如 verify 一致性比对）把已存血缘永久清空——已移除。
        
        # ===== Layer 1: Source (原始数据层) =====
        source_node = None
        if not file_id and getattr(dataset, "file_id", None):
            file_id = dataset.file_id
        if file_id:
            file_result = await db.execute(select(File).where(File.id == file_id))
            file = file_result.scalar_one_or_none()
            if file:
                source_node = LineageNodeData(
                    id=str(uuid.uuid4()),
                    node_type=LineageLevel.SOURCE.value,
                    ref_id=file_id,
                    name=file.name or f"文件_{file_id[:8]}",
                    description=f"原始文件: {file.mime_type or file.extension}",
                    logic_json={"mime_type": file.mime_type, "size": file.size, "extension": file.extension}
                )
                nodes.append(source_node)
                layer_nodes[LineageLevel.SOURCE.value].append(source_node)
        
        # ===== Layer 2: Table (数据表层) —— 2026-09-18 对齐原型：贴源表 + 清洗表 =====
        stg_node = LineageNodeData(
            id=str(uuid.uuid4()),
            node_type=LineageLevel.TABLE.value,
            ref_id=dataset_id,
            name=dataset.name or f"数据集_{dataset_id[:8]}",
            description=f"贴源入库 · {dataset.row_count if dataset.row_count is not None else '?'} 行 · 原样上传",
            logic_json={
                "grain": dataset.grain,
                "row_count": dataset.row_count,
                "schema": dataset.schema_json
            }
        )
        nodes.append(stg_node)
        layer_nodes[LineageLevel.TABLE.value].append(stg_node)

        # DuckDB 实查清洗表行数（真实"清洗后 N 行"），失败则降级为无清洗表节点
        clean_tbl_node = None
        _duck = None
        _tbl = None
        try:
            from app.core.duckdb_manager import get_duckdb as _get_duckdb
            _duck = _get_duckdb()
            for _layer in ("cleaned", "raw"):
                _cand = _duck.get_layer_table_name(dataset_id, _layer)
                if _duck.table_exists(_cand):
                    _tbl = _cand
                    break
            if not _tbl:
                _cand = getattr(dataset, "duckdb_table", None) or f"ds_{dataset_id.replace('-', '_')}"
                if _duck.table_exists(_cand):
                    _tbl = _cand
            if _tbl and str(_tbl) != f"ds_{dataset_id.replace('-', '_')}" or (_tbl and "_cleaned" in str(_tbl)):
                _cnt = _duck.conn.execute(f'SELECT COUNT(*) FROM "{_tbl}"').fetchone()[0]
                clean_tbl_node = LineageNodeData(
                    id=str(uuid.uuid4()),
                    node_type=LineageLevel.TABLE.value,
                    ref_id=str(_tbl),
                    name=str(_tbl),
                    description=f"清洗后 {_cnt:,} 行 ✓",
                    logic_json={"table": str(_tbl), "row_count": _cnt, "layer": "cleaned"}
                )
                nodes.append(clean_tbl_node)
                layer_nodes[LineageLevel.TABLE.value].append(clean_tbl_node)
        except Exception as e:
            print(f"[Lineage] 清洗表节点构建降级（不影响血缘）: {e}")

        # 连接: source → table
        if source_node:
            edges.append(LineageEdgeData(
                id=str(uuid.uuid4()),
                source_id=source_node.id,
                target_id=stg_node.id,
                transform_type="direct",
                description="文件导入为数据表"
            ))
        if clean_tbl_node:
            edges.append(LineageEdgeData(
                id=str(uuid.uuid4()),
                source_id=stg_node.id,
                target_id=clean_tbl_node.id,
                transform_type="transform",
                description="清洗加工"
            ))

        # ===== Layer 3: Field (字段层) —— 2026-09-18 对齐原型：逐字段节点 =====
        # 优先展示被图表 / 清洗规则 / 派生指标引用的字段，其余按 schema 顺序补齐
        schema_cols = ((dataset.schema_json or {}).get("columns") or [])
        col_types = {c.get("name"): c.get("type", "") for c in schema_cols if isinstance(c, dict)}
        col_names = [c.get("name") for c in schema_cols if isinstance(c, dict) and c.get("name")]

        # 质检结果 → 字段质量标记（✓ 已修复 / ⚠ 有遗留问题 / * 含估算值）
        field_flags: Dict[str, str] = {}
        try:
            q_rows = (await db.execute(
                select(QualityIssue).where(QualityIssue.dataset_id == dataset_id)
            )).scalars().all()
            for q in q_rows:
                f = getattr(q, "field_name", None)
                if not f:
                    continue
                status = getattr(q, "status", "")
                itype = str(getattr(q, "type", ""))
                if "估算" in itype or "fill" in itype or "median" in itype:
                    field_flags[f] = "* 含估算值"
                if status in ("todo", "pending", "") and f not in field_flags:
                    field_flags[f] = "⚠ 有遗留问题"
                elif status in ("done", "fixed") and f not in field_flags:
                    field_flags[f] = "✓ 已修复"
        except Exception:
            pass

        # 引用优先级：清洗规则目标字段 > 派生指标成分 > 图表维度/度量
        referenced: List[str] = []
        try:
            _cr = (await db.execute(
                select(CleanRule).where(CleanRule.dataset_id == dataset_id)
            )).scalars().all()
        except Exception:
            _cr = []
        for r in _cr:
            if r.target_field and r.target_field not in referenced:
                referenced.append(r.target_field)

        field_nodes = []
        seen_fields = set()

        def _add_field_node(fname: str):
            if not fname or fname in seen_fields or fname not in col_names:
                return
            seen_fields.add(fname)
            ftype = col_types.get(fname, "")
            fnode = LineageNodeData(
                id=str(uuid.uuid4()),
                node_type=LineageLevel.FIELD.value,
                ref_id=f"{dataset_id}_{fname}",
                name=fname,
                description=f"{ftype}字段" if ftype else "标准字段",
                quality_flag=field_flags.get(fname, ""),
                logic_json={"field": fname, "type": ftype}
            )
            nodes.append(fnode)
            layer_nodes[LineageLevel.FIELD.value].append(fnode)
            field_nodes.append(fnode)

        for f in referenced:
            _add_field_node(f)
        # 派生指标成分字段稍后（derived_metrics 在 4b 才识别）会补；这里先按 schema 顺序补齐到 8 个
        for f in col_names:
            if len(field_nodes) >= 8:
                break
            _add_field_node(f)

        # 字段连接来源：清洗表（有则从清洗表引出，体现"清洗后的字段"），否则贴源表
        field_anchor = clean_tbl_node or stg_node
        for fnode in field_nodes:
            edges.append(LineageEdgeData(
                id=str(uuid.uuid4()),
                source_id=field_anchor.id,
                target_id=fnode.id,
                transform_type="direct",
                description="标准化字段"
            ))
        
        # ===== Layer 3: Clean (数据清洗层) =====
        clean_result = await db.execute(
            select(CleanRule).where(CleanRule.dataset_id == dataset_id)
        )
        clean_rules = clean_result.scalars().all()
        
        clean_nodes = []
        # 清洗层：优先数据库清洗规则；无独立规则时抽象管道清洗节点，保证六层链路完整
        if not clean_rules:
            clean_node = LineageNodeData(
                id=str(uuid.uuid4()),
                node_type=LineageLevel.CLEAN.value,
                ref_id=f"{dataset_id}_clean",
                name="清洗/标准化",
                # 2026-09-17：此前是"数据清洗与字段标准化（自动管道）"这种空话，用户看不出做了什么。
                # 没有显式规则就如实说明，并告诉用户在哪里能产生真实记录。
                description="未记录显式清洗规则：数据以入库状态直接进入加工层"
                            "（在质检页执行修复后，这里会登记每一条清洗动作）",
                logic_json={"pipeline": "auto"}
            )
            nodes.append(clean_node)
            layer_nodes[LineageLevel.CLEAN.value].append(clean_node)
            clean_nodes.append(clean_node)
            edges.append(LineageEdgeData(
                id=str(uuid.uuid4()),
                source_id=field_anchor.id,
                target_id=clean_node.id,
                transform_type="transform",
                description="应用清洗管道"
            ))
        for rule in clean_rules:
            rule_type_label = {
                "fill_null": "空值填充",
                "remove_duplicate": "去重处理",
                "format": "格式化",
                "null": "空值处理",
                "duplicate": "去重处理"
            }.get(rule.rule_type, rule.rule_type)
            
            clean_node = LineageNodeData(
                id=str(uuid.uuid4()),
                node_type=LineageLevel.CLEAN.value,
                ref_id=rule.id,
                name=f"清洗: {rule_type_label}",
                description=f"{rule_type_label} · {rule.target_field or '全表'}",
                logic_json={
                    "rule_type": rule.rule_type,
                    "field": rule.target_field,
                    "params": rule.params
                }
            )
            nodes.append(clean_node)
            layer_nodes[LineageLevel.CLEAN.value].append(clean_node)
            clean_nodes.append(clean_node)

            # 连接: 匹配字段 → 清洗规则（对齐原型：R1/R2/R3 挂在具体字段下）；匹配不到再从表引出
            src_for_rule = next(
                (fnode for fnode in field_nodes if fnode.name == rule.target_field),
                field_anchor,
            )
            edges.append(LineageEdgeData(
                id=str(uuid.uuid4()),
                source_id=src_for_rule.id,
                target_id=clean_node.id,
                transform_type="transform",
                description=f"应用清洗规则: {rule_type_label}"
            ))
        
        # ===== Layer 4: Business (业务加工层) =====
        biz_nodes = []
        if dataset.schema_json and "columns" in dataset.schema_json:
            for col in dataset.schema_json["columns"]:
                if col.get("business_logic"):
                    biz_node = LineageNodeData(
                        id=str(uuid.uuid4()),
                        node_type=LineageLevel.BUSINESS.value,
                        ref_id=f"{dataset_id}_{col.get('name')}",
                        name=f"口径: {col.get('name')}",
                        description=col.get("business_logic", ""),
                        logic_json={
                            "field": col.get("name"),
                            "type": col.get("type"),
                            "business_logic": col.get("business_logic")
                        }
                    )
                    nodes.append(biz_node)
                    layer_nodes[LineageLevel.BUSINESS.value].append(biz_node)
                    biz_nodes.append(biz_node)
                    
                    # 连接: clean → business（从所有清洗节点连接到该业务节点）
                    if clean_nodes:
                        for cn in clean_nodes:
                            edges.append(LineageEdgeData(
                                id=str(uuid.uuid4()),
                                source_id=cn.id,
                                target_id=biz_node.id,
                                transform_type="transform",
                                description=f"清洗后应用业务口径: {col.get('name')}"
                            ))
                    else:
                        # 无清洗规则时，直接从 field 连接
                        edges.append(LineageEdgeData(
                            id=str(uuid.uuid4()),
                            source_id=field_node.id,
                            target_id=biz_node.id,
                            transform_type="transform",
                            description=f"定义业务口径: {col.get('name')}"
                        ))
        # ===== Layer 4b: 派生指标（跨列加工公式，如 抵押率 = 贷款金额 ÷ 抵押物评估价值）=====
        # 2026-09-17：业务加工层此前只读取 schema 里的 business_logic（业务上通常为空），
        # 导致「抵押率」这类跨列派生指标在血缘里完全没有加工定义，用户看不出它从哪来。
        # 这里改用真实数据反推：在清洗层上做四则运算校验，命中即把公式写进血缘。
        derived_metrics: List[Dict[str, Any]] = []
        try:
            from app.core.duckdb_manager import get_duckdb as _get_duckdb
            from app.core.derived_metric_service import detect_derived_metrics as _detect
            _duck = _get_duckdb()
            _tbl = None
            for _layer in ("cleaned", "raw"):
                _cand = _duck.get_layer_table_name(dataset_id, _layer)
                if _duck.table_exists(_cand):
                    _tbl = _cand
                    break
            if _tbl is None:
                _cand = getattr(dataset, "duckdb_table", None) or f"ds_{dataset_id.replace('-', '_')}"
                if _duck.table_exists(_cand):
                    _tbl = _cand
            if _tbl:
                _cols = ((dataset.schema_json or {}).get("columns")
                         or _duck.get_table_info(_tbl).get("columns", []))
                derived_metrics = _detect(_duck, _tbl, _cols)
        except Exception as e:
            print(f"[Lineage] 派生指标识别失败（不影响血缘构建）: {e}")

        # 派生指标的分子/分母字段补进字段层（若尚未展示），保证"公式看得见、字段也找得到"
        for dm in derived_metrics:
            for comp in (dm.get("components") or []):
                if comp not in seen_fields and comp in col_names:
                    _n_before = len(field_nodes)
                    _add_field_node(comp)
                    if len(field_nodes) > _n_before:
                        edges.append(LineageEdgeData(
                            id=str(uuid.uuid4()),
                            source_id=field_anchor.id,
                            target_id=field_nodes[-1].id,
                            transform_type="direct",
                            description="标准化字段"
                        ))

        for dm in derived_metrics:
            biz_node = LineageNodeData(
                id=str(uuid.uuid4()),
                node_type=LineageLevel.BUSINESS.value,
                ref_id=f"{dataset_id}_derived_{dm['metric']}",
                name=f"派生指标: {dm['metric']}",
                description=(f"{dm['formula']}（匹配率 {dm['match_ratio']:.0%}，"
                             f"基于 {dm['valid_rows']} 行数据反推校验）"),
                logic_json={
                    "kind": "derived_metric",
                    "metric": dm["metric"],
                    "expression": dm["expression"],
                    "op": dm["op"],
                    "components": dm["components"],
                    "match_ratio": dm["match_ratio"],
                    "valid_rows": dm["valid_rows"],
                    "sample_rows": dm["sample_rows"],
                }
            )
            nodes.append(biz_node)
            layer_nodes[LineageLevel.BUSINESS.value].append(biz_node)
            biz_nodes.append(biz_node)

            # 连接: clean/field → business（派生指标的分子分母来自这些层）
            for sn in (clean_nodes or [field_node]):
                edges.append(LineageEdgeData(
                    id=str(uuid.uuid4()),
                    source_id=sn.id,
                    target_id=biz_node.id,
                    transform_type="transform",
                    description=(f"由「{dm['components'][0]}」与「{dm['components'][1]}」"
                                 f"计算派生指标: {dm['metric']}")
                ))

        if not biz_nodes:
            # 无独立业务口径字段时抽象加工层节点，保证六层链路完整
            biz_node = LineageNodeData(
                id=str(uuid.uuid4()),
                node_type=LineageLevel.BUSINESS.value,
                ref_id=f"{dataset_id}_biz",
                name="业务口径(加工层)",
                # 2026-09-17：同样是空话，如实说明并指向真正有内容的聚合层
                description="未配置自定义业务口径（字段级 business_logic 为空）；"
                            "本数据集的实际加工逻辑见「聚合计算层」",
                logic_json={"pipeline": "business"}
            )
            nodes.append(biz_node)
            layer_nodes[LineageLevel.BUSINESS.value].append(biz_node)
            biz_nodes.append(biz_node)
            for cn in clean_nodes:
                edges.append(LineageEdgeData(
                    id=str(uuid.uuid4()),
                    source_id=cn.id,
                    target_id=biz_node.id,
                    transform_type="transform",
                    description="清洗后定义业务口径"
                ))
            if not clean_nodes:
                edges.append(LineageEdgeData(
                    id=str(uuid.uuid4()),
                    source_id=field_node.id,
                    target_id=biz_node.id,
                    transform_type="transform",
                    description="定义业务口径"
                ))

        # ===== Layer 5: Agg (聚合计算层) =====
        chart_result = await db.execute(
            select(Chart).where(Chart.dataset_id == dataset_id)
        )
        chart_rows = chart_result.scalars().all()
        # 图表来源：优先 charts 表；LLM 生成路径的图表存于 Dashboard.config，从看板兜底读取
        chart_items = []
        for chart in chart_rows:
            chart_items.append({
                "ref_id": chart.id,
                "title": chart.title or f"图表_{str(chart.id)[:8]}",
                "type": chart.type,
                "config": chart.config_json or {}
            })
        if not chart_items:
            # 2026-09-17 修复：多文件看板里本数据集常常不是主数据集，
            # 只按 primary_dataset_id 匹配会漏掉它贡献的图表（血缘链路断在加工层）。
            # 现同时按 primary / dataset_ids / 图表自带 dataset_id 三种方式匹配。
            dash_result = await db.execute(select(Dashboard))
            for dash in dash_result.scalars().all():
                cfg = dash.config or {}
                charts = [c for c in (cfg.get("charts") or []) if isinstance(c, dict)]
                ds_ids = [str(x) for x in (dash.dataset_ids or []) if x]
                owns = (
                    str(dash.primary_dataset_id) == str(dataset_id)
                    or str(dataset_id) in ds_ids
                    or any(str(c.get("dataset_id")) == str(dataset_id) for c in charts)
                )
                if not owns:
                    continue
                for ch in charts:
                    chart_items.append({
                        "ref_id": ch.get("id") or f"chart_{uuid.uuid4().hex[:6]}",
                        "title": ch.get("title", "") or "图表",
                        "type": ch.get("chart_type", "chart"),
                        "config": ch
                    })
        chart_items = chart_items[:10]

        # 派生指标公式索引：聚合层若用到了这些指标，一并标注它们的来源公式
        derived_by_metric = {str(d.get("metric")): d for d in derived_metrics}

        agg_nodes = []
        for cit in chart_items:
            config = cit["config"]
            # 2026-09-17：统一输出"人能读懂的加工公式"，例如
            #   柱状图：按「单位所属行业」分组 → 计数
            #   柱状图：按「贷款类型」分组 → 求和(「贷款金额」)
            # 此前是"聚合(单位所属行业)"这类半截话，用户看不出这一层到底算了什么。
            CTYPE_CN = {"bar": "柱状图", "column": "柱状图", "pie": "饼图", "line": "折线图",
                        "scatter": "散点图", "table": "表格", "kpi": "KPI卡"}
            OP_CN = {"sum": "求和", "count": "计数", "cnt": "计数", "avg": "求平均",
                     "mean": "求平均", "max": "取最大", "min": "取最小"}
            ctype = CTYPE_CN.get(str(cit.get("type") or "").lower(), str(cit.get("type") or "图表"))
            dim = (config.get("category") or config.get("category_field")
                   or config.get("x_field") or config.get("field"))
            val = (config.get("y_field") or config.get("value_field")
                   or config.get("value") or config.get("measure"))
            agg = config.get("aggregate") or config.get("agg")

            if dim and val and str(dim) != str(val):
                op = OP_CN.get(str(agg).lower(), agg or "统计")
                agg_desc = f"{ctype}：按「{dim}」分组 → {op}(「{val}」)"
            elif dim and val:
                agg_desc = f"{ctype}：按「{dim}」分组 → 计数"
            elif val:
                op = OP_CN.get(str(agg).lower(), agg or "汇总")
                agg_desc = f"{ctype}：{op}(「{val}」)"
            elif dim:
                agg_desc = f"{ctype}：按「{dim}」分组统计"
            else:
                agg_desc = f"{ctype}：明细数据展示"

            # 2026-09-17：若聚合用到的字段本身是派生指标（如「抵押率」），必须把它的
            # 加工公式一并写明——否则血缘只显示"求和(抵押率)"，看不出抵押率从哪来
            for _f in (val, dim):
                # 图表自带口径优先（S3 生成时已注入，跨数据集图表也带得过来），
                # 其次用本数据集反推出的公式，保证血缘总能说清这个指标怎么来的
                _dm = ((config.get("derived_metric") if isinstance(
                    config.get("derived_metric"), dict) and
                    str(config["derived_metric"].get("metric")) == str(_f) else None)
                    or (derived_by_metric.get(str(_f)) if _f else None))
                if _dm:
                    agg_desc += f"；其中「{_dm['metric']}」为派生指标：{_dm['expression']}"
                    break

            agg_node = LineageNodeData(
                id=str(uuid.uuid4()),
                node_type=LineageLevel.AGG.value,
                ref_id=f"{cit['ref_id']}_agg",
                name=f"聚合: {cit['title']}",
                description=agg_desc,
                logic_json={
                    "chart_ref": cit["ref_id"],
                    "chart_type": cit["type"],
                    "config": config
                }
            )
            nodes.append(agg_node)
            layer_nodes[LineageLevel.AGG.value].append(agg_node)
            agg_nodes.append((agg_node, cit, config))

            # 连接: business → agg（匹配业务节点到聚合节点）
            referenced_fields = set()
            for val in config.values():
                if isinstance(val, str):
                    referenced_fields.add(val)
            matched_biz = [b for b in biz_nodes if any(f in b.name for f in referenced_fields)]

            if matched_biz:
                for bn in matched_biz:
                    edges.append(LineageEdgeData(
                        id=str(uuid.uuid4()),
                        source_id=bn.id,
                        target_id=agg_node.id,
                        transform_type="aggregate",
                        description=f"按口径聚合: {agg_desc}"
                    ))
            elif biz_nodes:
                for bn in biz_nodes:
                    edges.append(LineageEdgeData(
                        id=str(uuid.uuid4()),
                        source_id=bn.id,
                        target_id=agg_node.id,
                        transform_type="aggregate",
                        description="聚合计算"
                    ))
            else:
                edges.append(LineageEdgeData(
                    id=str(uuid.uuid4()),
                    source_id=clean_nodes[0].id if clean_nodes else field_anchor.id,
                    target_id=agg_node.id,
                    transform_type="aggregate",
                    description=f"聚合计算: {agg_desc}"
                ))
        
        # ===== Layer 6: Chart (看板输出层) =====
        for agg_node, cit, config in agg_nodes:
            # 2026-09-17：此前是"bar图表"这种机器视角描述，改为可审计的输出口径
            _TYPE_CN = {"bar": "柱状图", "column": "柱状图", "pie": "饼图", "line": "折线图",
                        "scatter": "散点图", "table": "表格", "kpi": "KPI卡"}
            _ctype_cn = _TYPE_CN.get(str(cit.get("type") or "").lower(), cit.get("type") or "图表")
            _src_ds = (config or {}).get("dataset_id") or "未记录"
            # KPI 卡实算当前值（DuckDB 清洗层直出，对齐原型"逾期率 0.62%"的节点详情）
            _cur = None
            try:
                if str(cit.get("type")).lower() == "kpi" and _duck is not None and _tbl:
                    _meas = (config.get("y_field") or config.get("value_field")
                             or config.get("measure") or config.get("value"))
                    _agg = str(config.get("aggregate") or config.get("agg") or "sum").lower()
                    if _meas:
                        _func = {"sum": "SUM", "avg": "AVG", "mean": "AVG", "max": "MAX",
                                 "min": "MIN", "count": "COUNT"}.get(_agg, "SUM")
                        _row = _duck.conn.execute(
                            f'SELECT {_func}(TRY_CAST("{_meas}" AS DOUBLE)) FROM "{_tbl}"'
                        ).fetchone()
                        _cur = _row[0] if _row else None
                    else:
                        _row = _duck.conn.execute(f'SELECT COUNT(*) FROM "{_tbl}"').fetchone()
                        _cur = _row[0] if _row else None
            except Exception:
                _cur = None
            _cur_txt = f"｜当前值 {_cur:,.4g}" if isinstance(_cur, (int, float)) else ""
            chart_node = LineageNodeData(
                id=str(uuid.uuid4()),
                node_type=LineageLevel.CHART.value,
                ref_id=cit["ref_id"],
                name=cit["title"] or f"图表_{str(cit['ref_id'])[:8]}",
                description="看板输出：{}（{}）｜来源数据集: {}{}".format(
                    cit.get("title") or "未命名图表", _ctype_cn, _src_ds, _cur_txt
                ),
                logic_json={
                    "chart_type": cit["type"],
                    "config": config,
                    "current_value": _cur
                }
            )
            nodes.append(chart_node)
            layer_nodes[LineageLevel.CHART.value].append(chart_node)
            
            # 连接: agg → chart
            edges.append(LineageEdgeData(
                id=str(uuid.uuid4()),
                source_id=agg_node.id,
                target_id=chart_node.id,
                transform_type="direct",
                description=f"聚合结果输出为{cit['type']}图表"
            ))
        
        return {
            "dataset_id": dataset_id,
            "nodes": [n.to_dict() for n in nodes],
            "edges": [e.to_dict() for e in edges],
            "layer_count": 6,
            "node_count": len(nodes),
            "edge_count": len(edges)
        }
    
    @staticmethod
    async def save_lineage_to_db(
        db: AsyncSession,
        dataset_id: str,
        lineage_data: Dict[str, Any]
    ) -> bool:
        """保存血缘到数据库"""
        try:
            # 先删除该数据集旧的边和节点
            old_nodes_result = await db.execute(
                select(LineageNode).where(LineageNode.dataset_id == dataset_id)
            )
            old_nodes = old_nodes_result.scalars().all()
            old_node_ids = [n.id for n in old_nodes]
            
            # 先删边（SQLite 不支持 CASCADE，需手动清理）
            if old_node_ids:
                await db.execute(
                    delete(LineageEdge).where(
                        LineageEdge.source_id.in_(old_node_ids) |
                        LineageEdge.target_id.in_(old_node_ids)
                    )
                )
            
            # 再删节点
            for node in old_nodes:
                await db.delete(node)
            
            # 保存新节点
            node_id_map = {}  # 临时ID -> 数据库ID
            for node_data in lineage_data["nodes"]:
                node = LineageNode(
                    id=str(uuid.uuid4()),
                    dataset_id=dataset_id,
                    node_type=node_data["node_type"],
                    ref_id=node_data["ref_id"],
                    name=node_data["name"],
                    description=node_data.get("description", ""),
                    logic_json=node_data.get("logic_json", {}),
                    quality_flag=node_data.get("quality_flag", "")
                )
                db.add(node)
                node_id_map[node_data["id"]] = node.id
            
            await db.flush()
            
            # 保存边
            for edge_data in lineage_data["edges"]:
                source_db_id = node_id_map.get(edge_data["source_id"])
                target_db_id = node_id_map.get(edge_data["target_id"])
                
                if source_db_id and target_db_id:
                    edge = LineageEdge(
                        id=str(uuid.uuid4()),
                        source_id=source_db_id,
                        target_id=target_db_id,
                        transform_type=edge_data.get("transform_type", "direct"),
                        description=edge_data.get("description", "")
                    )
                    db.add(edge)
            
            await db.commit()
            return True
            
        except Exception as e:
            await db.rollback()
            raise e
    
    @staticmethod
    async def get_lineage_graph(
        db: AsyncSession,
        dataset_id: str,
        _allow_rebuild: bool = True
    ) -> Dict[str, Any]:
        """获取血缘图谱（用于前端展示）"""
        # 查询所有相关节点（按归属数据集）
        result = await db.execute(
            select(LineageNode).where(LineageNode.dataset_id == dataset_id)
        )
        nodes = result.scalars().all()

        if not nodes:
            return {
                "dataset_id": dataset_id,
                "nodes": [],
                "edges": [],
                "layers": {}
            }

        # 2026-09-18 结构升级自动迁移（修复"最终加工完的一层是空"）：
        #   1) 旧版血缘无 table 层 → 重建补齐；
        #   2) 有看板却无 chart 层 → 血缘建于看板生成之前（旧版在质检/清洗阶段构建），
        #      图表层永久缺失 → 重建补齐。
        # _allow_rebuild 防递归：重建一次后仍缺层就如实返回，不再循环重建。
        if _allow_rebuild:
            types = {n.node_type for n in nodes}
            has_dash = False
            try:
                dash_rows = (await db.execute(select(Dashboard))).scalars().all()
                for _d in dash_rows:
                    _ids = [str(x) for x in (_d.dataset_ids or []) if x]
                    if str(_d.primary_dataset_id) == str(dataset_id) or str(dataset_id) in _ids:
                        has_dash = True
                        break
            except Exception:
                pass
            need_rebuild = ("table" not in types) or (has_dash and "chart" not in types)
            if need_rebuild:
                try:
                    ds_row = (await db.execute(
                        select(Dataset).where(Dataset.id == dataset_id)
                    )).scalar_one_or_none()
                    lineage_data = await LineageService.build_lineage_for_dataset(
                        db, dataset_id, file_id=ds_row.file_id if ds_row else None
                    )
                    # 校验重建结果有效才替换旧数据：防止重建异常（如图表查询失败）时
                    # 把已存的完整血缘覆盖成空，导致"最终层为空"。
                    _built_types = {n.get("node_type") for n in lineage_data.get("nodes", [])}
                    _valid = (
                        len(lineage_data.get("nodes", [])) > 0
                        and (not has_dash or "chart" in _built_types)
                    )
                    if _valid:
                        await LineageService.save_lineage_to_db(db, dataset_id, lineage_data)
                        return await LineageService.get_lineage_graph(db, dataset_id, _allow_rebuild=False)
                    else:
                        print(f"[Lineage] 重建结果无效（节点为空或缺失 chart 层），保留旧血缘: {dataset_id}")
                except Exception as e:
                    print(f"[Lineage] 自动迁移重建失败（返回旧数据）: {e}")

        node_ids = [n.id for n in nodes]
        
        # 查询边
        edge_result = await db.execute(
            select(LineageEdge).where(
                LineageEdge.source_id.in_(node_ids) | 
                LineageEdge.target_id.in_(node_ids)
            )
        )
        edges = edge_result.scalars().all()
        
        # 按层级分组
        layers = {}
        for node in nodes:
            layer = node.node_type
            if layer not in layers:
                layers[layer] = []
            layers[layer].append({
                "id": node.id,
                "name": node.name,
                "type": node.node_type,
                "ref_id": node.ref_id,
                # 2026-09-17：layers 分组此前漏了 description，前端链路视图拿不到加工说明
                "description": node.description,
                "quality_flag": node.quality_flag,
                # 2026-09-18：补充 logic_json（图表类型/KPI 当前值/派生公式/质量标记全在里面），
                # 否则前端链路视图与节点详情面板渲染不出加工明细
                "logic_json": node.logic_json if isinstance(node.logic_json, dict) else {}
            })
        
        return {
            "dataset_id": dataset_id,
            "nodes": [
                {
                    "id": n.id,
                    "name": n.name,
                    "type": n.node_type,
                    "ref_id": n.ref_id,
                    "description": n.description,
                    "quality_flag": n.quality_flag,
                    "logic_json": n.logic_json if isinstance(n.logic_json, dict) else {}
                }
                for n in nodes
            ],
            "edges": [
                {
                    "id": e.id,
                    "source": e.source_id,
                    "target": e.target_id,
                    "transform_type": e.transform_type,
                    "description": e.description
                }
                for e in edges
            ],
            "layers": layers
        }
    
    @staticmethod
    async def verify_lineage_consistency(
        db: AsyncSession,
        dataset_id: str
    ) -> Dict[str, Any]:
        """
        血缘一致性验证（重算比对）
        
        验证逻辑：
        1. 从数据库重新构建血缘
        2. 与现存血缘对比
        3. 计算差异（应为0）
        """
        # 获取现存血缘
        existing = await LineageService.get_lineage_graph(db, dataset_id)
        
        # 重新构建血缘（带上 file_id，保证 source 层一致）
        ds_result = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
        dataset = ds_result.scalar_one_or_none()
        file_id = dataset.file_id if dataset else None
        rebuilt = await LineageService.build_lineage_for_dataset(db, dataset_id, file_id=file_id)
        
        # 对比节点（统一 type / node_type 键名）
        def node_type(n: Dict) -> str:
            return n.get("type") or n.get("node_type") or ""

        existing_nodes = {(n["name"], node_type(n)) for n in existing["nodes"]}
        rebuilt_nodes = {(n["name"], node_type(n)) for n in rebuilt["nodes"]}
        
        # 边对比：按 (源层type → 目标层type, 转换类型) 三元组，
        # 规避 DB ID 与重算临时 UUID 永不匹配导致的误报
        def edges_by_type(nodes: List[Dict], edges: List[Dict]) -> set:
            tmap = {n["id"]: node_type(n) for n in nodes}
            triples = set()
            for e in edges:
                s = tmap.get(e.get("source") or e.get("source_id"))
                t = tmap.get(e.get("target") or e.get("target_id"))
                if s is not None and t is not None:
                    triples.add((s, e.get("transform_type", "direct"), t))
            return triples

        existing_edges = edges_by_type(existing["nodes"], existing["edges"])
        rebuilt_edges = edges_by_type(rebuilt["nodes"], rebuilt["edges"])
        
        # 计算差异
        node_diff = existing_nodes.symmetric_difference(rebuilt_nodes)
        edge_diff = existing_edges.symmetric_difference(rebuilt_edges)
        
        total_diff = len(node_diff) + len(edge_diff)
        
        return {
            "dataset_id": dataset_id,
            "verified": total_diff == 0,
            "error_count": total_diff,
            "node_diff": [{"name": n, "type": t} for n, t in node_diff],
            "edge_diff": [
                {"source_type": s, "transform_type": t, "target_type": tg}
                for s, t, tg in edge_diff
            ],
            "existing_node_count": len(existing["nodes"]),
            "rebuilt_node_count": len(rebuilt["nodes"]),
            "existing_edge_count": len(existing["edges"]),
            "rebuilt_edge_count": len(rebuilt["edges"])
        }
    
    @staticmethod
    async def get_impact_analysis(
        db: AsyncSession,
        node_id: str
    ) -> Dict[str, Any]:
        """影响分析：查询下游影响"""
        # 获取节点信息
        result = await db.execute(
            select(LineageNode).where(LineageNode.id == node_id)
        )
        node = result.scalar_one_or_none()
        
        if not node:
            return {"error": "节点不存在"}
        
        # 递归查询下游节点
        downstream = []
        visited = set()
        
        async def find_downwards(current_id: str, depth: int = 0):
            if depth > 10 or current_id in visited:  # 防止循环
                return
            visited.add(current_id)
            
            edge_result = await db.execute(
                select(LineageEdge).where(LineageEdge.source_id == current_id)
            )
            outgoing = edge_result.scalars().all()
            
            for edge in outgoing:
                target_result = await db.execute(
                    select(LineageNode).where(LineageNode.id == edge.target_id)
                )
                target = target_result.scalar_one_or_none()
                if target:
                    downstream.append({
                        "node_id": target.id,
                        "name": target.name,
                        "type": target.node_type,
                        "depth": depth + 1,
                        "transform": edge.transform_type
                    })
                    await find_downwards(target.id, depth + 1)
        
        await find_downwards(node_id)
        
        return {
            "source_node": {
                "id": node.id,
                "name": node.name,
                "type": node.node_type
            },
            "downstream_count": len(downstream),
            "downstream_nodes": downstream
        }