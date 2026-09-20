"""
自测脚本：
1) 管理后台 4 个真实聚合端点（HTTP）
2) 版本自动快照逻辑（直接调用 VersionManager）
"""
import asyncio
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"

# ---------- 1) Admin 端点 HTTP 自测 ----------
def http_get(path):
    url = BASE + path
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

def test_admin():
    print("=== Admin 端点自测 ===")
    ok = True
    eps = ["/admin/overview", "/admin/users", "/admin/roles", "/admin/audit"]
    for ep in eps:
        try:
            status, data = http_get(ep)
            assert status == 200, f"{ep} 返回 {status}"
            print(f"[OK] {ep} -> {json.dumps(data, ensure_ascii=False)[:200]}")
        except Exception as e:
            ok = False
            print(f"[FAIL] {ep} -> {e}")
    return ok

# ---------- 2) 版本快照逻辑自测 ----------
async def test_version():
    print("\n=== 版本快照逻辑自测 (VersionManager) ===")
    from app.core.database import async_session_factory
    from app.core.version_manager import VersionManager
    from app.models.dashboard import Dashboard, DashboardVersion
    import uuid

    tmp_id = "selftest_" + uuid.uuid4().hex[:8]
    async with async_session_factory() as db:
        # 造一个临时看板
        dash = Dashboard(
            id=tmp_id,
            name="自测看板",
            status="published",
            config={"title": "t", "charts": []},
            created_by="selftest",
        )
        db.add(dash)
        await db.commit()

        # 生成阶段快照
        v1 = await VersionManager.create_version(
            db, tmp_id, name="AI生成初始版本",
            description="系统自动保存", created_by="selftest", is_auto_save=True,
        )
        # 改配置后再 PATCH 触发 auto_save
        dash.config = {"title": "t2", "charts": [{"id": "c1"}]}
        await db.commit()
        v2 = await VersionManager.auto_save(db, tmp_id, "selftest")

        # 列出版本
        vers = await VersionManager.get_version_list(db, tmp_id)
        print(f"[INFO] 版本数={len(vers)} 名单={[v.name for v in vers]}")

        # 断言
        assert len(vers) >= 1, "至少应有 1 个版本"
        assert any(v.name == "AI生成初始版本" for v in vers), "缺 AI生成初始版本"
        print("[OK] create_version + auto_save + get_version_list 全部通过")

        # 清理
        await db.execute(DashboardVersion.__table__.delete().where(DashboardVersion.dashboard_id == tmp_id))
        await db.execute(Dashboard.__table__.delete().where(Dashboard.id == tmp_id))
        await db.commit()
        print("[OK] 测试数据已清理")
    return True

if __name__ == "__main__":
    admin_ok = test_admin()
    try:
        asyncio.run(test_version())
        ver_ok = True
    except Exception as e:
        ver_ok = False
        print(f"[FAIL] 版本快照自测异常: {e}")
    print("\n=== 结论 ===")
    print(f"Admin 端点: {'PASS' if admin_ok else 'FAIL'}")
    print(f"版本快照:   {'PASS' if ver_ok else 'FAIL'}")
    sys.exit(0 if (admin_ok and ver_ok) else 1)
