# -*- coding: utf-8 -*-
"""
ISS-025 防复发：前端裸 fetch 扫描（CI 门禁，红线5 同类问题）。

核心判定：交叉比对 OpenAPI。
- 只有「指向已加鉴权后端端点」的裸 fetch（不带 authHeaders）才判 FAIL。
- 指向未加鉴权端点（ISS-025 真漏 backlog / 测试桩 / 公开端点）的裸 fetch 暂不要求，
  待对应后端端点在本轮/后续加固后，扫描会自然转为要求带 token。

这样避免两种误判：
1. 误报：headers 写在 fetch 下一行的正常调用（窗口检查）。
2. 误报：指向未加固后端的调用（尚未要求 token）。

用法：
  python scripts/fe_bare_fetch_scan.py --url http://127.0.0.1:8000/openapi.json
  python scripts/fe_bare_fetch_scan.py --openapi openapi.json
退出码：0=无问题；1=发现裸 fetch 指向已鉴权端点（必须同步带 token）；2=参数/IO 错误。
"""
import argparse
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SRC = os.path.join(HERE, "..", "frontend", "src")

# 前端 URL 模板里出现的动态段标识
TEMPLATE_RE = re.compile(r"\$\{([^}]+)\}")


def load_openapi(url=None, path=None):
    if path:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    req = urllib.request.Request(url, headers={"User-Agent": "fe_scan"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def build_secured(openapi):
    """返回已加鉴权的 (method_upper, path) 集合。"""
    secured = set()
    for p, item in openapi.get("paths", {}).items():
        for method, op in item.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete"):
                continue
            if op.get("security"):
                secured.add((method.upper(), p))
                secured.add(("ANY", p))
    return secured


def resolve_path(url_expr):
    """把前端 fetch URL 表达式归一化为 OpenAPI 路径（含 {param}）。"""
    # 去掉引号与模板前缀
    s = url_expr.strip().strip("`\"'")
    # ${API_BASE} -> /api/v1
    s = s.replace("${API_BASE}", "/api/v1")
    # 其余 ${xxx} -> {param}
    s = TEMPLATE_RE.sub("{param}", s)
    # 归一化：确保以 / 开头
    if not s.startswith("/"):
        s = "/" + s
    return s


def match_secured(path, secured):
    """路径可能含字面 id，尝试逐级回退匹配 OpenAPI 路径。"""
    candidates = [path]
    parts = path.split("/")
    # 回退：把末尾若干段替换为 {param}
    for k in range(1, min(3, len(parts))):
        cand = parts[: len(parts) - k] + ["{param}"] * k
        candidates.append("/".join(cand))
    for c in candidates:
        if ("ANY", c) in secured or (c in {pp for _, pp in secured}):
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--url", default="http://127.0.0.1:8000/openapi.json")
    ap.add_argument("--openapi", default=None)
    args = ap.parse_args()

    src = os.path.abspath(args.src)
    if not os.path.isdir(src):
        print("前端源目录不存在: %s" % src)
        return 2

    try:
        openapi = load_openapi(url=args.url, path=args.openapi)
    except Exception as e:
        print("无法加载 OpenAPI（前端扫描依赖它判断端点是否已鉴权）: %s" % e)
        return 2
    secured = build_secured(openapi)

    fetch_re = re.compile(r"(?<![\w.])fetch\s*\(")
    violations = []
    scanned = 0
    for root, _, files in os.walk(src):
        for fn in files:
            if not fn.endswith((".ts", ".tsx")):
                continue
            fp = os.path.join(root, fn)
            rel = os.path.relpath(fp, src).replace(os.sep, "/")
            if rel.endswith("utils/request.ts"):
                continue  # 封装本体，内部负责带 token
            scanned += 1
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
            for i, line in enumerate(lines):
                if not fetch_re.search(line):
                    continue
                # 跳过整行注释
                stripped = line.lstrip()
                if stripped.startswith("//"):
                    continue
                # 窗口检查：本行 + 后续 3 行是否含 authHeaders
                window = "\n".join(lines[i : i + 4])
                if "authHeaders" in window:
                    continue
                # 提取 fetch 的 URL 表达式（第一个字符串参数）
                m = re.search(r"fetch\s*\(\s*[`\"']([^`\"']*)", line)
                if not m:
                    continue
                url_expr = m.group(1)
                path = resolve_path(url_expr)
                if match_secured(path, secured):
                    violations.append((rel, i + 1, path))

    print("扫描前端源文件: %d 个；已鉴权后端端点数: %d" % (scanned, len(secured)))
    print("裸 fetch 指向已鉴权端点: %d 处" % len(violations))
    if violations:
        print("\n❌ 发现裸 fetch 指向已加鉴权端点（CI FAIL，必须同步带 token）：")
        for rel, i, path in sorted(violations, key=lambda x: (x[0], x[1])):
            print("  %s:%d  -> %s" % (rel, i, path))
        print("\n处理：给该 fetch 的 headers 注入 ...authHeaders() 或追加 { headers: authHeaders() }。")
        return 1
    print("\n✅ 所有指向已鉴权端点的前端调用均已带 token。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
