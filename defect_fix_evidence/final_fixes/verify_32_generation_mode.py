# 验证 3.2c 后端：S2 后写入 _RUN_STATUS["generation_mode"]，且 /status 回传该字段
# 直接调用 get_run_status（绕过 FastAPI Depends，current_user 作为普通参数传入）
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

import importlib
mod = importlib.import_module('app.api.brain_run_sse')
_run_status = mod._RUN_STATUS  # 模块级状态字典（SSE 写、/status 读，同一对象）

RID = "__verify_32c__"

def run_case(mode):
    _run_status.clear()
    _run_status[RID] = {
        "status": "running",
        "stage": "S3",
        "progress": 55,
        "message": "推荐图表中",
        "detail": {},
        "generation_mode": mode,   # 模拟 S2 结束后 SSE 写入
        "finished": False,
    }
    res = asyncio.run(mod.get_run_status(RID, dataset_id=None, current_user={}))
    return res

ok = True
for mode in ("ai", "rule"):
    r = run_case(mode)
    got = r.get("generation_mode")
    flag = got == mode
    ok = ok and flag
    print(f"[3.2c] generation_mode={mode!r} -> /status 回传 {got!r}  {'PASS' if flag else 'FAIL'}")

# 反向：SSE 写入点是否真实存在（源码层确认，非推断）
import io
src = io.open(os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'app', 'api', 'brain_run_sse.py'), encoding='utf-8').read()
has_write = '_RUN_STATUS.setdefault(run_id, {})["generation_mode"]' in src
has_read = '"generation_mode": cache.get("generation_mode")' in src
print(f"[源码] SSE 写入点存在: {has_write} | /status 读取点存在: {has_read}")
ok = ok and has_write and has_read

print("RESULT:", "ALL PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
