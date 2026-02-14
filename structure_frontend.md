# Agent Arena — 前端实现架构

> 本文档描述前端（frontend）的实际代码结构、各文件职责、以及与后端的协作方式。

---

## 一、目录结构

```
frontend/
├── index.html                           # HTML 入口，挂载 #root，引入 main.tsx
├── package.json                         # 项目依赖与脚本
├── tsconfig.json                        # TypeScript 配置（路径别名 @ -> src）
├── vite.config.ts                       # Vite 构建与开发代理
├── src/
│   ├── main.tsx                         # React 入口，挂载 App
│   ├── App.tsx                          # 根组件：状态聚合、布局、数据拉取
│   ├── App.css                          # 全局与布局样式
│   ├── vite-env.d.ts                    # Vite 环境类型声明
│   │
│   ├── types/                           # 类型定义（与后端 Pydantic 对齐）
│   │   └── api.ts                       #   Group / StoredMessage / AgentProfile / WebSocket 报文类型
│   │
│   ├── api/                             # 后端 REST 调用
│   │   └── client.ts                    #   listGroups / getMessages / sendMessage / listAgents 等
│   │
│   ├── hooks/                           # 自定义 Hooks
│   │   └── useGroupWebSocket.ts         #   按群组建立 WebSocket，处理 user_message / agent_message / agent_status / system_message
│   │
│   └── components/                      # UI 组件
│       ├── GroupSidebar.tsx             #   左侧群组列表与「新建群组」入口
│       ├── GroupSidebar.css
│       ├── ChatArea.tsx                 #   中间对话区：消息列表 + 输入框（@mention 解析）
│       ├── ChatArea.css
│       ├── AgentPanel.tsx               #   右侧员工状态面板（idle / analyzing / generating 等）
│       ├── AgentPanel.css
│       ├── CreateGroupModal.tsx         #   新建群组弹窗（名称、描述）
│       └── CreateGroupModal.css
│
└── (构建产物 dist/ 由 vite build 生成，通常 gitignore)
```

---

## 二、各文件职责详解

### 2.1 入口与配置

| 文件 | 职责 |
|------|------|
| `index.html` | 单页入口。`<div id="root">` 挂载点；通过 Google Fonts 引入 Outfit、JetBrains Mono；`<script type="module" src="/src/main.tsx">` 启动应用。 |
| `src/main.tsx` | React 入口。`createRoot` 挂载 `<App />`，包裹 `StrictMode`。 |
| `vite.config.ts` | Vite 配置。`@vitejs/plugin-react`；路径别名 `@` → `src`；开发服务器端口 5173；**代理**：`/api` → `http://localhost:8000`，`/ws` → `ws://localhost:8000`，便于前后端同源开发。 |
| `tsconfig.json` | TypeScript：ES2020、JSX、严格模式、`paths: { "@/*": ["src/*"] }`，仅编译 `src`。 |
| `package.json` | 依赖：react、react-dom；开发依赖：vite、@vitejs/plugin-react、typescript、@types/react*。脚本：`dev`（vite）、`build`（tsc -b && vite build）、`preview`。 |

### 2.2 类型层 (`src/types/`)

与后端 Pydantic 模型一一对应，保证请求/响应与 WebSocket 报文类型安全。

| 文件 | 核心类型 | 说明 |
|------|---------|------|
| `api.ts` | `Group` | 群组：id、name、description、members、config |
|  | `GroupConfig` | 群组配置：max_responders、turn_timeout_seconds、chain_depth_limit 等 |
|  | `GroupMember` | 成员：type(human/agent)、agent_id、display_name、role_in_group |
|  | `StoredMessage` | 持久化消息：group_id、turn_id、author_id/type/name、content、mentions、timestamp |
|  | `AgentProfile` | 员工档案：agent_id、name、avatar、workspace_dir、skills、cli_config、response_config |
|  | `AgentStatus` | 状态枚举：idle / analyzing / reading_memory / generating / done / error / timeout 等 |
|  | `WsUserMessage` / `WsAgentMessage` / `WsAgentStatus` / `WsSystemMessage` | WebSocket 入站报文类型 |
|  | `WsSendMessage` | WebSocket 出站：发送消息（content、mentions） |
|  | `WsIncoming` | 入站报文联合类型 |

### 2.3 API 层 (`src/api/`)

