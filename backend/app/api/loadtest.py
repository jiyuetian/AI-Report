"""
压测 API - M5-03
10万行上传解析、20并发对话、图表1万点抽样
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime

from app.core.load_test import LoadTester, run_all_load_tests

router = APIRouter(prefix="/loadtest", tags=["Load Test"])


# 缓存测试结果
_test_cache: Dict[str, Any] = {}


class LoadTestConfig(BaseModel):
    """压测配置"""
    upload_iterations: int = Field(3, description="上传测试迭代次数")
    chat_concurrency: int = Field(20, description="对话并发数")
    chat_requests_per_thread: int = Field(5, description="每线程请求数")
    chart_iterations: int = Field(5, description="图表测试迭代次数")


@router.post("/run")
async def run_load_test(
    background_tasks: BackgroundTasks,
    config: Optional[LoadTestConfig] = None
):
    """
    执行完整压测
    
    三个场景:
    1. 10万行上传解析
    2. 20并发对话
    3. 图表1万点抽样
    
    验收标准:
    - 上传平均耗时 < 30秒
    - 对话P99 < 10秒
    - 图表平均耗时 < 5秒
    """
    try:
        cfg = config or LoadTestConfig()
        
        tester = LoadTester()
        results = []
        
        # 场景1: 10万行上传
        result1 = await tester.test_upload_100k_rows(
            None, 
            iterations=cfg.upload_iterations
        )
        results.append(result1)
        
        # 场景2: 20并发对话
        result2 = await tester.test_concurrent_chat(
            None,
            concurrency=cfg.chat_concurrency,
            requests_per_thread=cfg.chat_requests_per_thread
        )
        results.append(result2)
        
        # 场景3: 图表1万点
        result3 = await tester.test_chart_sampling_10k(
            None,
            iterations=cfg.chart_iterations
        )
        results.append(result3)
        
        # 生成报告
        report = tester.generate_report(results)
        
        # 缓存结果
        report_id = f"loadtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        _test_cache[report_id] = report
        
        return {
            "success": True,
            "report_id": report_id,
            "report": report
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"压测执行失败: {str(e)}")


@router.post("/upload-100k")
async def test_upload_100k(iterations: int = 3):
    """单独测试：10万行上传解析"""
    tester = LoadTester()
    result = await tester.test_upload_100k_rows(None, iterations=iterations)
    
    avg_sec = result.avg_time_ms / 1000
    passed = avg_sec < 30
    
    return {
        "success": result.fail_count == 0,
        "scenario": "10万行上传解析",
        "metrics": {
            "avg_time_sec": round(avg_sec, 1),
            "p99_sec": round(result.p99_ms / 1000, 1),
            "min_sec": round(result.min_time_ms / 1000, 1),
            "max_sec": round(result.max_time_ms / 1000, 1),
            "success_rate": round((result.success_count / result.total_requests) * 100, 1)
        },
        "acceptance": {
            "requirement": "平均耗时 < 30秒",
            "actual": f"{avg_sec:.1f}秒",
            "passed": passed
        }
    }


@router.post("/concurrent-chat")
async def test_concurrent_chat(
    concurrency: int = 20,
    requests_per_thread: int = 5
):
    """单独测试：20并发对话"""
    tester = LoadTester()
    result = await tester.test_concurrent_chat(
        None,
        concurrency=concurrency,
        requests_per_thread=requests_per_thread
    )
    
    p99_sec = result.p99_ms / 1000
    passed = p99_sec < 10
    
    return {
        "success": result.fail_count == 0,
        "scenario": "20并发对话",
        "metrics": {
            "total_requests": result.total_requests,
            "success_count": result.success_count,
            "fail_count": result.fail_count,
            "avg_time_ms": round(result.avg_time_ms, 0),
            "p50_ms": round(result.p50_ms, 0),
            "p95_ms": round(result.p95_ms, 0),
            "p99_ms": round(result.p99_ms, 0),
            "throughput_rps": round(result.throughput_rps, 2)
        },
        "acceptance": {
            "requirement": "P99 < 10秒",
            "actual": f"{p99_sec:.1f}秒",
            "passed": passed
        }
    }


@router.post("/chart-10k")
async def test_chart_10k(iterations: int = 5):
    """单独测试：图表1万点抽样"""
    tester = LoadTester()
    result = await tester.test_chart_sampling_10k(None, iterations=iterations)
    
    avg_sec = result.avg_time_ms / 1000
    passed = avg_sec < 5
    
    return {
        "success": result.fail_count == 0,
        "scenario": "图表1万点抽样",
        "metrics": {
            "avg_time_sec": round(avg_sec, 1),
            "p95_sec": round(result.p95_ms / 1000, 1),
            "p99_sec": round(result.p99_ms / 1000, 1),
            "success_rate": round((result.success_count / result.total_requests) * 100, 1)
        },
        "acceptance": {
            "requirement": "平均耗时 < 5秒",
            "actual": f"{avg_sec:.1f}秒",
            "passed": passed
        }
    }


@router.get("/report/{report_id}")
async def get_loadtest_report(report_id: str):
    """获取压测报告"""
    if report_id not in _test_cache:
        raise HTTPException(status_code=404, detail="报告不存在")
    
    return {
        "success": True,
        "report": _test_cache[report_id]
    }


@router.get("/reports/latest")
async def get_latest_report():
    """获取最新压测报告"""
    if not _test_cache:
        raise HTTPException(status_code=404, detail="暂无压测报告")
    
    latest_id = max(_test_cache.keys())
    return {
        "success": True,
        "report_id": latest_id,
        "report": _test_cache[latest_id]
    }


@router.get("/acceptance-check")
async def check_acceptance():
    """检查验收标准"""
    if not _test_cache:
        return {
            "checked": False,
            "message": "请先执行压测",
            "criteria": {
                "upload_100k": "平均耗时 < 30秒",
                "concurrent_chat": "P99 < 10秒",
                "chart_10k": "平均耗时 < 5秒"
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
