hello from opencode

hello from openclaw
# Agent Arena — 架构设计（Claude 版）

> 多 AI 员工协作系统：一个「飞书式」的 Agent 群组工作平台。
> 本文档是可落地的工程架构，不是概念堆砌。每个模块都给出了清晰的职责边界、接口定义和关键实现思路。

---

uvicorn src.main:app --reload 

npm run dev


## 零、核心理念：我们在做什么，不在做什么

**在做什么：**
我们要做一个**协作平台**——把多个已有的 AI Agent（Claude CLI、Cursor CLI、或任何 Str-in/Str-out 的服务）组织成一个「虚拟团队」，在统一的会话界面中协作完成任务。系统本身**不替代 Agent 的能力**，只做三件事：
1. **路由** —— 决定谁收到什么消息、谁必须回复
2. **适配** —— 把不同 CLI/API 的输入输出转成统一格式
3. **记忆** —— 管理会话上下文，按需注入给每个 Agent

**不在做什么：**
我们不是又一个「多智能体编排框架」（如 CrewAI、AutoGen）。那些框架的目标是把多个 Agent 编排成一个流水线，最终输出一个结果。我们的目标是让多个**独立的、已编排好的** Agent 像真人一样在群里协作. 每个「员工」本身可能就是一个复杂的 Agent 系统，但在我们的平台里，它就是一个能对话的节点。

---

## 一、语言选型：Python，不犹豫

| 考量因素 | 结论 |
|---------|------|
| 你会 Python | 能看懂、能改、能维护，这是最大的优势 |
| AI 生态 | LangChain、LlamaIndex、各家 SDK 全在 Python 生态 |
| CLI 集成 | `subprocess`、`asyncio` 天然适合管理 CLI 进程 |
| 前端怎么办 | 前端用任何框架（React/Vue/Svelte），后端提供 API + WebSocket，前后端分离 |
| TS 的优势 | 类型安全确实好，但你现在不会 TS，学习成本会拖慢 MVP |

**最终建议：**
- **后端**：Python 3.11+，FastAPI（异步、WebSocket 原生支持、自动生成 API 文档）
- **前端**：随你选，推荐 React + TypeScript（前端那边 TS 是标配，且 UI 组件库丰富）
- **协议定义**：用 JSON Schema / Pydantic Model，语言无关，前后端都能用

---

## 二、系统架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        前端 (React / Vue)                           │
│  ┌──────────────┐  ┌──────────────────┐  ┌───────────────────────┐ │
│  │ 群组列表侧栏 │  │   对话空间主区   │  │ 员工状态面板 + 动画  │ │
│  └──────────────┘  └──────────────────┘  └───────────────────────┘ │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTP + WebSocket
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      API 网关 (FastAPI)                              │
│  REST: 群组/员工/消息 CRUD    WebSocket: 实时消息 + 员工状态推送     │
└────────────────────────────┬────────────────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
│  会话管理器       │ │ 编排引擎     │ │ 员工运行时        │
│  SessionManager  │ │ Orchestrator │ │ WorkerRuntime    │
│                  │ │              │ │                  │
│ • 群组 CRUD      │ │ • 谁该回复   │ │ • 进程生命周期    │
│ • 消息存储       │◄│ • 入参组装   │►│ • Adapter 调用   │
│ • 成员管理       │ │ • 回合控制   │ │ • 流式输出转发    │
│ • 消息历史查询   │ │ • 防循环     │ │ • 状态事件上报    │
└────────┬─────────┘ └──────┬───────┘ └────────┬─────────┘
         │                  │                   │
         │           ┌──────┴───────┐           │
         │           │ 上下文构建器 │           │
         │           │ ContextBuilder│          │
         │           │              │           │
         │           │ • 消息截断   │           │
         │           │ • 记忆检索   │           │
         │           │ • 摘要生成   │           │
         │           │ • Token 预算 │           │
         │           └──────┬───────┘           │
         │                  │                   │
         ▼                  ▼                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        数据层                                       │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────────┐ │
│  │ SQLite/PG   │  │ 文件系统     │  │ 员工 & 技能注册表          │ │
│  │ 消息/群组   │  │ 记忆快照     │  │ AgentRegistry              │ │
│  │ 元数据      │  │ 项目文件     │  │ • 员工 Profile             │ │
│  └─────────────┘  └──────────────┘  │ • Skill 配置               │ │
│                                     │ • Adapter 类型映射          │ │
│                                     └────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

**模块数量控制在 6 个**，每个职责单一：

| # | 模块 | 一句话职责 |
|---|------|-----------|
| 1 | SessionManager | 管数据：群组、消息、成员 |
| 2 | Orchestrator | 管逻辑：谁回复、什么顺序 |
| 3 | ContextBuilder | 管上下文：截断、摘要、记忆检索、Token 预算 |
| 4 | WorkerRuntime | 管进程：启动/停止 CLI、调 Adapter、推状态 |
| 5 | AgentRegistry | 管配置：员工档案、技能、Adapter 映射 |
| 6 | API Gateway | 管通信：REST + WebSocket，前后端桥梁 |

---

## 三、Agent 交互协议（全系统的基石）

这是最重要的一层。所有 Agent 无论来自哪里，只要满足这套协议就能接入。

### 3.1 系统 → Agent 的入参（AgentInput）

```python
class AgentInput(BaseModel):
    """系统发给 Agent 的输入"""

    # 身份与会话
    session_id: str                          # 群组会话 ID
    turn_id: str                             # 本轮回合 ID（用于去重和排序）
    agent_id: str                            # 本员工的 ID
    role_prompt: str                         # 本员工的角色描述 / System Prompt

    # 响应要求
    invocation: Literal["must_reply", "may_reply"]
    mentioned_by: str | None = None          # 谁 @ 了你（agent_id 或 user_id）

    # 消息上下文（已经过截断/摘要处理）
    messages: list[Message]
    # 结构如下：
    # class Message:
    #     role: Literal["user", "assistant", "system"]
    #     author_id: str
    #     author_name: str
    #     content: str
    #     timestamp: datetime

    # 记忆注入（由 ContextBuilder 按需检索）
    memory_context: str | None = None

    # Token 控制
    max_output_tokens: int = 2000
    prefer_concise: bool = True              # 提示 Agent 简洁回复
```

