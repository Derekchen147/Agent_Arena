"""认证模块数据模型定义"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class LoginType(str, Enum):
    """登录类型"""

    OPENLIBING = "openlibing"


class UserInfo(BaseModel):
    """用户信息"""

    account_id: str = Field(..., description="账户ID，用于所有API调用")
    username: str = Field(..., description="用户名")
    email: str | None = Field(None, description="邮箱")
    phone: str | None = Field(None, description="手机号")
    avatar: str | None = Field(None, description="头像URL")
    token: str = Field(..., description="访问令牌")
    refresh_token: str = Field(..., description="刷新令牌")
    login_type: LoginType = Field(..., description="登录类型")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")


class OpenLibingAuthCallback(BaseModel):
    """OpenLibing认证回调参数"""

    code: str = Field(..., description="授权码")
    state: str = Field(..., description="状态值，用于防CSRF")


class RefreshTokenRequest(BaseModel):
    """Token刷新请求"""

    refreshed_token: str = Field(..., description="刷新令牌")


class TokenResponse(BaseModel):
    """Token响应"""

    token: str = Field(..., description="访问令牌")
    refreshed_token: str = Field(..., description="刷新令牌")
    account_id: str = Field(..., description="账户ID")
    account_name: str = Field(..., description="账户名")
    email: str | None = Field(None, description="邮箱")


class LoginRequest(BaseModel):
    """登录请求"""

    login_type: LoginType = Field(..., description="登录类型")
    client_name: str = Field(default="agent_arena", description="客户端名称")
    redirect_uri: str | None = Field(None, description="回调地址")


class LoginResponse(BaseModel):
    """登录响应"""

    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    login_url: str | None = Field(None, description="登录URL（需要用户在浏览器中打开）")
    state: str | None = Field(None, description="状态值，用于验证回调")


class LogoutResponse(BaseModel):
    """登出响应"""

    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")


class UserInfoResponse(BaseModel):
    """用户信息响应"""

    account_id: str
    username: str
    email: str | None
    login_type: LoginType
    is_logged_in: bool
