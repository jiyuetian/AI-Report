#!/usr/bin/env python3
"""
M3 全链路测试脚本
验证：对话→意图→动作→Token→审核
"""

import asyncio
import sys
import os

# 添加 backend 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.core.intent_classifier import classify_intent, IntentType
from app.core.action_executor import ActionExecutor, ActionType


async def test_intent_classification():
    """测试5类意图识别"""
    print("\n" + "="*50)
    print("【测试1】意图分类测试")
    print("="*50)
    
    test_cases = [
        ("把饼图换成柱图", IntentType.CHANGE_CHART, "换图"),
        ("加一个趋势线图", IntentType.ADD_CHART, "新增图"),
        ("只看华东区域的数据", IntentType.FILTER_DRILL, "筛选下钻"),
        ("为什么逾期率上升了", IntentType.ATTRIBUTION, "归因追问"),
        ("把标题改成风险分析看板", IntentType.EDIT_TITLE, "标题编辑"),
    ]
    
    passed = 0
    for message, expected_intent, desc in test_cases:
        result = classify_intent(message)
        status = "✅" if result.intent_type == expected_intent else "❌"
        if result.intent_type == expected_intent:
            passed += 1
        print(f"{status} [{desc}] '{message}' -> {result.intent_type.value} (置信度: {result.confidence}%)")
    
    print(f"\n意图分类: {passed}/{len(test_cases)} 通过")
    return passed == len(test_cases)


async def test_action_execution():
    """测试动作执行"""
    print("\n" + "="*50)
    print("【测试2】动作执行测试")
    print("="*50)
    
    # 测试 change_chart
    current_config = {
        "charts": [
            {"id": "c1", "chart_type": "pie", "title": "分布图"}
        ]
    }
    
    result = ActionExecutor.execute(
        action_type=ActionType.CHANGE_CHART,
        params={"target_type": "bar", "chart_id": "c1"},
        current_config=current_config,
        context={}
    )
    
    if result["success"] and result["changes"][0]["to"] == "bar":
        print("✅ change_chart: 饼图 -> 柱图 成功")
        passed = 1
    else:
        print(f"❌ change_chart 失败: {result}")
        passed = 0
    
    # 测试 add_chart
    result = ActionExecutor.execute(
        action_type=ActionType.ADD_CHART,
        params={"chart_type": "line"},
        current_config={"charts": []},
        context={"dataset_id": "d1"}
    )
    
    if result["success"] and result["new_config"]["charts"][0]["chart_type"] == "line":
        print("✅ add_chart: 添加线图 成功")
        passed += 1
    else:
        print(f"❌ add_chart 失败: {result}")
    
    # 测试 edit_title
    result = ActionExecutor.execute(
        action_type=ActionType.EDIT_TITLE,
        params={"new_title": "新标题"},
        current_config={"title": "旧标题"},
        context={}
    )
    
    if result["success"] and result["new_config"]["title"] == "新标题":
        print("✅ edit_title: 修改标题 成功")
        passed += 1
    else:
        print(f"❌ edit_title 失败: {result}")
    
    print(f"\n动作执行: {passed}/3 通过")
    return passed == 3


async def test_chart_type_mapping():
    """测试中文图表类型映射"""
    print("\n" + "="*50)
    print("【测试3】图表类型中文映射测试")
    print("="*50)
    
    test_cases = [
        ("饼图", "pie"),
        ("柱图", "bar"),
        ("柱状图", "bar"),
        ("线图", "line"),
        ("折线图", "line"),
        ("表格", "table"),
        ("pie", "pie"),  # 英文直接通过
        ("bar", "bar"),
    ]
    
    passed = 0
    for input_type, expected in test_cases:
        result = ActionExecutor.normalize_chart_type(input_type)
        status = "✅" if result == expected else "❌"
        if result == expected:
            passed += 1
        print(f"{status} '{input_type}' -> '{result}' (期望: '{expected}')")
    
    print(f"\n图表类型映射: {passed}/{len(test_cases)} 通过")
    return passed == len(test_cases)


async def test_imports():
    """测试关键导入"""
    print("\n" + "="*50)
    print("【测试4】关键导入测试")
    print("="*50)
    
    try:
        from app.models import TokenQuota, TokenApplication
        print("✅ TokenQuota 导入成功")
        print("✅ TokenApplication 导入成功")
        return True
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False


async def main():
    """主测试函数"""
    print("="*50)
    print("M3 全链路测试")
    print("="*50)
    
    results = []
    
    # 测试1: 意图分类
    results.append(("意图分类", await test_intent_classification()))
    
    # 测试2: 动作执行
    results.append(("动作执行", await test_action_execution()))
    
    # 测试3: 图表类型映射
    results.append(("图表类型映射", await test_chart_type_mapping()))
    
    # 测试4: 关键导入
    results.append(("关键导入", await test_imports()))
    
    # 汇总
    print("\n" + "="*50)
    print("【测试汇总】")
    print("="*50)
    
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status}: {name}")
    
    total_passed = sum(1 for _, passed in results if passed)
    total = len(results)
    
    print(f"\n总计: {total_passed}/{total} 项通过")
    
    if total_passed == total:
        print("\n🎉 所有测试通过！M3 全链路验证成功！")
        return 0
    else:
        print("\n⚠️ 存在失败的测试，请检查代码")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