### 3.2 Agent → 系统的出参（AgentOutput）

```python
class AgentOutput(BaseModel):
    """Agent 返回给系统的输出"""

    # 必填
    content: str                             # 回复的文本内容

    # 可选：链式调用
    next_mentions: list[str] = []            # 希望下一轮强制回复的 agent_id 列表
                                             # 相当于 Agent 在回复中 @ 了其他人

    # 可选：状态上报（用于右侧动画）
    status_updates: list[StatusEvent] = []
    # class StatusEvent:
    #     status: Literal["analyzing", "reading_memory", "calling_tool",
    #                      "generating", "reviewing", "done", "error"]
    #     detail: str = ""                   # 如 "正在调用 MCP 工具: file_search"
    #     progress: float | None = None      # 0.0 ~ 1.0

    # 可选：附件
    attachments: list[Attachment] = []
    # class Attachment:
    #     type: Literal["file", "code", "json", "image"]
    #     name: str
    #     data: str                          # base64 或文本内容

    # 可选：自我判断（仅 may_reply 时有效）
    should_respond: bool = True              # 如果 Agent 判断自己不需要回复，设为 False
```

### 3.3 Adapter 接口

每个 CLI/API 一个 Adapter，职责：把 `AgentInput` 转成该 CLI 的调用方式，把输出解析成 `AgentOutput`。

```python
class BaseAdapter(ABC):
    """所有 Adapter 的基类"""

    @abstractmethod
    async def invoke(self, input: AgentInput, stream_callback=None) -> AgentOutput:
        """
        调用底层 CLI/API，返回结果。
        stream_callback: 可选，用于流式输出时逐步推送给前端。
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """检查底层服务是否可用"""
        ...

    @abstractmethod
    async def start(self, config: dict) -> None:
        """启动底层进程/连接"""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """停止底层进程/连接"""
        ...
```

**内置 Adapter 示例：**

| Adapter | 底层 | 调用方式 |
|---------|------|---------|
| `ClaudeCliAdapter` | Claude Code CLI | `subprocess` 管理进程，stdin/stdout 通信 |
| `CursorCliAdapter` | Cursor CLI | `subprocess`，解析其特定输出格式 |
| `OpenAIApiAdapter` | OpenAI API | `httpx` 调用 REST API |
| `AnthropicApiAdapter` | Anthropic API | `anthropic` SDK |
| `LocalModelAdapter` | Ollama / vLLM | 本地 HTTP API |
| `GenericCliAdapter` | 任意 CLI | 配置化：指定启动命令、输入格式、输出解析规则 |

**新增一个 CLI 只需要：** 写一个继承 `BaseAdapter` 的类 + 在 AgentRegistry 注册。

---

## 四、编排引擎（Orchestrator）—— 系统的大脑

这是系统最核心的模块。它决定「谁在什么时候、收到什么输入、是否必须回复」。

### 4.1 回合（Turn）模型

一条消息触发一个「回合」，一个回合内可以有多个 Agent 回复。

```python
class Turn:
    turn_id: str
    trigger_message: Message            # 触发本回合的消息
    trigger_source: str                 # 谁发的（user_id 或 agent_id）

    must_reply_agents: list[str]        # 本轮必须回复的 agent_id
    may_reply_agents: list[str]         # 本轮可以回复的 agent_id
    completed_replies: list[AgentOutput]  # 已收到的回复

    max_responders: int = 5             # 本轮最多几个 Agent 回复（防刷屏）
    timeout_seconds: int = 120          # 本轮超时时间
```

### 4.2 响应决策规则（核心逻辑）

当一条新消息到达时，Orchestrator 执行以下流程：

```
新消息到达
    │
    ▼
┌─────────────────────────────┐
│ Step 1: 解析 @mention       │
│                             │
│ • @具体员工 → must_reply    │
│ • @所有人   → 全员 must     │
│ • 无 @      → 见 Step 2    │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ Step 2: 处理链式调用         │
│                             │
│ 如果发送方是 Agent 且返回了 │
│ next_mentions，将这些 Agent │
│ 加入 must_reply             │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ Step 3: 其余 Agent 评估     │
│                             │
│ 不在 must_reply 中的 Agent  │
│ 收到 may_reply 请求，自行   │
│ 判断是否回复（返回          │
│ should_respond = True/False）│
│                             │
│ 评估方式（二选一，可配置）：  │
│ A. 发给 Agent 让它自己判断  │
│ B. 系统侧做轻量匹配（关键  │
│    词 + 角色相关性）        │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ Step 4: 两阶段串行执行       │
│                             │
│ Phase A: must_reply（并行） │
│   → 全部完成后，回复写入    │
│     消息流，推前端           │
│                             │
│ Phase B: may_reply（并行）  │
│   → 可以看到 Phase A 的回复 │
│   → 全部完成后，回复写入    │
│     消息流，推前端           │
│                             │
│ 总数不超过 max_responders   │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ Step 5: 收集 next_mentions  │
│         批量开启下一个 Turn  │
│                             │
│ 等本 Turn 全部回复完成后：  │
│ • 汇总所有回复中的           │
│   next_mentions，去重        │
│ • 合并为下一个 Turn 的       │
│   must_reply 列表            │
│ • 不是每条回复立刻触发新     │
│   Turn，而是「收齐再开」    │
└─────────────────────────────┘
```

### 4.3 Turn 内部的执行模型（关键细节）

一个 Turn 的内部执行分为**两个阶段**，阶段之间串行，阶段内部并行：

```
Turn N
├── Phase A: must_reply agents（并行调用）
│   │
│   │  架构师、合规 同时收到消息，同时开始生成回复
│   │  它们看到的上下文是一样的（都是到 Turn N 触发消息为止的历史）
│   │  它们互相看不到对方本轮的回复（因为是同时执行帮的）
│   │
│   ├─ 架构师回复 → 写入消息流 → 推前端
│   │   next_mentions: [开发]
│   │
│   └─ 合规回复 → 写入消息流 → 推前端
│       next_mentions: [测试]
│
├── Phase B: may_reply agents（并行调用）
│   │
│   │  开发（自主判断要回复）收到消息
│   │  它能看到 Phase A 中架构师和合规的回复（因为 Phase A 已完成）
│   │  这样 may_reply 的 Agent 拥有更完整的信息
│   │
│   └─ 开发回复 → 写入消息流 → 推前端
│       next_mentions: [测试]
│
└── Turn N 结束
    │
    │  汇总所有 next_mentions:
    │  架构师 → [开发]
    │  合规   → [测试]
    │  开发   → [测试]
    │
    │  去重后: must_reply = [开发, 测试]
    │  但是！开发已经在 Turn N 回复过了 → 从列表中移除
    │  最终: must_reply = [测试]
    │
    ▼
Turn N+1
├── Phase A: must_reply = [测试]
│   测试能看到 Turn N 中所有人的回复（架构师 + 合规 + 开发）
│   ...
```

