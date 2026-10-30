# -*- coding: utf-8 -*-
"""运行上下文暂存（债B 飞轮闭环：写路径）。

brain/run 在 S2 完成时把本次运行的「字段形态签名」暂存进来；
反馈端点（/runs/{run_id}/feedback）据此把 👍/👎 经验按「(主题, 数据形态签名)」写回经验库，
使未来同形态数据的 S2 生成能读回该经验（见 flywheel.build_flywheel_context_from_fields）。

注意：进程内内存存储，后端重启后丢失（同会话反馈闭环足够；如需跨重启持久化可迁 DB，见《白盒规则说明》）。
"""
from typing import Dict, Optional

_RUN_CONTEXT: Dict[str, Dict] = {}


def set_run_context(
    run_id: str, fields, grain: str, theme: str, signature: str, dataset_id: str = ""
) -> None:
    """S2 完成时记录本次运行的字段形态，供反馈端点回写经验库。"""
    _RUN_CONTEXT[run_id] = {
        "fields": list(fields or []),
        "grain": grain or "detail",
        "theme": theme or "",
        "signature": signature,
        "dataset_id": dataset_id,
    }


def get_run_context(run_id: str) -> Optional[Dict]:
    """反馈端点取回运行上下文（含数据形态签名）。"""
    return _RUN_CONTEXT.get(run_id)


def clear_run_context(run_id: str) -> None:
    _RUN_CONTEXT.pop(run_id, None)
