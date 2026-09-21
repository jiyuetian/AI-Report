"""1.3 真凶复现：httpx.AsyncClient 跨 loop 缓存 -> Event loop is closed。

复现 backend/app/core/llm_gateway.py 旧 _get_client（按 name 缓存）在
action_executor/intent_classifier 用 asyncio.run 工作线程跑 chat_complete 时的崩溃。
"""
import asyncio
import threading
import httpx


# ===== 旧模式：模块级/按 name 缓存，绑定首次调用所在 loop =====
OLD_CLIENT = httpx.AsyncClient(timeout=0.5)  # 导入期(主线程)创建，绑定主线程 loop

# ===== 新模式：按 (loop_id, name) 分键 =====
_NEW_CLIENTS = {}
def new_client(name):
    loop = asyncio.get_running_loop()
    key = (id(loop), name)
    c = _NEW_CLIENTS.get(key)
    if c is None or c.is_closed:
        c = httpx.AsyncClient(timeout=0.5)
        _NEW_CLIENTS[key] = c
    return c


async def use_old():
    # 在工作线程的新 loop 里复用主线程旧 loop 的 client
    await OLD_CLIENT.get("http://127.0.0.1:1/")

async def use_new():
    c = new_client("default")  # 在本 loop 创建
    try:
        await c.get("http://127.0.0.1:1/")
    except httpx.ConnectError:
        pass  # 连接被拒 = 客户端在本 loop 正常工作（无 loop 错误）


def run(thread_fn, label, out):
    try:
        asyncio.run(thread_fn())
        out[label] = ("OK(无loop错误)", None)
    except RuntimeError as e:
        out[label] = (type(e).__name__, str(e)[:100])
    except Exception as e:
        out[label] = (type(e).__name__, str(e)[:100])


def main():
    out = {}
    print("=== 旧模式：主线程 client，在工作线程 asyncio.run 内请求 ===")
    t = threading.Thread(target=run, args=(use_old, "old", out)); t.start(); t.join()
    print(f"  [old] {out['old']}")

    print("=== 新模式：按 (loop_id,name) 分键，同在工作线程 ===")
    t2 = threading.Thread(target=run, args=(use_new, "new", out)); t2.start(); t2.join()
    print(f"  [new] {out['new']}")

    print()
    print(f"结论：旧模式跨 loop 复用 client -> {out['old'][0]}；新模式按运行 loop 创建 -> {out['new'][0]}")
    assert "OK" not in out["old"][0], f"旧模式应抛 loop 错误，实际 {out['old']}"
    assert "OK" in out["new"][0], f"新模式应正常，实际 {out['new']}"


if __name__ == "__main__":
    main()