**为什么选择「收齐再开下一 Turn」而不是「边收边开」？**

| 方案 | 优点 | 缺点 |
|------|------|------|
| **收齐再开（批量，本方案）** | 下一 Turn 的 Agent 能看到本 Turn 全部回复，信息完整；不会产生竞态条件 | 延迟略高（要等最慢的 Agent 完成） |
| 边收边开（流式） | 延迟低，架构师一回复就立刻触发开发 | 开发看不到合规的回复；可能产生并发冲突；逻辑复杂 |

**批量模式更安全、更可预测**，且 Agent 响应通常在秒级，多等几秒换来的是信息完整性。

### 4.4 特殊情况处理

**情况 1：多个 Agent @ 了同一个人**
```
Turn N:
  架构师 next_mentions: [开发]    "请按这个方案实现"
  合规   next_mentions: [开发]    "实现时注意以下合规要求"

Turn N+1:
  开发收到 must_reply
  它的消息上下文中同时包含架构师和合规的回复
  开发自己综合两边的要求来回复（这就是"收齐再开"的好处）
```

**情况 2：被 next_mention 的人已经在本 Turn 回复过了**
```
Turn N:
  架构师 must_reply → 回复了 → next_mentions: [开发]
  开发   may_reply  → 也回复了 → next_mentions: [测试]

去重逻辑：
  汇总 next_mentions = [开发, 测试]
  开发已经在 Turn N 回复过 → 移除
  最终 Turn N+1 的 must_reply = [测试]
```

但如果架构师 @ 开发的内容是**新的指令**（不是对之前消息的回应），开发是否需要再回复一次？这里提供一个可配置项：

```python
class TurnConfig:
    # 如果某 Agent 已在本 Turn 回复过，但被其他 Agent next_mention 了，
    # 是否在下一 Turn 中再次触发它？
    re_invoke_already_replied: bool = False  # 默认不重复触发
    # 设为 True 则允许同一个 Agent 在连续 Turn 中被反复调用
    # （适合需要多轮确认的场景，但需配合 chain_depth_limit 使用）
```

**情况 3：may_reply 的 Agent 也带了 next_mentions**
```
Turn N:
  架构师 must_reply → next_mentions: [开发]
  测试   may_reply  → next_mentions: [开发, 合规]

处理方式：完全一样。may_reply 的 Agent 回复同样可以 @ 其他人。
汇总 next_mentions 时不区分来源是 must 还是 may。
```

**情况 4：没有任何 Agent 产生 next_mentions**
```
Turn N:
  架构师 must_reply → next_mentions: []
  开发   may_reply  → next_mentions: []

→ 没有新的 must_reply
→ 不会产生 Turn N+1
→ 等待人类发送下一条消息
```

### 4.5 执行伪代码

把以上逻辑汇总成 Orchestrator 的核心方法：

```python
class Orchestrator:
    async def execute_turn(self, turn: Turn, session_id: str):
        """执行一个完整的 Turn"""

        all_next_mentions: set[str] = set()
        replied_agents: set[str] = set()

        # ── Phase A: must_reply（并行）──
        must_tasks = [
            self._invoke_one(agent_id, session_id, "must_reply", turn)
            for agent_id in turn.must_reply_agents
        ]
        must_outputs = await asyncio.gather(*must_tasks)

        for agent_id, output in zip(turn.must_reply_agents, must_outputs):
            await self.session_manager.save_message(output, turn.turn_id)
            await self.ws_manager.broadcast_message(output)
            all_next_mentions.update(output.next_mentions)
            replied_agents.add(agent_id)

        # ── Phase B: may_reply（并行）──
        # may_reply 的 Agent 现在能看到 Phase A 的回复了
        may_agents = [
            aid for aid in turn.may_reply_agents
            if aid not in replied_agents  # 已经回复过的不再重复
        ]
        may_tasks = [
            self._invoke_one(agent_id, session_id, "may_reply", turn)
            for agent_id in may_agents
        ]
        may_outputs = await asyncio.gather(*may_tasks)

        for agent_id, output in zip(may_agents, may_outputs):
            if output.should_respond:  # may_reply 可以选择不回复
                await self.session_manager.save_message(output, turn.turn_id)
                await self.ws_manager.broadcast_message(output)
                all_next_mentions.update(output.next_mentions)
                replied_agents.add(agent_id)

        # ── 决定是否开启下一个 Turn ──
        # 去重：移除本 Turn 已回复过的 Agent（可配置）
        if not self.config.re_invoke_already_replied:
            all_next_mentions -= replied_agents

        if all_next_mentions and turn.chain_depth < self.config.chain_depth_limit:
            next_turn = Turn(
                turn_id=generate_turn_id(),
                trigger_message=None,  # 下一 Turn 的触发不是单条消息，而是本 Turn 的全部回复
                must_reply_agents=list(all_next_mentions),
                may_reply_agents=self._evaluate_may_reply(session_id, all_next_mentions),
                chain_depth=turn.chain_depth + 1,
            )
            await self.execute_turn(next_turn, session_id)  # 递归
        elif turn.chain_depth >= self.config.chain_depth_limit:
            # 链式深度达到上限，通知前端
            await self.ws_manager.broadcast_system_message(
                session_id,
                f"⚠️ 自动对话已达到 {self.config.chain_depth_limit} 轮上限，等待人类指令。"
            )
```

### 4.3 防护机制（防止混乱）

