"""大脑阶段隔离 / 用户可读失败消息 验收（批次A-P0 异常流完整性）。

覆盖：
  - _short_err：异常压缩为单行可读原因（≤160 字，无换行）
  - _record_stage_error：阶段失败消息写入 _RUN_STATUS 供 /status 回传
  - chat.py safe_stream：对话 SSE 生成中断兜底（静态守卫，防止回归）
"""
import inspect

import pytest

import app.api.brain_run_sse as brain


def test_short_err_collapses_multiline():
    e = ValueError("line1\n  File x.py line 10\n  more traceback\nfinal line")
    out = brain._short_err(e)
    assert "\n" not in out
    assert len(out) <= 160
    assert out == "line1"


def test_short_err_handles_none():
    assert brain._short_err(None) == "未知异常"


def test_record_stage_error_writes_to_status():
    run_id = "test_run_xyz"
    try:
        brain._record_stage_error(run_id, "S2", "第2步 目标生成失败：xxx")
        errs = brain._RUN_STATUS[run_id]["stage_errors"]
        assert errs["S2"] == "第2步 目标生成失败：xxx"
    finally:
        brain._RUN_STATUS.pop(run_id, None)


def test_chat_safe_stream_wrapper_present():
    """对话流兜底必须保留：异常时 yield error 事件，避免断流卡死。"""
    import app.api.chat as chat

    src = inspect.getsource(chat)
    assert "async def safe_stream" in src, "chat.py 应保留 safe_stream 兜底"
    assert 'sse_event("error"' in src or "sse_event('error'" in src, \
        "safe_stream 应在异常时 yield error 事件"
