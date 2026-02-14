# Agent Arena — 项目实现架构

> 本文档描述项目的实际代码结构、每个文件的职责、以及运行时的调用链路。

---

## 一、目录结构

```
agent_arena/
├── pyproject.toml                       # 项目配置与依赖
├── .env.example                         # 环境变量模板（无需 API Key）
├── .gitignore
│
├── agents/                              # Agent 配置（YAML）
│   ├── architect.yaml                   #   架构师
│   ├── developer.yaml                   #   全栈开发
│   ├── tester.yaml                      #   测试工程师
│   ├── compliance.yaml                  #   合规检查员
│   └── supervisor.yaml                  #   超级管理员（路由决策器）
│
├── workspaces/                          # Agent 工作目录（每个 Agent 一个）
│   ├── architect/CLAUDE.md              #   架构师的上下文与角色定义
│   ├── developer/CLAUDE.md
│   ├── tester/CLAUDE.md
│   ├── compliance/CLAUDE.md
│   └── supervisor/CLAUDE.md
│
├── src/
│   ├── main.py                          # FastAPI 入口 + 生命周期管理
│   │
│   ├── models/                          # 数据模型（全系统的类型定义）
│   │   ├── protocol.py                  #   AgentInput / AgentOutput / Message
│   │   ├── session.py                   #   Group / GroupMember / StoredMessage / GroupConfig
│   │   └── agent.py                     #   AgentProfile / CliConfig / ResponseConfig
│   │
│   ├── api/                             # API 网关层（REST + WebSocket）
│   │   ├── routes_group.py              #   群组 CRUD
│   │   ├── routes_message.py            #   消息发送 + 触发编排
│   │   ├── routes_agent.py              #   Agent 查询、接入、管理
│   │   └── websocket.py                 #   WebSocket 连接管理与广播
│   │
│   ├── core/                            # 核心业务层
│   │   ├── orchestrator.py              #   编排引擎（Turn 模型、两阶段执行）
│   │   ├── context_builder.py           #   上下文构建器（消息截断、记忆注入）
│   │   └── session_manager.py           #   会话管理器（SQLite CRUD）
│   │
│   ├── worker/                          # 员工运行时
│   │   ├── runtime.py                   #   WorkerRuntime（选择 Adapter、执行调用）
│   │   └── adapters/                    #   CLI Adapter 实现
│   │       ├── base.py                  #     BaseAdapter 抽象基类
│   │       ├── claude_cli.py            #     Claude Code CLI Adapter
│   │       └── generic_cli.py           #     通用 CLI Adapter（任意命令行工具）
│   │
│   ├── workspace/                       # 工作目录管理
│   │   └── manager.py                   #   WorkspaceManager（clone、初始化、注册）
│   │
│   ├── memory/                          # 记忆系统
│   │   ├── store.py                     #   MemoryStore（JSON 文件存储 + 关键词检索）
│   │   └── summarizer.py               #   Summarizer（消息摘要生成）
│   │
│   └── registry/                        # 注册表
│       └── agent_registry.py            #   AgentRegistry（从 YAML 加载配置）
│
├── data/                                # 运行时数据（gitignore）
│   ├── agent_arena.db                   #   SQLite 数据库
│   ├── memory/                          #   记忆快照（JSON）
│   └── attachments/                     #   附件文件
│
├── tests/                               # 测试
│   ├── test_session_manager.py
│   ├── test_orchestrator.py
│   ├── test_adapters.py
│   ├── test_registry.py
│   └── test_workspace.py
│
└── frontend/                            # 前端（待开发）
```

---

## 二、各文件职责详解

### 2.1 入口与配置

| 文件 | 职责 |
|------|------|
| `src/main.py` | FastAPI 应用入口。在 `lifespan()` 中初始化所有组件（SessionManager、AgentRegistry、WorkerRuntime、Orchestrator、WorkspaceManager），通过全局 `app_state` 暴露给路由层。注册了 REST 路由和 WebSocket 端点。 |
| `pyproject.toml` | 项目元数据和依赖声明。核心依赖：FastAPI、uvicorn、Pydantic、aiosqlite、PyYAML。**无 API SDK 依赖**——所有 AI 调用走 CLI。 |
| `.env.example` | 环境变量模板。只有服务端口和数据库路径，不需要任何 API Key。 |

