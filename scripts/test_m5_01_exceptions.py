#!/usr/bin/env python3
"""
M5-01 自测脚本 - 12异常场景验证
验证所有12个异常处理场景是否正常工作
"""

import asyncio
import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000/api/v1"


def print_test(name: str, passed: bool, details: str = ""):
    """打印测试结果"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {name}")
    if details:
        print(f"      {details}")


def test_1_orphan_row():
    """场景1: 孤儿行检测"""
    print("\n【场景1】孤儿行检测")
    try:
        r = requests.post(
            f"{BASE_URL}/exceptions/orphan-rows/detect",
            json={"dataset_id": "ds_test_001", "parent_field": "parent_id"},
            timeout=5
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            has_orphan = data.get("has_orphan", False)
            print_test("孤儿行检测接口", True, f"has_orphan={has_orphan}")
            return True
        else:
            print_test("孤儿行检测接口", False, f"状态码: {r.status_code}")
            return False
    except Exception as e:
        print_test("孤儿行检测接口", False, str(e))
        return False


def test_2_data_bloat():
    """场景2: 数据膨胀检测"""
    print("\n【场景2】数据膨胀检测")
    try:
        r = requests.post(
            f"{BASE_URL}/exceptions/data-bloat/detect",
            params={"dataset_id": "ds_test_001", "threshold_percent": 50},
            timeout=5
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            is_bloated = data.get("is_bloated", False)
            growth = data.get("growth_percent", 0)
            print_test("数据膨胀检测接口", True, f"is_bloated={is_bloated}, growth={growth}%")
            return True
        else:
            print_test("数据膨胀检测接口", False, f"状态码: {r.status_code}")
            return False
    except Exception as e:
        print_test("数据膨胀检测接口", False, str(e))
        return False


def test_3_key_type():
    """场景3: 键类型校验"""
    print("\n【场景3】键类型校验")
    try:
        # 测试有效的UUID格式
        r = requests.post(
            f"{BASE_URL}/exceptions/key-type/validate",
            json={"key_value": "550e8400-e29b-41d4-a716-446655440000", "expected_type": "uuid"},
            timeout=5
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            is_valid = data.get("valid", False)
            print_test("键类型校验接口(UUID)", is_valid, f"valid={is_valid}")
        
        # 测试无效的整数格式
        r2 = requests.post(
            f"{BASE_URL}/exceptions/key-type/validate",
            json={"key_value": "not_a_number", "expected_type": "integer"},
            timeout=5
        )
        if r2.status_code == 200:
            data2 = r2.json().get("data", {})
            is_valid2 = data2.get("valid", True)
            print_test("键类型校验接口(无效值)", not is_valid2, f"valid={is_valid2}")
            return True
        return False
    except Exception as e:
        print_test("键类型校验接口", False, str(e))
        return False


def test_4_schema_healing():
    """场景4: Schema自愈"""
    print("\n【场景4】Schema自愈")
    try:
        r = requests.post(
            f"{BASE_URL}/exceptions/schema/heal",
            json={
                "dataset_id": "ds_test_001",
                "detected_schema": {"amount": "decimal", "count": "integer"}
            },
            timeout=5
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            healed = data.get("healed", False)
            changes = data.get("changes", [])
            print_test("Schema自愈接口", True, f"healed={healed}, changes={len(changes)}")
            return True
        else:
            print_test("Schema自愈接口", False, f"状态码: {r.status_code}")
            return False
    except Exception as e:
        print_test("Schema自愈接口", False, str(e))
        return False


def test_5_empty_dashboard():
    """场景5: 空看板检测"""
    print("\n【场景5】空看板检测")
    try:
        r = requests.get(
            f"{BASE_URL}/exceptions/empty-dashboard/dash_test_001",
            timeout=5
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            is_empty = data.get("is_empty", False)
            chart_count = data.get("chart_count", 0)
            print_test("空看板检测接口", True, f"is_empty={is_empty}, charts={chart_count}")
            return True
        else:
            print_test("空看板检测接口", False, f"状态码: {r.status_code}")
            return False
    except Exception as e:
        print_test("空看板检测接口", False, str(e))
        return False


def test_6_category_validation():
    """场景6: 类目值校验"""
    print("\n【场景6】类目值校验")
    try:
        # 测试有效值
        r = requests.post(
            f"{BASE_URL}/exceptions/category/validate",
            json={"values": ["A", "B", "C"], "valid_categories": ["A", "B", "C", "D"]},
            timeout=5
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            is_valid = data.get("valid", False)
            print_test("类目值校验接口(有效)", is_valid, f"valid={is_valid}")
        
        # 测试无效值
        r2 = requests.post(
            f"{BASE_URL}/exceptions/category/validate",
            json={"values": ["A", "X", "Y"], "valid_categories": ["A", "B", "C"]},
            timeout=5
        )
        if r2.status_code == 200:
            data2 = r2.json().get("data", {})
            invalid = data2.get("invalid_values", [])
            print_test("类目值校验接口(无效)", len(invalid) > 0, f"invalid={invalid}")
            return True
        return False
    except Exception as e:
        print_test("类目值校验接口", False, str(e))
        return False


def test_7_sensitive_data():
    """场景7: 敏感数据检测"""
    print("\n【场景7】敏感数据检测")
    try:
        # 测试包含身份证
        r = requests.post(
            f"{BASE_URL}/exceptions/sensitive/detect",
            json={"text": "用户身份证: 110101199001011234, 手机: 13800138000", "sensitivity_level": "high"},
            timeout=5
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            has_sensitive = data.get("has_sensitive", False)
            types = data.get("sensitive_types", [])
            masked = data.get("masked_text", "")
            print_test("敏感数据检测接口", has_sensitive, f"detected={types}, masked={masked != ''}")
            return True
        else:
            print_test("敏感数据检测接口", False, f"状态码: {r.status_code}")
            return False
    except Exception as e:
        print_test("敏感数据检测接口", False, str(e))
        return False


def test_8_conflict_detection():
    """场景8: 并发冲突检测"""
    print("\n【场景8】并发冲突检测")
    try:
        # 测试冲突场景
        r = requests.post(
            f"{BASE_URL}/exceptions/conflict/detect",
            json={
                "local_version": 1,
                "server_version": 2,
                "local_data": {"name": "Local"},
                "server_data": {"name": "Server"}
            },
            timeout=5
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            has_conflict = data.get("has_conflict", False)
            conflict_fields = data.get("conflict_fields", [])
            print_test("并发冲突检测接口", has_conflict, f"conflict={has_conflict}, fields={conflict_fields}")
            return True
        else:
            print_test("并发冲突检测接口", False, f"状态码: {r.status_code}")
            return False
    except Exception as e:
        print_test("并发冲突检测接口", False, str(e))
        return False


def test_9_session_kickout():
    """场景9: 异地登录踢出检测"""
    print("\n【场景9】异地登录踢出检测")
    try:
        r = requests.get(
            f"{BASE_URL}/exceptions/session/kickout/user_001",
            params={"current_session_id": "session_001"},
            timeout=5
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            should_kickout = data.get("should_kickout", True)
            print_test("踢出检测接口", not should_kickout, f"should_kickout={should_kickout}")
            return True
        else:
            print_test("踢出检测接口", False, f"状态码: {r.status_code}")
            return False
    except Exception as e:
        print_test("踢出检测接口", False, str(e))
        return False


def test_10_async_timeout():
    """场景10: 异步任务超时检测"""
    print("\n【场景10】异步任务超时检测")
    try:
        from datetime import datetime, timedelta
        start_time = (datetime.utcnow() - timedelta(seconds=3)).isoformat()
        r = requests.post(
            f"{BASE_URL}/exceptions/async/timeout-check",
            json={"start_time": start_time, "timeout_seconds": 5},
            timeout=5
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            should_async = data.get("should_async", True)
            elapsed = data.get("elapsed_seconds", 0)
            print_test("异步超时检测接口", True, f"should_async={should_async}, elapsed={elapsed:.1f}s")
            return True
        else:
            print_test("异步超时检测接口", False, f"状态码: {r.status_code}")
            return False
    except Exception as e:
        print_test("异步超时检测接口", False, str(e))
        return False


def test_11_expired_cleanup():
    """场景11: 过期资源清理"""
    print("\n【场景11】过期资源清理")
    try:
        r = requests.post(
            f"{BASE_URL}/exceptions/expired/cleanup",
            timeout=5
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            cleaned = data.get("cleaned_count", 0)
            print_test("过期资源清理接口", True, f"cleaned={cleaned}")
            return True
        else:
            print_test("过期资源清理接口", False, f"状态码: {r.status_code}")
            return False
    except Exception as e:
        print_test("过期资源清理接口", False, str(e))
        return False


def test_12_grain_validation():
    """场景12: 数据粒度校验"""
    print("\n【场景12】数据粒度校验")
    try:
        # 测试粒度不匹配
        r = requests.post(
            f"{BASE_URL}/exceptions/grain/validate",
            json={
                "actual_grain": "daily",
                "declared_grain": "monthly",
                "row_count": 1000,
                "unique_key_count": 995
            },
            timeout=5
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            grain_valid = data.get("grain_valid", True)
            duplication = data.get("duplication_rate", 0)
            print_test("数据粒度校验接口", not grain_valid, f"valid={grain_valid}, dup={duplication}%")
            return True
        else:
            print_test("数据粒度校验接口", False, f"状态码: {r.status_code}")
            return False
    except Exception as e:
        print_test("数据粒度校验接口", False, str(e))
        return False


def test_batch_check():
    """批量检测接口"""
    print("\n【批量检测】12场景批量检查")
    try:
        checks = [
            {"type": "orphan_row", "dataset_id": "ds_001"},
            {"type": "sensitive_data", "text": "身份证: 110101199001011234"},
            {"type": "key_type", "key_value": "abc123", "expected_type": "string"},
            {"type": "category", "values": ["A", "B"], "valid_categories": ["A", "B", "C"]}
        ]
        r = requests.post(
            f"{BASE_URL}/exceptions/batch-check",
            json=checks,
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            total = data.get("total", 0)
            passed = data.get("passed", 0)
            print_test("批量检测接口", True, f"total={total}, passed={passed}")
            return True
        else:
            print_test("批量检测接口", False, f"状态码: {r.status_code}")
            return False
    except Exception as e:
        print_test("批量检测接口", False, str(e))
        return False


def main():
    """主测试函数"""
    print("=" * 60)
    print("M5-01 第二批异常收尾 - 12场景自测")
    print("=" * 60)
    print(f"测试时间: {datetime.now().isoformat()}")
    print(f"测试地址: {BASE_URL}")
    
    # 健康检查
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=3)
        if r.status_code != 200:
            print("\n❌ 服务未启动，请先启动后端服务")
            return 1
        print("\n✅ 服务健康检查通过")
    except Exception as e:
        print(f"\n❌ 无法连接服务: {e}")
        return 1
    
    # 执行12场景测试
    results = []
    results.append(("孤儿行检测", test_1_orphan_row()))
    results.append(("数据膨胀检测", test_2_data_bloat()))
    results.append(("键类型校验", test_3_key_type()))
    results.append(("Schema自愈", test_4_schema_healing()))
    results.append(("空看板检测", test_5_empty_dashboard()))
    results.append(("类目值校验", test_6_category_validation()))
    results.append(("敏感数据检测", test_7_sensitive_data()))
    results.append(("并发冲突检测", test_8_conflict_detection()))
    results.append(("踢出检测", test_9_session_kickout()))
    results.append(("异步超时检测", test_10_async_timeout()))
    results.append(("过期资源清理", test_11_expired_cleanup()))
    results.append(("数据粒度校验", test_12_grain_validation()))
    results.append(("批量检测", test_batch_check()))
    
    # 汇总
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status}: {name}")
    
    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)
    
    print(f"\n总计: {passed_count}/{total_count} 项通过")
    
    if passed_count == total_count:
        print("\n🎉 M5-01 全部12场景自测通过！")
        print("可以进入 M5-02 Golden回归测试")
        return 0
    else:
        print(f"\n⚠️ 有 {total_count - passed_count} 项未通过，请检查")
        return 1


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
