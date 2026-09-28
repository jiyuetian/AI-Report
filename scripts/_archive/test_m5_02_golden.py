#!/usr/bin/env python3
"""
M5-02 Golden回归测试 - 自测脚本
验证 v2五表 + 10基线 + 5边界 = 20份数据集
验收标准: >80%评分≥70, 匹配度≥80%
"""

import asyncio
import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000/api/v1"


def print_section(title: str):
    """打印章节标题"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def print_result(name: str, passed: bool, detail: str = ""):
    """打印测试结果"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {name:<30} {detail}")


def test_health():
    """健康检查"""
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        return r.status_code == 200
    except:
        return False


def test_list_datasets():
    """测试：获取Golden数据集列表"""
    print_section("1. Golden数据集列表")
    
    try:
        r = requests.get(f"{BASE_URL}/golden/datasets", timeout=10)
        if r.status_code == 200:
            data = r.json()
            total = data.get("total", 0)
            datasets = data.get("datasets", [])
            
            # 统计各类型
            v2_count = len([d for d in datasets if d.get("type") == "v2_schema"])
            base_count = len([d for d in datasets if d.get("type") == "baseline"])
            bound_count = len([d for d in datasets if d.get("type") == "boundary"])
            
            print_result("数据集列表接口", True, f"总计:{total} (v2:{v2_count}, 基线:{base_count}, 边界:{bound_count})")
            
            # 验证数量
            expected_total = 20  # 5+10+5
            if total == expected_total:
                print_result("数据集数量检查", True, f"期望{expected_total}, 实际{total}")
                return True
            else:
                print_result("数据集数量检查", False, f"期望{expected_total}, 实际{total}")
                return False
        else:
            print_result("数据集列表接口", False, f"状态码:{r.status_code}")
            return False
    except Exception as e:
        print_result("数据集列表接口", False, str(e))
        return False


def test_dataset_detail():
    """测试：获取单个数据集详情"""
    print_section("2. 单个数据集详情")
    
    try:
        # 测试v2数据集
        r = requests.get(f"{BASE_URL}/golden/datasets/v2_order", timeout=5)
        if r.status_code == 200:
            data = r.json()
            has_schema = "schema" in data
            has_expected = "expected_charts" in data
            print_result("v2_order详情", has_schema and has_expected, 
                        f"schema:{has_schema}, expected_charts:{has_expected}")
            return True
        else:
            print_result("v2_order详情", False, f"状态码:{r.status_code}")
            return False
    except Exception as e:
        print_result("数据集详情接口", False, str(e))
        return False


def test_stats_summary():
    """测试：统计摘要"""
    print_section("3. 统计摘要")
    
    try:
        r = requests.get(f"{BASE_URL}/golden/stats/summary", timeout=5)
        if r.status_code == 200:
            data = r.json()
            total = data.get("total_datasets", 0)
            breakdown = data.get("breakdown", {})
            
            print_result("统计摘要接口", True, 
                        f"总计:{total}, v2:{breakdown.get('v2_schema',0)}, "
                        f"基线:{breakdown.get('baseline',0)}, 边界:{breakdown.get('boundary',0)}")
            return True
        else:
            print_result("统计摘要接口", False, f"状态码:{r.status_code}")
            return False
    except Exception as e:
        print_result("统计摘要接口", False, str(e))
        return False


