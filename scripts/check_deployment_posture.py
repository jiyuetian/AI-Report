# -*- coding: utf-8 -*-
"""投产姿势离线门禁（Task #716）。

静态断言：模板开关、无明文密钥、姿势模块被 /health 与启动流程真实消费、
config 不再重复定义 settings、写端点无条件鉴权仍在。零 DB、零网络、零写入。
"""
import os
import re
import sys
import py_compile

BACKEND = r"C:\Users\Asus009\Desktop\临时\ai大赛\AI-Report\backend"
SCRIPTS = r"C:\Users\Asus009\Desktop\临时\ai大赛\AI-Report\scripts"

results = []


def ck(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (" | " + detail if detail else ""))


def read(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def main():
    posture_py = os.path.join(BACKEND, "app", "core", "deployment_posture.py")
    health_py = os.path.join(BACKEND, "app", "api", "health.py")
    main_py = os.path.join(BACKEND, "app", "main.py")
    config_py = os.path.join(BACKEND, "app", "core", "config.py")
    sec_py = os.path.join(BACKEND, "app", "core", "security.py")
    env_ex = os.path.join(BACKEND, ".env.production.example")

    ck("posture 模块存在", os.path.exists(posture_py))
    if os.path.exists(posture_py):
        s = read(posture_py)
        for fn in ("def posture(", "def posture_summary(", "def log_posture("):
            ck("posture 导出 " + fn.strip(), fn in s)
        ck("posture 不输出密钥明文", "print(settings.SECRET_KEY" not in s and "print(secret" not in s)
        ck("posture 含 4 个阻断项", all(k in s for k in (
            "debug_off", "internal_endpoints_closed", "api_docs_closed", "strong_secret")))

    hs = read(health_py)
    ck("health.py 导入 posture_summary", "from app.core.deployment_posture import posture_summary" in hs)
    ck("health.py /health 下发 deployment 摘要", '"deployment": posture_summary()' in hs)

    ms = read(main_py)
    ck("main.py 启动期调用 log_posture", "log_posture()" in ms and "deployment_posture import log_posture" in ms)

    cs = read(config_py)
    ck("config.py get_settings 只定义一次", len(re.findall(r"^def get_settings\(", cs, re.M)) == 1)
    ck("config.py settings 只赋值一次", len(re.findall(r"^settings = get_settings\(\)", cs, re.M)) == 1)

    ss = read(sec_py)
    ck("写方法无条件鉴权仍在", "is_write = request.method.upper()" in ss
       and "if settings.ENABLE_INTERNAL_ENDPOINTS and not is_write:" in ss)

    ck("投产模板存在", os.path.exists(env_ex))
    if os.path.exists(env_ex):
        e = read(env_ex)
        for line in ("DEBUG=false", "ENABLE_INTERNAL_ENDPOINTS=false", "ENABLE_API_DOCS=false"):
            ck("投产模板 " + line, line in e)
        ck("投产模板无明文 LLM key", "sk-" not in e)
        ck("投产模板无明文 NVIDIA key", "nvapi-" not in e)
        ck("投产模板密钥为占位符", "__REPLACE_WITH_RANDOM_64_HEX_CHARS__" in e)
        ck("投产模板 LLM 走注入", "__INJECT_VIA_ENV__" in e)

    for p in (posture_py, health_py, main_py, config_py):
        try:
            py_compile.compile(p, doraise=True)
            ck("py_compile " + os.path.basename(p), True)
        except Exception as ex:
            ck("py_compile " + os.path.basename(p), False, str(ex)[:160])

    ok = sum(1 for _, v, _ in results if v)
    bad = [(n, d) for n, v, d in results if not v]
    print("POSTURE GATE RESULT: %d PASS / %d FAIL" % (ok, len(bad)))
    if bad:
        print("FAILED:", bad)
        sys.exit(1)


if __name__ == "__main__":
    main()