| 文件 | 职责 |
|------|------|
| `client.ts` | 封装所有 REST 调用。`request<T>(path, options)` 统一 fetch、JSON、错误抛出。**Groups**：listGroups、getGroup、createGroup、deleteGroup、addMember、removeMember。**Messages**：getMessages(groupId, { limit, before })、sendMessage({ group_id, content, mentions })。**Agents**：listAgents、getAgent、searchAgentsBySkill。BASE 为空字符串，依赖 Vite 代理将 `/api` 转发到后端。 |

### 2.4 Hooks (`src/hooks/`)

| 文件 | 核心导出 | 职责 |
|------|----------|------|
| `useGroupWebSocket.ts` | `useGroupWebSocket(groupId, callbacks)` | 根据 `groupId` 建立 `ws://.../ws/{groupId}` 连接（开发时通过 Vite 代理到 8000）。维护 `connected`、`agentStatuses: Record<agent_id, AgentStatus>`。收到 `user_message` → `onUserMessage`；`agent_message` → `onAgentMessage`；`agent_status` → 更新 statuses + `onAgentStatus`；`system_message` → `onSystemMessage`。返回 `{ connected, agentStatuses, sendMessage }`，`sendMessage(content, mentions)` 通过 WebSocket 发送 `send_message` 报文。 |

### 2.5 组件层 (`src/components/`)

| 组件 | Props | 职责 |
|------|-------|------|
| `GroupSidebar` | groups, currentId, onSelect, onAddGroup | 左侧边栏。展示群组列表，当前选中高亮；「+ 群组」触发 onAddGroup；无群组时显示「暂无群组，点击上方创建」。 |
| `ChatArea` | groupName, messages, systemMessage, agents, connected, onSend | 中间主区域。顶部显示群组名称与 WebSocket 连接指示；消息列表按 human/agent 样式区分，显示头像、作者、时间、内容；底部输入框支持 @mention 解析（@agent_id 或 @名称），Enter 发送，Shift+Enter 换行；提交时从文本中提取 mentions 传给 onSend。 |
| `AgentPanel` | agents, statuses, memberIds | 右侧面板。列出所有已注册 Agent，显示头像、名称、状态徽章（空闲/分析中/生成中等）；当前群组成员高亮（in-group）。 |
| `CreateGroupModal` | onClose, onCreate | 模态框。表单：名称（必填）、描述（可选）；提交调用 onCreate(name, description)，成功后 onClose；错误时展示错误信息。 |

### 2.6 根组件 (`src/App.tsx`)

| 职责 | 说明 |
|------|------|
| 状态聚合 | groups、agents、currentGroupId、messages、systemMessage、showCreateModal、loading。currentGroup、memberAgentIds 由 currentGroupId 派生。 |
| 数据拉取 | 首屏 `listGroups()` + `listAgents()`；切换群组时 `getMessages(currentGroupId, { limit: 50 })`。 |
| WebSocket 集成 | `useGroupWebSocket(currentGroupId, { onUserMessage: mergeMessage, onAgentMessage, onSystemMessage })`。onAgentMessage 时将 payload 转成 StoredMessage 追加到 messages。 |
| 发送消息 | handleSend：调用 `sendMessage` REST，并将返回的 message 通过 mergeMessage 加入列表（当前实现走 REST，未用 wsSend）。 |
| 创建群组 | handleCreateGroup：createGroup → 新群组加入 groups 并设为当前选中。 |
| 布局 | 左 GroupSidebar、中 ChatArea、右 AgentPanel；showCreateModal 时渲染 CreateGroupModal。 |

---

## 三、运行时数据流与调用关系

### 3.1 应用初始化

```
打开页面
    │
    ▼
main.tsx 挂载 App
    │
    ▼
App 初始 loading=true
    │
    ▼
useEffect: Promise.all([ listGroups(), listAgents() ])
    │
    ├── listGroups()  → GET /api/groups  → setGroups
    └── listAgents()  → GET /api/agents  → setAgents
    │
    ▼
setLoading(false) → 渲染三栏布局
```

### 3.2 切换群组

