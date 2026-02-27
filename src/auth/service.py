"""认证服务核心类"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from urllib.parse import quote
from datetime import datetime
from typing import Literal

import httpx

from src.auth.models import (
    LoginType,
    LoginResponse,
    LogoutResponse,
    OpenLibingAuthCallback,
    RefreshTokenRequest,
    TokenResponse,
    UserInfo,
    UserInfoResponse,
)
from src.auth.storage import AuthStorage

logger = logging.getLogger(__name__)


class AuthService:
    """认证服务类，负责用户登录、登出、token管理等"""

    STATE_KEY = "agent_arena.auth_state"

    def __init__(self, storage: AuthStorage, api_base_url: str = "https://beta.openlibing.com"):
        """初始化认证服务

        Args:
            storage: 认证数据存储实例
            api_base_url: API基础URL
        """
        self.storage = storage
        self.api_base_url = api_base_url
        self._user_info: UserInfo | None = None

    async def initialize(self) -> None:
        """初始化认证服务，加载用户信息"""
        await self.storage.initialize()
        await self._load_user_info()

    async def close(self) -> None:
        """关闭认证服务"""
        await self.storage.close()

    def get_user_info(self) -> UserInfo | None:
        """获取当前用户信息"""
        return self._user_info

    def is_logged_in(self) -> bool:
        """是否已登录"""
        return self._user_info is not None

    def get_login_type(self) -> LoginType | None:
        """获取当前登录类型"""
        return self._user_info.login_type if self._user_info else None

    def get_token(self) -> str | None:
        """获取当前访问令牌"""
        return self._user_info.token if self._user_info else None

    def get_refresh_token(self) -> str | None:
        """获取当前刷新令牌"""
        return self._user_info.refresh_token if self._user_info else None

    async def login(
        self,
        login_type: LoginType = LoginType.OPENLIBING,
        client_name: str = "agent_arena",
        redirect_uri: str | None = None,
    ) -> LoginResponse:
        """发起登录请求

        Args:
            login_type: 登录类型
            client_name: 客户端名称
            redirect_uri: 回调地址

        Returns:
            登录响应，包含登录URL和state
        """
        try:
            state = str(uuid.uuid4())

            # 将 state 保存到数据库，5分钟有效期
            await self.storage.save_auth_state(state, expires_in_seconds=300)

            login_url = self._build_login_url(state, login_type, client_name, redirect_uri)

            logger.info(f"[AuthService] 登录URL: {login_url} (客户端: {client_name})")

            return LoginResponse(
                success=True,
                message="请在浏览器中完成登录",
                login_url=login_url,
                state=state,
            )
        except Exception as e:
            logger.error(f"[AuthService] 登录失败: {e}")
            return LoginResponse(
                success=False,
                message=f"登录失败: {str(e)}",
                login_url=None,
                state=None,
            )

    async def handle_openlibing_callback(self, callback: OpenLibingAuthCallback) -> bool:
        """处理OpenLibing认证回调

        Args:
            callback: 认证回调参数

        Returns:
            是否处理成功
        """
        try:
            logger.info(
                f"[AuthService] 收到回调，state: {callback.state}, code: {callback.code[:20]}..."
            )
            # 从数据库验证 state
            state_valid = await self.storage.get_auth_state(callback.state)
            if not state_valid:
                logger.error(f"[AuthService] 状态验证失败，state: {callback.state}")
                return False

            # 删除已使用的 state
            await self.storage.delete_auth_state(callback.state)

            token_response = await self._get_access_token(callback.code)
            if not token_response:
                return False

            self._user_info = UserInfo(
                account_id=token_response.account_id,
                username=token_response.account_name,
                email=token_response.email,
                phone=None,
                avatar=None,
                token=token_response.token,
                refresh_token=token_response.refreshed_token,
                login_type=LoginType.OPENLIBING,
            )

            await self.storage.save_user(self._user_info)
            logger.info(f"[AuthService] OpenLibing登录成功: {self._user_info.username}")
            return True
        except Exception as e:
            logger.error(f"[AuthService] OpenLibing登录失败: {e}")
            return False

    async def logout(self) -> LogoutResponse:
        """退出登录

        Returns:
            登出响应
        """
        try:
            login_type = self._user_info.login_type if self._user_info else None
            self._user_info = None
            await self.storage.delete_user()

            logger.info("[AuthService] 已退出登录")

            return LogoutResponse(
                success=True,
                message="已退出登录",
            )
        except Exception as e:
            logger.error(f"[AuthService] 登出失败: {e}")
            return LogoutResponse(
                success=False,
                message=f"登出失败: {str(e)}",
            )

    async def refresh_token(self) -> bool:
        """刷新访问令牌

        Returns:
            是否刷新成功
        """
        if not self._user_info or not self._user_info.refresh_token:
            logger.warning("[AuthService] 没有可用的refresh token")
            return False

        try:
            if self._is_token_expired(self._user_info.refresh_token):
                logger.warning("[AuthService] Refresh token已过期")
                await self.logout()
                return False

            token_response = await self._refresh_access_token(self._user_info.refresh_token)
            if not token_response:
                return False

            self._user_info.token = token_response.token
            self._user_info.refresh_token = token_response.refreshed_token
            self._user_info.account_id = token_response.account_id

            await self.storage.save_user(self._user_info)
            logger.info("[AuthService] Token刷新成功")
            return True
        except Exception as e:
            logger.error(f"[AuthService] Token刷新失败: {e}")
            return False

    async def get_valid_token(self) -> str | None:
        """获取有效的访问令牌（自动刷新）

        Returns:
            有效的访问令牌，如果获取失败返回None
        """
        if not self._user_info:
            return None

        if self._is_token_expired(self._user_info.token):
            refreshed = await self.refresh_token()
            if not refreshed:
                return None

        return self._user_info.token

    def get_user_info_response(self) -> UserInfoResponse:
        """获取用户信息响应

        Returns:
            用户信息响应
        """
        if self._user_info:
            return UserInfoResponse(
                account_id=self._user_info.account_id,
                username=self._user_info.username,
                email=self._user_info.email,
                login_type=self._user_info.login_type,
                is_logged_in=True,
            )
        else:
            return UserInfoResponse(
                account_id="",
                username="",
                email=None,
                login_type=LoginType.OPENLIBING,
                is_logged_in=False,
            )

    def _build_login_url(
        self, state: str, login_type: LoginType, client_name: str, redirect_uri: str | None = None
    ) -> str:
        """构建登录URL"""
        if not redirect_uri:
            redirect_uri = "http://localhost:3002/callback"
        uri = quote(redirect_uri, safe="!*'()")
        return f"{self.api_base_url}?state={state}&plugin_id={uri}&client={client_name}"

    async def _get_access_token(self, code: str) -> TokenResponse | None:
        """使用授权码获取访问令牌"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_base_url}/gateway/plugin/get/access/token",
                    json={"code": code},
                    timeout=30.0,
                )
                response.raise_for_status()

                data = response.json()
                logger.info(f"[AuthService] 获取访问令牌响应: {data}")
                if not data.get("data"):
                    logger.error(f"[AuthService] 服务器响应异常: {data}")
                    return None

                token_data = data["data"]
                return TokenResponse(
                    token=token_data["token"],
                    refreshed_token=token_data["refreshedToken"],
                    account_id=token_data.get("accountId", ""),
                    account_name=token_data.get("accountName", ""),
                    email=token_data.get("email"),
                )
        except Exception as e:
            logger.error(f"[AuthService] 获取访问令牌失败: {e}")
            return None

    async def _refresh_access_token(self, refresh_token: str) -> TokenResponse | None:
        """使用刷新令牌获取新的访问令牌"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_base_url}/gateway/plugin/get/access/token/by/refresh/token",
                    json={"refreshedToken": refresh_token},
                    timeout=30.0,
                )
                response.raise_for_status()

                data = response.json()
                if not data.get("data"):
                    logger.error("[AuthService] 服务器响应异常")
                    return None

                token_data = data["data"]
                return TokenResponse(
                    token=token_data["token"],
                    refreshed_token=token_data["refreshedToken"],
                    account_id=token_data.get("accountId", ""),
                    account_name=token_data.get("accountName", ""),
                    email=token_data.get("email"),
                )
        except Exception as e:
            logger.error(f"[AuthService] 刷新访问令牌失败: {e}")
            return None

    def _is_token_expired(self, token: str) -> bool:
        """检查JWT token是否过期"""
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return True

            payload = json.loads(base64.b64decode(parts[1] + "===").decode())
            if not payload.get("exp"):
                return False

            expiration_time = payload["exp"] * 1000
            buffer_time = 5 * 60 * 1000
            return datetime.now().timestamp() * 1000 >= expiration_time - buffer_time
        except Exception:
            return False

    async def _load_user_info(self) -> None:
        """从存储加载用户信息"""
        try:
            user_info = await self.storage.get_user()
            if user_info:
                self._user_info = user_info
                logger.info(
                    f"[AuthService] 用户信息加载成功: {user_info.username} ({user_info.login_type})"
                )
            else:
                logger.info("[AuthService] 未找到保存的用户信息")
        except Exception as e:
            logger.error(f"[AuthService] 加载用户信息失败: {e}")
