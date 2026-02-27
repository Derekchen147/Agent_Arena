# 认证模块登录流程说明

## 登录流程

### 1. 前端启动时检查登录状态

- 前端启动时自动调用 `GET /api/auth/status` 检查是否已登录
- 如果未登录，显示登录模态框
- 如果已登录，加载用户信息和群组数据

### 2. 用户点击登录按钮

1. 前端调用 `POST /api/auth/login` 获取登录 URL
2. 后端返回登录 URL 和 state 参数
3. 前端在新窗口打开登录 URL（浏览器跳转到 OpenLibing 登录页面）

### 3. 用户在浏览器完成登录

1. 用户在 OpenLibing 登录页面完成认证
2. OpenLibing 重定向到前端回调页面：`http://localhost:3000/callback?code=xxx&state=xxx`

### 4. 回调页面处理

1. 回调页面 (`/callback`) 获取 URL 参数中的 `code` 和 `state`
2. 调用 `POST /api/auth/callback/openlibing` 发送回调参数
3. 后端验证 state 并获取 access token
4. 后端保存用户信息到数据库
5. 回调页面通过 `window.opener.postMessage()` 通知主窗口登录成功
6. 回调页面自动关闭

### 5. 主窗口处理登录成功

1. 主窗口收到 `message` 事件
2. 验证消息类型为 `auth_callback`
3. 关闭登录模态框
4. 重新加载用户信息和群组数据
5. 显示用户名和退出登录按钮

## 文件说明

### 前端文件

- `frontend/src/App.tsx` - 主应用，包含登录状态检查和登录模态框
- `frontend/src/components/LoginModal.tsx` - 登录模态框组件
- `frontend/src/pages/AuthCallback.tsx` - 认证回调页面
- `frontend/src/api/authClient.ts` - 认证 API 客户端
- `frontend/src/types/index.ts` - 认证相关类型定义

### 后端文件

- `src/auth/models.py` - 认证数据模型
- `src/auth/service.py` - 认证服务核心类
- `src/auth/storage.py` - 认证数据存储层
- `src/auth/routes.py` - 认证 API 路由

## 配置说明

### 需要配置回调 URL

在 OpenLibing 平台配置回调 URL 为：
```
http://localhost:3000/callback
```

### Vite 配置

确保 `vite.config.ts` 中配置了 API 代理：
```typescript
export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

## 启动步骤

1. 启动后端服务：
```bash
uvicorn src.main:app --reload
```

2. 启动前端服务：
```bash
cd frontend
npm run dev
```

3. 访问 `http://localhost:3000`

4. 如果未登录，会自动显示登录模态框

5. 点击"登录"按钮，在浏览器中完成登录

6. 登录成功后，回调页面会自动关闭，主页面显示用户信息
