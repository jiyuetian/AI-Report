"""
血缘 API - M4-01
六层血缘查询 + 重算验证
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.lineage_service import LineageService
from app.models.dataset import Dataset
from app.api.datasets import _assert_dataset_access

router = APIRouter(prefix="/lineage", tags=["Lineage"])


class BuildLineageRequest(BaseModel):
    """构建血缘请求"""
    dataset_id: str = Field(..., description="数据集ID")
    file_id: Optional[str] = Field(None, description="关联文件ID")


class LineageVerifyResponse(BaseModel):
    """血缘验证响应"""
    dataset_id: str
    verified: bool
    error_count: int
    node_diff: List[Dict[str, Any]]
    edge_diff: List[Dict[str, Any]]
    existing_node_count: int
    rebuilt_node_count: int
    existing_edge_count: int
    rebuilt_edge_count: int


class LineageNodeResponse(BaseModel):
    """血缘节点响应"""
    id: str
    name: str
    type: str
    ref_id: str
    description: str = ""
    quality_flag: str = ""
    logic_json: Dict[str, Any] = {}


class LineageEdgeResponse(BaseModel):
    """血缘边响应"""
    id: str
    source: str
    target: str
    transform_type: str
    description: str = ""


class LineageGraphResponse(BaseModel):
    """血缘图谱响应"""
    dataset_id: str
    nodes: List[LineageNodeResponse]
    edges: List[LineageEdgeResponse]
    layers: Dict[str, List[Dict[str, Any]]]


class ImpactAnalysisResponse(BaseModel):
    """影响分析响应"""
    source_node: Dict[str, Any]
    downstream_count: int
    downstream_nodes: List[Dict[str, Any]]


@router.get("/resolve")
async def resolve_default_dataset(db: AsyncSession = Depends(get_db)):
    """解析血缘页默认展示的数据集：最近一个"有看板"的数据集（保证指标/图表层有内容）；
    没有任何看板时退回最近上传的数据集。"""
    from sqlalchemy import select
    from app.models.dataset import Dataset
    from app.models.dashboard import Dashboard

    try:
        dash_rows = (await db.execute(
            select(Dashboard).order_by(Dashboard.created_at.desc())
        )).scalars().all()
        seen = []
        for d in dash_rows:
            ids = [str(x) for x in (d.dataset_ids or []) if x]
            if d.primary_dataset_id:
                ids.append(str(d.primary_dataset_id))
            for dsid in ids:
                if dsid not in seen:
                    seen.append(dsid)
        for dsid in seen:
            ds = (await db.execute(
                select(Dataset).where(Dataset.id == dsid)
            )).scalar_one_or_none()
            if ds:
                return {"dataset_id": ds.id, "name": ds.name, "reason": "latest_with_dashboard"}
    except Exception as e:
        print(f"[Lineage] resolve 看板匹配失败: {e}")

    ds = (await db.execute(
        select(Dataset).order_by(Dataset.created_at.desc())
    )).scalars().first()
    if ds:
        return {"dataset_id": ds.id, "name": ds.name, "reason": "latest_dataset"}
    return {"dataset_id": "", "name": "", "reason": "empty"}


@router.post("/build", response_model=Dict[str, Any])
async def build_lineage(
    request: BuildLineageRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    构建六层血缘
    
    六层结构：
    1. source - 原始数据层（文件）
    2. field - 字段标准化层（dataset字段）
    3. clean - 数据清洗层（清洗规则）
    4. business - 业务加工层（口径定义）
    5. agg - 聚合计算层
    6. chart - 看板输出层（图表）
    """
    try:
        # 构建血缘
        lineage_data = await LineageService.build_lineage_for_dataset(
            db, 
            dataset_id=request.dataset_id,
            file_id=request.file_id
        )
        
        # 保存到数据库
        await LineageService.save_lineage_to_db(db, request.dataset_id, lineage_data)
        
        return {
            "success": True,
            "message": f"血缘构建完成，共{lineage_data['node_count']}个节点，{lineage_data['edge_count']}条边",
            "dataset_id": request.dataset_id,
            "node_count": lineage_data["node_count"],
            "edge_count": lineage_data["edge_count"],
            "layers": ["source", "table", "field", "clean", "business", "agg", "chart"]
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"血缘构建失败: {str(e)}")


@router.get("/graph/{dataset_id}", response_model=LineageGraphResponse)
async def get_lineage_graph(
    dataset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    """获取血缘图谱（用于前端展示）（G3：需登录 + 数据集归属校验）"""
    await _assert_dataset_access(db, dataset_id, current_user)
    graph = await LineageService.get_lineage_graph(db, dataset_id)
    
    if not graph["nodes"]:
        # 如果没有血缘数据，自动构建
        try:
            lineage_data = await LineageService.build_lineage_for_dataset(db, dataset_id)
            await LineageService.save_lineage_to_db(db, dataset_id, lineage_data)
            graph = await LineageService.get_lineage_graph(db, dataset_id)
        except:
            pass
    
    return LineageGraphResponse(**graph)


@router.post("/verify", response_model=LineageVerifyResponse)
async def verify_lineage(
    request: BuildLineageRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    血缘重算验证（误差=0）
    
    验证逻辑：
    1. 从数据库重新构建血缘
    2. 与现存血缘对比
    3. 返回差异统计（应为0）
    """
    try:
        result = await LineageService.verify_lineage_consistency(db, request.dataset_id)
        return LineageVerifyResponse(**result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"验证失败: {str(e)}")


@router.get("/impact/{node_id}", response_model=ImpactAnalysisResponse)
async def get_impact_analysis(
    node_id: str,
    db: AsyncSession = Depends(get_db)
):
    """影响分析：查询指定节点的下游影响"""
    result = await LineageService.get_impact_analysis(db, node_id)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return ImpactAnalysisResponse(**result)


@router.get("/stats/{dataset_id}")
async def get_lineage_stats(
    dataset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    """获取血缘统计信息（G3：需登录 + 数据集归属校验）"""
    await _assert_dataset_access(db, dataset_id, current_user)
    graph = await LineageService.get_lineage_graph(db, dataset_id)
    
    layer_counts = {layer: len(nodes) for layer, nodes in graph["layers"].items()}
    
    return {
        "dataset_id": dataset_id,
        "total_nodes": len(graph["nodes"]),
        "total_edges": len(graph["edges"]),
        "layer_distribution": layer_counts,
        "six_layers_complete": all(layer in layer_counts for layer in ["source", "table", "field", "clean", "business", "chart"])
    }


@router.post("/rebuild-all")
async def rebuild_all_lineage(
    db: AsyncSession = Depends(get_db)
):
    """重建所有数据集的血缘（管理接口）"""
    from sqlalchemy import select
    from app.models.dataset import Dataset
    
    result = await db.execute(select(Dataset))
    datasets = result.scalars().all()
    
    success_count = 0
    failed_count = 0
    
    for dataset in datasets:
        try:
            lineage_data = await LineageService.build_lineage_for_dataset(
                db, dataset.id, dataset.file_id
            )
            await LineageService.save_lineage_to_db(db, dataset.id, lineage_data)
            success_count += 1
        except Exception as e:
            failed_count += 1
    
    return {
        "success": True,
        "message": f"血缘重建完成: {success_count}成功, {failed_count}失败",
        "total": len(datasets),
        "success_count": success_count,
        "failed_count": failed_count
    }