# Agent Arena — 软件工程架构设计

> 基于「多 AI 员工 + 群组会话」的飞书式协作系统。每个员工对应一个 Agent CLI 进程（或兼容 Str-in/Str-out 的服务），系统负责会话、路由、记忆与可扩展接入。

---

## 一、架构总览与语言选型

### 1.1 总体思路

- **员工**：一个「员工」= 一个可对话的 Agent 实例（背后多为 CLI 进程或等价服务），同一 CLI 可创建多个员工。
- **群组**：一个会话 = 一个群组，内有若干人类参与者 + 若干 AI 员工；左侧对话记录/群组列表，中间对话区，右侧员工列表与状态。
- **核心职责**：系统不替代 Agent 能力，只做「谁在什么时候、收到什么输入、必须/可选是否回复」的编排，以及统一入参/出参与存储。

架构**与具体实现语言解耦**：通过「交互规范 + 适配器」抽象，TS 与 Python 均可实现同一套协议；以下用「服务/模块」描述，不绑定语言。

### 1.2 语言建议（可选）

| 维度 | TypeScript/Node | Python |
|------|------------------|--------|
| 前端 | 与 React/Vue 同栈，类型一致 | 需单独前端或 Electron+Py 后端 |
| AI 生态 | 偏 AI SDK、Vercel AI SDK、LangChain.js | 偏 LangChain、LlamaIndex、本地模型 |
| 实时 | WebSocket/SSE 自然 | 需 asyncio + WebSocket 库 |
| 你的熟练度 | 需学习 | 可直接维护 |

**建议**：  
- 若**先做 MVP、你主维护**：后端用 **Python**（FastAPI + 异步），前端用 TS/React 或任意；核心交互规范与协议用 JSON Schema 或 OpenAPI 描述，语言无关。  
- 若**偏产品化、前后端一体**：全栈 **TS**，后端 Node + 同一套类型定义。  
架构层**不依赖语言**，只依赖下面这套「Agent 交互规范」与模块边界。

---

## 二、核心：Agent 交互规范（Protocol）

这是**最重要的一层**：所有「员工」无论来自 Claude CLI、Cursor CLI 还是自研服务，只要满足规范即可接入。

### 2.1 抽象能力

- **调用形态**：本质为 **Str-in / Str-out**（可带结构化附件，见下）。
- **可选能力**：流式输出、取消、心跳/状态上报（用于右侧「在干啥」动画）。

### 2.2 统一消息体（系统 ↔ 员工）

系统发给员工的「当前轮次输入」建议包含：

```yaml
# 发给 Agent 的入参（示例）
session_id: string          # 群组会话唯一标识
turn_id: string             # 本轮回合
role_context: string        # 该员工的角色描述（如「项目经理」「测试员」）
invocation_type: "must_reply" | "may_reply"  # 本轮是否被 @，必须回复
mentioned_by: string | null # 谁 @ 了本员工（user_id 或 agent_id）
messages:                   # 本会话中发给该员工的可见消息列表（可能做过截断/摘要）
  - { role: "user"|"assistant"|"system", author_id, content, ts }
memory_query_result: string | null  # 记忆模块返回的与本轮相关的上下文（按需注入）
options:
  max_tokens: number
  prefer_concise: boolean    # 用于 token 节省
```

员工返回给系统的出参建议：

```yaml
# Agent 返回
content: string             # 主文本内容（必填）
attachments: []             # 可选：文件、结构化数据
next_mention_agent_ids: []   # 可选：本员工希望「强制下一轮回复」的 agent_id 列表（隐形字段）
status_updates: []          # 可选：用于右侧状态动画，如 ["reading_memory", "calling_mcp", "generating"]
```

这样：  
- **谁必须回复**：由 `invocation_type === "must_reply"` 与 `mentioned_by` 表达；  
- **谁可以回复**：由各员工根据 `role_context` + `messages` 自行判断（见下节「交互逻辑」）；  
- **谁在下一轮被强制回复**：由发送方通过 `next_mention_agent_ids` 声明，实现「权限在发送方」的可控扩展。

### 2.3 CLI 适配器（Adapter）

- 每个接入源（如 Claude CLI、Cursor CLI、OpenAI API）一个 **Adapter**。  
- Adapter 负责：把「统一入参」转成该 CLI/API 的调用方式，再把 CLI/API 的输出解析成「统一出参」。  
- 若某 CLI 无法提供 `next_mention_agent_ids`，Adapter 可在其输出里做简单解析（如解析 @AgentName），或默认为空。

---

## 三、交互逻辑模块（Orchestration / Turn-Taking）

