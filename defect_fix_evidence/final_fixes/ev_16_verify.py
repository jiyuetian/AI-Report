"""
1.6 实测：造 AI 不可用场景，确认生成看板路径会触发"AI 失败弹窗"。
弹窗触发源 = 后端 /brain/run/{id}/status 返回的 ai_awaiting 字段
（LoadingPage.tsx:152-153 读它 → open Modal:425）。

本测试用 LLM_BASE_URL=http://127.0.0.1:9（死地址）启动后端 →
probe 阶段（brain_run_sse.py:559-576）LLM 不可达 → _request_user_choice
设置 ai_awaiting（:188）→ /status 回传（:1323）→ 前端弹窗。
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


def req(method, path, body=None, timeout=10):
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


def wait_health(max_s=45):
    for _ in range(max_s):
        s, d = req("GET", "/health")
        if s == 200:
            return d
        time.sleep(1)
    return None


DS_CANDIDATES = [
    "3716856d-b67b-437b-9584-6e7c69320df2",
    "e8c94106-9f2f-4e5b-82cf-fce947780a95",
    "cb0a9738-1f25-4616-83ff-651d9d8b3815",
    "5bd315e3-24a5-42db-9f9b-5292064c75cc",
    "04d68399-abcd-4661-915d-132c9c349f6d",
    "c4da0c26-4c13-45f8-a4b7-3e7099c2e183",
]

print("=== 等待后端就绪 ===")
h = wait_health()
if not h:
    print("FAIL: 后端未就绪")
    sys.exit(1)
print("后端就绪 | llm_reachable =", h.get("llm_reachable"), "(false=将触发 probe 暂停弹窗)")

run_id = None
DS = None
print("\n=== POST /brain/run（遍历候选，绕过质量门禁 403）===")
for cand in DS_CANDIDATES:
    s, d = req("POST", "/brain/run", {"dataset_id": cand, "user_id": "current"})
    print(f"  dataset {cand[:8]} -> {s} run_id={d.get('run_id')}")
    if s == 200 and d.get("run_id"):
        run_id = d["run_id"]
        DS = cand
        break
    elif s == 403:
        print(f"     门禁拦截: {d.get('detail', {}).get('message')}")
if not run_id:
    print("FAIL: 所有候选均被门禁拦截或未启动")
    sys.exit(1)
print("选用 dataset:", DS, "run_id:", run_id)

print("\n=== 轮询 /status 抓 ai_awaiting（弹窗触发源）===")
found = None
for i in range(30):  # 最多 30s
    time.sleep(1)
    s, d = req("GET", f"/brain/run/{run_id}/status")
    aw = d.get("ai_awaiting")
    stage = d.get("stage")
    status = d.get("status")
    print(f"  t={i+1}s status={status} stage={stage} ai_awaiting={'YES' if aw else 'no'}")
    if aw:
        found = aw
        break

print("\n=== 结论 ===")
if found:
    print("PASS: 生成路径 AI 失败时 /status 返回 ai_awaiting，前端 LoadingPage 将弹出选择框")
    print("  stage      =", found.get("stage"))
    print("  options    =", found.get("options"))
    print("  message    =", (found.get("message") or "")[:120])
    print("  reason     =", (found.get("reason") or "")[:120])
else:
    print("FAIL: 轮询 30s 内未出现 ai_awaiting（弹窗未触发）")
