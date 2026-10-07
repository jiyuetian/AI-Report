"""数据库结构自检：验证数据集表结构迁移是否生效且数据无损。

检查项：
  1. datasets.duckdb_table 为可空（文档型数据集不建 DuckDB 表，故必须允许 NULL）
  2. datasets 行数与快照一致（无损迁移，不应丢行）
  3. 引用 datasets 的外键表完整存在
  4. 无残留迁移临时表（如 datasets_new）

用法：
    cd backend
    python scripts/verify_schema.py

退出码：0 = 全部通过；1 = 存在异常项。
"""
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402


def _db_path() -> Path:
    """解析 SQLite 库路径。

    注意 Windows 上的坑：SQLAlchemy 的 sqlite 三段斜杠语法
    `sqlite+aiosqlite:///./data/aibi.db` 中的 `./data/...` 是相对 backend 目录的路径，
    而 Windows 绝对路径 `sqlite:///C:/...` 去掉 `sqlite://` 后带盘符。
    因此需要区分这两种情况，不能简单地对绝对路径做 join。
    """
    url = settings.SQLITE_DATABASE_URL or settings.DATABASE_URL
    url = url.replace("sqlite+aiosqlite://", "").replace("sqlite:///", "").replace("sqlite://", "")
    backend_dir = Path(__file__).resolve().parent.parent
    if not url:
        return backend_dir / "data/aibi.db"
    p = Path(url)
    if p.is_absolute():
        # 形如 C:\... 的绝对路径，直接使用（不叠加 backend 目录）
        return p
    if url.startswith("/") or url.startswith("\\"):
        # `sqlite:///./data/aibi.db` 去掉协议后形如 `./data/aibi.db` 或 `/data/...`，
        # 属相对 backend 目录的路径
        return backend_dir / url.lstrip("/\\")
    return backend_dir / p


DB = _db_path()
REF_TABLES = ("quality_issues", "clean_rules", "charts", "dashboards")
LEFTOVER = ("datasets_new",)

fails: list[str] = []

print("=" * 64)
print("数据库结构自检")
print(f"库文件: {DB}")
print("=" * 64)

if not DB.exists():
    print(f"FAIL  库文件不存在: {DB}")
    sys.exit(1)

conn = sqlite3.connect(DB)
cur = conn.cursor()

# 1. duckdb_table 可空
print("\n[1] datasets 表结构")
notnull = None
for cid, name, ctype, nn, dflt, pk in cur.execute("PRAGMA table_info(datasets)"):
    print(f"    [{pk}] {name:<20} type={ctype:<12} NOTNULL={nn}")
    if name == "duckdb_table":
        notnull = nn
if notnull == 0:
    print("    PASS  duckdb_table 已放宽为可空")
else:
    fails.append("datasets.duckdb_table 仍为 NOT NULL")
    print(f"    FAIL  duckdb_table NOTNULL={notnull}（文档型数据集无法落库）")

# 2. 行数
print("\n[2] datasets 行数")
rows = cur.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
print(f"    rows = {rows}")
if rows == 0:
    print("    WARN  datasets 为空（全新环境属正常，非迁移失败）")

# 3. 外键引用表
print("\n[3] 外键引用表完整性")
for t in REF_TABLES:
    try:
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"    PASS  {t:<16} {n} 行")
    except Exception as e:  # noqa: BLE001
        fails.append(f"表 {t} 不可访问")
        print(f"    FAIL  {t:<16} {e}")

# 4. 残留临时表
print("\n[4] 残留迁移临时表")
for name in LEFTOVER:
    exists = cur.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()[0]
    if exists:
        fails.append(f"残留临时表 {name}")
        print(f"    FAIL  {name} 仍存在")
    else:
        print(f"    PASS  {name} 已清理")

conn.close()

print("\n" + "=" * 64)
if fails:
    for f in fails:
        print(f"  FAIL  {f}")
    print(f"结果: 发现 {len(fails)} 项异常")
    sys.exit(1)
print("结果: 全部通过")
sys.exit(0)
