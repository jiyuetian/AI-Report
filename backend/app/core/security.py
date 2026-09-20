"""安全工具 - JWT、密码、锁定机制"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import redis
import json
import uuid

from app.core.config import settings

# 密码加密
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT配置
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

# Redis连接（用于登录锁定）；本地无 Redis 时降级为不锁定，避免阻断登录
try:
    redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    redis_client.ping()
except Exception:
    redis_client = None

# 登录锁定配置
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 30

# Redis 不可用时的内存兜底（D0-2）：本地无 Redis 时锁定仍生效，避免降级为不锁定
_memory_attempts: Dict[str, Dict[str, Any]] = {}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    return pwd_context.hash(password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """创建JWT令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "jti": str(uuid.uuid4())})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """解码JWT令牌"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


# ============== 令牌吊销（服务端态，D2-5） ==============
# 内存缓存用于高频校验（O(1)），DB 持久化用于重启后旧 token 仍失效。
_blacklist_cache: set = set()


def is_token_blacklisted(jti: str) -> bool:
    """检查 jti 是否已被吊销"""
    return jti in _blacklist_cache


async def blacklist_token(jti: str, exp) -> None:
    """吊销某个 jti（登出时调用）：写入内存缓存 + 持久化到 token_blacklist 表。"""
    if not jti:
        return
    _blacklist_cache.add(jti)
    try:
        from app.core.database import async_session_factory
        from sqlalchemy import select
        from app.models.blacklist import TokenBlacklist
        async with async_session_factory() as db:
            existing = (await db.execute(
                select(TokenBlacklist).where(TokenBlacklist.jti == jti)
            )).scalar_one_or_none()
            if not existing:
                db.add(TokenBlacklist(jti=jti, exp=exp))
                await db.commit()
    except Exception as e:
        # 持久化失败不影响本次登出（内存缓存已生效）
        print(f"[SECURITY] 黑名单持久化失败(忽略): {e}")


async def load_blacklist_cache() -> None:
    """启动时从 DB 载入已吊销 jti（重启后旧 token 仍失效）。"""
    try:
        from app.core.database import async_session_factory
        from sqlalchemy import select
        from app.models.blacklist import TokenBlacklist
        async with async_session_factory() as db:
            rows = (await db.execute(select(TokenBlacklist.jti))).scalars().all()
            for j in rows:
                _blacklist_cache.add(j)
        if _blacklist_cache:
            print(f"✅ 已载入 {len(_blacklist_cache)} 条吊销令牌")
    except Exception as e:
        print(f"[SECURITY] 黑名单载入失败(忽略): {e}")


# 登录锁定管理
class LoginLockManager:
    """登录锁定管理器"""
    
    @staticmethod
    def _get_key(username: str) -> str:
        return f"login_attempts:{username}"
    
    @classmethod
    def get_attempts(cls, username: str) -> Dict[str, Any]:
        """获取登录尝试记录（Redis 优先，缺 Redis 用内存兜底）"""
        key = cls._get_key(username)
        if redis_client:
            data = redis_client.get(key)
            if data:
                return json.loads(data)
            return {"count": 0, "locked_until": None}
        return _memory_attempts.get(key, {"count": 0, "locked_until": None})
    
    @classmethod
    def record_attempt(cls, username: str, success: bool = False) -> Dict[str, Any]:
        """记录登录尝试"""
        key = cls._get_key(username)
        record = cls.get_attempts(username)
        
        if success:
            # 登录成功，清除记录
            if redis_client:
                redis_client.delete(key)
            _memory_attempts.pop(key, None)
            return {"count": 0, "locked_until": None}
        
        # 增加失败次数
        record["count"] = record.get("count", 0) + 1
        
        # 检查是否达到锁定阈值
        if record["count"] >= MAX_LOGIN_ATTEMPTS:
            lock_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            record["locked_until"] = lock_until.isoformat()
        
        # 保存记录（30分钟后过期）
        if redis_client:
            redis_client.setex(key, timedelta(minutes=LOCKOUT_DURATION_MINUTES), json.dumps(record))
        else:
            _memory_attempts[key] = record
        return record
    
    @classmethod
    def is_locked(cls, username: str) -> tuple[bool, Optional[datetime]]:
        """检查账户是否被锁定"""
        record = cls.get_attempts(username)
        locked_until = record.get("locked_until")
        
        if locked_until:
            lock_time = datetime.fromisoformat(locked_until)
            if datetime.utcnow() < lock_time:
                return True, lock_time
        
        return False, None
    
    @classmethod
    def get_remaining_attempts(cls, username: str) -> int:
        """获取剩余尝试次数"""
        record = cls.get_attempts(username)
        return max(0, MAX_LOGIN_ATTEMPTS - record.get("count", 0))


# JWT认证
security = HTTPBearer(auto_error=False)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """获取当前用户（依赖注入）"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    payload = decode_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 吊销检查（D2-5）：已登出的 token 立即失效
    jti = payload.get("jti")
    if jti and is_token_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌已吊销，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌格式错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return {
        "user_id": user_id,
        "username": payload.get("username"),
        "roles": payload.get("roles", []),
        "is_superuser": payload.get("is_superuser", False),
        "jti": payload.get("jti"),
        "token_exp": payload.get("exp"),
    }


# RBAC权限检查
def require_roles(allowed_roles: list):
    """角色权限装饰器（依赖注入 current_user 后做 RBAC 校验）"""
    async def role_checker(current_user: Dict = Depends(get_current_user)):
        user_roles = current_user.get("roles", [])
        if not any(role in allowed_roles for role in user_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足，无法访问此资源"
            )
        return current_user
    return role_checker


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Optional[Dict[str, Any]]:
    """与 get_current_user 类似，但缺失/无效/已吊销令牌时返回 None 而非 401。

    用于"看板明细"等接口：未登录用户可凭有效 share_code 访问分享内容，
    否则必须登录（D2-4c 关闭匿名直读，同时保留分享功能）。
    """
    if not credentials:
        return None
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None:
        return None
    jti = payload.get("jti")
    if jti and is_token_blacklisted(jti):
        return None
    user_id = payload.get("sub")
    if user_id is None:
        return None
    return {
        "user_id": user_id,
        "username": payload.get("username"),
        "roles": payload.get("roles", []),
        "is_superuser": payload.get("is_superuser", False),
        "jti": payload.get("jti"),
        "token_exp": payload.get("exp"),
    }


async def require_admin(
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user)
) -> Dict[str, Any]:
    """管理员门禁：基于 is_superuser 或 admin 角色（本系统 admin 仅 is_superuser，无角色）。"""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未认证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_user.get("is_superuser") and "admin" not in current_user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user


# 内置角色
class Roles:
    """系统内置角色"""
    ADMIN = "admin"           # 管理员
    ANALYST = "analyst"       # 分析师
    VIEWER = "viewer"         # 查看者
    OPERATOR = "operator"     # 运营人员
    
    @classmethod
    def all(cls):
        return [cls.ADMIN, cls.ANALYST, cls.VIEWER, cls.OPERATOR]