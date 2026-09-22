# -*- coding: utf-8 -*-
"""2.5 P0 真库验证：_compute_field_profiles 在真实 duckdb ds_ 表上算出 distinct/空值率。"""
import sys, os, json
REPO = "C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report"
sys.path.insert(0, os.path.join(REPO, "backend"))

from app.core.duckdb_manager import get_duckdb
from app.api.brain_run_sse import _compute_field_profiles

duck = get_duckdb()
tables = [r[0] for r in duck.conn.execute(
    "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'ds_%' LIMIT 3"
).fetchall()]
print("候选 ds_ 表:", tables)

fails = 0
for t in tables:
    cols = [d[0] for d in duck.conn.execute(f'SELECT * FROM "{t}" LIMIT 0').description]
    if not cols:
        continue
    profs = _compute_field_profiles(duck, t, cols, None)
    ok = isinstance(profs, list) and len(profs) == len(cols)
    print(f"\n表 {t}: {len(cols)} 列 -> profiles {len(profs) if profs else 0}")
    for p in (profs or [])[:4]:
        print("   ", p["name"], "distinct=", p["distinct_count"], "null_rate=", p["null_rate"])
        if p["distinct_count"] is None:
            ok = False
    if not ok:
        fails += 1
        print("   FAIL: 返回结构异常")

print("\nRESULT:", "ALL PASS" if fails == 0 else f"{fails} FAIL")
sys.exit(1 if fails else 0)
