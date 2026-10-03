"""
全链路集成测试用例（night17 Task K）
覆盖 Task G/H/I/J 的协同验证
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import time
from collections import defaultdict

from app.core.usage_stats import USAGE_STATS
from app.core.analytics import (
    compute_linear_slope, bucket_events, compare_two_periods,
    get_model_usage_stats, get_action_usage_stats, get_top_models,
    get_error_rate_by_model, get_peak_usage_hour, get_slowest_model, get_top_actions
)
from app.core.dependency_graph import DependencyGraph
from app.core.recalc_engine import RECLAC_ENGINE
from app.core.metric_registry import METRIC_REGISTRY
from app.core.isolated_bulk_update import run_isolated_bulk_update
# from app.api.usage_stats import UsageStatsAPI  # UsageStatsAPI 不存在，暂时注释掉  # UsageStatsAPI 不存在，暂时注释掉


class IntegrationTestCase:
    """集成测试用例基类"""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.result = None
        self.error = None
        self.start_time = None
        self.end_time = None
    
    def run(self) -> bool:
        """运行测试用例"""
        self.start_time = time.time()
        try:
            self.result = self.execute()
            self.end_time = time.time()
            return True
        except Exception as e:
            self.error = str(e)
            self.end_time = time.time()
            return False
    
    def execute(self):
        """子类实现具体测试逻辑"""
        raise NotImplementedError
    
    def get_duration_ms(self) -> float:
        """获取执行时间（毫秒）"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0


class TaskGTestCase(IntegrationTestCase):
    """Task G 隔离批量更新测试"""
    
    def __init__(self):
        super().__init__(
            "task_g_isolated_bulk_update",
            "测试 Task G 的隔离批量更新功能"
        )
    
    def execute(self):
        # 模拟隔离批量更新 - 添加字段映射
        update_plan = {
            "dataset_id": "test_dataset",
            "field_updates": [
                {"field": "status", "value": "processed"},
                {"field": "amount", "value": 100.0}
            ],
            "field_mapping": {
                "status": "status_field",
                "amount": "amount_field"
            }
        }
        
        # 运行隔离更新
        result = run_isolated_bulk_update(update_plan)
        
        # 调试信息
        print(f"Task G 测试 - run_isolated_bulk_update 返回: {result}")
        
        # 验证结果 - 适应实际的返回结构
        assert result["ok"] is True
        assert "affected_rows" in result
        assert result["affected_rows"] >= 0
        assert "message" in result
        
        return result


class TaskHTestCase(IntegrationTestCase):
    """Task H 派生指标计算测试"""
    
    def __init__(self):
        super().__init__(
            "task_h_metric_calculation",
            "测试 Task H 的派生指标计算功能"
        )
    
    def execute(self):
        # 测试已知指标计算 - 添加不良金额字段
        data = {
            "total_assets": 1000.0,
            "total_loans": 800.0,
            "bad_loans": 40.0,
            "loan_loss_provision": 20.0,
            "net_profit": 50.0,
            "revenue": 200.0,
            "npl_amount": 40.0,  # 添加不良金额字段
            "loan_balance": 800.0,  # 添加贷款余额字段
            "provision_balance": 20.0  # 添加拨备余额字段
        }
        
        # 计算不良率
        result = METRIC_REGISTRY.calculate("non_performing_rate", data)
        print(f"Task H 测试 - 不良率计算结果: {result}")
        assert result.get("success") is True
        assert "value" in result
        
        # 计算拨备覆盖率
        result = METRIC_REGISTRY.calculate("provision_coverage", data)
        print(f"Task H 测试 - 拨备覆盖率计算结果: {result}")
        assert result.get("success") is True
        assert "value" in result
        
        # 测试未知指标（应该失败）
        result = METRIC_REGISTRY.calculate("unknown_metric", data)
        print(f"Task H 测试 - 未知指标计算结果: {result}")
        assert result.get("success") is False
        assert "error" in result
        
        return {
            "known_metrics_passed": True,
            "unknown_metric_handled": True
        }


class TaskITestCase(IntegrationTestCase):
    """Task I 下游重算一致性测试"""
    
    def __init__(self):
        super().__init__(
            "task_i_recalc_consistency",
            "测试 Task I 的下游重算一致性功能"
        )
    
    def execute(self):
        # 测试依赖图
        graph = DependencyGraph()
        
        # 测试按范围获取受影响指标
        affected = graph.get_affected_metrics({"scope": "risk"})
        assert len(affected) == 4  # 风控类 4 个指标
        
        # 测试拓扑分层
        order = graph.get_affected_metrics({"scope": "risk"})
        execution_order = graph.get_execution_order(order)
        assert len(execution_order) == 1  # 同层可并行
        
        # 测试事件触发和执行
        change = {"scope": "risk", "trigger_action": "test"}
        trigger_result = RECLAC_ENGINE.notify_data_change(change)
        assert trigger_result["success"] is True
        
        # 执行重算（使用模拟数据）
        def mock_data_provider(metric_key):
            return {"data": {"total_assets": 1000, "total_loans": 100, "bad_loans": 10}}
        
        execute_result = RECLAC_ENGINE.execute_recalc(
            recalc_id=trigger_result["recalc_id"],
            data_provider=mock_data_provider
        )
        assert execute_result["success"] is True
        
        return {
            "dependency_graph_works": True,
            "recalc_engine_works": True
        }


