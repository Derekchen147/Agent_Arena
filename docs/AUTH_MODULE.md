# 认证模块使用文档

## 概述

认证模块是一个独立的用户认证登录模块，支持 OpenLibing 登录方式。

## 功能特性

- **OAuth2 登录**：支持 OpenLibing（OAuth2 授权码模式）
- **Token 管理**：自动管理访问令牌和刷新令牌
- **自动刷新**：Token 过期时自动刷新
- **持久化存储**：用户信息存储在 SQLite 数据库中
- **状态查询**：提供认证状态和用户信息查询接口

## 模块结构

```
src/auth/
├── __init__.py      # 模块入口，导出主要类和类型
├── models.py        # 数据模型定义
├── storage.py       # 数据存储层（SQLite）
├── service.py       # 认证服务核心类
└── routes.py        # FastAPI 路由
```

## API 接口

### 1. 发起登录

**POST** `/api/auth/login`

请求体参数：
```json
{
  "login_type": "openlibing",  // 或 "hidevlab"
  "client_name": "agent_arena"  // 可选，默认为 "agent_arena"
}
```

响应：
```json
{
  "success": true,
  "message": "请在浏览器中完成登录",
  "login_url": "https://hidevlab.huawei.com/web-ide?state=xxx&plugin_id=xxx&client=xxx",
  "state": "uuid"
}
```

### 2. 处理 OpenLibing 认证回调

**POST** `/api/auth/callback/openlibing`

请求体参数：
```json
{
  "code": "授权码",
  "state": "状态值"
}
```

响应：
```json
{
  "success": true,
  "message": "登录成功"
}
```

### 3. 退出登录

**POST** `/api/auth/logout`

响应：
```json
{
  "success": true,
  "message": "已退出OpenLibing登录"
}
```

### 5. 获取用户信息

**GET** `/api/auth/userinfo`

响应：
```json
{
  "account_id": "账户ID",
  "username": "用户名",
  "email": "邮箱",
  "login_type": "openlibing",
  "is_logged_in": true
}
```

### 6. 刷新 Token

**POST** `/api/auth/refresh`

响应：
```json
{
  "success": true,
  "message": "Token刷新成功"
}
```

### 7. 获取有效的访问令牌

**GET** `/api/auth/token`

响应：
```json
{
  "token": "访问令牌"
}
```

### 8. 获取认证状态

**GET** `/api/auth/status`

响应：
```json
{
  "is_logged_in": true,
  "login_type": "openlibing"
}
```

## 使用示例

### Python 代码示例

```python
from src.auth import AuthService, AuthStorage, LoginType

# 初始化
storage = AuthStorage(db_path="data/agent_arena.db")
await storage.initialize()

auth_service = AuthService(storage=storage)
await auth_service.initialize()

# 发起登录
login_response = await auth_service.login(
    login_type=LoginType.OPENLIBING,
    client_name="agent_arena"
)

if login_response.success:
    print(f"请在浏览器中打开: {login_response.login_url}")
    print(f"State: {login_response.state}")

# 处理回调
from src.auth.models import OpenLibingAuthCallback

callback = OpenLibingAuthCallback(
    code="从浏览器回调获取的code",
    state="登录时返回的state"
)

success = await auth_service.handle_openlibing_callback(callback)
if success:
    print("登录成功！")

# 获取用户信息
user_info = auth_service.get_user_info()
if user_info:
    print(f"用户: {user_info.username}")
    print(f"账户ID: {user_info.account_id}")

# 获取有效的 Token（自动刷新）
token = await auth_service.get_valid_token()
print(f"Token: {token}")

# 退出登录
logout_response = await auth_service.logout()
print(logout_response.message)
```

### HTTP 请求示例

```bash
# 发起登录
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"login_type": "openlibing"}'

# 获取用户信息
curl http://localhost:8000/api/auth/userinfo

# 获取认证状态
curl http://localhost:8000/api/auth/status

# 退出登录
curl -X POST http://localhost:8000/api/auth/logout
```

## 数据模型

### UserInfo

```python
{
    "account_id": str,      # 账户ID
    "username": str,       # 用户名
    "email": str | None,   # 邮箱
    "phone": str | None,   # 手机号
    "avatar": str | None,  # 头像URL
    "token": str,          # 访问令牌
    "refresh_token": str,  # 刷新令牌
    "login_type": LoginType,  # 登录类型
    "resource_id": str | None,  # HidevLab资源ID
    "created_at": datetime,    # 创建时间
    "updated_at": datetime     # 更新时间
}
```

### LoginType

```python
class LoginType(str, Enum):
    OPENLIBING = "openlibing"
```

## 集成到现有系统

认证模块已经集成到 `src/main.py` 中，可以通过 `app_state.auth_service` 访问：

```python
from src.main import app_state

# 获取认证服务
auth_service = app_state.auth_service

# 检查是否已登录
if auth_service.is_logged_in():
    user_info = auth_service.get_user_info()
    print(f"当前用户: {user_info.username}")
```

## 注意事项

1. **State 验证**：登录时返回的 state 必须在回调时验证，防止 CSRF 攻击
2. **Token 过期**：Token 会自动刷新，但如果刷新失败需要重新登录
3. **单用户限制**：当前实现只支持单用户登录，新登录会覆盖旧用户
4. **数据库路径**：默认使用 `data/agent_arena.db`，可通过构造函数自定义

## 配置

### 环境变量

可以在 `.env` 文件中配置：

```env
# API 基础 URL（默认：https://hidevlab.huawei.com）
AUTH_API_BASE_URL=https://hidevlab.huawei.com

# 数据库路径（默认：data/agent_arena.db）
AUTH_DB_PATH=data/agent_arena.db
```

## 扩展

### 添加新的登录方式

1. 在 `models.py` 中添加新的 `LoginType` 枚举值
2. 在 `service.py` 中实现对应的回调处理方法
3. 在 `routes.py` 中添加对应的 API 路由

### 自定义 Token 验证逻辑

继承 `AuthService` 并重写 `_is_token_expired` 方法：

```python
class CustomAuthService(AuthService):
    def _is_token_expired(self, token: str) -> bool:
        # 自定义验证逻辑
        return super()._is_token_expired(token)
```