| 风险 | 防护措施 |
|------|---------|
| 无限循环（A @ B → B @ A → ...） | **链式深度限制**：同一会话内连续自动 Turn 最多 N 层（默认 5），超过则暂停并提示人类 |
| 同时回复太多 | **max_responders**：每个 Turn 最多 N 个 Agent 回复 |
| Agent 卡死 | **超时机制**：每个 Agent 回复有时限，超时则跳过并标记状态为 timeout |
| 重复回复 | **Turn ID 去重**：同一 Turn 内每个 Agent 最多回复一次 |
| 成本失控 | **Token 预算**：每个 Turn / 每个会话有 Token 上限，超限则降级或暂停 |

### 4.4 可选：Supervisor 模式

如果你希望有一个「超级管理员」来统一决定谁回复，可以启用 Supervisor 模式：

```python
# Supervisor 也是一个 Agent，只是它的职责是做路由决策
class SupervisorConfig:
    enabled: bool = False
    agent_id: str = "supervisor"
    # Supervisor 收到消息后，输出结构化决策：
    # { "should_reply": ["agent_A", "agent_B"], "reason": "..." }
    # 系统据此设置 must_reply
```

Supervisor 模式适用于：任务流程固定、需要严格控制谁干什么的场景。
自由模式适用于：开放讨论、头脑风暴、灵活协作的场景。
两种模式可以按群组配置，甚至可以混用。

---

## 五、会话管理器（SessionManager）

纯数据层，不包含业务逻辑。

### 5.1 数据模型

```python
class Group:
    """群组"""
    id: str
    name: str
    description: str
    created_at: datetime
    members: list[GroupMember]        # 人类 + AI 员工
    config: GroupConfig              # 群组级配置（如 max_responders、supervisor 等）

class GroupMember:
    """群组成员"""
    id: str
    type: Literal["human", "agent"]
    agent_id: str | None             # 如果是 AI 员工，关联到 AgentRegistry
    joined_at: datetime
    role_in_group: str | None        # 在本群组中的角色（可覆盖默认角色）

class Message:
    """消息"""
    id: str
    group_id: str
    turn_id: str
    author_id: str
    author_type: Literal["human", "agent", "system"]
    author_name: str
    content: str
    mentions: list[str]              # 被 @ 的成员 ID 列表
    attachments: list[Attachment]
    timestamp: datetime
    metadata: dict                   # 扩展字段（如 status_updates、next_mentions 等）
```

### 5.2 存储选择

**MVP 阶段**：SQLite —— 零配置、单文件、够用到几十万条消息。
**后期**：可迁移到 PostgreSQL，Schema 不变。

```
data/
├── agent_arena.db          # SQLite 主数据库（群组、消息、成员）
├── memory/                 # 记忆快照（JSON 文件）
│   ├── session_{id}.json
│   └── summary_{id}.json
└── attachments/            # 附件文件存储
    └── {message_id}/
```

---

## 六、上下文构建器（ContextBuilder）

**职责**：为每个被唤醒的 Agent 组装它的 `AgentInput`，核心是控制「它能看到什么」以及「花多少 Token」。

### 6.1 上下文组装流程

```python
class ContextBuilder:
    async def build_input(
        self,
        agent_id: str,
        session_id: str,
        trigger_message: Message,
        invocation: Literal["must_reply", "may_reply"],
        mentioned_by: str | None,
    ) -> AgentInput:
        # 1. 获取员工 Profile
        profile = self.registry.get_agent(agent_id)

        # 2. 获取消息历史（带截断）
        messages = await self.get_truncated_history(
            session_id,
            max_tokens=profile.context_window - profile.reserved_output_tokens
        )

        # 3. 检索相关记忆（按需）
        memory = await self.retrieve_memory(session_id, trigger_message.content)

        # 4. 组装 AgentInput
        return AgentInput(
            session_id=session_id,
            turn_id=generate_turn_id(),
            agent_id=agent_id,
            role_prompt=profile.role_prompt,
            invocation=invocation,
            mentioned_by=mentioned_by,
            messages=messages,
            memory_context=memory,
            max_output_tokens=profile.max_output_tokens,
            prefer_concise=True,
        )
```

### 6.2 Token 节省策略（四层）

```
Layer 1: 消息截断
    │  只保留最近 N 条消息，或最近 N tokens
    │  重要消息（被标记的决策、需求）永远保留
    ▼
Layer 2: 历史摘要
    │  当消息超过阈值时，将旧消息压缩成摘要
    │  摘要可以用轻量模型生成（如 Haiku / GPT-4o-mini）
    │  摘要替换原始消息，大幅减少 Token
    ▼
Layer 3: 记忆检索
    │  不是把所有记忆都塞进去，而是按当前消息的语义
    │  检索最相关的 Top-K 条记忆片段
    │  可用简单的 TF-IDF，也可以用向量检索
    ▼
Layer 4: 简洁回复引导
    │  在 role_prompt 中加入 "请简洁回复" 的指令
    │  设置 max_output_tokens 限制输出长度
    │  前端可以展示 "展开详情" 让用户按需查看
```

### 6.3 记忆系统设计

**核心决策：记忆按群组会话存储，不按员工切分。**

理由：
- 同一个群组内的员工需要看到相同的项目上下文
- 员工是无状态的，它的「记忆」由系统在调用时注入
- 大幅简化存储和管理逻辑

```python
class MemoryStore:
    """会话记忆存储"""

    async def save_memory(self, session_id: str, memory: MemoryEntry):
        """保存一条记忆"""
        ...

    async def search_memory(
        self, session_id: str, query: str, top_k: int = 5
    ) -> list[MemoryEntry]:
        """按语义检索相关记忆"""
        ...

    async def generate_summary(self, session_id: str) -> str:
        """生成当前会话的摘要"""
        ...

class MemoryEntry:
    id: str
    session_id: str
    content: str                     # 记忆内容
    memory_type: Literal[
        "decision",                  # 关键决策
        "requirement",               # 需求定义
        "task",                      # 任务分配
        "issue",                     # 问题/Bug
        "summary",                   # 阶段摘要
    ]
    importance: float                # 0.0 ~ 1.0，决定是否在截断时保留
    created_at: datetime
    source_message_id: str           # 关联的原始消息
```

**什么时候写入记忆？**
- 不是每条消息都写。由 ContextBuilder 判断哪些消息值得记忆（如包含决策、需求变更、任务分配等关键信息）。
- 也可以做成后台定时任务：每隔 N 条消息，用轻量模型提取关键信息存入记忆。

