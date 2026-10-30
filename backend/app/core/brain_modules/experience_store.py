"""经验库（A0-2 · K2 经验引擎）。

沉淀"之前 AI 处理的经验"：同一 (领域, 数据形态签名) 下哪些图表/叙事决策被证明有效（低编辑率/被导出），
哪些被用户改掉（反向教材）。飞轮与历史 AI 处理持续写入，离线生成器与在线 AI 均可检索复用。
白盒、可扩展：以 JSON 文件存储（与 domain_playbooks 同级），专家可直接查看/编辑；后续可平滑迁移到 DB。

见《白盒规则说明》§2.5.4 / §6.2。
"""
import hashlib
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

_STORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "experience_store.json")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load() -> Dict[str, Any]:
    if os.path.exists(_STORE_PATH):
        try:
            with open(_STORE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save(data: Dict[str, Any]) -> None:
    with open(_STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _sig(domain: str, data_signature: str) -> str:
    return f"{domain}::{hashlib.md5(data_signature.encode('utf-8')).hexdigest()[:12]}"


def record_experience(
    domain: str,
    data_signature: str,
    decision: str,
    outcome: str = "good",
) -> Dict[str, Any]:
    """记录一条经验：某 (领域,数据形态) 下的决策及其结果。

    outcome: "good"（被采纳/低编辑/导出）| "edited"（被用户改掉，反向教材）。
    """
    data = _load()
    key = _sig(domain, data_signature)
    rec = data.get(key, {
        "domain": domain, "signature": data_signature,
        "decisions": {}, "good": 0, "edited": 0, "count": 0,
    })
    rec["decisions"][decision] = rec["decisions"].get(decision, 0) + 1
    if outcome == "good":
        rec["good"] += 1
    elif outcome == "edited":
        rec["edited"] += 1
    rec["count"] += 1
    rec["last_outcome"] = outcome
    rec["last_seen"] = _now()
    data[key] = rec
    _save(data)
    return rec


def retrieve_experience(
    domain: str, data_signature: str, top_n: int = 3
) -> List[Dict[str, Any]]:
    """检索历史有效决策，按被采纳次数降序返回（含被改次数，供反向教材）。"""
    data = _load()
    rec = data.get(_sig(domain, data_signature))
    if not rec:
        return []
    ranked = sorted(rec["decisions"].items(), key=lambda kv: kv[1], reverse=True)
    return [
        {"decision": d, "count": c, "good": rec.get("good", 0), "edited": rec.get("edited", 0)}
        for d, c in ranked[:top_n]
    ]


def stats() -> Dict[str, Any]:
    data = _load()
    return {"records": len(data), "path": _STORE_PATH}
