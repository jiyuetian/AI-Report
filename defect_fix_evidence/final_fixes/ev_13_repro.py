"""1.3 Event loop is closed 复现与修复验证（受控，不依赖业务重库）。

真实场景（backend 代码路径）：
  - llm_gateway.py:277 在【导入期/主线程】创建全局 rate_limiter，其信号量绑定到当时 loop；
  - action_executor.py:653 / intent_classifier.py 用 ex.submit(lambda: asyncio.run(llm_chat(...)))
    在【工作线程】里跑 chat_complete → rate_limiter.acquire() 的 await 命中主线程旧 loop
    → 跨 loop / 已关闭 loop → "Event loop is closed"。
修复：信号量惰性按【运行中的 loop】创建。
"""
import asyncio
import threading


class OldLimiter:
    def __init__(self, n):
        self.sem = asyncio.Semaphore(n)  # 导入期：绑定主线程当时的 loop
    async def acquire(self):
        await self.sem.acquire()

class NewLimiter:
    def __init__(self, n):
        self._sems = {}
        self.n = n
    def _loop_sem(self):
        loop = asyncio.get_running_loop()
        s = self._sems.get(id(loop))
        if s is None:
            s = asyncio.Semaphore(self.n)
            self._sems[id(loop)] = s
        return s
    async def acquire(self):
        await self._loop_sem().acquire()

# 模块导入期（主线程）创建——模拟全局 rate_limiter
_OLD = OldLimiter(2)
_NEW = NewLimiter(2)


def run_in_worker_thread(lim, label, results):
    try:
        asyncio.run(lim.acquire())
        results[label] = ("OK", None)
    except Exception as e:
        results[label] = (type(e).__name__, str(e)[:120])


def main():
    results = {}
    print("=== 旧模式：导入期(主线程)信号量，在工作线程 asyncio.run 内 acquire ===")
    t = threading.Thread(target=run_in_worker_thread, args=(_OLD, "old", results))
    t.start(); t.join()
    print(f"  [old] {results.get('old')}")

    print("=== 新模式：惰性 per-loop 信号量，同在工作线程 ===")
    t2 = threading.Thread(target=run_in_worker_thread, args=(_NEW, "new", results))
    t2.start(); t2.join()
    print(f"  [new] {results.get('new')}")

    print()
    ok_old = results["old"][0] == "OK"
    ok_new = results["new"][0] == "OK"
    print(f"结论：旧模式跨线程命中旧 loop -> {results['old']}；新模式按运行 loop 创建 -> {results['new']}")
    assert not ok_old, f"旧模式应复现错误，实际 {results['old']}"
    assert ok_new, f"新模式应正常，实际 {results['new']}"


if __name__ == "__main__":
    main()
