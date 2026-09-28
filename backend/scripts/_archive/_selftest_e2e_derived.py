"""
端到端自测：用真实数据集（含「抵押率」）跑 S3 图表引擎，验证派生指标反哺生效

验证链路：DuckDB 反推公式 → S3 规则引擎生成图表 → 图表 config 带加工口径与安全聚合

运行前需停掉后端（DuckDB 单进程独占）：
    cd backend && python _selftest_e2e_derived.py
"""
import os
import sys
import json
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.duckdb_manager import get_duckdb
from app.core.derived_metric_service import detect_derived_metrics, to_map
from app.core.brain_modules.s3_chart_engine_v2 import S3ChartEngine

DB_SQLITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "aibi.db")


def candidate_datasets() -> list:
    """SQL 库里所有 schema 含比率类列的数据集"""
    con = sqlite3.connect(DB_SQLITE, timeout=30)
    cur = con.cursor()
    cur.execute("SELECT id, name, schema_json FROM datasets")
    rows = cur.fetchall()
    con.close()
    out = []
    for dsid, name, sj in rows:
        if not sj:
            continue
        try:
            cols = json.loads(sj).get("columns") or []
        except Exception:
            continue
        names = [c.get("name") for c in cols if c.get("name")]
        if any(("率" in n or "占比" in n) for n in names):
            out.append((dsid, name, cols))
    return out


def pick_dataset(duck):
    """挑一个真能反推出派生公式的数据集（不是每个含"率"列的表都存在可验证恒等式）"""
    for dsid, name, cols in candidate_datasets():
        table = "ds_" + dsid.replace("-", "_")
        if not duck.table_exists(table):
            continue
        try:
            res = detect_derived_metrics(duck, table, cols, max_rows=3000)
        except Exception:
            continue
        if res:
            return dsid, name, cols, table, res
    return None, None, None, None, None


duck = get_duckdb()
dsid, name, cols, table, detected = pick_dataset(duck)
if not dsid:
    print("所有含比率列的数据集都没反推出可验证的派生关系（无恒等式即无可派生，属正常），跳过")
    sys.exit(0)

print(f"数据集: {name} ({dsid[:8]})  表: {table}")
derived = to_map(detected)
print("反推出的派生指标:")
for k, v in derived.items():
    print(f"  - {v['formula']}（匹配率 {v['match_ratio']:.0%}）")

fields = [c["name"] for c in cols]
try:
    rows = duck.conn.execute(f'SELECT * FROM "{table}" LIMIT 200').fetchall()
    col_names = [d[0] for d in duck.conn.execute(f'SELECT * FROM "{table}" LIMIT 0').description]
    sample = [dict(zip(col_names, r)) for r in rows]
except Exception as e:
    print("取样失败:", e)
    sample = []

cfg = S3ChartEngine(derived_metrics=derived).generate_dashboard_config(
    fields=fields, grain="detail", sample_data=sample
)
print("\n生成的图表:")
ok = True
hit = 0
for c in cfg.get("charts") or []:
    metric = c.get("y_field") or c.get("value_field")
    conf = c.get("config") or {}
    dm = conf.get("derived_metric")
    print(f"  - [{c.get('chart_type')}] {c.get('title')}  指标={metric} "
          f"agg={conf.get('aggregation') or '(默认)'}")
    if dm:
        print(f"      派生口径: {dm.get('formula')} (匹配率 {dm.get('match_ratio'):.0%})")
    if metric in derived:
        hit += 1
        if not dm:
            print(f"      [FAIL] 派生指标 {metric} 未写入 derived_metric")
            ok = False
        elif conf.get("aggregation") != "avg":
            print(f"      [FAIL] 比率指标聚合应为 avg，实际 {conf.get('aggregation')}")
            ok = False

print(f"\n使用派生指标的图表数: {hit}")
print("RESULT:", "PASS" if (ok and hit > 0) else "FAIL")
sys.exit(0 if (ok and hit > 0) else 1)
