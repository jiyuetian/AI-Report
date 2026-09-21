"""导出真实看板数据契约到 JSON，供 routefix_proof.html 与证据文件引用。"""
import sys, json, urllib.request, urllib.error
sys.path.insert(0, r"C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/backend")
from app.core.security import create_access_token

BASE = "http://127.0.0.1:8000/api/v1"
ADMIN_SUB = "6eb8198e-943d-443d-8b14-9b25d14ba139"
DASH = "dash_3716856d_35d769"

token = create_access_token({"sub": ADMIN_SUB, "username": "admin", "roles": ["admin"], "is_superuser": True})
H = {"Authorization": f"Bearer {token}"}


def call(path, headers=None):
    req = urllib.request.Request(BASE + path, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa
        return None, {"error": str(e)}


out = {"dashboard": None, "chart_data": None}

s, db = call(f"/dashboards/{DASH}", H)
out["dashboard"] = {
    "status": s,
    "name": db.get("name"),
    "primary_dataset_id": db.get("primary_dataset_id"),
    "dataset_ids": db.get("dataset_ids"),
    "charts": [(c.get("title") or c.get("name") or c.get("id")) for c in (db.get("config") or {}).get("charts") or []],
    "chart_count": len((db.get("config") or {}).get("charts") or []),
}

pid = db.get("primary_dataset_id") or (db.get("dataset_ids") or [None])[0]
if pid:
    s2, cd = call(f"/datasets/{pid}/chart-data", H)
    out["chart_data"] = {
        "status": s2,
        "columns": [c.get("name") or c.get("field") if isinstance(c, dict) else c for c in (cd.get("columns") or [])],
        "row_count": len(cd.get("data") or cd.get("rows") or []),
        "sample": (cd.get("data") or cd.get("rows") or [])[:3],
    }

# 概览
s3, ov = call("/admin/overview", H)
out["overview"] = {"status": s3, "data": ov}

# 导出诚实返回
import urllib.request as u
body = json.dumps({"dashboard_id": DASH, "format": "pdf", "include_watermark": True,
                  "include_logic": False, "include_data": False}).encode()
req = urllib.request.Request(BASE + "/exports/sync", headers={"Content-Type": "application/json", **H}, method="POST", data=body)
try:
    with u.urlopen(req, timeout=15) as r:
        exp = json.loads(r.read().decode("utf-8", "replace"))
        out["export_pdf"] = {"status": r.status, "mode": exp.get("mode"), "has_download_url": "download_url" in exp, "message": exp.get("message")}
except urllib.error.HTTPError as e:
    out["export_pdf"] = {"status": e.code, "body": e.read().decode("utf-8", "replace")[:300]}

with open(r"C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/defect_fix_evidence/final_fixes/proof_data.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(json.dumps(out, ensure_ascii=False, indent=2))
