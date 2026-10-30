# -*- coding: utf-8 -*-
"""运行上下文暂存（债B 飞轮闭环：写路径）。

brain/run 在 S2 完成时把本次运行的「字段形态签名」暂存进来；
反馈端点（/runs/{run_id}/feedback）据此把 👍/👎 经验按「(主题, 数据形态签名)」写回经验库，
使未来同形态数据的 S2 生成能读回该经验（见 flywheel.build_flywheel_context_from_fields）。

持久化：内存 + 同目录 _run_context.json 双写。
【为何必须持久化】读路径的经验键是 `FLYWHEEL_DOMAIN::md5(derive_signature(fields, grain))`；
若 run_context 仅存内存，后端重启后反馈端点取不到签名，会降级写成 `domain=dataset_id / signature=run:{run_id}`，
领域与签名两把钥匙全错，读路径永远读不到 —— 飞轮闭环在重启后静默断裂。
改为 JSON 持久化后，重启也能恢复签名，写路径始终命中读路径认的键，闭环闭合。
（运行时文件，前导下划线 `_` 已被 .gitignore 的 `_*.json` 忽略；后续可平滑迁 DB。）
"""
import json
import os
from typing import Dict, Optional

_STORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_run_context.json")
_RUN_CONTEXT: Dict[str, Dict] = {}


def _load() -> Dict[str, Dict]:
    if os.path.exists(_STORE_PATH):
        try:
            with open(_STORE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save(data: Dict[str, Dict]) -> None:
    try:
        with open(_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        # 持久化失败不应影响主流程，内存态仍可用
        pass


def set_run_context(
    run_id: str, fields, grain: str, theme: str, signature: str, dataset_id: str = ""
) -> None:
    """S2 完成时记录本次运行的字段形态，供反馈端点回写经验库。"""
    rec = {
        "fields": list(fields or []),
        "grain": grain or "detail",
        "theme": theme or "",
        "signature": signature,
        "dataset_id": dataset_id,
    }
    _RUN_CONTEXT[run_id] = rec
    data = _load()
    data[run_id] = rec
    _save(data)


def get_run_context(run_id: str) -> Optional[Dict]:
    """反馈端点取回运行上下文（含数据形态签名）。内存优先，缺失则回退磁盘（重启恢复）。"""
    rec = _RUN_CONTEXT.get(run_id)
    if rec is not None:
        return rec
    data = _load()
    rec = data.get(run_id)
    if rec is not None:
        _RUN_CONTEXT[run_id] = rec  # 恢复进内存缓存
    return rec


def clear_run_context(run_id: str) -> None:
    """反馈消费后清理，避免无限累积。"""
    _RUN_CONTEXT.pop(run_id, None)
    data = _load()
    if run_id in data:
        data.pop(run_id, None)
        _save(data)