---

## 七、员工运行时（WorkerRuntime）

**职责**：管理每个 Agent 的底层进程/连接，执行 Adapter 调用，上报状态。

### 7.1 进程生命周期

```python
class WorkerRuntime:
    """管理所有活跃的 Agent 进程"""

    workers: dict[str, WorkerProcess]  # agent_id → WorkerProcess

    async def ensure_worker(self, agent_id: str) -> WorkerProcess:
        """确保某个 Agent 的底层进程已启动"""
        if agent_id not in self.workers:
            profile = self.registry.get_agent(agent_id)
            adapter = self.create_adapter(profile.adapter_type, profile.adapter_config)
            await adapter.start(profile.adapter_config)
            self.workers[agent_id] = WorkerProcess(
                agent_id=agent_id,
                adapter=adapter,
                status="idle",
            )
        return self.workers[agent_id]

    async def invoke_agent(
        self, agent_id: str, input: AgentInput, stream_callback=None
    ) -> AgentOutput:
        """调用一个 Agent，返回结果"""
        worker = await self.ensure_worker(agent_id)
        worker.status = "busy"
        try:
            # 上报状态：开始处理
            await self.emit_status(agent_id, "analyzing", "正在分析消息...")

            output = await worker.adapter.invoke(input, stream_callback)

            # 上报状态：完成
            await self.emit_status(agent_id, "done")
            return output
        except TimeoutError:
            await self.emit_status(agent_id, "error", "响应超时")
            raise
        finally:
            worker.status = "idle"

    async def emit_status(self, agent_id: str, status: str, detail: str = ""):
        """通过 WebSocket 推送状态给前端"""
        await self.ws_manager.broadcast({
            "type": "agent_status",
            "agent_id": agent_id,
            "status": status,
            "detail": detail,
            "timestamp": now(),
        })
```

### 7.2 状态事件（驱动右侧动画）

预定义的状态类型，前端据此显示不同动画：

| status | 含义 | 前端动画建议 |
|--------|------|-------------|
| `idle` | 空闲 | 灰色头像，静止 |
| `analyzing` | 正在分析消息 | 蓝色呼吸灯 |
| `reading_memory` | 正在读取记忆 | 翻书图标 |
| `calling_tool` | 正在调用工具/MCP | 齿轮转动 |
| `generating` | 正在生成回复 | 打字动画（三个点） |
| `reviewing` | 正在审查/检验 | 放大镜图标 |
| `waiting` | 等待其他 Agent | 沙漏图标 |
| `done` | 完成 | 绿色对勾，闪一下 |
| `error` | 出错 | 红色感叹号 |
| `timeout` | 超时 | 黄色警告 |

---

## 八、员工与技能注册表（AgentRegistry）

### 8.1 员工 Profile

```yaml
# agents/architect.yaml
agent_id: "architect"
name: "架构师"
avatar: "🏗️"

# 角色描述（会作为 System Prompt 注入）
role_prompt: |
  你是一位资深软件架构师。你的职责是：
  1. 分析用户需求，拆解成具体的技术任务
  2. 设计系统架构和技术方案
  3. 评估技术选型和可行性
  回复要求：简洁、结构化、用列表和代码块。

# 技能标签（用于 Orchestrator 做相关性匹配）
skills:
  - "需求分析"
  - "架构设计"
  - "任务拆解"
  - "技术选型"

# 响应配置
response_config:
  auto_respond: true                  # 是否参与 may_reply 自主判断
  response_threshold: 0.6            # 相关性阈值（0~1），越低越容易触发
  priority_keywords: ["架构", "设计", "方案", "技术选型", "拆解"]

# Adapter 配置
adapter_type: "anthropic_api"         # 使用哪个 Adapter
adapter_config:
  model: "claude-sonnet-4-5-20250929"
  max_tokens: 4096

# Token 配置
context_window: 32000                 # 上下文窗口大小
max_output_tokens: 2000              # 最大输出 Token
reserved_output_tokens: 2000         # 为输出预留的 Token
```

### 8.2 注册表管理

```python
class AgentRegistry:
    """员工与技能注册表"""

    def __init__(self, config_dir: str = "agents/"):
        self.agents: dict[str, AgentProfile] = {}
        self._load_from_dir(config_dir)

    def _load_from_dir(self, config_dir: str):
        """从 YAML 文件批量加载员工配置"""
        for file in Path(config_dir).glob("*.yaml"):
            profile = AgentProfile.from_yaml(file)
            self.agents[profile.agent_id] = profile

    def get_agent(self, agent_id: str) -> AgentProfile:
        return self.agents[agent_id]

    def list_agents(self) -> list[AgentProfile]:
        return list(self.agents.values())

    def find_by_skill(self, keyword: str) -> list[AgentProfile]:
        """按技能关键词查找匹配的员工"""
        return [
            a for a in self.agents.values()
            if any(keyword in s for s in a.skills)
        ]
```

**扩展新员工**：只需在 `agents/` 目录下新增一个 YAML 文件，系统自动加载。

---

## 九、完整消息流（端到端示例）

以一个更复杂的场景为例：人类 @架构师 和 @合规，同时开发自主判断也想回复。

### 9.1 初始消息

```
人类: "@架构师 @合规 请帮我拆解这个需求：做一个用户管理系统，需要符合 GDPR"
```

### 9.2 Turn 1 的完整执行过程

