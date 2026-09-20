"""令牌吊销黑名单（服务端态 JWT 吊销，D2-5）

logout 时将 token 的 jti 写入此表，get_current_user 校验时拒绝已吊销的 jti。
不依赖 Redis，SQLite/Postgres 均可，重启后仍能保持吊销生效。
"""
from sqlalchemy import String, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.models.base import Base


class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True, nullable=False)
    exp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    blacklisted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