### 2.2 数据模型层 (`src/models/`)

系统的类型基石，所有模块都依赖这一层。

| 文件 | 核心类型 | 说明 |
|------|---------|------|
| `protocol.py` | `AgentInput` | 系统发给 Agent 的输入：会话ID、回合ID、消息历史、记忆上下文、响应要求 |
|  | `AgentOutput` | Agent 返回的输出：回复内容、`next_mentions`（链式 @）、`should_respond`（是否回复） |
|  | `Message` | 对话中的一条消息（role/author/content/timestamp） |
|  | `StatusEvent` | Agent 状态事件（analyzing/generating/done/error 等），驱动前端动画 |
| `session.py` | `Group` | 群组：名称、成员列表、配置 |
|  | `GroupConfig` | 群组级配置：max_responders、chain_depth_limit、turn_timeout 等 |
|  | `StoredMessage` | 持久化消息（比 Message 多了 group_id、turn_id、mentions 等元数据） |
| `agent.py` | `AgentProfile` | 员工档案：agent_id、name、**workspace_dir**、repo_url、skills、cli_config |
|  | `CliConfig` | CLI 调用配置：cli_type（claude/generic）、command、timeout、extra_args |

### 2.3 API 网关层 (`src/api/`)

前后端的桥梁，提供 REST + WebSocket。

| 文件 | 路由 | 说明 |
|------|------|------|
| `routes_message.py` | `POST /api/messages/send` | **最关键的入口**。保存人类消息 → WebSocket 广播 → 异步触发 `orchestrator.on_new_message()` |
|  | `GET /api/messages/{group_id}` | 获取群组消息历史 |
| `routes_group.py` | `POST/GET/DELETE /api/groups` | 群组 CRUD |
|  | `POST /api/groups/{id}/members` | 添加/移除群组成员 |
| `routes_agent.py` | `POST /api/agents/onboard` | **接入新 Agent**：clone 仓库 + 初始化工作目录 + 注册 |
|  | `DELETE /api/agents/{id}` | 移除 Agent（可选删除工作目录） |
|  | `POST /api/agents/{id}/update` | 更新 Agent 工作目录（git pull） |
|  | `GET /api/agents/workspaces/list` | 列出所有工作目录及状态 |
| `websocket.py` | `WebSocketManager` | 管理按群组分组的 WebSocket 连接，提供 `broadcast_message()` 和 `broadcast_status()` |

### 2.4 核心业务层 (`src/core/`)

系统的大脑。

| 文件 | 核心类 | 职责 |
|------|--------|------|
| `orchestrator.py` | `Orchestrator` | 编排引擎。接收新消息 → 解析 @mention → 创建 Turn → 两阶段并行执行 → 收集 next_mentions → 递归下一 Turn |
|  | `Turn` | 回合数据结构：must_reply_agents、may_reply_agents、chain_depth、timeout |
| `context_builder.py` | `ContextBuilder` | 为每个被唤醒的 Agent 组装 `AgentInput`。从 SessionManager 获取消息历史（截断），从 MemoryStore 检索记忆，从 Registry 获取 role_prompt |
| `session_manager.py` | `SessionManager` | 纯数据层。SQLite 存储群组、成员、消息。提供 CRUD 和 `stored_to_protocol()` 格式转换 |

### 2.5 Worker 运行时 (`src/worker/`)

管理 CLI 调用。

| 文件 | 核心类 | 职责 |
|------|--------|------|
| `runtime.py` | `WorkerRuntime` | 调用入口。根据 Agent 的 `cli_config.cli_type` 选择对应 Adapter，校验 `workspace_dir` 存在，执行调用，通过 WebSocket 上报状态 |
| `adapters/base.py` | `BaseAdapter` | 抽象基类。定义 `invoke(input, workspace_dir)` 和 `health_check(workspace_dir)` 接口 |
| `adapters/claude_cli.py` | `ClaudeCliAdapter` | **核心 Adapter**。在 Agent 的 workspace_dir 中执行 `claude -p "prompt" --output-format json`。Claude CLI 自动读取该目录的 CLAUDE.md 作为上下文。解析 JSON 输出，提取 next_mentions 和 SKIP 标记 |
| `adapters/generic_cli.py` | `GenericCliAdapter` | 通用 Adapter。通过 `asyncio.create_subprocess_shell` 执行任意命令，stdin 传入 prompt，stdout 接收输出 |

