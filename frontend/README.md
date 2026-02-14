# Agent Arena 前端

React + TypeScript + Vite，对接后端 REST API 与 WebSocket。

## 环境要求

- **Node.js**：建议 18.x 或 20.x LTS
- **npm**：随 Node 安装（或使用 pnpm / yarn）

## 第一步：安装 Node.js（若尚未安装）

1. 打开 [Node.js 官网](https://nodejs.org/) 下载 **LTS 版本**（推荐 20.x）。
2. 运行安装程序，勾选「Add to PATH」。
3. **重新打开**终端（或重启 Cursor），执行验证：
   ```powershell
   node -v
   npm -v
   ```
   能输出版本号即表示安装成功。

## 第二步：安装依赖并启动

在项目根目录或本目录下执行：

```powershell
cd d:\projects\Agent_Arena\frontend
npm install
npm run dev
```

- `npm install`：安装 package.json 中的依赖（仅需首次或依赖变更时执行）。
- `npm run dev`：启动开发服务器，默认访问 **http://localhost:5173**。

前端会把 `/api` 和 `/ws` 代理到 `http://localhost:8000`，因此需要**先启动后端**，否则接口会报错。

## 启动顺序建议

1. 启动后端（在项目根目录）：
   ```powershell
   cd d:\projects\Agent_Arena
   uvicorn src.main:app --reload
   ```
2. 再启动前端：
   ```powershell
   cd d:\projects\Agent_Arena\frontend
   npm run dev
   ```
3. 浏览器打开：http://localhost:5173

## 常用命令

| 命令 | 说明 |
|------|------|
| `npm run dev` | 开发模式（热更新） |
| `npm run build` | 生产构建，输出到 `dist/` |
| `npm run preview` | 本地预览构建结果 |

## 故障排查

- **`node` 或 `npm` 无法识别**：未安装 Node 或未加入 PATH，请完成「第一步」并重启终端。
- **端口 5173 被占用**：在 `vite.config.ts` 的 `server.port` 中修改端口。
- **接口 404 / 连接失败**：确认后端已在 8000 端口运行，且 Vite 代理配置正确（见 `vite.config.ts` 的 `server.proxy`）。
