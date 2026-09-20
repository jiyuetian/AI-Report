"""自测：派生指标（跨列比值公式）识别 —— 验证血缘能否白盒展示 抵押率=担保余额/抵押物评估价值"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.duckdb_manager import get_duckdb
from app.core.derived_metric_service import detect_derived_metrics

KEYWORDS = ("抵押率", "担保余额", "抵押物评估价值")


def main():
    duck = get_duckdb()
    tables = [r[0] for r in duck.conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    ).fetchall()]
    ds_tables = [t for t in tables if t.startswith("ds_")]
    print(f"[tables] 共 {len(tables)} 张，ds_* {len(ds_tables)} 张")

    hit_any = False
    for t in ds_tables:
        info = duck.get_table_info(t)
        cols = info.get("columns", [])
        names = {c.get("name") for c in cols}
        if not all(any(k in n for n in names) for k in KEYWORDS):
            continue
        hit_any = True
        print(f"\n=== {t} === 行数={info.get('row_count')} 列数={len(cols)}")
        res = detect_derived_metrics(duck, t, cols)
        if not res:
            print("  未识别到派生指标")
            continue
        for r in res:
            print(f"  ✓ {r['formula']}   匹配率={r['match_ratio']:.1%} "
                  f"(校验 {r['valid_rows']}/{r['sample_rows']} 行)")
        break  # 只验证首个命中表，避免 200+ 张表重复刷屏

    if not hit_any:
        # 没有完全命中的表，退而求其次：对每张 ds 表都跑一遍，看有没有识别结果
        for t in ds_tables:
            info = duck.get_table_info(t)
            cols = info.get("columns", [])
            if len(cols) < 3:
                continue
            res = detect_derived_metrics(duck, t, cols)
            if res:
                print(f"\n=== {t} ===")
                for r in res:
                    print(f"  ✓ {r['formula']}  匹配率={r['match_ratio']:.1%}")

    print("\nSELFTEST_DONE")


if __name__ == "__main__":
    main()
