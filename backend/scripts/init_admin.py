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


async def ensure_admin(username: str = "admin", password: str = "Admin@123456") -> None:
    email = f"{username}@aibi.local"
    async with async_session_factory() as db:
        res = await db.execute(select(User).where(User.username == username))
        u = res.scalar_one_or_none()
        if u is None:
            u = User(
                username=username,
                email=email,
                hashed_password=get_password_hash(password),
                full_name="Administrator",
                is_active=True,
                is_superuser=True,
            )
            db.add(u)
            print(f"[OK] 已创建管理员账号: {username} / {password}")
        else:
            u.hashed_password = get_password_hash(password)
            u.is_active = True
            u.is_superuser = True
            print(f"[OK] 已重置账号 {username} 的密码为: {password}")
        await db.commit()


if __name__ == "__main__":
    un = sys.argv[1] if len(sys.argv) > 1 else "admin"
    pw = sys.argv[2] if len(sys.argv) > 2 else "Admin@123456"
    if len(pw) < 8 or not any(c.isupper() for c in pw) or not any(c.isdigit() for c in pw):
        print("[WARN] 密码建议至少8位且含大小写字母与数字（前端登录规则）。")
    asyncio.run(ensure_admin(username=un, password=pw))