```
1. 前端 → API Gateway（WebSocket）
   │  消息内容: "请帮我拆解这个需求..."
   │  mentions: ["architect", "compliance"]
   │
2. API Gateway → SessionManager.save_message()
   │
3. API Gateway → Orchestrator.on_new_message()
   │
4. Orchestrator 创建 Turn 1 (chain_depth=0)
   │  解析 mentions → must_reply: [architect, compliance]
   │  其余群组成员 → may_reply: [developer, tester]
   │
   ╔══════════════════════════════════════════════════════════╗
   ║  Turn 1 · Phase A: must_reply（并行）                    ║
   ╠══════════════════════════════════════════════════════════╣
   ║                                                          ║
   ║  架构师 和 合规 同时被调用（asyncio.gather）              ║
   ║  它们看到的消息历史相同：截止到人类这条消息为止           ║
   ║  它们互相看不到对方在本 Turn 的回复                       ║
   ║                                                          ║
   ║  ┌─ 架构师（并行线程 1）────────────────────────────┐    ║
   ║  │  ContextBuilder 组装 AgentInput                   │    ║
   ║  │  → messages: [...历史, 人类消息]                   │    ║
   ║  │  → invocation: "must_reply"                       │    ║
   ║  │                                                    │    ║
   ║  │  WorkerRuntime.invoke_agent("architect")           │    ║
   ║  │  → emit_status("analyzing")                       │    ║
   ║  │  → emit_status("generating")                      │    ║
   ║  │  → 回复完成                                        │    ║
   ║  │                                                    │    ║
   ║  │  AgentOutput:                                      │    ║
   ║  │    content: "需求拆解如下：                         │    ║
   ║  │      1. 用户认证模块                                │    ║
   ║  │      2. 权限管理模块                                │    ║
   ║  │      3. 数据加密模块                                │    ║
   ║  │      @全栈开发 请按此方案实现"                      │    ║
   ║  │    next_mentions: ["developer"]                    │    ║
   ║  └────────────────────────────────────────────────────┘    ║
   ║                                                          ║
   ║  ┌─ 合规（并行线程 2）──────────────────────────────┐    ║
   ║  │  ContextBuilder 组装 AgentInput                   │    ║
   ║  │  → messages: [...历史, 人类消息]（和架构师看到一样）│    ║
   ║  │  → invocation: "must_reply"                       │    ║
   ║  │                                                    │    ║
   ║  │  AgentOutput:                                      │    ║
   ║  │    content: "GDPR 合规要求：                        │    ║
   ║  │      1. 需要用户同意机制                            │    ║
   ║  │      2. 数据可删除 ...                              │    ║
   ║  │      @测试工程师 请准备合规测试用例"                │    ║
   ║  │    next_mentions: ["tester"]                       │    ║
   ║  └────────────────────────────────────────────────────┘    ║
   ║                                                          ║
   ║  Phase A 完成 →                                          ║
   ║    架构师的回复写入消息流，推前端                          ║
   ║    合规的回复写入消息流，推前端                            ║
   ╚══════════════════════════════════════════════════════════╝
   │
   │  此时消息流状态：
   │  [人类消息] → [架构师回复] → [合规回复]
   │
   ╔══════════════════════════════════════════════════════════╗
   ║  Turn 1 · Phase B: may_reply（并行）                     ║
   ╠══════════════════════════════════════════════════════════╣
   ║                                                          ║
   ║  developer 和 tester 被评估是否自主回复                   ║
   ║  注意：它们能看到 Phase A 的回复！                        ║
   ║                                                          ║
   ║  ┌─ 开发（may_reply）──────────────────────────────┐    ║
   ║  │  ContextBuilder 组装 AgentInput                   │    ║
   ║  │  → messages: [...历史, 人类消息, 架构师回复, 合规回复] │
   ║  │  → invocation: "may_reply"                        │    ║
   ║  │                                                    │    ║
   ║  │  开发看到架构师的方案 + 合规要求                     │    ║
   ║  │  → 判断 should_respond = True                      │    ║
   ║  │                                                    │    ║
   ║  │  AgentOutput:                                      │    ║
   ║  │    content: "收到，我先实现用户认证模块，             │    ║
   ║  │      会按照合规要求加入同意机制。                     │    ║
   ║  │      @测试工程师 认证模块完成后请做冒烟测试"         │    ║
   ║  │    next_mentions: ["tester"]                       │    ║
   ║  │    should_respond: true                            │    ║
   ║  └────────────────────────────────────────────────────┘    ║
   ║                                                          ║
   ║  ┌─ 测试（may_reply）──────────────────────────────┐    ║
   ║  │  ContextBuilder 组装 AgentInput                   │    ║
   ║  │  → 看到了所有人的回复                              │    ║
   ║  │  → 关键词匹配 "测试" 相关性 0.4 < 阈值 0.8        │    ║
   ║  │  → should_respond = False（没被 @ 且相关性不够）   │    ║
   ║  └────────────────────────────────────────────────────┘    ║
   ║                                                          ║
   ║  Phase B 完成 →                                          ║
   ║    开发的回复写入消息流，推前端                            ║
   ║    测试没有回复                                           ║
   ╚══════════════════════════════════════════════════════════╝
   │
   │  Turn 1 全部完成，消息流状态：
   │  [人类消息] → [架构师回复] → [合规回复] → [开发回复]
   │
5. 汇总 next_mentions
   │  架构师 → ["developer"]
   │  合规   → ["tester"]
   │  开发   → ["tester"]
   │
   │  合并去重: ["developer", "tester"]
   │  开发已在 Turn 1 回复过 → 移除
   │  最终 Turn 2 的 must_reply: ["tester"]
   │
6. 创建 Turn 2 (chain_depth=1)
   │
   ╔══════════════════════════════════════════════════════════╗
   ║  Turn 2 · Phase A: must_reply                            ║
   ╠══════════════════════════════════════════════════════════╣
   ║                                                          ║
   ║  ┌─ 测试工程师（must_reply）────────────────────────┐   ║
   ║  │  ContextBuilder 组装 AgentInput                   │    ║
   ║  │  → messages 包含 Turn 1 所有人的回复               │    ║
   ║  │  → 测试能看到：架构师的方案 + 合规的要求 + 开发     │    ║
   ║  │    的计划 → 信息完整                                │    ║
   ║  │                                                    │    ║
   ║  │  AgentOutput:                                      │    ║
   ║  │    content: "好的，我会准备以下测试用例：            │    ║
   ║  │      1. 用户注册流程测试                             │    ║
   ║  │      2. GDPR 同意机制测试                            │    ║
   ║  │      3. 数据删除请求测试"                            │    ║
   ║  │    next_mentions: []    ← 不 @ 任何人               │    ║
   ║  └────────────────────────────────────────────────────┘    ║
   ╚══════════════════════════════════════════════════════════╝
   │
7. 汇总 next_mentions: 空
   │  → 不会产生 Turn 3
   │  → 整个对话轮次结束
   │  → 等待人类下一条消息
```

### 9.3 前端时间线视角（用户看到的）

