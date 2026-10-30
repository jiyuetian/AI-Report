# -*- coding: utf-8 -*-
"""
O10-5 真机 UI 验证（Playwright 真实浏览器）。
前置：隔离后端 8077 + 隔离前端 5199 已起，/tmp/iso_creds.json 已生成。
动作：注入 token → 打开 /#/profile → 展开单步 → 校验推理日志渲染 → 点赞反馈 → 截图。
"""
import json
import sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5199"
creds = json.load(open("/tmp/iso_creds.json", encoding="utf-8"))
token = creds["token"]
user = creds["user"]

checks = []


def chk(name, cond, detail=""):
    checks.append((name, bool(cond)))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail and not cond else ""))


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1280, "height": 1000})
    page = ctx.new_page()
    pageerrors = []
    page.on("pageerror", lambda e: pageerrors.append(str(e)))

    # 先访问 origin 再注入 token（vite HMR 下 networkidle 不可达，用 domcontentloaded）
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.evaluate(
        "([t,u])=>{localStorage.setItem('token',t);localStorage.setItem('user',JSON.stringify(u));}",
        [token, user],
    )
    page.goto(BASE + "/profile", wait_until="domcontentloaded")

    try:
        page.wait_for_selector("text=个人中心 · 运行记录", timeout=20000)
        chk("UI-运行记录页渲染", True)
    except Exception as e:
        chk("UI-运行记录页渲染", False, str(e)[:200])

    chk("UI-权限隔离说明可见",
        page.locator("text=普通用户仅可见自己的运行记录").count() > 0)

    try:
        page.wait_for_selector("button:has-text('查看')", timeout=15000)
        chk("UI-运行列表含数据行", True)
    except Exception as e:
        chk("UI-运行列表含数据行", False, str(e)[:200])

    page.locator("button:has-text('查看')").first.click()
    try:
        page.wait_for_selector("text=处理方案与原因（每步推理日志）", timeout=15000)
        chk("UI-单步详情展开(推理日志标题)", True)
    except Exception as e:
        chk("UI-单步详情展开(推理日志标题)", False, str(e)[:200])

    chk("UI-渲染『处置决定』字段", page.locator("text=处置决定").count() > 0)
    chk("UI-渲染『决定依据 / 原因』字段", page.locator("text=决定依据 / 原因").count() > 0)
    chk("UI-渲染『应用规则』字段", page.locator("text=应用规则").count() > 0)
    chk("UI-渲染『输出指代』字段", page.locator("text=输出指代").count() > 0)

    # O10-3 自纠叙事
    chk("UI-S3自纠『AI 原想』可见(O10-3)", page.locator("text=AI 原想").count() > 0)
    chk("UI-S3自纠『规则改成』可见(O10-3)", page.locator("text=规则改成").count() > 0)

    page.screenshot(path="/tmp/iso_profile.png", full_page=True)
    chk("UI-截图已保存", True, "/tmp/iso_profile.png")

    # 导出详情面板真实 DOM 文本（确凿证据，避免视觉模型误读小字体中文）
    try:
        detail_text = page.locator(".ant-card").nth(1).inner_text(timeout=8000)
    except Exception:
        detail_text = page.inner_text()
    with open("/tmp/iso_detail.txt", "w", encoding="utf-8") as f:
        f.write(detail_text)
    print("---- 详情面板真实文本片段 ----")
    print(detail_text[:1500])

    # O10-4 点赞反馈
    try:
        page.get_by_role("button", name="赞").click(timeout=5000)
        page.wait_for_selector("text=已点赞", timeout=8000)
        chk("UI-点赞反馈成功(O10-4)", True)
    except Exception as e:
        chk("UI-点赞反馈成功(O10-4)", False, str(e)[:200])

    chk("UI-无JS运行时错误", len(pageerrors) == 0, f"errors={pageerrors[:3]}")
    browser.close()

passed = sum(1 for _, c in checks if c)
total = len(checks)
print(f"\n==== Playwright UI 验证 (O10-5): {passed}/{total} 通过 ====")
sys.exit(0 if passed == total else 1)
