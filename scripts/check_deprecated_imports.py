# -*- coding: utf-8 -*-
"""Task #714 · 重复版本债防复发（CI 静态门禁）。

1) 扫描 backend/app 下所有 .py 的 import，禁止重新导入已废弃的
   app.core.brain_modules.s3_chart_engine（必须显式用 _v2）。
2) 核验主链路确实引用 _v2（防止有人把权威实现改回死文件）。
不删除任何文件，只做静态断言。
"""
import ast, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "backend", "app")
DEPRECATED = "app.core.brain_modules.s3_chart_engine"
AUTHORITATIVE = "app.core.brain_modules.s3_chart_engine_v2"

def imports_of(path):
    try:
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    except SyntaxError as e:
        return [], ["SYNTAX_ERROR %s: %s" % (path, e)]
    mods, errs = [], []
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            mods.append(n.module)
        elif isinstance(n, ast.Import):
            for a in n.names:
                mods.append(a.name)
    return mods, errs

def main():
    bad, v2_refs = [], 0
    for root, dirs, files in os.walk(APP):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(root, fn)
            mods, errs = imports_of(p)
            bad.extend(errs)
            for m in mods:
                if m == DEPRECATED:
                    bad.append("DEPRECATED_IMPORT %s -> %s" % (os.path.relpath(p, APP), m))
                elif m == AUTHORITATIVE:
                    v2_refs += 1
    print("权威实现 _v2 引用数: %d" % v2_refs)
    print("违规(导入废弃文件/语法错): %d" % len(bad))
    for b in bad:
        print("  ❌", b)
    if v2_refs == 0:
        print("  ❌ 主链路未引用 s3_chart_engine_v2")
        return 1
    if bad:
        return 1
    print("✅ 无废弃文件误引用，主链路仍指向 _v2。")
    return 0

if __name__ == "__main__":
    sys.exit(main())