```
14:30  🧑 你
       @架构师 @合规 请帮我拆解这个需求...

14:31  🏗️ 架构师                                    ← Turn 1, Phase A
       需求拆解如下：1. 用户认证模块 2. 权限管理模块 ...
       @全栈开发 请按此方案实现

14:31  📋 合规检查员                                  ← Turn 1, Phase A（几乎同时）
       GDPR 合规要求：1. 需要用户同意机制 ...
       @测试工程师 请准备合规测试用例

14:32  👨‍💻 全栈开发                                    ← Turn 1, Phase B
       收到，我先实现用户认证模块，会按照合规要求加入同意机制。
       @测试工程师 认证模块完成后请做冒烟测试

14:33  🧪 测试工程师                                  ← Turn 2, Phase A
       好的，我会准备以下测试用例：...

       ── 自动对话结束，等待你的下一条指令 ──
```

### 9.4 关键观察

| 要点 | 说明 |
|------|------|
| Phase A 内并行 | 架构师和合规**同时**生成回复，互相看不到对方的回复 |
| Phase B 看到 Phase A | 开发在 Phase B 中，能看到架构师和合规的回复，所以它的回复能综合两者 |
| 收齐再开下一 Turn | 不是架构师 @ 开发后立刻触发，而是等 Turn 1 全部完成后，汇总 next_mentions |
| 去重 | 开发在 Turn 1 已回复，不再出现在 Turn 2 的 must_reply 中 |
| 信息完整性 | 测试在 Turn 2 中能看到 Turn 1 所有人的回复，拿到完整上下文 |
| 自然结束 | 测试没有 next_mentions → 没有 Turn 3 → 等待人类 |

---

## 十、前端界面设计要点

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Agent Arena                                                    [设置] [+群组]│
├──────────┬──────────────────────────────────────────┬────────────────────────┤
│          │                                          │                        │
│ 群组列表  │            对话空间                       │    员工状态面板         │
│          │                                          │                        │
│ ┌──────┐ │  ┌────────────────────────────────────┐  │  ┌──────────────────┐  │
│ │项目A │ │  │ 🧑 你 (14:30)                      │  │  │ 🏗️ 架构师        │  │
│ │      │ │  │ @架构师 请帮我拆解这个需求：        │  │  │ ● generating...  │  │
│ └──────┘ │  │ 做一个用户管理系统                   │  │  │ ████░░░░ 50%     │  │
│ ┌──────┐ │  └────────────────────────────────────┘  │  └──────────────────┘  │
│ │项目B │ │                                          │  ┌──────────────────┐  │
│ │      │ │  ┌────────────────────────────────────┐  │  │ 👨‍💻 全栈开发      │  │
│ └──────┘ │  │ 🏗️ 架构师 (14:31)                  │  │  │ ○ idle           │  │
│ ┌──────┐ │  │ 好的，我来拆解这个需求：            │  │  └──────────────────┘  │
│ │讨论组 │ │  │ 1. 用户认证模块 ...                │  │  ┌──────────────────┐  │
│ │      │ │  │ 2. 用户管理模块 ...                │  │  │ 🧪 测试工程师     │  │
│ └──────┘ │  │ @全栈开发 请按这个方案实现          │  │  │ ○ idle           │  │
│          │  └────────────────────────────────────┘  │  └──────────────────┘  │
│          │                                          │  ┌──────────────────┐  │
│          │  ┌────────────────────────────────────┐  │  │ 📋 合规检查员     │  │
│          │  │ 👨‍💻 全栈开发 (14:33)                │  │  │ ○ idle           │  │
│          │  │ 收到，我开始实现用户认证模块...     │  │  └──────────────────┘  │
│          │  └────────────────────────────────────┘  │                        │
│          │                                          │  ── Token 用量 ──      │
│          │  ┌────────────────────────────────────┐  │  本会话: 12,450        │
│          │  │  [输入消息...]           [@] [发送] │  │  预算: 100,000         │
│          │  └────────────────────────────────────┘  │  ████░░░░░░ 12%        │
│          │                                          │                        │
└──────────┴──────────────────────────────────────────┴────────────────────────┘
```

**前后端通信：**
- **REST API**：群组 CRUD、消息历史查询、员工管理
- **WebSocket**：实时消息推送、员工状态更新、流式输出

---

## 十一、项目目录结构

```
agent_arena/
├── README.md
├── pyproject.toml                    # Python 项目配置
├── .env                              # 环境变量（API Keys 等）
│
├── agents/                           # 员工配置（YAML 文件）
│   ├── architect.yaml
│   ├── developer.yaml
│   ├── tester.yaml
│   ├── compliance.yaml
│   └── supervisor.yaml               # 可选：超级管理员
│
├── src/
│   ├── __init__.py
│   ├── main.py                       # FastAPI 入口
│   │
│   ├── api/                          # API 网关层
│   │   ├── __init__.py
│   │   ├── routes_group.py           # 群组相关路由
│   │   ├── routes_message.py         # 消息相关路由
│   │   ├── routes_agent.py           # 员工相关路由
│   │   └── websocket.py              # WebSocket 管理
│   │
│   ├── core/                         # 核心业务层
│   │   ├── __init__.py
│   │   ├── orchestrator.py           # 编排引擎
│   │   ├── context_builder.py        # 上下文构建器
│   │   └── session_manager.py        # 会话管理器
│   │
│   ├── worker/                       # 员工运行时
│   │   ├── __init__.py
│   │   ├── runtime.py                # WorkerRuntime
│   │   └── adapters/                 # Adapter 实现
│   │       ├── __init__.py
│   │       ├── base.py               # BaseAdapter 基类
│   │       ├── anthropic_api.py      # Anthropic API Adapter
│   │       ├── openai_api.py         # OpenAI API Adapter
│   │       ├── claude_cli.py         # Claude CLI Adapter
│   │       ├── cursor_cli.py         # Cursor CLI Adapter
│   │       └── generic_cli.py        # 通用 CLI Adapter
│   │
│   ├── memory/                       # 记忆系统
│   │   ├── __init__.py
│   │   ├── store.py                  # MemoryStore
│   │   └── summarizer.py             # 摘要生成器
│   │
│   ├── registry/                     # 员工与技能注册
│   │   ├── __init__.py
│   │   └── agent_registry.py         # AgentRegistry
│   │
│   └── models/                       # 数据模型
│       ├── __init__.py
│       ├── protocol.py               # AgentInput / AgentOutput
│       ├── session.py                # Group / Message / Member
│       └── agent.py                  # AgentProfile / Skill
│
├── data/                             # 运行时数据（.gitignore）
│   ├── agent_arena.db                # SQLite 数据库
│   ├── memory/                       # 记忆快照
│   └── attachments/                  # 附件文件
│
├── frontend/                         # 前端项目（独立）
│   ├── package.json
│   ├── src/
│   └── ...
│
└── tests/                            # 测试
    ├── test_orchestrator.py
    ├── test_context_builder.py
    ├── test_adapters.py
    └── ...
