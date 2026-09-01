"""认证API - 登录/找回密码/验证码"""
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from typing import Optional
import random
import string

from app.core.security import (
    verify_password, get_password_hash, create_access_token,
    LoginLockManager, MAX_LOGIN_ATTEMPTS, LOCKOUT_DURATION_MINUTES,
    get_current_user
)
from app.core.audit import audit_log
from app.core.database import get_db
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User, Role, UserRole

router = APIRouter(prefix="/auth", tags=["Authentication"])


# 请求模型
class LoginRequest(BaseModel):
    username: str
    password: str
    captcha: Optional[str] = None  # 验证码


class ForgotPasswordRequest(BaseModel):
    phone: str  # 手机号


class VerifyCodeRequest(BaseModel):
    phone: str
    code: str


class ResetPasswordRequest(BaseModel):
    phone: str
    code: str
    new_password: str


# 验证码存储（实际应用应使用Redis）
_verification_codes: dict = {}


def _generate_code() -> str:
    """生成6位验证码"""
    return ''.join(random.choices(string.digits, k=6))


def _generate_captcha() -> tuple[str, str]:
    """生成图形验证码（简化版）"""
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    # 实际应返回图片，这里简化
    return code, code


@router.post("/login")
async def login(request: Request, login_req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    用户登录
    
    错误状态：
    - 账号不存在
    - 密码错误（剩余X次）
    - 账号已锁定（请30分钟后重试）
    """
    username = login_req.username
    
    # 检查是否被锁定
    is_locked, lock_until = LoginLockManager.is_locked(username)
    if is_locked:
        remaining_minutes = int((lock_until - datetime.utcnow()).total_seconds() / 60)
        audit_log(
            action="login_failed",
            user=username,
            ip=request.client.host,
            detail={"reason": "account_locked", "remaining_minutes": remaining_minutes}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ACCOUNT_LOCKED",
                "message": f"账号已锁定，请{remaining_minutes}分钟后重试",
                "lock_until": lock_until.isoformat()
            }
        )
    
    # 查询用户（真实数据库查询）
    user = None
    result = await db.execute(select(User).where(User.username == username))
    db_user = result.scalars().first()
    if db_user is not None:
        role_names = (await db.execute(
            select(Role.name).join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == db_user.id)
        )).scalars().all()
        user = {
            "id": str(db_user.id),
            "username": db_user.username,
            "full_name": db_user.full_name,
            "hashed_password": db_user.hashed_password,
            "roles": list(role_names),
        }

    if not user:
        audit_log(
            action="login_failed",
            user=username,
            ip=request.client.host,
            detail={"reason": "user_not_found"}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "USER_NOT_FOUND",
                "message": "账号不存在"
            }
        )
    
    # 验证密码
    if not verify_password(login_req.password, user.get("hashed_password", "")):
        # 记录失败尝试
        record = LoginLockManager.record_attempt(username, success=False)
        remaining = LoginLockManager.get_remaining_attempts(username)
        
        audit_log(
            action="login_failed",
            user=username,
            ip=request.client.host,
            detail={"reason": "wrong_password", "remaining_attempts": remaining}
        )
        
        if remaining == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "ACCOUNT_LOCKED",
                    "message": f"密码错误次数过多，账号已锁定，请{LOCKOUT_DURATION_MINUTES}分钟后重试"
                }
            )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "WRONG_PASSWORD",
                "message": f"密码错误，还剩{remaining}次机会"
            }
        )
    
    # 登录成功
    LoginLockManager.record_attempt(username, success=True)
    
    # 创建令牌
    access_token = create_access_token(
        data={
            "sub": user.get("id"),
            "username": user.get("username"),
            "roles": user.get("roles", [])
        }
    )
    
    audit_log(
        action="login_success",
        user=username,
        ip=request.client.host,
        detail={"user_id": user.get("id")}
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 30 * 60,  # 30分钟
        "user": {
            "id": user.get("id"),
            "username": user.get("username"),
            "full_name": user.get("full_name"),
            "roles": user.get("roles", [])
        }
    }


@router.post("/forgot-password/send-code")
async def send_verification_code(request: Request, forgot_req: ForgotPasswordRequest):
    """发送验证码（找回密码第1步）"""
    phone = forgot_req.phone
    
    # 检查手机号是否存在
    # TODO: 查询数据库
    
    # 生成验证码
    code = _generate_code()
    _verification_codes[phone] = {
        "code": code,
        "expires_at": datetime.utcnow() + timedelta(minutes=5)
    }
    
    # TODO: 调用短信服务发送验证码
    print(f"[SMS] 验证码已发送至 {phone}: {code}")
    
    audit_log(
        action="send_verify_code",
        user=phone,
        ip=request.client.host
    )
    
    return {
        "success": True,
        "message": "验证码已发送",
        "expires_in": 300  # 5分钟有效期
    }


@router.post("/forgot-password/verify-code")
async def verify_code(request: Request, verify_req: VerifyCodeRequest):
    """验证验证码（找回密码第2步）"""
    phone = verify_req.phone
    record = _verification_codes.get(phone)
    
    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CODE_NOT_FOUND", "message": "验证码不存在或已过期"}
        )
    
    if datetime.utcnow() > record["expires_at"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CODE_EXPIRED", "message": "验证码已过期"}
        )
    
    if record["code"] != verify_req.code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "WRONG_CODE", "message": "验证码错误"}
        )
    
    return {
        "success": True,
        "message": "验证成功",
        "token": "temp_token_for_reset"  # 临时令牌用于下一步
    }


@router.post("/forgot-password/reset")
async def reset_password(request: Request, reset_req: ResetPasswordRequest):
    """重置密码（找回密码第3-4步）"""
    phone = reset_req.phone
    
    # 验证临时令牌（简化版）
    # TODO: 验证token
    
    # 更新密码
    hashed_password = get_password_hash(reset_req.new_password)
    # TODO: 更新数据库
    
    # 清除验证码
    _verification_codes.pop(phone, None)
    
    audit_log(
        action="password_reset",
        user=phone,
        ip=request.client.host
    )
    
    return {
        "success": True,
        "message": "密码重置成功"
    }


@router.post("/logout")
async def logout(request: Request, current_user = Depends(get_current_user)):
    """用户登出"""
    audit_log(
        action="logout",
        user=current_user.get("username"),
        ip=request.client.host
    )
    return {"success": True, "message": "登出成功"}


@router.get("/captcha")
async def get_captcha():
    """获取图形验证码"""
    code, image = _generate_captcha()
    return {
        "captcha_id": "captcha_id",
        "image": image  # base64编码的图片
    }