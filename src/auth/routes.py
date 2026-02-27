"""认证模块 FastAPI 路由"""

from fastapi import APIRouter, HTTPException, status

from src.auth.models import (
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    OpenLibingAuthCallback,
    UserInfoResponse,
)
from src.auth.service import AuthService

router = APIRouter(prefix="/api/auth", tags=["认证"])


def get_auth_service() -> AuthService:
    """获取认证服务实例（依赖注入）"""
    from src.main import app_state

    if not hasattr(app_state, "auth_service"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="认证服务未初始化",
        )

    return app_state.auth_service


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """发起登录请求

    返回登录URL，用户需要在浏览器中打开该URL完成登录
    """
    auth_service = get_auth_service()
    return await auth_service.login(
        login_type=request.login_type,
        client_name=request.client_name,
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout() -> LogoutResponse:
    """退出登录"""
    auth_service = get_auth_service()
    return await auth_service.logout()


@router.get("/userinfo", response_model=UserInfoResponse)
async def get_userinfo() -> UserInfoResponse:
    """获取当前用户信息"""
    auth_service = get_auth_service()
    return auth_service.get_user_info_response()


@router.post("/callback/openlibing")
async def handle_openlibing_callback(callback: OpenLibingAuthCallback):
    """处理 OpenLibing 认证回调"""
    auth_service = get_auth_service()
    success = await auth_service.handle_openlibing_callback(callback)

    if success:
        return {"success": True, "message": "登录成功"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="登录失败",
        )


@router.post("/refresh")
async def refresh_token():
    """刷新访问令牌"""
    auth_service = get_auth_service()
    success = await auth_service.refresh_token()

    if success:
        return {"success": True, "message": "Token刷新成功"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token刷新失败",
        )


@router.get("/token")
async def get_valid_token():
    """获取有效的访问令牌（自动刷新）"""
    auth_service = get_auth_service()
    token = await auth_service.get_valid_token()

    if token:
        return {"token": token}
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或Token无效",
        )


@router.get("/status")
async def get_auth_status():
    """获取认证状态"""
    auth_service = get_auth_service()
    return {
        "is_logged_in": auth_service.is_logged_in(),
        "login_type": auth_service.get_login_type(),
    }
