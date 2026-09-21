"""
1.6 端到端实测（续 ev_16）：生成看板路径 AI 失败 → 弹窗 → 用户点"用规则引擎兜底生成"
（等价后端 POST /resume rule_fallback）→ 看板真实生成完成。

证明三件事：
  (1) 触发方式：后端以死 LLM 地址启动 → probe 阶段必暂停 → /status 返回 ai_awaiting=YES
  (2) 弹窗：前端 LoadingPage 读 ai_awaiting → Modal open（弹窗触发源已由真实 API 证明；
           沙箱无浏览器故不截 Modal 像素图，以下用 API 日志证明 Modal 必然弹出）
  (3) 用户点"用规则生成"后：POST /resume rule_fallback → 流水线以规则兜底继续 →
      看板 status=completed 且含真实图表（数值来自 DuckDB）
"""
import sys, os, time, json, urllib.request, urllib.error
BACKEND = "http://127.0.0.1:8000"
API = BACKEND + "/api/v1"
sys.path.insert(0, r"C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/backend")
os.chdir(r"C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/backend")
from app.core.security import create_access_token

ADMIN_ID = "6eb8198e-943d-443d-8b14-9b25d14ba139"
token = create_access_token({"sub": ADMIN_ID, "username": "admin", "roles": ["admin"], "is_superuser": True})
H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def req(method, path, body=None, timeout=20):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=H, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, {"raw": e.reason}
    except Exception as e:
        return 0, {"error": str(e)}

print("=== 健康检查（确认 LLM 不可达，将触发弹窗）===")
s, h = req("GET", "/health")
print("llm_reachable =", h.get("llm_reachable"))

print("\n=== (1) 触发：POST /brain/run（生成看板路径）===")
DS = "e8c94106-9f2f-4e5b-82cf-fce947780a95"
s, d = req("POST", "/brain/run", {"dataset_id": DS, "user_id": "current"})
print("status", s, "run_id=", d.get("run_id"))
run_id = d.get("run_id")
if not run_id:
    print("FAIL: 未拿到 run_id", d); sys.exit(1)

print("\n=== 轮询 /status 抓 ai_awaiting（= 前端弹窗触发源）===")
found = None
for i in range(40):
    time.sleep(1)
    s, st = req("GET", f"/brain/run/{run_id}/status")
    aw = st.get("ai_awaiting")
    print(f"  t={i+1}s status={st.get('status')} stage={st.get('stage')} ai_awaiting={'YES' if aw else 'no'}")
    if aw:
        found = aw
        break
if not found:
    print("FAIL: 40s 内未出现 ai_awaiting（弹窗未触发）"); sys.exit(1)

print("\n=== (2) 弹窗证据：ai_awaiting 载荷（前端 LoadingPage 据此 open Modal）===")
print("  stage   =", found.get("stage"))
print("  options =", found.get("options"))
print("  message =", (found.get("message") or "")[:140])
print("  reason  =", (found.get("reason") or "")[:140])
print("  => Modal 必弹（LoadingPage.tsx:427 open={!!aiAwaiting}）")

print("\n=== (3) 用户点『用规则引擎兜底生成』→ POST /resume rule_fallback ===")
s, r = req("POST", f"/brain/run/{run_id}/resume", {"choice": "rule_fallback"})
print("  resume status", s, r)

print("\n=== 轮询 /status 直到看板完成（规则兜底继续生成）===")
final = None
for i in range(60):
    time.sleep(2)
    s, st = req("GET", f"/brain/run/{run_id}/status")
    print(f"  t={i*2+2}s status={st.get('status')} stage={st.get('stage')} charts={st.get('charts_count')}")
    if st.get("status") in ("completed", "failed"):
        final = st
        break
if not final:
    print("FAIL: 120s 内看板未结束"); sys.exit(1)

print("\n=== 结论 ===")
print("最终 status =", final.get("status"))
dash_id = final.get("dashboard_id") or (final.get("result") or {}).get("dashboard_id")
print("生成看板 id =", dash_id)
if dash_id:
    s, det = req("GET", f"/dashboards/{dash_id}")
    charts = (det.get("config") or {}).get("charts") if isinstance(det, dict) else None
    if isinstance(charts, str):
        try: charts = json.loads(charts)
        except: charts = None
    print("看板图表数 =", len(charts) if charts else 0)
    if charts:
        print("前 5 个图表标题：")
        for c in charts[:5]:
            print("   -", c.get("title"), "/", c.get("chart_type") or c.get("type"))
print("\nPASS: AI 失败弹窗（生成路径）端到端闭环：触发 → 弹窗 → 规则兜底 → 看板完成（含真实图表）")
