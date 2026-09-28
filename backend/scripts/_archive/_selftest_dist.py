# -*- coding: utf-8 -*-
"""P2 分布检测三口径自测：P1/P99 统计异常值 + 3σ 极端值 + 零值占比。"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/backend")
import pandas as pd, duckdb
from app.core.quality_checker import QualityChecker

class StubDB:
    def __init__(self, conn):
        self.conn = conn

df = pd.read_excel(r"C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/backend/data/uploads/0eaf373c-ee64-4774-995e-0b3b14a56201.xlsx")
conn = duckdb.connect(":memory:")
conn.register("dfv", df)
conn.execute("CREATE TABLE t AS SELECT * FROM dfv")
info = {"columns": [{"name": c, "type": str(t)} for c, t in conn.execute(
    "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='t'").fetchall()]}
checker = QualityChecker(StubDB(conn), {})
result = checker.check_table("t", info["columns"])
dist = [i for i in result["issues"] if i["type"] == "distribution"]

print(f"分布类问题共 {len(dist)} 条：")
for i in dist:
    rec = [o for o in i["repair_options"] if o.get("recommended")]
    print(f"  [{i['rule']}] {i['message']}  推荐方案={rec[0]['label'] if rec else '无'}")

# 断言
msgs = " | ".join(i["message"] for i in dist)
checks = [
    ("担保余额 P1/P99 统计异常值", "22 个统计异常值" in msgs and "担保余额" in msgs),
    ("贷款金额 3σ 极端值(13个)", "贷款金额」有 13 个极端值" in msgs),
    ("逾期天数 零值占比 94%", "零值占比 94%" in msgs),
    ("抵押率 3σ 极端值(15个)", "抵押率」有 15 个极端值" in msgs),
    ("推荐方案标记存在", any(any(o.get("recommended") for o in i["repair_options"]) for i in dist if "零值" not in i["rule"])),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
conn.close()
sys.exit(1 if failed else 0)
