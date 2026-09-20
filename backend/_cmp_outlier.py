# -*- coding: utf-8 -*-
"""对比 A(IQR×3) 与 B(P1/P99 + 3σ + 零值占比) 的统计口径差异，定位 A 为何没提示。只读，不改任何数据。"""
import glob, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import pandas as pd
import duckdb

TARGET_COLS = ["担保余额", "贷款金额", "抵押物评估价值", "逾期天数", "抵押率"]

class StubDB:
    def __init__(self, conn):
        self.conn = conn

def find_files():
    hits = []
    for p in glob.glob(r"C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/backend/data/uploads/*.xlsx"):
        try:
            df = pd.read_excel(p, nrows=5)
        except Exception:
            continue
        cols = set(map(str, df.columns))
        if {"担保余额", "贷款金额"} <= cols:
            hits.append((p, df.columns.tolist()))
    return hits

def main():
    # 引入 A 的质检引擎
    sys.path.insert(0, r"C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/backend")
    from app.core.quality_checker import QualityChecker

    for p, cols in find_files():
        print("=" * 70)
        print("文件:", p.split("/")[-1], "| 列:", cols)
        df = pd.read_excel(p)
        n = len(df)
        print("行数:", n)
        conn = duckdb.connect(":memory:")
        conn.register("df_view", df)
        conn.execute("CREATE TABLE t AS SELECT * FROM df_view")
        stub = StubDB(conn)
        info = {"columns": [{"name": c, "type": str(t)} for c, t in zip(df.columns, conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='t'").fetchall())]}
        # 用 A 的引擎全量跑
        checker = QualityChecker(stub, {})
        result = checker.check_table("t", info["columns"])
        dist = [i for i in result["issues"] if i["type"] == "distribution"]
        print(f"[A 引擎全量质检] 共 {len(result['issues'])} 个问题, 其中 distribution {len(dist)} 个")
        for i in dist:
            print("   -", i["message"])

        # 手工按四种口径算
        print("--- 四种口径对比（对目标数值列） ---")
        for col in TARGET_COLS:
            if col not in df.columns:
                print(f"  列「{col}」不存在, 跳过")
                continue
            xs = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(xs) < 10:
                print(f"  列「{col}」有效样本 {len(xs)} <10, 跳过")
                continue
            q1, q3 = xs.quantile(0.25), xs.quantile(0.75)
            iqr = q3 - q1
            lo3, hi3 = q1 - 3 * iqr, q3 + 3 * iqr          # A: IQR×3
            p1, p99 = xs.quantile(0.01), xs.quantile(0.99)  # B: P1/P99
            mu, sd = xs.mean(), xs.std()                    # B: 3σ
            lo3s, hi3s = mu - 3 * sd, mu + 3 * sd
            n_iqr = int(((xs < lo3) | (xs > hi3)).sum())
            n_p1p99 = int(((xs < p1) | (xs > p99)).sum())
            n_3sig = int(((xs < lo3s) | (xs > hi3s)).sum())
            zero_share = (xs == 0).mean()
            print(f"  列「{col}」: A_IQR×3={n_iqr}  B_P1/P99={n_p1p99} (界[{p1:.2f},{p99:.2f}])  B_3σ={n_3sig}  零值占比={zero_share:.1%}")
        conn.close()

if __name__ == "__main__":
    main()
