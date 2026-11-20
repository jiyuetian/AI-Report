"""投产姿势（deployment posture）单一真相源 —— Task #716。

背景：`.env` 为本地开发便利同时打开了
  DEBUG=true / ENABLE_INTERNAL_ENDPOINTS=on / ENABLE_API_DOCS=on
并使用了弱 SECRET_KEY 与明文 LLM key。写端点虽已在 Task #713 加固为「无条件鉴权」，
但「投产前到底还有几项没关」此前没有任何一处能一眼看清，只能靠人翻 .env。

本模块只做【只读自检与可见性】，不修改任何配置、不改任何业务逻辑：
  - posture()          完整结果（含中文修复建议），仅供进程内/启动日志使用
  - posture_summary()  摘要（仅一个布尔 + 检查项数），供公开 /health 使用
  - log_posture()      启动时打印完整清单与修复建议

安全约定：**绝不输出 SECRET_KEY / API key / 连接串的任何明文或长度以外的值**；
公开 /health 只暴露 production_ready 布尔，不暴露具体未通过项，
避免给外部探测者提供可用信息。投产时请复制 backend/.env.production.example，
并通过环境变量/密钥管理服务注入真实值，不要把密钥写进仓库文件。
"""
from typing import Any, Dict, List

from app.core.config import settings, get_llm_provider_list

# 已知的开发默认弱密钥（仅做等值比对，不打印实际值）
_DEV_SECRETS = {
    "local-dev-secret-key", "your-secret-key-here", "changeme",
    "secret", "dev", "test", "",
}
_MIN_SECRET_LEN = 32

# 阻断项：投产必须全部通过
_BLOCKER_KEYS = (
    "debug_off",
    "internal_endpoints_closed",
    "api_docs_closed",
    "strong_secret",
)
# 建议项：不阻断 production_ready，但启动日志会提示
_ADVISORY_KEYS = ("llm_configured", "short_token_ttl")

_HINTS = {
    "debug_off": "DEBUG=true 会在启动时执行开发期建表/迁移逻辑，投产须设 DEBUG=false",
    "internal_endpoints_closed": "ENABLE_INTERNAL_ENDPOINTS=on 会放开内部端点匿名只读，投产须设 false",
    "api_docs_closed": "ENABLE_API_DOCS=on 会公开 /docs /redoc /openapi.json，投产须设 false",
    "strong_secret": "SECRET_KEY 仍是开发默认值或长度不足 32，投产须注入随机强密钥",
    "llm_configured": "未配置任何 LLM provider，AI 链路将全程走规则兜底（功能降级但不报错）",
    "short_token_ttl": "ACCESS_TOKEN_EXPIRE_MINUTES > 120，令牌有效期偏长，建议缩短到 120 分钟以内",
}


def posture() -> Dict[str, Any]:
    """返回完整投产姿势自检结果（不含任何密钥明文）。"""
    secret = settings.SECRET_KEY or ""
    checks = {
        "debug_off": not bool(settings.DEBUG),
        "internal_endpoints_closed": not bool(settings.ENABLE_INTERNAL_ENDPOINTS),
        "api_docs_closed": not bool(settings.ENABLE_API_DOCS),
        "strong_secret": secret not in _DEV_SECRETS and len(secret) >= _MIN_SECRET_LEN,
        "llm_configured": bool(get_llm_provider_list()),
        "short_token_ttl": int(settings.ACCESS_TOKEN_EXPIRE_MINUTES or 0) <= 120,
    }

    def _items(keys: tuple) -> List[Dict[str, str]]:
        return [
            {"code": k, "hint": _HINTS[k]}
            for k in keys if not checks.get(k, True)
        ]

    blockers = _items(_BLOCKER_KEYS)
    advisories = _items(_ADVISORY_KEYS)
    return {
        "production_ready": not blockers,
        "checks": checks,
        "check_count": len(checks),
        "blockers": blockers,
        "advisories": advisories,
    }


def posture_summary() -> Dict[str, Any]:
    """公开 /health 使用的摘要：不给外部探测者任何具体缺口信息。"""
    p = posture()
    return {
        "production_ready": p["production_ready"],
        "checks": p["check_count"],
    }


def log_posture() -> Dict[str, Any]:
    """启动期打印完整清单（运维可见），异常绝不阻断服务启动。"""
    p = posture()
    if p["production_ready"] and not p["advisories"]:
        print("[POSTURE] 投产姿势自检：%d 项全部通过，production_ready=true" % p["check_count"])
        return p
    print(
        "[POSTURE] 投产姿势自检：production_ready=%s（阻断 %d 项 / 建议 %d 项）"
        % (p["production_ready"], len(p["blockers"]), len(p["advisories"]))
    )
    for item in p["blockers"]:
        print("[POSTURE-BLOCK] %s -> %s" % (item["code"], item["hint"]))
    for item in p["advisories"]:
        print("[POSTURE-ADVICE] %s -> %s" % (item["code"], item["hint"]))
    print(
        "[POSTURE] 本地开发可保留 dev 值（写端点已无条件鉴权）；投产请复制 "
        ".env.production.example 并用环境变量注入密钥，勿把密钥写进仓库。"
    )
    return p