### 2.6 工作目录管理 (`src/workspace/`)

| 文件 | 核心类 | 职责 |
|------|--------|------|
| `manager.py` | `WorkspaceManager` | 管理 Agent 工作目录的完整生命周期。`onboard_agent()`: clone 仓库 → 写 CLAUDE.md → 保存 YAML → 注册。`remove_agent()`: 注销 + 删除。`update_workspace()`: git pull |

### 2.7 记忆系统 (`src/memory/`)

| 文件 | 核心类 | 职责 |
|------|--------|------|
| `store.py` | `MemoryStore` | 按会话存储记忆（JSON 文件）。支持 5 种记忆类型：decision/requirement/task/issue/summary。MVP 阶段用关键词匹配做检索 |
| `summarizer.py` | `Summarizer` | 消息摘要生成器。MVP 阶段做简单截取，后期替换为轻量模型 |

### 2.8 注册表 (`src/registry/`)

| 文件 | 核心类 | 职责 |
|------|--------|------|
| `agent_registry.py` | `AgentRegistry` | 启动时从 `agents/*.yaml` 批量加载 AgentProfile。提供 `get_agent()`、`find_by_skill()`、`register_agent()`（动态注册）、`reload()`（热重载） |

---

## 三、运行时调用链路

### 3.1 用户发送消息的完整链路

