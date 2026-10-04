# verify_script_guide.md — 验证脚本编写准则

> 经验沉淀：验证脚本怎么写才不是「假绿」。

## 铁律（2026-10-04 由 ISS-066 night27 守卫缺陷补出）

**结构性断言（grep / 字符串存在性）不能替代运行时断言。**

- async/await 类缺陷：缺 `await` 时函数返回 `coroutine`，`if coroutine:` 恒真，结构上看似「有赋值」，
  真跑时把 coroutine 塞进响应体 → `json.dumps` 抛 `TypeError` → SSE 中断。grep 永远查不出这种 bug。
- JSON 序列化类缺陷：把 `dict` / `coroutine` / `datetime` 等非可序列化对象塞进要 `json.dumps` 的字段，
  只有真跑 `json.dumps(...)` 才会暴露。

**判定标准**：凡涉及以下任一类改动，验证脚本必须「真跑分支」而非只 grep：
1. 调用 `async def` 函数（缺 await 类）；
2. 把函数返回值（dict / 对象）直接放进要序列化的响应体；
3. 任何「非空 / 非 None」契约（防前端空气泡、防空响应）。

**真跑分支的最小成本做法**：直接 `import` 真实后端函数（如 `from app.api.chat import generate_intent_response`），
用真实输入 `await` 它，再把结果按修复后的逻辑走一遍分支，最后对「最终落库的响应对象」做：
- `isinstance(resp["message"], str) and len(resp["message"]) > 0`
- `json.dumps(full_response, ensure_ascii=False)` 不抛异常

**参考实现**：`tests/_fixtures/real/_verify_iss066_message.py`
（复现旧 bug 的 coroutine→TypeError，再验证修复后 message 为非空 str 且可序列化，10/10 PASS）。

## 反例（本次踩的坑）

night27 原 `_verify_night27_iss062_066.py` 对 ISS-066 只做了「`generate_intent_response` 回退分支存在」「统一兜底文案存在」
的结构性断言 → 23/23 全绿，却没拦住「缺 await + 赋 dict 进 message」的崩溃。结构绿 ≠ 运行绿。
