"""
make_demo_db.py — 2.4 演示数据准备
=================================================================
用途：生成独立的演示库 demo_aibi.db，预置两个看板，供路演本机打开验证 2.4 徽标：
  - 看板 A（绿标）：ai_participated=true / generation_mode='ai' / s2_generated_by='llm' / generated_by='llm'
  - 看板 B（灰标）：ai_participated=false / generation_mode='rule' / s2_generated_by='rule' / generated_by='rule_engine'

用法（务必先停后端，释放 qa_aibi.db 锁）：
  cd backend
  <停掉运行中的 run_backend.py>
  python scripts/make_demo_db.py
  # 启动独立演示实例：
  DUCKDB_PATH="./data/duckdb/demo_aibi.db" python run_backend.py
  # 前端打开打印出的两个 dashboard id 即可看到绿标 / 灰标

注意：
  - 不改动 qa_aibi.db（线上库），仅 shutil 复制一份 demo_aibi.db 再改写。
  - qa_aibi.db 被后端独占锁定时复制会失败，脚本会提示先停后端。
"""
import os
import sys
import shutil
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
DUCKDB_DIR = os.path.join(BACKEND, "data", "duckdb")
SRC = os.path.join(DUCKDB_DIR, "qa_aibi.db")
DST = os.path.join(DUCKDB_DIR, "demo_aibi.db")


def pick_demo_dashboard(rows):
    """优先选名字含'合规月度'的（已知演示看板），否则选 config.charts 最多的。"""
    for r in rows:
        cfg = r[2] or {}
        if "合规月度" in (r[1] or ""):
            return r
    best = None
    best_n = -1
    for r in rows:
        cfg = r[2] or {}
        n = len(cfg.get("charts") or []) if isinstance(cfg, dict) else 0
        if n > best_n:
            best_n = n
            best = r
    return best


def demo_goals(llm: bool):
    by = "llm" if llm else "rule"
    return [
        {
            "goal_id": "G1",
            "title": "各区域担保逾期率趋势",
            "description": "按月观察华东/华北/华南逾期率走势，识别抬升区域",
            "type": "趋势",
            "priority": 8,
            "generated_by": by,
        },
        {
            "goal_id": "G2",
            "title": "担保类型结构分布",
            "description": "信用/抵押/保证三类担保额度占比对比",
            "type": "分布",
            "priority": 6,
            "generated_by": by,
        },
    ]


def main():
    if not os.path.exists(SRC):
        print(f"[ERR] 源库不存在: {SRC}")
        sys.exit(1)
    try:
        shutil.copyfile(SRC, DST)
    except PermissionError:
        print("[ERR] 无法复制 qa_aibi.db：文件被后端独占锁定。")
        print("      请先停掉运行中的 run_backend.py（释放 DuckDB 锁），再运行本脚本。")
        sys.exit(2)
    print(f"[OK] 已克隆 -> {DST}")

    import duckdb

    con = duckdb.connect(DST, read_only=False)
    rows = con.execute("SELECT id, name, config FROM dashboards").fetchall()
    print(f"[INFO] 源库看板数 = {len(rows)}")

    A = pick_demo_dashboard(rows)
    if A is None:
        print("[ERR] 源库无看板，无法生成演示数据。")
        sys.exit(3)
    a_id, a_name, a_cfg = A
    a_cfg = dict(a_cfg or {})
    a_cfg.update(
        {
            "ai_participated": True,
            "generation_mode": "ai",
            "s2_generated_by": "llm",
            "generated_by": "llm",
            "goals": demo_goals(llm=True),
        }
    )
    con.execute("UPDATE dashboards SET config = ? WHERE id = ?", [a_cfg, a_id])

    # 看板 B：优先取另一个不同 id 的看板；否则造一条合成规则看板行
    others = [r for r in rows if r[0] != a_id]
    if others:
        b_id, b_name, b_cfg = others[0]
        b_cfg = dict(b_cfg or {})
        b_cfg.update(
            {
                "ai_participated": False,
                "generation_mode": "rule",
                "s2_generated_by": "rule",
                "generated_by": "rule_engine",
                "goals": demo_goals(llm=False),
            }
        )
        con.execute("UPDATE dashboards SET config = ? WHERE id = ?", [b_cfg, b_id])
    else:
        b_id = str(uuid.uuid4())
        b_cfg = {
            "ai_participated": False,
            "generation_mode": "rule",
            "s2_generated_by": "rule",
            "generated_by": "rule_engine",
            "goals": demo_goals(llm=False),
            "charts": [],
        }
        con.execute(
            "INSERT INTO dashboards (id, name, config, status) VALUES (?, ?, ?, 'published')",
            [b_id, "演示-规则兜底看板", b_cfg],
        )

    con.close()
    print("\n=== 演示看板已就绪 ===")
    print(f"绿标（AI 参与生成）看板 id: {a_id}   名称: {a_name}")
    print(f"灰标（规则兜底生成）看板 id: {b_id}")
    print("\n启动演示实例后，前端打开：")
    print(f"  http://127.0.0.1:8000/dashboard/{a_id}   <- 绿标")
    print(f"  http://127.0.0.1:8000/dashboard/{b_id}   <- 灰标")
    print("\n翻车保险验证：LLM 不可达时，用规则生成后打开任一看板即为灰标。")


if __name__ == "__main__":
    main()
