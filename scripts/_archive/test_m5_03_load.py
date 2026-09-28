#!/usr/bin/env python3
"""
M5-03 压测 - 自测脚本
验证3个压测场景:
1. 10万行上传解析
2. 20并发对话  
3. 图表1万点抽样

验收标准:
- 上传平均耗时 < 30秒
- 对话P99 < 10秒
- 图表平均耗时 < 5秒
"""

import requests
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


def test_upload_100k():
    """测试：10万行上传解析"""
    print_section("场景1: 10万行上传解析")
    
    try:
        print("正在执行10万行上传测试（3次迭代）...")
        r = requests.post(f"{BASE_URL}/loadtest/upload-100k", 
                         params={"iterations": 3}, 
                         timeout=60)
        
        if r.status_code == 200:
            data = r.json()
            metrics = data.get("metrics", {})
            acceptance = data.get("acceptance", {})
            
            print(f"\n  📊 测试结果:")
            print(f"     平均耗时: {metrics.get('avg_time_sec', 0)}秒")
            print(f"     P99: {metrics.get('p99_sec', 0)}秒")
            print(f"     成功率: {metrics.get('success_rate', 0)}%")
            
            print(f"\n  ✅ 验收标准:")
            print(f"     要求: {acceptance.get('requirement', 'N/A')}")
            print(f"     实际: {acceptance.get('actual', 'N/A')}")
            print(f"     结果: {'✅ 通过' if acceptance.get('passed') else '❌ 未通过'}")
            
            passed = acceptance.get("passed", False)
            print_result("10万行上传解析", passed)
            return passed
        else:
            print_result("10万行上传解析", False, f"状态码:{r.status_code}")
            return False
    except Exception as e:
        print_result("10万行上传解析", False, str(e))
        return False


def test_concurrent_chat():
    """测试：20并发对话"""
    print_section("场景2: 20并发对话")
    
    try:
        print("正在执行20并发对话测试（20并发 x 5请求 = 100总请求）...")
        r = requests.post(f"{BASE_URL}/loadtest/concurrent-chat",
                         params={"concurrency": 20, "requests_per_thread": 5},
                         timeout=120)
        
        if r.status_code == 200:
            data = r.json()
            metrics = data.get("metrics", {})
            acceptance = data.get("acceptance", {})
            
            print(f"\n  📊 测试结果:")
            print(f"     总请求: {metrics.get('total_requests', 0)}")
            print(f"     成功: {metrics.get('success_count', 0)}")
            print(f"     失败: {metrics.get('fail_count', 0)}")
            print(f"     平均响应: {metrics.get('avg_time_ms', 0)}ms")
            print(f"     P50: {metrics.get('p50_ms', 0)}ms")
            print(f"     P95: {metrics.get('p95_ms', 0)}ms")
            print(f"     P99: {metrics.get('p99_ms', 0)}ms")
            print(f"     吞吐量: {metrics.get('throughput_rps', 0)} RPS")
            
            print(f"\n  ✅ 验收标准:")
            print(f"     要求: {acceptance.get('requirement', 'N/A')}")
            print(f"     实际: {acceptance.get('actual', 'N/A')}")
            print(f"     结果: {'✅ 通过' if acceptance.get('passed') else '❌ 未通过'}")
            
            passed = acceptance.get("passed", False)
            print_result("20并发对话", passed)
            return passed
        else:
            print_result("20并发对话", False, f"状态码:{r.status_code}")
            return False
    except Exception as e:
        print_result("20并发对话", False, str(e))
        return False


def test_chart_10k():
    """测试：图表1万点抽样"""
    print_section("场景3: 图表1万点抽样")
    
    try:
        print("正在执行图表1万点抽样测试（5次迭代）...")
        r = requests.post(f"{BASE_URL}/loadtest/chart-10k",
                         params={"iterations": 5},
                         timeout=60)
        
        if r.status_code == 200:
            data = r.json()
            metrics = data.get("metrics", {})
            acceptance = data.get("acceptance", {})
            
            print(f"\n  📊 测试结果:")
            print(f"     平均耗时: {metrics.get('avg_time_sec', 0)}秒")
            print(f"     P95: {metrics.get('p95_sec', 0)}秒")
            print(f"     P99: {metrics.get('p99_sec', 0)}秒")
            print(f"     成功率: {metrics.get('success_rate', 0)}%")
            
            print(f"\n  ✅ 验收标准:")
            print(f"     要求: {acceptance.get('requirement', 'N/A')}")
            print(f"     实际: {acceptance.get('actual', 'N/A')}")
            print(f"     结果: {'✅ 通过' if acceptance.get('passed') else '❌ 未通过'}")
            
            passed = acceptance.get("passed", False)
            print_result("图表1万点抽样", passed)
            return passed
        else:
            print_result("图表1万点抽样", False, f"状态码:{r.status_code}")
            return False
    except Exception as e:
        print_result("图表1万点抽样", False, str(e))
        return False


def test_full_loadtest():
    """测试：完整压测流程"""
    print_section("完整压测流程")
    
    try:
        print("正在执行3场景完整压测...")
        r = requests.post(f"{BASE_URL}/loadtest/run", timeout=180)
        
        if r.status_code == 200:
            data = r.json()
            report = data.get("report", {})
            summary = report.get("summary", {})
            criteria = report.get("acceptance_criteria", {})
            
            print(f"\n  📊 总体结果:")
            print(f"     场景数: {summary.get('total_scenarios', 0)}")
            print(f"     全部通过: {'✅' if summary.get('all_passed') else '❌'}")
            
            print(f"\n  ✅ 验收标准检查:")
            for key, value in criteria.items():
                passed = value.get("passed", False)
                print(f"     {'✅' if passed else '❌'} {value.get('description', key)}: "
                      f"{value.get('actual', 'N/A')} (要求{value.get('requirement', 'N/A')})")
            
            all_passed = summary.get("all_passed", False)
            print_result("完整压测流程", all_passed)
            return all_passed
        else:
            print_result("完整压测流程", False, f"状态码:{r.status_code}")
            return False
    except Exception as e:
        print_result("完整压测流程", False, str(e))
        return False


def main():
    """主测试函数"""
    print("="*60)
    print("M5-03 压测 - 自测")
    print("="*60)
    print(f"测试时间: {datetime.now().isoformat()}")
    print(f"测试地址: {BASE_URL}")
    print(f"\n验收标准:")
    print(f"  1. 10万行上传解析: 平均耗时 < 30秒")
    print(f"  2. 20并发对话: P99 < 10秒")
    print(f"  3. 图表1万点抽样: 平均耗时 < 5秒")
    
    # 健康检查
    if not test_health():
        print("\n❌ 服务未启动，请先启动后端服务")
        return 1
    print("\n✅ 服务健康检查通过")
    
    # 执行测试
    results = []
    results.append(("10万行上传解析", test_upload_100k()))
    results.append(("20并发对话", test_concurrent_chat()))
    results.append(("图表1万点抽样", test_chart_10k()))
    results.append(("完整压测流程", test_full_loadtest()))
    
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
        print("\n🎉 M5-03 压测自测通过！")
        print("符合验收标准，可以进入 M5-04 UAT缺陷修复")
        return 0
    else:
        print(f"\n⚠️ 有 {total_count - passed_count} 项未通过")
        print("注意: 压测指标可能受环境性能影响")
        return 1


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
