"""
Golden回归测试 API - M5-02
v2五表 + 10份基线 + 5份边界构造集
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.golden_regression import (
    GoldenRegressionTester, 
    run_golden_regression_test,
    DatasetType
)

router = APIRouter(prefix="/golden", tags=["Golden Regression"])


# 缓存测试结果
_test_cache: Dict[str, Any] = {}


@router.get("/datasets")
async def list_golden_datasets(
    type: Optional[str] = None,
    tag: Optional[str] = None
):
    """
    获取Golden数据集列表
    
    Query参数:
    - type: v2_schema/baseline/boundary 筛选类型
    - tag: 按标签筛选
    """
    tester = GoldenRegressionTester()
    datasets = tester.get_all_datasets()
    
    # 筛选
    if type:
        datasets = [d for d in datasets if d.type.value == type]
    if tag:
        datasets = [d for d in datasets if tag in d.tags]
    
    return {
        "total": len(datasets),
        "datasets": [
            {
                "id": d.id,
                "name": d.name,
                "type": d.type.value,
                "description": d.description,
                "row_count": d.row_count,
                "expected_score": d.expected_score,
                "expected_charts": d.expected_charts,
                "tags": d.tags
            }
            for d in datasets
        ]
    }


@router.get("/datasets/{dataset_id}")
async def get_golden_dataset_detail(dataset_id: str):
    """获取单个Golden数据集详情"""
    tester = GoldenRegressionTester()
    dataset = tester.get_dataset_by_id(dataset_id)
    
    if not dataset:
        raise HTTPException(status_code=404, detail="数据集不存在")
    
    return {
        "id": dataset.id,
        "name": dataset.name,
        "type": dataset.type.value,
        "description": dataset.description,
        "schema": dataset.schema,
        "row_count": dataset.row_count,
        "expected_score": dataset.expected_score,
        "expected_charts": dataset.expected_charts,
        "tags": dataset.tags
    }


@router.post("/run")
async def run_golden_test(
    background_tasks: BackgroundTasks,
    dataset_ids: Optional[List[str]] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    执行Golden回归测试
    
    参数:
    - dataset_ids: 指定测试的数据集ID列表（为空则测试全部）
    
    返回:
    - 测试报告
    """
    try:
        report = await run_golden_regression_test()
        
        # 缓存结果
        report_id = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        _test_cache[report_id] = report
        
        return {
            "success": True,
            "report_id": report_id,
            "report": report
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"测试执行失败: {str(e)}")


@router.post("/run-single/{dataset_id}")
async def run_single_golden_test(
    dataset_id: str,
    db: AsyncSession = Depends(get_db)
):
    """执行单个Golden数据集测试"""
    tester = GoldenRegressionTester()
    dataset = tester.get_dataset_by_id(dataset_id)
    
    if not dataset:
        raise HTTPException(status_code=404, detail="数据集不存在")
    
    result = await tester.run_single_test(dataset, None)
    
    return {
        "success": result.success,
        "dataset_id": result.dataset_id,
        "dataset_name": result.dataset_name,
        "match_score": result.match_score,
        "quality_score": result.quality_score,
        "execution_time_ms": result.execution_time_ms,
        "expected_charts": result.expected_charts,
        "generated_charts": result.generated_charts,
        "error": result.error_message
    }


@router.get("/report/{report_id}")
async def get_golden_report(report_id: str):
    """获取测试报告"""
    if report_id not in _test_cache:
        raise HTTPException(status_code=404, detail="报告不存在或已过期")
    
    return {
        "success": True,
        "report": _test_cache[report_id]
    }


@router.get("/reports/latest")
async def get_latest_report():
    """获取最新测试报告"""
    if not _test_cache:
        raise HTTPException(status_code=404, detail="暂无测试报告")
    
    latest_id = max(_test_cache.keys())
    return {
        "success": True,
        "report_id": latest_id,
        "report": _test_cache[latest_id]
    }


@router.get("/stats/summary")
async def get_golden_stats_summary():
    """获取Golden测试统计摘要"""
    tester = GoldenRegressionTester()
    all_datasets = tester.get_all_datasets()
    
    v2_count = len([d for d in all_datasets if d.type == DatasetType.V2_SCHEMA])
    baseline_count = len([d for d in all_datasets if d.type == DatasetType.BASELINE])
    boundary_count = len([d for d in all_datasets if d.type == DatasetType.BOUNDARY])
    
    total_rows = sum(d.row_count for d in all_datasets)
    avg_expected_score = sum(d.expected_score for d in all_datasets) / len(all_datasets)
    
    return {
        "total_datasets": len(all_datasets),
        "breakdown": {
            "v2_schema": v2_count,
            "baseline": baseline_count,
            "boundary": boundary_count
        },
        "total_rows": total_rows,
        "avg_expected_score": round(avg_expected_score, 1),
        "chart_types_covered": list(set(
            chart for d in all_datasets for chart in d.expected_charts
        ))
    }


@router.post("/export-report/{report_id}")
async def export_golden_report(report_id: str, format: str = "json"):
    """
    导出测试报告
    
    格式: json/csv/pdf
    """
    if report_id not in _test_cache:
        raise HTTPException(status_code=404, detail="报告不存在")
    
    report = _test_cache[report_id]
    
    if format == "json":
        return {
            "success": True,
            "format": "json",
            "data": report
        }
    elif format == "csv":
        # 生成CSV格式数据
        csv_data = []
        csv_data.append("数据集ID,数据集名称,匹配度,质量评分,耗时(ms),状态")
        for r in report.get("results", []):
            status = "通过" if r.get("success") else "失败"
            csv_data.append(
                f"{r.get('dataset_id')},{r.get('dataset_name')},"
                f"{r.get('match_score')},{r.get('quality_score')},"
                f"{r.get('execution_time_ms')},{status}"
            )
        return {
            "success": True,
            "format": "csv",
            "content": "\n".join(csv_data)
        }
    else:
        raise HTTPException(status_code=400, detail=f"不支持的格式: {format}")


@router.get("/acceptance-check")
async def check_acceptance_criteria():
    """
    检查验收标准
    
    验收标准:
    - >80% 数据集评分≥70
    - 匹配度≥80%
    """
    if not _test_cache:
        return {
            "checked": False,
            "message": "请先执行Golden回归测试",
            "criteria": {
                "quality_70_plus_rate": ">=80%",
                "match_80_plus_rate": ">=80%"
            }
        }
    
    latest_id = max(_test_cache.keys())
    report = _test_cache[latest_id]
    criteria = report.get("acceptance_criteria", {})
    
    all_passed = all(c.get("passed", False) for c in criteria.values())
    
    return {
        "checked": True,
        "all_passed": all_passed,
        "criteria": criteria,
        "report_id": latest_id
    }