这是**系统的核心业务模块**：决定「谁在什么时候、收到什么、是否必须/可以回复」。

### 3.1 规则（与你设想对齐）

1. **人类 @ 员工**：被 @ 的员工本轮 `invocation_type = must_reply`，必须回复；未被 @ 的员工为 `may_reply`，可自行决定是否回复。  
2. **人类 @all**：当前群组内所有员工本轮均为 `must_reply`（或约定为「全部 may_reply 但等效于全员被唤起」）。  
3. **员工 A 发言后**：  
   - A 可在返回中带上 `next_mention_agent_ids: [B, C]`，则 B、C 下一轮为 `must_reply`；  
   - 其余员工仍为 `may_reply`，各自根据消息内容判断是否回复。  
4. **避免乱序与重复**：  
   - 同一回合内，先只收集「必须回复」的员工，再允许「可选回复」的员工（或按优先级/角色排序）；  
   - 可规定：同一轮最多 N 个员工回复，或采用「一轮一主回复 + 其余异步补充」等策略，由 Orchestration 模块配置。

### 3.2 模块职责

- **输入**：一条新消息（来自人或某员工）+ 当前群组员工列表 + 当前会话状态。  
- **输出**：  
  - 本轮回合要「唤醒」的员工列表及各自的 `invocation_type`；  
  - 给每个被唤醒员工的 `messages` 与 `memory_query_result`（调用记忆模块）。  
- **不负责**：具体调用 CLI，只做「路由与参数准备」；实际调用由「员工运行时」执行。

### 3.3 可选：「超级管理员」员工

若希望集中控制谁回复，可引入一个特权员工（Supervisor），其职责仅为：  
- 读当前消息与上下文；  
- 输出结构化决策，如 `{ reply_agents: [B,C], reason: "..." }`。  
系统据此设置 B、C 为 `must_reply`。  
这与「发送方通过 next_mention_agent_ids 指定」可二选一或并存（例如人类消息走 Supervisor，员工消息走 next_mention_agent_ids）。

---

## 四、模块划分（高内聚、可替换）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            Frontend (可选 TS)                            │
│  左侧：群组/会话列表 │ 中间：对话区 │ 右侧：员工列表 + 状态（含动画）      │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         API / Gateway 层                                 │
│  会话 CRUD、发消息、拉历史、员工状态 SSE、认证                             │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        ▼                             ▼                             ▼
┌───────────────┐           ┌─────────────────┐           ┌─────────────────┐
│ 会话与群组     │           │ 交互逻辑         │           │ 员工运行时       │
│ Session/Group │           │ Orchestration    │           │ Worker Runtime  │
│ - 群组/线程   │◄──────────│ - 谁回复         │──────────►│ - 进程/连接管理  │
│ - 消息存储    │           │ - 入参组装       │           │ - Adapter 调用  │
│ - 成员关系    │           │ - 回合与顺序     │           │ - 流式/状态上报  │
└───────────────┘           └────────┬────────┘           └────────┬────────┘
        │                             │                             │
        │                             ▼                             │
        │                    ┌─────────────────┐                    │
        └───────────────────│ 记忆模块         │◄───────────────────┘
                             │ Memory          │  读：按 session/query
                             │ - 按会话存储    │  写：由 Runtime 或独立
                             │ - 按需检索注入  │
                             └─────────────────┘
