"""创建 / 重置管理员账号（首次部署或忘记密码时使用）

用法：
    cd backend
    python scripts/init_admin.py                 # 默认 admin / Admin@123456
    python scripts/init_admin.py 用户名 密码       # 自定义

说明：
    - 复用项目已有的安全函数（bcrypt 哈希）与数据库会话工厂，确保与后端一致。
    - 账号已存在则只重置密码并置为激活 + 超管；不存在则新建。
    - email 为必填唯一列，默认使用 <username>@aibi.local。
"""
import asyncio
import sys

from app.core.database import async_session_factory
from app.core.security import get_password_hash
from app.models.user import User
from sqlalchemy import select


async def ensure_user(username: str, password: str, is_superuser: bool = True) -> None:
    """创建 / 重置账号（管理员或普通用户）。

    - 管理员：is_superuser=True（默认，兼容旧 ensure_admin 行为）。
    - 普通用户：is_superuser=False，用于「普通用户只看报表效果」验收对照。
    """
    email = f"{username}@aibi.local"
    async with async_session_factory() as db:
        res = await db.execute(select(User).where(User.username == username))
        u = res.scalar_one_or_none()
        if u is None:
            u = User(
                username=username,
                email=email,
                hashed_password=get_password_hash(password),
                full_name="Administrator" if is_superuser else "Normal User",
                is_active=True,
                is_superuser=is_superuser,
            )
            db.add(u)
            role = "管理员" if is_superuser else "普通用户"
            print(f"[OK] 已创建{role}账号: {username} / {password}")
        else:
            u.hashed_password = get_password_hash(password)
            u.is_active = True
            u.is_superuser = is_superuser
            role = "管理员" if is_superuser else "普通用户"
            print(f"[OK] 已重置账号 {username} 的密码为: {password}（角色={role}）")
        await db.commit()


# 向后兼容别名
ensure_admin = ensure_user


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="创建 / 重置账号（管理员或普通用户）")
    ap.add_argument("username", nargs="?", default="admin", help="用户名（默认 admin）")
    ap.add_argument("password", nargs="?", default="Admin@123456", help="密码（默认 Admin@123456）")
    ap.add_argument("--normal", action="store_true", help="创建普通用户（非超管）；默认创建管理员")
    args = ap.parse_args()
    if len(args.password) < 8 or not any(c.isupper() for c in args.password) or not any(c.isdigit() for c in args.password):
        print("[WARN] 密码建议至少8位且含大小写字母与数字（前端登录规则）。")
    asyncio.run(ensure_user(username=args.username, password=args.password, is_superuser=not args.normal))
