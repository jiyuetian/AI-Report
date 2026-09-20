import sqlite3, json

DB = r"C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/backend/data/aibi.db"
con = sqlite3.connect(DB)
cur = con.cursor()

# 仅清理测试/僵尸看板（e2e_test 与 admin 均为非真实用户生成）
ids = [r[0] for r in cur.execute(
    "SELECT id FROM dashboards WHERE created_by IN ('e2e_test','admin')"
)]
print("to delete dashboards:", len(ids), ids)

ds_ids = set()
for did in ids:
    row = cur.execute(
        "SELECT dataset_ids, primary_dataset_id FROM dashboards WHERE id=?", (did,)
    ).fetchone()
    if row:
        pds = row[1]
        if pds:
            ds_ids.add(pds)
        try:
            dj = json.loads(row[0]) if row[0] else []
            for x in dj:
                if x:
                    ds_ids.add(x)
        except Exception:
            pass

for did in ids:
    cur.execute("DELETE FROM dashboards WHERE id=?", (did,))
print("dashboards deleted:", len(ids))

# 清理这些数据集相关的 lineage / quality / clean 残留（仅测试数据集，不碰用户真实数据）
for ds in ds_ids:
    for tbl in ("lineage_nodes", "quality_issues", "clean_rules"):
        try:
            cur.execute(f"DELETE FROM {tbl} WHERE dataset_id=?", (ds,))
        except Exception as e:
            print(f"  skip {tbl} for {ds}: {e}")
con.commit()

print("after delete, dashboards count:", cur.execute("SELECT COUNT(*) FROM dashboards").fetchone()[0])
print("deleted test datasets:", ds_ids)
print("remaining dashboards:")
for r in cur.execute("SELECT id,name,created_by,status FROM dashboards ORDER BY rowid DESC"):
    print("  ", r)
con.close()
print("CLEANUP_DONE")
