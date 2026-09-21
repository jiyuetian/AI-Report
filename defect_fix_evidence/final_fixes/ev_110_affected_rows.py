"""
1.10 验证：附录 B "影响行数" 是否已在真实数据上填充。
GET /dashboards/{id}/appendix → clean_log[].affected_rows 是否非空。
路演前拍板：不做行级明细，但加"影响行数"统计。
"""
import sys, os, json, urllib.request, urllib.error
BACKEND = "http://127.0.0.1:8000"
API = BACKEND + "/api/v1"
sys.path.insert(0, r"C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/backend")
os.chdir(r"C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/backend")
from app.core.security import create_access_token

ADMIN_ID = "6eb8198e-943d-443d-8b14-9b25d14ba139"
token = create_access_token({"sub": ADMIN_ID, "username": "admin", "roles": ["admin"], "is_superuser": True})
H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def req(method, path, body=None):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=H, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, {"raw": e.reason}
    except Exception as e:
        return 0, {"error": str(e)}

s, lst = req("GET", "/dashboards")
dashboards = (lst.get("dashboards") or lst.get("items") or []) if isinstance(lst, dict) else []
print(f"看板列表：{len(dashboards)} 个")

found = 0
for d in dashboards[:8]:
    did = d.get("id")
    s2, ap = req("GET", f"/dashboards/{did}/appendix")
    if s2 != 200 or not isinstance(ap, dict):
        continue
    clog = ap.get("clean_log") or []
    if not clog:
        continue
    found += 1
    non_null = sum(1 for r in clog if r.get("affected_rows") is not None)
    print(f"\n看板 {did}（{d.get('name')}）  clean_log={len(clog)} 条，其中 affected_rows 非空={non_null} 条")
    for r in clog[:6]:
        print(f"  seq={r.get('seq')} 阶段={r.get('stage')} 算子={r.get('rule_type')} 策略={r.get('strategy')} "
              f"字段={r.get('target_field')} 影响行数={r.get('affected_rows')} 说明={r.get('detail')}")

if not found:
    print("\n（无看板含 clean_log 记录，无法验证影响行数填充；需确认是否存在已执行清洗/质检的看板）")