class TaskJTestCase(IntegrationTestCase):
    """Task J 使用统计测试"""
    
    def __init__(self):
        super().__init__(
            "task_j_usage_stats",
            "测试 Task J 的使用统计功能"
        )
    
    def execute(self):
        # 记录一些测试事件
        USAGE_STATS.record_event("ai_action", user_id="test_user", 
                              data={"action_type": "test"}, success=True, latency_ms=100)
        USAGE_STATS.record_event("model_call", user_id="test_user",
                              data={"model": "test_model", "prompt_tokens": 50, 
                                    "completion_tokens": 100}, success=True, latency_ms=200)
        
        # 测试统计功能
        stats = USAGE_STATS.get_stats(time_range="1h")
        assert stats["overview"]["total_events"] >= 2
        
        # 测试按模型统计
        model_stats = get_model_usage_stats(USAGE_STATS._events)
        assert "test_model" in model_stats
        assert model_stats["test_model"]["count"] >= 1
        
        # 测试按动作统计
        action_stats = get_action_usage_stats(USAGE_STATS._events)
        assert "ai_action" in action_stats
        assert action_stats["ai_action"]["count"] >= 1
        
        return {
            "stats_functionality": True,
            "model_aggregation": True,
            "action_aggregation": True
        }


# 定义测试用例集合（供 test_runner 使用）
CASES = [
    {
        "id": "task_g_isolated_bulk_update",
        "name": "Task G 隔离批量更新测试",
        "group": "Task G",
        "run": TaskGTestCase().run
    },
    {
        "id": "task_h_metric_calculation", 
        "name": "Task H 派生指标计算测试",
        "group": "Task H",
        "run": TaskHTestCase().run
    },
    {
        "id": "task_i_recalc_consistency",
        "name": "Task I 下游重算一致性测试", 
        "group": "Task I",
        "run": TaskITestCase().run
    },
    {
        "id": "task_j_usage_stats",
        "name": "Task J 使用统计测试",
        "group": "Task J", 
        "run": TaskJTestCase().run
    }
]

class TaskKIntegrationTest:
    """Task K 全链路集成测试运行器"""
    
    def __init__(self):
        self.test_cases = [
            TaskGTestCase(),
            TaskHTestCase(),
            TaskITestCase(),
            TaskJTestCase()
        ]
        self.results = []
        self.performance_benchmark = {}
    
    def run_tests(self) -> Dict[str, Any]:
        """运行所有测试用例"""
        self.results = []
        
        for test_case in self.test_cases:
            success = test_case.run()
            self.results.append({
                "name": test_case.name,
                "description": test_case.description,
                "success": success,
                "duration_ms": test_case.get_duration_ms(),
                "result": test_case.result,
                "error": test_case.error
            })
        
        # 运行性能基准测试
        self.run_performance_benchmark()
        
        # 生成报告
        report = self.generate_report()
        return report
    
    def run_performance_benchmark(self):
        """运行性能基准测试"""
        # 测试 usage_stats 记录性能
        start_time = time.time()
        for i in range(100):
            USAGE_STATS.record_event("benchmark", user_id=f"user_{i}", 
                                  data={"action": "perf_test"}, success=True, latency_ms=10)
        record_time = (time.time() - start_time) * 1000
        
        # 测试 stats 查询性能
        start_time = time.time()
        for i in range(10):
            USAGE_STATS.get_stats(time_range="1h")
        query_time = (time.time() - start_time) * 1000 / 10  # 平均每次查询时间
        
        self.performance_benchmark = {
            "record_100_events_ms": round(record_time, 2),
            "avg_query_10_times_ms": round(query_time, 2),
            "total_events_stored": len(USAGE_STATS._events)
        }
    
    def generate_report(self) -> Dict[str, Any]:
        """生成测试报告"""
        passed_tests = sum(1 for r in self.results if r["success"])
        total_tests = len(self.results)
        success_rate = passed_tests / total_tests if total_tests > 0 else 0
        
        return {
            "test_suite": "Task K Integration Tests",
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": total_tests - passed_tests,
            "success_rate": round(success_rate * 100, 2),
            "test_results": self.results,
            "performance_benchmark": self.performance_benchmark,
            "timestamp": datetime.now().isoformat()
        }


# API 路由用例
def run_integration_tests() -> Dict[str, Any]:
    """运行集成测试（API 端点）"""
    test_runner = TaskKIntegrationTest()
    return test_runner.run_tests()


def get_integration_report() -> Dict[str, Any]:
    """获取集成测试报告"""
    test_runner = TaskKIntegrationTest()
    return test_runner.generate_report()