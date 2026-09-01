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
    """六层血缘层级"""
    SOURCE = "source"           # 原始数据层（文件）
    FIELD = "field"             # 字段标准化层（dataset字段）
    CLEAN = "clean"             # 数据清洗层（清洗规则）
    BUSINESS = "business"       # 业务加工层（口径）
    AGG = "agg"                 # 聚合计算层
    CHART = "chart"             # 看板输出层


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
        
        # ===== Layer 1: Source (原始数据层) =====
        source_node = None
        if file_id:
            file_result = await db.execute(select(File).where(File.id == file_id))
            file = file_result.scalar_one_or_none()
            if file:
                source_node = LineageNodeData(
                    id=str(uuid.uuid4()),
                    node_type=LineageLevel.SOURCE.value,
                    ref_id=file_id,
                    name=file.name,
                    description=f"原始文件: {file.mime_type or file.extension}",
                    logic_json={"mime_type": file.mime_type, "size": file.size, "extension": file.extension}
                )
                nodes.append(source_node)
                layer_nodes[LineageLevel.SOURCE.value].append(source_node)
        
        # ===== Layer 2: Field (字段标准化层) =====
        field_node = LineageNodeData(
            id=str(uuid.uuid4()),
            node_type=LineageLevel.FIELD.value,
            ref_id=dataset_id,
            name=dataset.name or f"Dataset_{dataset_id[:8]}",
            description=f"数据集: {dataset.grain}粒度",
            logic_json={
                "grain": dataset.grain,
                "row_count": dataset.row_count,
                "schema": dataset.schema_json
            }
        )
        nodes.append(field_node)
        layer_nodes[LineageLevel.FIELD.value].append(field_node)
        
        # 连接: source → field
        if source_node:
            edges.append(LineageEdgeData(
                id=str(uuid.uuid4()),
                source_id=source_node.id,
                target_id=field_node.id,
                transform_type="direct",
                description="文件导入为数据集"
            ))
        
        # ===== Layer 3: Clean (数据清洗层) =====
        clean_result = await db.execute(
            select(CleanRule).where(CleanRule.dataset_id == dataset_id)
        )
        clean_rules = clean_result.scalars().all()
        
        clean_nodes = []
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
            
            # 连接: field → clean
            edges.append(LineageEdgeData(
                id=str(uuid.uuid4()),
                source_id=field_node.id,
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
        
        # ===== Layer 5: Agg (聚合计算层) =====
        chart_result = await db.execute(
            select(Chart).where(Chart.dataset_id == dataset_id)
        )
        charts = chart_result.scalars().all()
        
        agg_nodes = []
        for chart in charts:
            # 从图表配置中提取聚合描述
            config = chart.config_json or {}
            agg_desc = "聚合计算"
            if config.get("aggregate"):
                agg_desc = f"{config['aggregate']}({config.get('y', config.get('kpi', ''))})"
            elif config.get("kpi"):
                agg_desc = f"汇总({config['kpi']})"
            elif config.get("measure"):
                agg_desc = f"聚合({config['measure']})"
            
            agg_node = LineageNodeData(
                id=str(uuid.uuid4()),
                node_type=LineageLevel.AGG.value,
                ref_id=f"{chart.id}_agg",
                name=f"聚合: {chart.title}",
                description=agg_desc,
                logic_json={
                    "chart_ref": chart.id,
                    "chart_type": chart.type,
                    "config": config
                }
            )
            nodes.append(agg_node)
            layer_nodes[LineageLevel.AGG.value].append(agg_node)
            agg_nodes.append((agg_node, chart, config))
            
            # 连接: business → agg（匹配业务节点到聚合节点）
            referenced_fields = set()
            for val in config.values():
                if isinstance(val, str):
                    referenced_fields.add(val)
            
            matched_biz = [b for b in biz_nodes
                          if any(f in b.name for f in referenced_fields)]
            
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
                        description=f"聚合计算"
                    ))
            else:
                edges.append(LineageEdgeData(
                    id=str(uuid.uuid4()),
                    source_id=field_node.id,
                    target_id=agg_node.id,
                    transform_type="aggregate",
                    description=f"聚合计算: {agg_desc}"
                ))
        
        # ===== Layer 6: Chart (看板输出层) =====
        for agg_node, chart, config in agg_nodes:
            chart_node = LineageNodeData(
                id=str(uuid.uuid4()),
                node_type=LineageLevel.CHART.value,
                ref_id=chart.id,
                name=chart.title or f"图表_{chart.id[:8]}",
                description=f"{chart.type}图表",
                logic_json={
                    "chart_type": chart.type,
                    "config": config
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
                description=f"聚合结果输出为{chart.type}图表"
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
        dataset_id: str
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
                "quality_flag": node.quality_flag
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
                    "quality_flag": n.quality_flag
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