# -*- coding: utf-8 -*-
"""Task #713 · 运行时鉴权断言（CI 门禁，补齐 OpenAPI 静态扫描的盲区）。

auth_scan.py 只看 OpenAPI 的 security 声明，而 internal_endpoint_guard 是普通
Depends，不产生 security 标记 —— 静态扫描无法证明「写端点真的拒绝匿名」。
本脚本直接对 OpenAPI 中所有写操作发无 token 请求，要求 401/403。

用法：
  python scripts/check_auth_runtime.py --base http://127.0.0.1:8000
  python scripts/check_auth_runtime.py --base http://127.0.0.1:8000 --update-expect-secured
退出码：0=全部写端点均拒绝匿名；1=存在匿名可写端点。
"""
import argparse, json, os, re, sys, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
WL_PATH = os.path.join(HERE, "auth_whitelist.json")


def load_json(url=None, path=None):
    if path:
        return json.load(open(path, encoding="utf-8"))
    req = urllib.request.Request(url, headers={"User-Agent": "auth-runtime-check"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def excluded(path, wl):
    if path in wl.get("intentional_public", []):
        return True
    for pref in wl.get("test_prefixes", []):
        if path.startswith(pref):
            return True
    return False


def probe(base, method, path):
    # 路径参数用无害占位；鉴权若生效一定在参数校验/业务逻辑之前返回 401/403
    real = re.sub(r"\{[^}]+\}", "authprobe", path)
    url = base.rstrip("/") + real
    body = b"{}" if method.upper() in ("POST", "PUT", "PATCH") else None
    req = urllib.request.Request(
        url, data=body, method=method.upper(),
        headers={"Content-Type": "application/json", "User-Agent": "auth-runtime-check"},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return "ERR:%s" % type(e).__name__


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--openapi", default=None)
    ap.add_argument("--update-expect-secured", action="store_true",
                    help="把真机验证为已鉴权的写端点写入 expect_secured（只增不删）")
    args = ap.parse_args()

    wl = json.load(open(WL_PATH, encoding="utf-8"))
    spec = load_json(url=args.base + "/openapi.json", path=args.openapi)
    writes = []
    for p, item in spec.get("paths", {}).items():
        for method, op in item.items():
            if method.lower() in ("post", "put", "patch", "delete") and isinstance(op, dict):
                writes.append((method.upper(), p, bool(op.get("security"))))
    checked, failed, secured, static_secured = [], [], [], []
    for method, p, has_sec in writes:
        if excluded(p, wl):
            continue
        st = probe(args.base, method, p)
        rec = (method, p, st)
        checked.append(rec)
        if st in (401, 403):
            secured.append(method + " " + p)
            # 只有「有 security 声明」的端点适合 auth_scan 的静态反向断言；
            # guard 保护的端点静态上永远无 security，交给本脚本的运行时断言即可。
            if has_sec:
                static_secured.append(p)
        else:
            failed.append(rec)

    print("写操作总数: %d  跳过(有意公开/测试桩): %d  实检: %d"
          % (len(writes), len(writes) - len(checked), len(checked)))
    print("拒绝匿名(401/403): %d   匿名可写或异常: %d" % (len(secured), len(failed)))
    print("其中有 security 声明(可做静态反向断言): %d" % len(static_secured))
    if failed:
        print("\n❌ 以下写端点未拒绝匿名请求（CI FAIL）：")
        for m, p, st in failed:
            print("  %-6s %-58s -> %s" % (m, p, st))
    else:
        print("\n✅ 全部实检写端点均拒绝匿名请求。")

    if args.update_expect_secured and not failed:
        # 只增不删：把已闭环的路径合并进 expect_secured
        cur = set(wl.get("expect_secured", []))
        for pth in static_secured:
            cur.add(pth)
        wl["expect_secured"] = sorted(cur)
        with open(WL_PATH, "w", encoding="utf-8") as f:
            json.dump(wl, f, ensure_ascii=False, indent=2)
        print("expect_secured 已更新为 %d 条（known_leak_tracked 保持不动）" % len(cur))

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
