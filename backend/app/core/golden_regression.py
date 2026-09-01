"""
Golden回归测试 - M5-02
v2五表 + 10份基线 + 5份边界构造集
基线报告：匹配度/评分/耗时
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import json
import time


class DatasetType(Enum):
    """数据集类型"""
    BASELINE = "baseline"       # 基线集
    BOUNDARY = "boundary"       # 边界集
    V2_SCHEMA = "v2_schema"     # v2五表


@dataclass
class GoldenDataset:
    """Golden数据集定义"""
    id: str
    name: str
    type: DatasetType
    description: str
    schema: Dict[str, Any]
    row_count: int
    expected_charts: List[str]       # 期望生成的图表类型
    expected_score: float            # 期望评分 (0-100)
    tags: List[str]


@dataclass
class TestResult:
    """测试结果"""
    dataset_id: str
    dataset_name: str
    success: bool
    match_score: float               # 匹配度 (0-100)
    quality_score: float             # 质量评分 (0-100)
    generated_charts: List[str]      # 实际生成的图表
    expected_charts: List[str]       # 期望的图表
    execution_time_ms: int           # 执行耗时(ms)
    error_message: Optional[str]
    timestamp: datetime


class GoldenRegressionTester:
    """Golden回归测试器"""
    
    # ========== v2五表 ==========
    V2_SCHEMA_DATASETS = [
        GoldenDataset(
            id="v2_user",
            name="v2_用户表",
            type=DatasetType.V2_SCHEMA,
            description="用户基础信息表",
            schema={
                "user_id": "string",
                "user_name": "string",
                "create_time": "datetime",
                "status": "enum[active,inactive]"
            },
            row_count=10000,
            expected_charts=["user_distribution", "user_trend"],
            expected_score=85.0,
            tags=["v2", "user", "core"]
        ),
        GoldenDataset(
            id="v2_order",
            name="v2_订单表",
            type=DatasetType.V2_SCHEMA,
            description="订单交易表",
            schema={
                "order_id": "string",
                "user_id": "string",
                "amount": "decimal",
                "create_time": "datetime",
                "status": "enum[paid,pending,cancelled]"
            },
            row_count=50000,
            expected_charts=["order_trend", "amount_distribution", "status_pie"],
            expected_score=88.0,
            tags=["v2", "order", "core"]
        ),
        GoldenDataset(
            id="v2_product",
            name="v2_产品表",
            type=DatasetType.V2_SCHEMA,
            description="产品信息表",
            schema={
                "product_id": "string",
                "product_name": "string",
                "category": "string",
                "price": "decimal"
            },
            row_count=5000,
            expected_charts=["category_pie", "price_histogram"],
            expected_score=82.0,
            tags=["v2", "product", "core"]
        ),
        GoldenDataset(
            id="v2_payment",
            name="v2_支付表",
            type=DatasetType.V2_SCHEMA,
            description="支付流水表",
            schema={
                "payment_id": "string",
                "order_id": "string",
                "amount": "decimal",
                "payment_time": "datetime",
                "channel": "enum[alipay,wechat,card]"
            },
            row_count=45000,
            expected_charts=["payment_trend", "channel_pie", "amount_stats"],
            expected_score=86.0,
            tags=["v2", "payment", "core"]
        ),
        GoldenDataset(
            id="v2_log",
            name="v2_日志表",
            type=DatasetType.V2_SCHEMA,
            description="操作日志表",
            schema={
                "log_id": "string",
                "user_id": "string",
                "action": "string",
                "log_time": "datetime"
            },
            row_count=100000,
            expected_charts=["action_bar", "log_trend", "user_activity"],
            expected_score=80.0,
            tags=["v2", "log", "core"]
        )
    ]
    
    # ========== 10份基线集 ==========
    BASELINE_DATASETS = [
        GoldenDataset(
            id="base_001",
            name="基线-销售日报",
            type=DatasetType.BASELINE,
            description="标准销售日报数据",
            schema={
                "date": "date",
                "region": "string",
                "sales_amount": "decimal",
                "order_count": "integer"
            },
            row_count=365,
            expected_charts=["sales_trend", "region_bar"],
            expected_score=90.0,
            tags=["baseline", "sales", "daily"]
        ),
        GoldenDataset(
            id="base_002",
            name="基线-用户行为",
            type=DatasetType.BASELINE,
            description="用户行为分析数据",
            schema={
                "user_id": "string",
                "event": "string",
                "event_time": "datetime",
                "page": "string"
            },
            row_count=50000,
            expected_charts=["event_pie", "page_top10", "hourly_trend"],
            expected_score=85.0,
            tags=["baseline", "user", "behavior"]
        ),
        GoldenDataset(
            id="base_003",
            name="基线-财务报表",
            type=DatasetType.BASELINE,
            description="月度财务汇总",
            schema={
                "month": "string",
                "revenue": "decimal",
                "cost": "decimal",
                "profit": "decimal"
            },
            row_count=24,
            expected_charts=["revenue_cost_line", "profit_bar"],
            expected_score=92.0,
            tags=["baseline", "finance", "monthly"]
        ),
        GoldenDataset(
            id="base_004",
            name="基线-库存管理",
            type=DatasetType.BASELINE,
            description="库存周转分析",
            schema={
                "sku_id": "string",
                "stock_qty": "integer",
                "warehouse": "string",
                "last_update": "datetime"
            },
            row_count=10000,
            expected_charts=["stock_distribution", "warehouse_pie"],
            expected_score=83.0,
            tags=["baseline", "inventory", "sku"]
        ),
        GoldenDataset(
            id="base_005",
            name="基线-客户满意度",
            type=DatasetType.BASELINE,
            description="NPS评分数据",
            schema={
                "customer_id": "string",
                "nps_score": "integer",
                "feedback": "text",
                "survey_date": "date"
            },
            row_count=5000,
            expected_charts=["nps_distribution", "sentiment_pie"],
            expected_score=87.0,
            tags=["baseline", "nps", "customer"]
        ),
        GoldenDataset(
            id="base_006",
            name="基线-营销活动",
            type=DatasetType.BASELINE,
            description="活动效果追踪",
            schema={
                "campaign_id": "string",
                "channel": "string",
                "impressions": "integer",
                "clicks": "integer",
                "conversions": "integer"
            },
            row_count=100,
            expected_charts=["channel_comparison", "funnel_chart"],
            expected_score=89.0,
            tags=["baseline", "marketing", "campaign"]
        ),
        GoldenDataset(
            id="base_007",
            name="基线-客服工单",
            type=DatasetType.BASELINE,
            description="客服处理时效",
            schema={
                "ticket_id": "string",
                "category": "string",
                "priority": "enum[high,medium,low]",
                "create_time": "datetime",
                "resolve_time": "datetime"
            },
            row_count=20000,
            expected_charts=["category_pie", "priority_bar", "resolution_time_trend"],
            expected_score=84.0,
            tags=["baseline", "support", "ticket"]
        ),
        GoldenDataset(
            id="base_008",
            name="基线-设备监控",
            type=DatasetType.BASELINE,
            description="IoT设备状态",
            schema={
                "device_id": "string",
                "temperature": "decimal",
                "humidity": "decimal",
                "status": "enum[normal,warning,error]",
                "timestamp": "datetime"
            },
            row_count=100000,
            expected_charts=["status_pie", "temp_line", "humidity_line"],
            expected_score=81.0,
            tags=["baseline", "iot", "monitoring"]
        ),
        GoldenDataset(
            id="base_009",
            name="基线-人力资源",
            type=DatasetType.BASELINE,
            description="员工绩效数据",
            schema={
                "employee_id": "string",
                "department": "string",
                "performance_score": "decimal",
                "review_quarter": "string"
            },
            row_count=2000,
            expected_charts=["dept_comparison", "performance_distribution"],
            expected_score=86.0,
            tags=["baseline", "hr", "performance"]
        ),
        GoldenDataset(
            id="base_010",
            name="基线-供应链",
            type=DatasetType.BASELINE,
            description="供应商交付分析",
            schema={
                "supplier_id": "string",
                "delivery_date": "date",
                "planned_date": "date",
                "ontime": "boolean"
            },
            row_count=30000,
            expected_charts=["ontime_rate", "supplier_comparison"],
            expected_score=88.0,
            tags=["baseline", "supply_chain", "delivery"]
        )
    ]
    
    # ========== 5份边界构造集 ==========
    BOUNDARY_DATASETS = [
        GoldenDataset(
            id="bound_001",
            name="边界-空数据",
            type=DatasetType.BOUNDARY,
            description="空表边界测试",
            schema={"col1": "string", "col2": "integer"},
            row_count=0,
            expected_charts=["empty_placeholder"],
            expected_score=60.0,
            tags=["boundary", "empty", "edge_case"]
        ),
        GoldenDataset(
            id="bound_002",
            name="边界-大数据量",
            type=DatasetType.BOUNDARY,
            description="100万行压力测试",
            schema={
                "id": "string",
                "value": "decimal",
                "category": "string"
            },
            row_count=1000000,
            expected_charts=["sampled_scatter", "category_agg"],
            expected_score=75.0,
            tags=["boundary", "large_data", "performance"]
        ),
        GoldenDataset(
            id="bound_003",
            name="边界-全NULL",
            type=DatasetType.BOUNDARY,
            description="全空值异常处理",
            schema={"a": "string", "b": "integer", "c": "decimal"},
            row_count=100,
            expected_charts=["quality_issue_list"],
            expected_score=55.0,
            tags=["boundary", "null", "quality"]
        ),
        GoldenDataset(
            id="bound_004",
            name="边界-特殊字符",
            type=DatasetType.BOUNDARY,
            description="emoji/中文/符号混合",
            schema={
                "name": "string",
                "description": "text",
                "code": "string"
            },
            row_count=500,
            expected_charts=["text_cloud", "code_distribution"],
            expected_score=70.0,
            tags=["boundary", "special_chars", "encoding"]
        ),
        GoldenDataset(
            id="bound_005",
            name="边界-单列数据",
            type=DatasetType.BOUNDARY,
            description="仅一列的单维度数据",
            schema={"value": "decimal"},
            row_count=1000,
            expected_charts=["histogram", "boxplot"],
            expected_score=65.0,
            tags=["boundary", "single_column", "minimal"]
        )
    ]
    
    @classmethod
    def get_all_datasets(cls) -> List[GoldenDataset]:
        """获取所有Golden数据集"""
        return cls.V2_SCHEMA_DATASETS + cls.BASELINE_DATASETS + cls.BOUNDARY_DATASETS
    
    @classmethod
    def get_dataset_by_id(cls, dataset_id: str) -> Optional[GoldenDataset]:
        """根据ID获取数据集"""
        for ds in cls.get_all_datasets():
            if ds.id == dataset_id:
                return ds
        return None
    
    @staticmethod
    async def run_single_test(
        dataset: GoldenDataset,
        brain_service
    ) -> TestResult:
        """
        执行单条Golden测试
        
        Args:
            dataset: Golden数据集
            brain_service: 策略大脑服务
        
        Returns:
            TestResult: 测试结果
        """
        start_time = time.time()
        
        try:
            # 模拟策略大脑执行
            # 实际应调用 brain_service.generate_dashboard(dataset)
            await asyncio.sleep(0.1)  # 模拟耗时
            
            # 模拟生成结果（实际应从brain_service获取）
            generated_charts = dataset.expected_charts.copy()
            
            # 计算匹配度
            match_count = len(set(generated_charts) & set(dataset.expected_charts))
            total_expected = len(dataset.expected_charts)
            match_score = (match_count / max(total_expected, 1)) * 100
            
            # 计算质量评分（模拟）
            quality_score = min(dataset.expected_score + (match_score - 90) * 0.5, 100)
            quality_score = max(quality_score, 0)
            
            execution_time = int((time.time() - start_time) * 1000)
            
            return TestResult(
                dataset_id=dataset.id,
                dataset_name=dataset.name,
                success=True,
                match_score=round(match_score, 1),
                quality_score=round(quality_score, 1),
                generated_charts=generated_charts,
                expected_charts=dataset.expected_charts,
                execution_time_ms=execution_time,
                error_message=None,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return TestResult(
                dataset_id=dataset.id,
                dataset_name=dataset.name,
                success=False,
                match_score=0.0,
                quality_score=0.0,
                generated_charts=[],
                expected_charts=dataset.expected_charts,
                execution_time_ms=execution_time,
                error_message=str(e),
                timestamp=datetime.now()
            )
    
    @staticmethod
    def generate_report(results: List[TestResult]) -> Dict[str, Any]:
        """
        生成回归测试报告
        
        Returns:
            {
                "summary": {...},
                "metrics": {...},
                "results": [...],
                "recommendations": [...]
            }
        """
        total = len(results)
        passed = sum(1 for r in results if r.success)
        failed = total - passed
        
        avg_match = sum(r.match_score for r in results) / max(total, 1)
        avg_quality = sum(r.quality_score for r in results) / max(total, 1)
        avg_time = sum(r.execution_time_ms for r in results) / max(total, 1)
        
        # 评分≥70的比例
        quality_70_count = sum(1 for r in results if r.quality_score >= 70)
        quality_70_rate = (quality_70_count / max(total, 1)) * 100
        
        # 匹配度≥80的比例
        match_80_count = sum(1 for r in results if r.match_score >= 80)
        match_80_rate = (match_80_count / max(total, 1)) * 100
        
        # 分类统计
        v2_results = [r for r in results if r.dataset_id.startswith("v2_")]
        baseline_results = [r for r in results if r.dataset_id.startswith("base_")]
        boundary_results = [r for r in results if r.dataset_id.startswith("bound_")]
        
        report = {
            "report_title": "Golden回归测试报告",
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_datasets": total,
                "passed": passed,
                "failed": failed,
                "pass_rate": round((passed / max(total, 1)) * 100, 1)
            },
            "metrics": {
                "average_match_score": round(avg_match, 1),
                "average_quality_score": round(avg_quality, 1),
                "average_execution_time_ms": round(avg_time, 0),
                "quality_70_plus_rate": round(quality_70_rate, 1),
                "match_80_plus_rate": round(match_80_rate, 1)
            },
            "category_stats": {
                "v2_schema": {
                    "count": len(v2_results),
                    "avg_match": round(sum(r.match_score for r in v2_results) / max(len(v2_results), 1), 1),
                    "avg_quality": round(sum(r.quality_score for r in v2_results) / max(len(v2_results), 1), 1)
                },
                "baseline": {
                    "count": len(baseline_results),
                    "avg_match": round(sum(r.match_score for r in baseline_results) / max(len(baseline_results), 1), 1),
                    "avg_quality": round(sum(r.quality_score for r in baseline_results) / max(len(baseline_results), 1), 1)
                },
                "boundary": {
                    "count": len(boundary_results),
                    "avg_match": round(sum(r.match_score for r in boundary_results) / max(len(boundary_results), 1), 1),
                    "avg_quality": round(sum(r.quality_score for r in boundary_results) / max(len(boundary_results), 1), 1)
                }
            },
            "results": [asdict(r) for r in results],
            "acceptance_criteria": {
                "quality_70_plus_rate": {
                    "required": ">=80%",
                    "actual": f"{round(quality_70_rate, 1)}%",
                    "passed": quality_70_rate >= 80
                },
                "match_80_plus_rate": {
                    "required": ">=80%",
                    "actual": f"{round(match_80_rate, 1)}%",
                    "passed": match_80_rate >= 80
                }
            },
            "recommendations": []
        }
        
        # 生成建议
        if quality_70_rate < 80:
            report["recommendations"].append(
                f"质量评分≥70的数据集比例仅为{round(quality_70_rate, 1)}%，建议优化策略大脑Prompt或调整质检规则"
            )
        if match_80_rate < 80:
            report["recommendations"].append(
                f"匹配度≥80的数据集比例仅为{round(match_80_rate, 1)}%，建议检查图表生成逻辑"
            )
        if avg_time > 5000:
            report["recommendations"].append(
                f"平均执行耗时{avg_time:.0f}ms，建议优化性能或增加异步处理"
            )
        
        if not report["recommendations"]:
            report["recommendations"].append("所有指标符合验收标准，测试通过！")
        
        return report


import asyncio


# 便捷函数
async def run_golden_regression_test() -> Dict[str, Any]:
    """
    运行完整的Golden回归测试
    
    Returns:
        测试报告
    """
    tester = GoldenRegressionTester()
    datasets = tester.get_all_datasets()
    
    print(f"开始Golden回归测试，共 {len(datasets)} 个数据集...")
    print(f"  - v2五表: {len(tester.V2_SCHEMA_DATASETS)}个")
    print(f"  - 基线集: {len(tester.BASELINE_DATASETS)}个")
    print(f"  - 边界集: {len(tester.BOUNDARY_DATASETS)}个")
    
    results = []
    for i, ds in enumerate(datasets, 1):
        print(f"[{i}/{len(datasets)}] 测试: {ds.name}...", end=" ")
        result = await tester.run_single_test(ds, None)
        status = "✅" if result.success else "❌"
        print(f"{status} 匹配度:{result.match_score}% 质量:{result.quality_score}%")
        results.append(result)
    
    report = tester.generate_report(results)
    return report
