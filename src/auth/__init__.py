"""认证模块 - 独立的用户认证登录模块

支持 OpenLibing 登录方式：
- OpenLibing: 使用 OAuth2 授权码模式

主要功能：
- 用户登录/登出
- Token 管理和自动刷新
- 用户信息持久化
- 认证状态查询
"""

from src.auth.models import (
    LoginRequest,
    LoginResponse,
    LoginType,
    LogoutResponse,
    OpenLibingAuthCallback,
    RefreshTokenRequest,
    TokenResponse,
    UserInfo,
    UserInfoResponse,
)
from src.auth.service import AuthService
from src.auth.storage import AuthStorage

__all__ = [
    "AuthService",
    "AuthStorage",
    "LoginType",
    "UserInfo",
    "TokenResponse",
    "OpenLibingAuthCallback",
    "RefreshTokenRequest",
    "LoginRequest",
    "LoginResponse",
    "LogoutResponse",
    "UserInfoResponse",
]