def test_run_golden_test():
    """测试：执行完整Golden回归测试"""
    print_section("4. 执行Golden回归测试")
    
    try:
        print("正在执行20份数据集测试，请稍候...")
        r = requests.post(f"{BASE_URL}/golden/run", json={}, timeout=120)
        
        if r.status_code == 200:
            data = r.json()
            if data.get("success"):
                report = data.get("report", {})
                summary = report.get("summary", {})
                metrics = report.get("metrics", {})
                acceptance = report.get("acceptance_criteria", {})
                
                print(f"\n  📊 测试结果:")
                print(f"     总计: {summary.get('total_datasets', 0)} 份")
                print(f"     通过: {summary.get('passed', 0)} 份")
                print(f"     失败: {summary.get('failed', 0)} 份")
                print(f"     通过率: {summary.get('pass_rate', 0)}%")
                
                print(f"\n  📈 核心指标:")
                print(f"     平均匹配度: {metrics.get('average_match_score', 0)}%")
                print(f"     平均质量评分: {metrics.get('average_quality_score', 0)}")
                print(f"     平均耗时: {metrics.get('average_execution_time_ms', 0)}ms")
                
                print(f"\n  ✅ 验收标准检查:")
                quality_check = acceptance.get("quality_70_plus_rate", {})
                match_check = acceptance.get("match_80_plus_rate", {})
                
                quality_passed = quality_check.get("passed", False)
                match_passed = match_check.get("passed", False)
                
                print(f"     评分≥70比例: {quality_check.get('actual', 'N/A')} (要求≥80%) {'✅' if quality_passed else '❌'}")
                print(f"     匹配度≥80比例: {match_check.get('actual', 'N/A')} (要求≥80%) {'✅' if match_passed else '❌'}")
                
                print_result("Golden回归测试", quality_passed and match_passed)
                return quality_passed and match_passed
            else:
                print_result("Golden回归测试", False, "测试未成功完成")
                return False
        else:
            print_result("Golden回归测试", False, f"状态码:{r.status_code}")
            return False
    except Exception as e:
        print_result("Golden回归测试", False, str(e))
        return False


def test_single_dataset():
    """测试：单数据集测试"""
    print_section("5. 单数据集测试")
    
    try:
        r = requests.post(f"{BASE_URL}/golden/run-single/base_001", timeout=30)
        if r.status_code == 200:
            data = r.json()
            success = data.get("success", False)
            match_score = data.get("match_score", 0)
            quality_score = data.get("quality_score", 0)
            
            print_result("单数据集测试", success, 
                        f"匹配度:{match_score}%, 质量:{quality_score}")
            return success
        else:
            print_result("单数据集测试", False, f"状态码:{r.status_code}")
            return False
    except Exception as e:
        print_result("单数据集测试", False, str(e))
        return False


def test_acceptance_check():
    """测试：验收标准检查"""
    print_section("6. 验收标准检查")
    
    try:
        r = requests.get(f"{BASE_URL}/golden/acceptance-check", timeout=5)
        if r.status_code == 200:
            data = r.json()
            checked = data.get("checked", False)
            
            if checked:
                all_passed = data.get("all_passed", False)
                criteria = data.get("criteria", {})
                
                print_result("验收标准检查", all_passed)
                for key, value in criteria.items():
                    passed = value.get("passed", False)
                    print(f"      {'✅' if passed else '❌'} {key}: {value.get('actual', 'N/A')} (要求{value.get('required', 'N/A')})")
                return all_passed
            else:
                print_result("验收标准检查", False, "请先执行Golden测试")
                return False
        else:
            print_result("验收标准检查", False, f"状态码:{r.status_code}")
            return False
    except Exception as e:
        print_result("验收标准检查", False, str(e))
        return False


def main():
    """主测试函数"""
    print("="*60)
    print("M5-02 Golden回归测试 - 自测")
    print("="*60)
    print(f"测试时间: {datetime.now().isoformat()}")
    print(f"测试地址: {BASE_URL}")
    print(f"数据集: v2五表 + 10基线 + 5边界 = 20份")
    print(f"验收标准: >80%评分≥70, 匹配度≥80%")
    
    # 健康检查
    if not test_health():
        print("\n❌ 服务未启动，请先启动后端服务")
        return 1
    print("\n✅ 服务健康检查通过")
    
    # 执行测试
    results = []
    results.append(("数据集列表", test_list_datasets()))
    results.append(("数据集详情", test_dataset_detail()))
    results.append(("统计摘要", test_stats_summary()))
    results.append(("Golden回归测试", test_run_golden_test()))
    results.append(("单数据集测试", test_single_dataset()))
    results.append(("验收标准检查", test_acceptance_check()))
    
    # 汇总
    print("\n" + "="*60)
    print("测试汇总")
    print("="*60)
    
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status}: {name}")
    
    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)
    
    print(f"\n总计: {passed_count}/{total_count} 项通过")
    
    if passed_count == total_count:
        print("\n🎉 M5-02 Golden回归测试自测通过！")
        print("符合验收标准，可以进入 M5-03 压测")
        return 0
    else:
        print(f"\n⚠️ 有 {total_count - passed_count} 项未通过")
        return 1


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
