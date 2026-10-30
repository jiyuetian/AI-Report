"""领域分析范式加载器（K1 行业成熟建议库）。

白盒可扩展：每个领域一个 <domain>.yaml，专家可编辑；新增领域无需改码。
见《白盒规则说明》§2.5.3。仅依赖 stdlib + PyYAML，可被离线生成器与在线 AI 上下文共用。
"""
import os
import yaml
from typing import Dict, List, Optional

_PLAYBOOK_DIR = os.path.dirname(os.path.abspath(__file__))
# 注意：本文件与 domain_playbooks/ 同级，故上溯一级
_PLAYBOOK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "domain_playbooks")

# 领域别名 → 文件 key（贴合用户当前项目：风控/财务/通用）
_ALIAS = {
    "风控": "risk", "担保": "risk", "信贷": "risk", "风险": "risk", "risk": "risk",
    "财务": "finance", "经营": "finance", "会计": "finance", "finance": "finance",
    "通用": "general", "其他": "general", "general": "general", "": "general",
}

_CACHE: Dict[str, dict] = {}


def _load_one(key: str) -> Optional[dict]:
    path = os.path.join(_PLAYBOOK_DIR, f"{key}.yaml")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_playbook(domain: str) -> dict:
    """返回领域 playbook；未知领域回退 general。结果缓存。"""
    d = (domain or "general").strip().lower()
    key = _ALIAS.get(d, d)
    if key not in _CACHE:
        pb = _load_one(key) or _load_one("general") or {}
        _CACHE[key] = pb
    return _CACHE[key]


def list_domains() -> List[str]:
    """已注册领域列表。"""
    return sorted(f[:-5] for f in os.listdir(_PLAYBOOK_DIR) if f.endswith(".yaml"))


def reload() -> None:
    """清空缓存（专家编辑 yaml 后热重载）。"""
    _CACHE.clear()
