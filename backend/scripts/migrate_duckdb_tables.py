# -*- coding: utf-8 -*-
"""
P0-2 修复：把历史数据集的 DuckDB 表从 qa_aibi.db 迁移进 aibi.db（后端当前唯一数据源）。
根因：历史数据集建表时 DUCKDB_PATH 指向 data/duckdb/qa_aibi.db，后来统一到 aibi.db，
      老表留在旧库里 -> chart-data 404 TABLE_NOT_FOUND -> 前端"该图表无可绘制数据"。

用法（必须先停后端，否则 aibi.db 被独占锁住）：
  <py312> scripts/migrate_duckdb_tables.py            # 干跑：只列出将迁移的表
  <py312> scripts/migrate_duckdb_tables.py --apply    # 真正迁移
"""
import os
import sys
import sqlite3
import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = os.path.join(ROOT, 'data', 'aibi.db')
MAIN = os.path.join(ROOT, 'data', 'duckdb', 'aibi.db')
LEGACY = os.path.join(ROOT, 'data', 'duckdb', 'qa_aibi.db')
# 其它历史分身库（按优先级回退查找）
OTHERS = [
    os.path.join(ROOT, 'data', 'duckdb', 'aibi_cap_d29372b3.db'),
    os.path.join(ROOT, 'data', 'duckdb', 'aibi_ui_ui3.db'),
    os.path.join(ROOT, 'data', 'duckdb', 'aibi_ui_742c4187.db'),
    os.path.join(ROOT, 'data', 'duckdb', 'aibi_glm.db'),
    os.path.join(ROOT, 'data', 'duckdb', 'qa_aibi_g21.db'),
]

APPLY = '--apply' in sys.argv

con = sqlite3.connect(META); con.row_factory = sqlite3.Row
ds = con.execute('select id, name, duckdb_table, row_count from datasets').fetchall()
con.close()
wanted = []   # (dataset_id, table_name, legacy_path)
for d in ds:
    t = (d['duckdb_table'] or '').strip()
    if not t:
        continue
    wanted.append((d['id'], t, d['row_count']))

# 打开主库 + 附加所有历史库
main = duckdb.connect(MAIN)
main_tbl = set(x[0] for x in main.execute('select table_name from information_schema.tables').fetchall())
print('主库 aibi.db 现有表:', len(main_tbl))

attached = {}
for idx, p in enumerate([LEGACY] + OTHERS):
    if not os.path.exists(p):
        continue
    alias = f'legacy{idx}'
    try:
        main.execute(f"ATTACH '{p}' AS {alias} (READ_ONLY)")
        attached[alias] = p
    except Exception as e:
        print(f'  ATTACH {os.path.basename(p)} 失败: {str(e)[:80]}')
print('已附加历史库:', [os.path.basename(p) for p in attached.values()])

def legacy_names(alias):
    """附加库没有 information_schema，用 duckdb_tables() 按库名过滤"""
    try:
        return set(x[0] for x in main.execute(
            "select table_name from duckdb_tables() where database_name = ?", [alias]
        ).fetchall())
    except Exception as e:
        print('  list err', alias, str(e)[:80])
        return set()

LEGACY_TABLES = {alias: legacy_names(alias) for alias in attached}

def find_legacy(tbl):
    """在历史库里找该表（含 _cleaned/_agg/_norm 等派生变体）"""
    for alias, names in LEGACY_TABLES.items():
        if tbl in names:
            return alias
    return None

def legacy_variants(tbl):
    """该表在历史库里的全部派生变体（base/_cleaned/_agg/_norm...）"""
    out = []
    for alias, names in LEGACY_TABLES.items():
        for n in names:
            if n == tbl or n.startswith(tbl + '_'):
                out.append((alias, n))
    return sorted(set(out))

plan, missing = [], []
for did, tbl, rc in wanted:
    if tbl in main_tbl:
        continue
    vs = [(a, n) for (a, n) in legacy_variants(tbl) if n not in main_tbl]
    if vs:
        for a, n in vs:
            plan.append((did, n, a, rc))
    else:
        missing.append((did, tbl, rc))

print('\n=== 待迁移（主库缺失、历史库存在） ===')
for did, c, alias, rc in plan:
    print(f"  {c:52s} <- {alias} ({os.path.basename(attached[alias])})  meta.rows={rc}")
print(f"合计 {len(plan)} 张")

print('\n=== 两库都没有（真丢失，需重传或废弃看板） ===')
for did, c, rc in missing:
    print(f"  {c:52s}  dataset={did}")
print(f"合计 {len(missing)} 张")

if not APPLY:
    print('\n[DRY-RUN] 未执行迁移。加 --apply 真正执行。')
    main.close(); sys.exit(0)

print('\n=== 开始迁移 ===')
ok, fail = 0, 0
for did, c, alias, rc in plan:
    try:
        main.execute(f'CREATE TABLE main."{c}" AS SELECT * FROM {alias}."{c}"')
        n = main.execute(f'select count(*) from main."{c}"').fetchone()[0]
        print(f"  OK  {c:52s} rows={n} (meta={rc})")
        ok += 1
    except Exception as e:
        print(f"  FAIL {c:52s} {str(e)[:100]}")
        fail += 1
main.execute('CHECKPOINT')
main.close()
print(f'\n迁移完成: OK={ok} FAIL={fail}')