```
用户点击「发送」
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  POST /api/messages/send                                     │
│  routes_message.py :: send_message()                         │
│                                                              │
│  1. session_manager.save_message()    → 写入 SQLite          │
│  2. ws_manager.broadcast_message()    → 推送给前端            │
│  3. asyncio.create_task(                                     │
│         orchestrator.on_new_message() → 异步触发编排，不阻塞  │
│     )                                                        │
│  4. return { message, status: "processing" }                 │
└─────────────────────┬───────────────────────────────────────┘
                      │ (异步)
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  orchestrator.py :: on_new_message()                         │
│                                                              │
│  1. 获取群组配置和 agent 成员列表                              │
│  2. 解析 @mention（_parse_mentions）                          │
│     • @具体agent → must_reply                                │
│     • @all       → 全员 must_reply                           │
│     • 无 @       → 全员 may_reply                            │
│  3. 创建 Turn(chain_depth=0)                                 │
│  4. 调用 execute_turn()                                      │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  orchestrator.py :: execute_turn()                            │
│                                                              │
│  ═══ Phase A: must_reply（并行）═══                           │
│  对每个 must_reply agent 调用 _invoke_one()                   │
│  用 asyncio.gather 并行执行                                   │
│  回复写入消息流 + WebSocket 推送                              │
│                                                              │
│  ═══ Phase B: may_reply（并行）═══                            │
│  对剩余 agent 调用 _invoke_one()                              │
│  agent 可以返回 should_respond=False 选择不回复               │
│  回复写入消息流 + WebSocket 推送                              │
│                                                              │
│  ═══ 链式触发 ═══                                             │
│  汇总所有回复中的 next_mentions                               │
│  去重（已回复的不重复触发）                                    │
│  如果有且 chain_depth < limit → 递归 execute_turn()           │
│  如果达到上限 → 通知前端「等待人类指令」                       │
└─────────────────────┬───────────────────────────────────────┘
                      │ (每个 agent)
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  orchestrator.py :: _invoke_one()                             │
│                                                              │
│  1. context_builder.build_input()  → 组装 AgentInput          │
│  2. worker_runtime.invoke_agent()  → 执行 CLI 调用            │
│  3. asyncio.wait_for(timeout)      → 超时保护                 │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  context_builder.py :: build_input()                         │
│                                                              │
│  1. registry.get_agent(agent_id)   → 获取 AgentProfile       │
│  2. session_manager.get_messages() → 获取最近 50 条消息       │
│  3. memory_store.search_memory()   → 检索相关记忆（可选）     │
│  4. 组装 AgentInput {                                        │
│       session_id, turn_id, agent_id,                         │
│       role_prompt,          ← 来自 AgentProfile              │
│       messages,             ← 截断后的消息历史                │
│       memory_context,       ← 记忆检索结果                   │
│       invocation,           ← must_reply / may_reply         │
│     }                                                        │
└─────────────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  runtime.py :: invoke_agent()                                │
│                                                              │
│  1. registry.get_agent() → 获取 workspace_dir 和 cli_config  │
│  2. 校验 workspace_dir 存在                                   │
│  3. _create_adapter(cli_type) → 实例化 Adapter                │
│  4. ws_manager.broadcast_status("analyzing")                 │
│  5. adapter.invoke(input, workspace_dir)                     │
│  6. ws_manager.broadcast_status("done")                      │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  claude_cli.py :: invoke()                                   │
│                                                              │
│  1. _build_prompt(input) → 构建对话文本                       │
│     • 拼接消息历史：[用户]: xxx  [架构师]: xxx                 │
│     • 注入记忆上下文                                          │
│     • 添加 may_reply 判断指引 / 协作 @mention 指引            │
│     • 注意：role_prompt 不在这里注入，                         │
│       它在 workspace_dir/CLAUDE.md 中，CLI 自动读取           │
│                                                              │
│  2. 执行 CLI 命令                                             │
│     ┌─────────────────────────────────────────────┐          │
│     │  claude -p "prompt" --output-format json     │          │
│     │  cwd = workspace_dir                         │          │
│     └─────────────────────────────────────────────┘          │
│     • Claude CLI 在 workspace_dir 中运行                      │
│     • 自动读取该目录的 CLAUDE.md 作为 system prompt            │
│     • Agent 只能看到和操作自己 workspace_dir 下的文件          │
│                                                              │
│  3. _parse_output() → 解析输出                                │
│     • 解析 JSON 输出，提取 result/content 字段                 │
│     • 检测 "SKIP" → should_respond = False                    │
│     • 提取 <!--NEXT_MENTIONS:["dev","tester"]--> → 链式 @      │
│     • 返回 AgentOutput                                        │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 接入新 Agent 的链路

```
POST /api/agents/onboard
{
  "agent_id": "frontend_dev",
  "name": "前端开发",
  "repo_url": "https://github.com/org/frontend-context.git",
  "role_prompt": "你是前端开发工程师...",
  "skills": ["React", "CSS", "前端开发"],
  "cli_type": "claude"
}
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  workspace_manager.py :: onboard_agent()                     │
│                                                              │
│  1. git clone repo_url → workspaces/frontend_dev/            │
│     （如果无 repo_url 则创建空目录）                           │
│                                                              │
│  2. 写入 CLAUDE.md → workspaces/frontend_dev/CLAUDE.md       │
│     （如果仓库里已有 CLAUDE.md 则不覆盖）                     │
│                                                              │
│  3. 构建 AgentProfile 对象                                    │
│                                                              │
│  4. 保存 YAML → agents/frontend_dev.yaml                     │
│                                                              │
│  5. registry.register_agent(profile)                         │
│     → Agent 立即可用，无需重启                                │
└─────────────────────────────────────────────────────────────┘

结果：
  workspaces/
  └── frontend_dev/          ← clone 下来的仓库
      ├── CLAUDE.md          ← 角色定义（CLI 自动读取）
      ├── README.md          ← 仓库原有内容（项目文档、需求等）
      ├── docs/              ← 仓库原有内容（设计稿、规范等）
      └── ...                ← Agent 可以看到和修改的所有文件

  agents/
  └── frontend_dev.yaml      ← 自动生成的配置文件
```

### 3.3 WebSocket 实时推送链路

```
前端建立连接: ws://localhost:8000/ws/{group_id}
    │
    ├── 收到 agent_status 消息 → 更新右侧员工状态面板
    │   { "type": "agent_status", "agent_id": "architect", "status": "generating" }
    │
    ├── 收到 agent_message 消息 → 追加到对话流
    │   { "type": "agent_message", "agent_id": "architect", "content": "..." }
    │
    └── 收到 system_message → 显示系统提示
        { "type": "system_message", "content": "自动对话已达上限" }