```
用户点击左侧某群组
    │
    ▼
onSelect(g.id) → setCurrentGroupId(g.id)
    │
    ▼
useEffect(currentGroupId):
    ├── getMessages(currentGroupId, { limit: 50 }) → setMessages
    └── setSystemMessage(null)
    │
    ▼
useGroupWebSocket(groupId) 依赖变化
    │
    ├── 若之前有连接 → 先 close 再重建
    └── 建立 ws://.../ws/{groupId}
    │
    ▼
ChatArea / AgentPanel 用新 messages、memberIds 重渲染
```

### 3.3 用户发送消息

```
用户在 ChatArea 输入并点击发送
    │
    ▼
handleSubmit: 解析 @mention → onSend(content, mentions)
    │
    ▼
App.handleSend
    │
    ├── sendMessage({ group_id, content, mentions })  → POST /api/messages/send
    │
    ├── 后端：存库 → WebSocket 广播 user_message → 异步触发 orchestrator
    │
    └── 前端：mergeMessage(res.message) → 消息列表立即显示用户消息
    │
    ▼
后端编排执行 Agent
    │
    ▼
WebSocket 推送 agent_status(analyzing/generating/done...)
    │
    ▼
useGroupWebSocket 收到 → setAgentStatuses → AgentPanel 更新状态徽章
    │
    ▼
WebSocket 推送 agent_message(agent_id, content, turn_id)
    │
    ▼
onAgentMessage → 合成 StoredMessage → setMessages 追加 → ChatArea 展示 Agent 回复
```

### 3.4 新建群组

```
用户点击「+ 群组」→ setShowCreateModal(true)
    │
    ▼
CreateGroupModal 打开，用户填写名称、描述并提交
    │
    ▼
onCreate(name, description) → createGroup({ name, description })
    │
    ▼
POST /api/groups → res.group
    │
    ▼
setGroups(prev => [...prev, res.group]); setCurrentGroupId(res.group.id); onClose()
```

---

## 四、与后端的协作方式

### 4.1 REST API 使用

| 场景 | 接口 | 说明 |
|------|------|------|
| 群组列表 / 当前群组 | GET /api/groups、GET /api/groups/:id | 侧边栏列表与详情 |
| 消息历史 | GET /api/messages/:group_id?limit=50 | 切换群组时拉取 |
| 发送消息 | POST /api/messages/send | body: group_id, content, mentions |
| 员工列表 | GET /api/agents | 右侧面板与 @mention 解析 |
| 新建群组 | POST /api/groups | body: name, description |

### 4.2 WebSocket 协议

- **连接**：`ws://localhost:8000/ws/{group_id}`（开发阶段由 Vite 代理 `/ws` → `ws://localhost:8000`）。
- **入站**：`user_message`（用户消息回显）、`agent_message`（Agent 回复）、`agent_status`（状态更新）、`system_message`（系统提示）。
- **出站**：`send_message`（content、mentions、author_id、author_name），可替代 REST 发送消息（当前前端主要用 REST 发送，WebSocket 仅用于接收实时推送）。

### 4.3 开发代理

```ts
// vite.config.ts
server: {
  port: 5173,
  proxy: {
    "/api": { target: "http://localhost:8000", changeOrigin: true },
    "/ws":  { target: "ws://localhost:8000", ws: true },
  },
}
```

前端访问 `http://localhost:5173`，请求 `/api/*` 和 `/ws/*` 由 Vite 转发到后端 8000，避免跨域与 WS 域名问题。

---

## 五、依赖清单

| 依赖 | 用途 |
|------|------|
| react | UI 组件与 Hooks |
| react-dom | 挂载与渲染 |
| vite | 开发服务器与生产构建 |
| @vitejs/plugin-react | React Fast Refresh |
| typescript | 类型检查与 TS 编译 |
| @types/react / @types/react-dom | React 类型定义 |

无路由库、无全局状态库；状态全部在 App 内 useState + 回调下发给子组件。

---

## 六、启动与运行

```bash
# 1. 安装依赖
cd frontend && npm install

# 2. 确保后端已启动（API 与 WebSocket 在 8000 端口）
# 例如：uvicorn src.main:app --reload

# 3. 启动前端开发服务器
npm run dev

# 4. 访问
#    前端: http://localhost:5173
#    API 与 WS 经 Vite 代理到 http://localhost:8000
```

### 生产构建

```bash
npm run build
# 输出到 dist/，可交由任意静态服务器托管；
# 需配置将 /api 与 /ws 反向代理到后端服务。
```
