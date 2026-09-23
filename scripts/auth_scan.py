# -*- coding: utf-8 -*-
"""
ISS-025 防复发：OpenAPI 鉴权扫描（CI 门禁）。

逻辑：拉取 /openapi.json，遍历每个 operation 的 security 声明。
- 有 security → 已鉴权，通过。
- 无 security → 必须与白名单匹配，否则判定为「新增无鉴权端点」→ CI FAIL。

白名单（scripts/auth_whitelist.json）三类：
- intentional_public：A 类(有意公开) + C 类(可选鉴权)，允许匿名
- test_prefixes：测试桩前缀（_internal/golden/loadtest/chat-test/quality-debug）
- known_leak_tracked：已知真漏 85 个（ISS-025 跟踪；每修一个从本清单删一个）

当某个 known_leak 被修复（加了鉴权），它不再出现在「无 security」列表，
扫描自然不再校验它；若有人把已修端点又改回匿名，会因不在白名单而 FAIL。
若有人新增一个无鉴权端点且未登记白名单 → FAIL（防复发核心）。

用法：
  python scripts/auth_scan.py --url http://127.0.0.1:8000/openapi.json
  python scripts/auth_scan.py --openapi openapi.json   # 离线文件
退出码：0=全部匹配白名单；1=发现未登记的无鉴权端点（新增越权）。
"""
import argparse
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
WHITELIST_PATH = os.path.join(HERE, "auth_whitelist.json")


def load_whitelist():
    with open(WHITELIST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_openapi(url=None, path=None):
    if path:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    req = urllib.request.Request(url, headers={"User-Agent": "auth_scan"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def is_whitelisted(path, wl):
    if path in wl.get("intentional_public", []):
        return "intentional_public"
    if path in wl.get("known_leak_tracked", []):
        return "known_leak_tracked"
    for pref in wl.get("test_prefixes", []):
        if path.startswith(pref):
            return "test_prefixes"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000/openapi.json")
    ap.add_argument("--openapi", default=None, help="离线 openapi.json 路径")
    args = ap.parse_args()

    wl = load_whitelist()
    spec = load_openapi(url=args.url, path=args.openapi)
    paths = spec.get("paths", {})

    total = 0
    unauth = []
    for p, item in paths.items():
        for method, op in item.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete"):
                continue
            total += 1
            sec = op.get("security")
            if sec:
                continue  # 已鉴权
            unauth.append((method.upper(), p))

    violations = []
    matched = {"intentional_public": 0, "test_prefixes": 0, "known_leak_tracked": 0}
    for method, p in unauth:
        bucket = is_whitelisted(p, wl)
        if bucket:
            matched[bucket] += 1
        else:
            violations.append((method, p))

    print("OpenAPI 操作总数: %d" % total)
    print("无 security 操作数: %d" % len(unauth))
    print("  命中 intentional_public: %d" % matched["intentional_public"])
    print("  命中 test_prefixes:     %d" % matched["test_prefixes"])
    print("  命中 known_leak_tracked:%d" % matched["known_leak_tracked"])
    print("  未登记(新增越权):      %d" % len(violations))

    if violations:
        print("\n❌ 发现未登记的无鉴权端点（ISS-025 新增越权，CI FAIL）：")
        for method, p in sorted(violations, key=lambda x: (x[1], x[0])):
            print("  %-6s %s" % (method, p))
        print("\n处理：要么给该端点加 Depends(get_current_user)，要么确认有意公开后加入 auth_whitelist.json。")
        return 1

    print("\n✅ 全部无鉴权端点均已登记白名单，无新增越权。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
