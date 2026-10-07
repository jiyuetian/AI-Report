#!/usr/bin/env python3
"""
API 验证测试脚本
验证 share / exports / admin / lineage 等关键 API
"""

import requests
import json
import sys

BASE_URL = "http://localhost:8000/api/v1"


def test_endpoint(method: str, path: str, data=None, expected_status=200):
    """测试单个端点"""
    url = f"{BASE_URL}{path}"
    try:
        if method == "GET":
            r = requests.get(url, timeout=10)
        elif method == "POST":
            r = requests.post(url, json=data, timeout=10)
        else:
            return False, f"不支持的method: {method}"
        
        success = r.status_code == expected_status
        return success, f"Status: {r.status_code}"
    except Exception as e:
        return False, str(e)


def main():
    print("=" * 60)
    print("API 验证测试")
    print("=" * 60)
    
    tests = [
        # Share API
        ("POST", "/shares/create", {"dashboard_id": "dash_001", "permission": "view", "expires_days": 7}, 200),
        ("GET", "/shares/my/list", None, 200),
        
        # Exports API
        ("POST", "/exports/sync", {"dashboard_id": "dash_001", "format": "pdf"}, 200),
        ("GET", "/exports/my/list", None, 200),
        
        # Admin API
        ("GET", "/admin/stats/overview", None, 200),
        ("GET", "/admin/users", None, 200),
        ("GET", "/admin/quota/stats", None, 200),
        ("GET", "/admin/audit-logs", None, 200),
        ("GET", "/admin/system/health", None, 200),
        
        # Lineage API
        ("POST", "/lineage/build", {"dataset_id": "ds_001"}, 200),
        ("GET", "/lineage/graph/ds_001", None, 200),
        ("POST", "/lineage/verify", {"dataset_id": "ds_001"}, 200),
        
        # Golden API
        ("GET", "/golden/datasets", None, 200),
        ("GET", "/golden/stats/summary", None, 200),
        
        # Loadtest API
        ("POST", "/loadtest/upload-100k", None, 200),
    ]
    
    passed = 0
    failed = 0
    
    for method, path, data, expected in tests:
        success, msg = test_endpoint(method, path, data, expected)
        status = "✅" if success else "❌"
        print(f"{status} {method} {path}: {msg}")
        if success:
            passed += 1
        else:
            failed += 1
    
    print("=" * 60)
    print(f"总计: {passed + failed}, 通过: {passed}, 失败: {failed}")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