```

### 4.1 会话与群组（Session / Group）

- **实体**：群组（Group）、会话线程（Session/Thread）、消息（Message）、成员（User + Agent 员工）。
- **存储**：群组元信息、成员关系、消息序列（含 role、author_id、content、ts、以及系统用的 mention/visibility 等）。
- **职责**：提供「当前会话消息列表」「当前群组内员工列表」给 Orchestration；不关心「谁该回复」，只做数据支撑。

### 4.2 交互逻辑（Orchestration）

- 见第三节；依赖「会话与群组」与「记忆模块」的只读/查询接口。
- 输出「本轮回合要对哪些员工发起调用 + 每人入参」，交给员工运行时执行。

### 4.3 员工运行时（Worker Runtime）

- **进程/连接管理**：每个「员工」对应一个 CLI 进程或长连接；创建/销毁/重启策略。
- **调用**：按 Orchestration 给出的入参，通过对应 **Adapter** 调 CLI/API，收集 Str-out。
- **流式与状态**：若 CLI 支持流式，则转成 SSE 推前端；若有 `status_updates`，推右侧状态（含动画）。
- **技能（Skill）**：若员工能力由「CLI + Skill」组成，Skill 的配置与存储可放在本模块或独立「员工配置」存储中（见 4.6）。

### 4.4 记忆模块（Memory）

- **粒度建议**：**按群组会话（Session）存储**，不按员工切分。同一会话中，所有员工共享同一份会话记忆；员工无状态，记忆在系统侧。
- **内容**：会话级摘要、关键决策、任务列表、错误与结论等（可按需设计 schema）。
- **使用**：Orchestration 或 Runtime 在组装某员工的入参时，按 `session_id` + 当前消息做检索，将结果填入 `memory_query_result`，实现「按需注入、省 token」。
- **可选**：若未来要做「员工跨会话经验」，可再加一层「员工维度的记忆」或全局知识库，与「会话记忆」并存。

### 4.5 Token 节省策略（Context & Cost）

- **策略**：  
  - 历史消息截断或摘要后放入 `messages`；  
  - 记忆模块只返回与当前轮相关的片段；  
  - 在入参中加 `prefer_concise: true`，并在 system/role 中要求员工简洁回复；  
  - 可配置每会话最大上下文长度，超出则摘要或丢弃最旧内容。  
- **落点**：可在 Orchestration 或单独「Context Builder」中实现摘要与截断逻辑，再交给 Runtime。

### 4.6 员工与技能存储（Worker & Skill Registry）

- **员工**：id、名称、角色描述（role_context）、绑定的 Adapter 类型、CLI 启动参数或 endpoint、所属群组等。
- **Skill**：若一个员工 = 一个 CLI + 多 Skill，可存为「员工 → Skill 列表」；Skill 可为标签或配置块，供 Adapter 在调用时传入 CLI（具体格式由各 CLI 约定）。
- **扩展**：新 CLI 只需新写一个 Adapter + 在 Registry 里注册员工类型即可。

---

## 五、与你设想的一一对应

| 你的想法 | 架构中的落点 |
|----------|----------------|
| 员工 = CLI 进程，同 CLI 多员工 | Worker Runtime + 进程/连接管理；员工与 CLI 类型多对一 |
| 左侧群组 / 中间对话 / 右侧员工状态 | 前端三栏布局；状态由 Runtime 的 status_updates + SSE 驱动 |
| @ 员工 / @all / 员工互相 @ | 交互规范中的 invocation_type + mentioned_by + next_mention_agent_ids；Orchestration 实现规则 |
| 响应权限在发送方 vs 接收方 | 混合：被 @ 的必须回（发送方指定）；其余接收方自决（may_reply） |
| 超级管理员统一派活 | 可选：Supervisor 员工 + Orchestration 解析其输出 |
| 入参/出参统一 | Agent 交互规范 + 各 CLI 的 Adapter |
| 角色（PM/开发/测试/合规） | 员工的 role_context + 可选 Skill；Orchestration 可按角色做优先级 |
| 记忆按会话、员工按需用 | 记忆模块按 Session 存储；Orchestration/Runtime 按需查询并注入 |
| Token 节省、简洁回复 | Context Builder + prefer_concise + 摘要/截断 |
| 右侧动画（在干啥） | status_updates 字段 + 前端状态机/动画映射 |
| 可扩展、适配主流 CLI | Protocol + Adapter + Worker & Skill Registry |

---

## 六、扩展与补充建议

1. **审计与合规**：对「谁在何时被唤醒、输入输出是什么」做日志，便于合规报告员工使用真实会话记录。  
2. **人机权限**：敏感操作（如执行命令、发外部请求）可限制为「仅人类确认后执行」或仅部分员工可执行。  
3. **多轮与超时**：若某员工挂起或超时，Orchestration 可标记该轮跳过并通知前端，避免整群卡死。  
4. **离线与重连**：CLI 进程崩溃时，Runtime 重启进程并从会话中恢复最近上下文，保证「员工」可恢复。  
5. **计费与限流**：按会话或按员工做 token/调用次数统计，便于限流与成本控制。

---

## 七、建议的实现顺序

1. **定义并固化「Agent 交互规范」**（JSON Schema 或 OpenAPI），实现一个最小 Adapter（如纯 HTTP Str-in/Str-out）。  
2. **实现会话与群组模型**（存储 + API），实现单员工、单会话的「人类 → 员工」对话。  
3. **实现 Orchestration**：@ 与 must_reply / may_reply，再接入多员工。  
4. **接入真实 CLI**（如 Claude CLI）的 Adapter，并做记忆模块与 token 节省。  
5. **前端三栏 + 员工状态**，最后再做右侧动画与体验优化。

---

本架构满足：**模块清晰、交互规范统一、与语言解耦、易于扩展新 CLI 与新员工类型**，可直接作为 `Structure.md` 的定稿骨架，后续可在同一文件中按模块补充接口定义与数据结构细节。