也可以通过 WebSocket 发送消息（替代 REST）：
    → { "type": "send_message", "content": "...", "mentions": ["architect"] }
```

---

## 四、核心设计决策

### 4.1 CLI 而非 API

```
传统方式:  系统 → API Key → 云端模型 → 返回文本
本项目:    系统 → CLI 子进程(cwd=workspace_dir) → CLI 自带认证 → 返回文本
```

好处：
- **不管理 API Key**——Claude CLI 自己管认证（`claude auth login`）
- **天然沙箱**——每个 Agent 在自己的 workspace_dir 中运行，只能看到和修改该目录的文件
- **上下文即文件**——Agent 的角色定义、项目文档、需求规范全部放在工作目录中，CLI 自动读取
- **可扩展**——任何能通过命令行调用的 AI 工具都能接入（Cursor CLI、Ollama 等）

### 4.2 工作目录 = GitHub 仓库

每个 Agent 的工作目录就是它的「知识库」和「权限边界」：

```
workspaces/architect/           ← 可以是 git clone 的仓库
├── CLAUDE.md                   ← 角色定义 + system prompt
├── docs/architecture.md        ← 架构文档
├── docs/tech-stack.md          ← 技术栈说明
└── templates/                  ← 方案模板
```

- 更新知识：`git pull` 或 `POST /api/agents/{id}/update`
- 新增 Agent：clone 一个新仓库 + 注册即可
- Agent 之间隔离：各自只能看到自己目录下的文件

### 4.3 两阶段执行模型

```
Turn N
├── Phase A: must_reply（并行）
│   被 @ 的 Agent 同时执行，互相看不到对方本轮回复
│   全部完成后，回复写入消息流
│
├── Phase B: may_reply（并行）
│   其余 Agent 自主判断是否回复
│   可以看到 Phase A 的全部回复（信息更完整）
│
└── 汇总 next_mentions → 去重 → 开启 Turn N+1（递归）
```

选择「收齐再开下一 Turn」而非「边收边开」，是为了保证信息完整性：下一 Turn 的 Agent 能看到上一 Turn 的全部回复。

---

## 五、数据库 Schema

SQLite，三张表：

```sql
groups          (id, name, description, created_at, config)
group_members   (id, group_id, type, agent_id, display_name, joined_at, role_in_group)
messages        (id, group_id, turn_id, author_id, author_type, author_name,
                 content, mentions, attachments, timestamp, metadata)
```

索引：`messages.group_id`、`messages.timestamp`、`group_members.group_id`

---

## 六、依赖清单

| 依赖 | 用途 |
|------|------|
| `fastapi` | Web 框架（REST + WebSocket） |
| `uvicorn` | ASGI 服务器 |
| `pydantic` | 数据模型验证 |
| `aiosqlite` | 异步 SQLite |
| `pyyaml` | 解析 Agent YAML 配置 |
| `websockets` | WebSocket 协议支持 |
| `python-dotenv` | 环境变量加载 |

**不依赖任何 AI SDK**（无 anthropic、openai 等）。所有 AI 调用通过 CLI 子进程完成。

---

## 七、启动与运行

```bash
# 1. 安装依赖
pip install -e ".[dev]"

# 2. 配置环境（无需 API Key）
cp .env.example .env

# 3. 确保 CLI 工具已安装并认证
claude auth login          # Claude Code CLI

# 4. 启动服务
uvicorn src.main:app --reload

# 5. 访问
#    API 文档: http://localhost:8000/docs
#    健康检查: http://localhost:8000/api/health
```

### 接入新 Agent

```bash
# 方式一：通过 API
curl -X POST http://localhost:8000/api/agents/onboard \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "frontend_dev",
    "name": "前端开发",
    "repo_url": "https://github.com/org/frontend-workspace.git",
    "role_prompt": "你是前端开发工程师...",
    "skills": ["React", "TypeScript"]
  }'

# 方式二：手动
# 1. clone 仓库到 workspaces/frontend_dev/
# 2. 确保 workspaces/frontend_dev/CLAUDE.md 存在
# 3. 创建 agents/frontend_dev.yaml
# 4. 调用 POST /api/agents/reload
```
