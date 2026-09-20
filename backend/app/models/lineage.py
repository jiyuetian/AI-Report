"""血缘模型"""
from sqlalchemy import String, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Dict, Any
from app.models.base import Base


class LineageNode(Base):
    """血缘节点表"""
    __tablename__ = "lineage_nodes"
    
    # 节点类型（6层）: source（原始数据层）/ field（字段标准化层）/ clean（数据清洗层）/ 
    #                   business（业务加工层）/ agg（聚合计算层）/ chart（看板输出层）
    node_type: Mapped[str] = mapped_column(String(30), nullable=False)
    
    # 归属数据集（用于按数据集整取血缘图）
    dataset_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True, default="")
    
    # 关联实体ID（根据node_type对应不同表）
    ref_id: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # 节点名称
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # 节点描述
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # 处理逻辑（JSON）
    logic_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # 质量标记
    quality_flag: Mapped[Optional[str]] = mapped_column(String(50))
    
    # 出边（作为源节点）
    outgoing_edges = relationship("LineageEdge", foreign_keys="LineageEdge.source_id", back_populates="source")
    # 入边（作为目标节点）
    incoming_edges = relationship("LineageEdge", foreign_keys="LineageEdge.target_id", back_populates="target")


class LineageEdge(Base):
    """血缘边表"""
    __tablename__ = "lineage_edges"
    
    # 源节点
    source_id: Mapped[str] = mapped_column(ForeignKey("lineage_nodes.id", ondelete="CASCADE"), nullable=False)
    
    # 目标节点
    target_id: Mapped[str] = mapped_column(ForeignKey("lineage_nodes.id", ondelete="CASCADE"), nullable=False)
    
    # 转换类型: direct（直接映射）/ transform（转换）/ aggregate（聚合）/ filter（过滤）
    transform_type: Mapped[str] = mapped_column(String(30), default="direct")
    
    # 转换说明
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # 关系
    source = relationship("LineageNode", foreign_keys=[source_id], back_populates="outgoing_edges")
    target = relationship("LineageNode", foreign_keys=[target_id], back_populates="incoming_edges")