```

---

## 十二、与你随想的逐条对应

| 你的想法 | 架构中的落点 |
|---------|-------------|
| 员工 = CLI 进程，同 CLI 多员工 | WorkerRuntime 管理进程，AgentRegistry 支持同一 adapter_type 创建多个员工 |
| 左侧群组 / 中间对话 / 右侧状态 | 前端三栏布局，WebSocket 驱动实时更新 |
| @ 员工 / @all / 员工互 @ | Orchestrator 解析 mentions → must_reply / may_reply；Agent 通过 next_mentions 链式 @ |
| 响应权限在发送方 vs 接收方 | 混合模式：被 @ 的必须回（发送方权限）+ 其余自主判断（接收方权限） |
| 超级管理员统一派活 | 可选的 Supervisor 模式，按群组配置开关 |
| 入参/出参统一 | AgentInput / AgentOutput 协议 + BaseAdapter 接口 |
| 角色（PM/架构/开发/测试/合规） | AgentRegistry 的 YAML 配置，每个角色一个文件 |
| 记忆模块，按会话还是按员工 | **按会话存储**，员工无状态，调用时由 ContextBuilder 注入 |
| Token 节省 | ContextBuilder 四层策略：截断 → 摘要 → 记忆检索 → 简洁引导 |
| 右侧动画（在干啥） | WorkerRuntime 的 emit_status + 前端状态机映射动画 |
| 可扩展、适配主流 CLI | BaseAdapter 接口 + 新增 YAML 配置文件即可 |
| 与多智能体编排框架的区别 | 明确区分：我们是「协作平台」不是「编排框架」，每个员工本身就是完整 Agent |

---

## 十三、补充设计（你没提但很重要的）

### 13.1 审计日志

所有 Agent 的输入输出都应该记录，便于：
- 合规检查员 Agent 生成合规报告（使用真实记录而非凭空编造）
- 出了问题可以回溯
- Token 用量统计

```python
class AuditLog:
    turn_id: str
    agent_id: str
    input_tokens: int
    output_tokens: int
    input_hash: str          # 不存原文，存 hash，节省空间
    output_content: str      # 输出需要存原文（用于合规审查）
    latency_ms: int
    status: Literal["success", "timeout", "error"]
    timestamp: datetime
```

### 13.2 人类确认机制

某些高风险操作（如 Agent 要执行命令、修改文件、调用外部 API），系统可以拦截并要求人类确认：

```python
class HumanApprovalConfig:
    require_approval_for: list[str] = [
        "execute_command",       # 执行系统命令
        "modify_file",           # 修改文件
        "external_api_call",     # 调用外部服务
        "deploy",                # 部署操作
    ]
```

### 13.3 群组模板

预定义一些常用的群组模板，快速创建带有默认员工配置的群组：

```yaml
# templates/software_dev.yaml
template_name: "软件开发项目"
description: "适用于软件开发的标准团队配置"
default_members:
  - agent_id: "architect"
    role_in_group: "架构师，负责需求分析和方案设计"
  - agent_id: "developer"
    role_in_group: "全栈开发，负责代码实现"
  - agent_id: "tester"
    role_in_group: "测试工程师，负责质量保障"
  - agent_id: "compliance"
    role_in_group: "合规检查员，负责流程合规"
config:
  max_responders: 3
  supervisor_enabled: false
  auto_summary_interval: 20       # 每 20 条消息自动生成摘要
```

### 13.4 消息格式扩展

Agent 的回复除了纯文本，还可以包含结构化内容：

```python
class StructuredContent:
    """Agent 可以返回结构化内容，前端据此做特殊渲染"""
    type: Literal[
        "task_list",          # 任务列表（前端渲染为 checklist）
        "code_block",         # 代码块（前端渲染为代码编辑器）
        "architecture_diagram",  # 架构图（前端渲染为 Mermaid 图）
        "diff",               # 代码 diff
        "approval_request",   # 审批请求（前端渲染为审批按钮）
    ]
    data: dict
```

---

## 十四、实施路线

### Phase 1: 最小可用（2~3 周）
- [ ] 定义 AgentInput / AgentOutput 协议（`models/protocol.py`）
- [ ] 实现一个 Adapter（推荐先做 `AnthropicApiAdapter`，最简单）
- [ ] 实现 SessionManager（SQLite + 基本 CRUD）
- [ ] 实现 Orchestrator（仅支持 @ 某人 → must_reply）
- [ ] 实现 ContextBuilder（仅做消息截断，不做记忆）
- [ ] 实现 WorkerRuntime（单 Agent 调用）
- [ ] 前端：最简单的聊天界面 + 1 个 Agent

**交付物：** 能和 1 个 AI 员工对话的最简系统。

### Phase 2: 多员工协作（2~3 周）
- [ ] 支持多 Agent、多群组
- [ ] Orchestrator 支持 may_reply 自主判断
- [ ] 支持 Agent 链式 @（next_mentions）
- [ ] 防循环、超时等防护机制
- [ ] 前端三栏布局 + 员工状态面板

**交付物：** 多个 AI 员工能在群里协作。

### Phase 3: 记忆与优化（2~3 周）
- [ ] 记忆系统：保存关键信息、语义检索
- [ ] 历史摘要生成
- [ ] Token 预算管理
- [ ] 审计日志
- [ ] 更多 Adapter（Claude CLI、OpenAI API 等）

**交付物：** 有记忆的、Token 友好的协作系统。

### Phase 4: 体验打磨（持续）
- [ ] 右侧员工状态动画
- [ ] 群组模板
- [ ] 人类确认机制
- [ ] Supervisor 模式
- [ ] 结构化消息渲染
- [ ] 性能优化、监控