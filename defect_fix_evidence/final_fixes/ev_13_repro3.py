"""1.3 忠实复现：httpx client 先在【已关闭的 loop】上建立连接池，再跨 loop 复用 -> Event loop is closed。

这正对应真实部署：client 首次在 uvicorn 主 loop 上请求（连接池绑定主 loop），
随后 action_executor 用 ex.submit(asyncio.run) 在工作线程新 loop 里复用它 -> 崩。
修复：_get_client 按 (loop_id, name) 分键，跨 loop 自动新建。
"""
import asyncio
import threading
import httpx

URL = "http://127.0.0.1:1/"  # 必拒绝/超时，仅用于触发 transport 在对应 loop 上建立


def make_client():
    return httpx.AsyncClient(timeout=0.5, trust_env=False)  # 关代理干扰


# ===== 旧模式：单例 client，跨 loop 复用 =====
OLD = make_client()

# ===== 新模式：按 (loop_id,name) 分键 =====
_NEW = {}
def new_client(name):
    loop = asyncio.get_running_loop()
    key = (id(loop), name)
    c = _NEW.get(key)
    if c is None:
        c = make_client()
        _NEW[key] = c
    return c


async def bind_on_main():
    # 在「即将关闭的主 loop」上先建立连接池（绑定该 loop）
    try:
        await OLD.get(URL)
    except Exception:
        pass


async def old_use():
    await OLD.get(URL)  # 复用已绑定到已关闭主 loop 的 client

async def new_use():
    c = new_client("default")  # 在本 loop 新建
    try:
        await c.get(URL)
    except (httpx.ConnectError, httpx.ReadTimeout):
        pass  # 连接被拒 = 本 loop 正常工作（无 loop 错误）


def run(fn, label, out):
    try:
        asyncio.run(fn())
        out[label] = ("OK(无loop错误)", None)
    except RuntimeError as e:
        out[label] = (type(e).__name__, str(e)[:90])
    except Exception as e:
        out[label] = (type(e).__name__, str(e)[:90])


def main():
    # 1) 先在主 loop 上绑定 OLD（其连接池绑定到该 loop），asyncio.run 结束后该 loop 关闭
    asyncio.run(bind_on_main())
    out = {}
    print("=== 旧模式：绑定到已关闭 loop 的 client，在工作线程 asyncio.run 内复用 ===")
    t = threading.Thread(target=run, args=(old_use, "old", out)); t.start(); t.join()
    print(f"  [old] {out['old']}")

    print("=== 新模式：按 (loop_id,name) 分键，同在工作线程 ===")
    t2 = threading.Thread(target=run, args=(new_use, "new", out)); t2.start(); t2.join()
    print(f"  [new] {out['new']}")

    print()
    print(f"结论：旧模式跨 loop 复用已关闭-loop 的 client -> {out['old'][0]}；新模式按运行 loop 创建 -> {out['new'][0]}")
    assert "OK" not in out["old"][0], f"旧模式应抛 loop 错误，实际 {out['old']}"
    assert "OK" in out["new"][0], f"新模式应正常，实际 {out['new']}"


if __name__ == "__main__":
    main()
