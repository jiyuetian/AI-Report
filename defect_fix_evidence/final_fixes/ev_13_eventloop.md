# 1.3 Event loop is closed — 证据与诚实结论

## 现象
`_start.log` 出现 `[LLM] LLM未知错误: Event loop is closed`（chat_complete catch-all `:493` 捕获）。

## 排查（逐项验证，未臆断）
1. `llm_gateway.py:277` 模块级 `rate_limiter`（`asyncio.Semaphore`）：Py3.12 的 Semaphore 已**惰性按运行 loop 绑定**，非根因（仍改为 per-loop 作卫生项）。
2. `llm_gateway.py:309/324` 模块级缓存 `httpx.AsyncClient`：`httpx.AsyncClient` 绑定创建时 loop；
   `action_executor.py:653` / `intent_classifier.py:240,656` 用 `ex.submit(lambda: asyncio.run(llm_chat(...)))`
   在**工作线程**跑 chat_complete → 复用主 loop 创建的 client → 跨 loop。**已改为按 (loop_id,name) 分键**（`_get_client`）。
3. `database.py:26` 导入期 `asyncio.get_event_loop().run_until_complete` → 改为独立临时 loop 并关闭。
4. `_record_usage(:600)` 的 `await redis_client.incrby` 已被 `try/except:pass` 吞掉 → 不是可见错误源。

## 本沙箱实测（关键诚实点）
- `httpx 0.28.1` + `Python 3.12` 下，`httpx.AsyncClient` / `asyncio.Semaphore` **均为 lazy loop-binding**；
  复现脚本（ev_13_repro2.py / ev_13_repro3.py）中跨 loop 复用 client **未抛 "Event loop is closed"**（仅 ConnectTimeout/ReadTimeout）。
  ⇒ 无法在本沙箱复现该错误串，故不能在此 100% 证明用户所见错误已消失。

## 已落地的防御性修复（消除跨 loop 复用这一标准成因）
- `llm_gateway.py`：`_get_client` 按 `(id(loop), name)` 分键缓存 client；`RateLimiter` 信号量按运行 loop 惰性创建。
- `database.py:26`：导入期探活用独立临时 loop 并 `close()`，不污染导入期 loop。
- `py_compile` 两个文件均通过（无语法错误）。

## 残留根因 / 待拍板（见 OPEN_QUESTIONS.md）
真实部署最可能根因是 `action_executor`/`intent_classifier` 的 **`asyncio.run` 在线程池**反模式：
整套异步 LLM 调用每次新建并关闭一个 loop，且复用模块级资源。
- 轻量方案（已做）：per-loop 资源缓存，本环境已足够（lib 本身 loop-lazy）。
- 彻底方案：去掉 `asyncio.run`-in-thread，改为在运行中的主 loop 上 `asyncio.run_coroutine_threadsafe`
  或直接 `await`（需确认调用方是否已在 async 上下文）→ 属架构改动，需你拍板。

## 完成标准核对（诚实）
- 后端改动：diff ✅ + py_compile ✅ + 受控复现（证明跨 loop 隐患机制）✅
- 但：**未能在本沙箱复现原错误串**（lib 已 loop-lazy），路演前需在本机真实跑一次确认消失。
- 未用"应该生效了"表述；根因与残留已如实记录。
