# 数字员工记忆架构设计分析

> 分析日期：2026-02-26
> 参考系统：OpenClaw、当前 Agent Arena 实现

---

## 一、现状梳理

### 当前已有的"记忆"层

| 层级 | 实现位置 | 内容 | 生命周期 |
|------|---------|------|---------|
| 静态角色 | `workspaces/{id}/CLAUDE.md` | 角色提示词（role_prompt） | 永久，手动更新 |
| 会话记忆 | `data/memory/session_{id}.json` | 决策/需求/任务/摘要条目 | 按群聊会话，永久 |
| 对话历史 | SessionManager（数据库） | 全量消息记录 | 永久，按条数截断注入 |
| 上下文注入 | ContextBuilder | 最近 50 条消息 + top-5 记忆 | 每次调用临时 |

### 当前的核心缺口

1. **没有 Agent 个人的成长记忆**：会话记忆是群聊级别的，Agent 自身学到的东西无处存放
2. **记忆注入粗糙**：只用最后一条消息做关键词匹配检索，无语义
3. **长对话无对策**：对话历史超过 50 条后直接截断，早期关键信息丢失
4. **记忆写入被动**：只有上层主动调用 MemoryStore，Agent 自身不能主动写记忆

---

## 二、OpenClaw 的参考价值与不适用点

### OpenClaw 的设计前提（与本系统不同）

OpenClaw 面向的是**公网多人群聊**场景：群里有多个真实用户，每人都有自己的 OpenClaw 实例。因此它需要：
- 防止 A 的私人记忆泄漏给 B（不同人类之间的隐私）
- 群聊中每个 OpenClaw 都不知道其他成员是谁的

所以 OpenClaw 在群聊中不加载 MEMORY.md，是出于**跨人类用户的隐私保护**。

### Agent Arena 的实际场景

```
Agent Arena 群聊结构：
  一个人类用户（群主/老板）
  + N 个 AI 数字员工（全部为该用户服务）
```

**这意味着：**
- 群里没有陌生人，所有 Agent 都是同一个用户的员工
- Agent A 的记忆泄漏给 Agent B 完全可以接受，甚至是期望的
- OpenClaw 的群聊记忆限制**不适用于本系统**

### OpenClaw 仍然值得借鉴的部分

1. **分层记忆结构**：身份层 / 个人成长层 / 会话协作层
2. **文件即记忆**：SOUL.md、MEMORY.md、daily logs 的文件组织方式
3. **Heartbeat 蒸馏机制**：定期从日志提炼精华到 MEMORY.md
4. **主动写记忆**：Agent 自己判断哪些值得保存，而不只是被动接受

### Heartbeat 记忆增长机制（值得借鉴）

OpenClaw 通过定期"心跳"任务：
1. 读取近期 daily logs
2. 提炼值得长期保留的内容
3. 更新 MEMORY.md（精华长期记忆）
4. 清理过时信息

---

## 三、Agent Arena 的记忆架构方案

### 3.1 建议的三层记忆模型

```
Layer 1: 身份层（Identity）- 静态，慢变化
  workspaces/{agent_id}/
  ├── CLAUDE.md           → 角色定义（现有）
  └── SOUL.md             → 核心人格、价值观（新增，可选）

Layer 2: 个人成长层（Personal Memory）- 动态，跨会话积累
  workspaces/{agent_id}/
  ├── MEMORY.md           → 精华长期记忆，每次都加载（新增）
  └── memory/
      └── YYYY-MM-DD.md   → 每日工作原始日志（新增）

Layer 3: 群聊协作层（Session Memory）- 动态，当前群聊上下文
  data/memory/
  ├── session_{group_id}.json   → 结构化记忆条目（现有 MemoryStore）
  └── summary_{group_id}.md    → 会话滚动摘要（新增）
```

**关键简化**：由于群聊里只有一个人类用户，Agent 的个人 MEMORY.md 在任何场景下都可以加载，不需要像 OpenClaw 一样区分主会话/群聊。

### 3.2 每次 Agent 调用时的记忆加载逻辑

唯一真正的约束是 **Token 预算**，不是隐私。所有记忆都可以加载，按优先级装填：

```python
# 在 ContextBuilder.build_input 中按 Token 优先级组装

def _build_memory_context(agent_id, session_id):
    parts = []

    # ① 身份层：总是完整加载，最高优先级（~200 tokens）
    claude_md = read_file(f"workspaces/{agent_id}/CLAUDE.md")
    parts.append(claude_md)

    # ② 个人精华记忆：跨会话成长的核心（~400 tokens，控制在限额内）
    long_term = read_file(f"workspaces/{agent_id}/MEMORY.md")
    parts.append(long_term)

    # ③ 今日/昨日工作日志：近期上下文（~300 tokens）
    today_log = read_file(f"workspaces/{agent_id}/memory/{today}.md")
    yesterday_log = read_file(f"workspaces/{agent_id}/memory/{yesterday}.md")
    parts.extend([today_log, yesterday_log])

    # ④ 群聊滚动摘要：解决长对话截断的关键（~300 tokens）
    rolling_summary = read_file(f"data/memory/summary_{session_id}.md")
    parts.append(rolling_summary)

    # ⑤ 结构化记忆检索：与当前问题相关的历史条目（top-5，~200 tokens）
    session_memory = memory_store.search(session_id, query=latest_message)
    parts.append(session_memory)

    # ⑥ 近期对话历史：在剩余 token 预算内尽量多取（倒序，优先最新）
    # （由现有的 _get_truncated_history 处理）

    return "\n\n---\n\n".join(filter(None, parts))
```

**Token 预算示例**（Claude Sonnet，200K 上下文）：

| 层级 | 预算 | 说明 |
|------|-----|------|
| 身份（CLAUDE.md） | ~500 tokens | 固定，角色定义 |
| 个人精华记忆（MEMORY.md） | ~800 tokens | 控制文件大小 |
| 近期日志（今+昨） | ~600 tokens | 近期工作上下文 |
| 群聊滚动摘要 | ~500 tokens | 防止长对话失忆 |
| 结构化记忆条目 | ~400 tokens | 相关历史检索 |
| **对话历史** | **剩余全部** | ~198K tokens 可用 |

### 3.3 Workspace 策略：独立 vs 共享

**真正的问题不是隐私，而是：个人成长记忆在哪存，协作时代码库怎么共享。**

#### 结论：个人 Workspace 独立，项目 Workspace 共享引用

| 维度 | 独立个人 Workspace | 共享项目 Workspace |
|------|-----------------|-----------------|
| 身份记忆 | ✅ 每个员工独立存储成长记忆 | ❌ 无法区分谁的记忆 |
| 项目文件 | ❌ 每人一份，同步麻烦 | ✅ 一份代码库，实时一致 |
| 工具执行隔离 | ✅ 互不干扰 | ❌ 并发写同一文件冲突 |
| 实现复杂度 | 中 | 低 |

**推荐方案：双 Workspace 模式**

```yaml
# agents/developer.yaml
agent_id: developer
workspace_dir: workspaces/developer     # 个人 workspace（记忆、身份文件）
project_workspace: workspaces/shared    # 项目 workspace（代码库，多员工共享）
```

- **个人 workspace**：存放 CLAUDE.md、MEMORY.md、daily logs，每个员工独立
- **项目 workspace**：Claude CLI 实际执行代码时 `--add-dir` 指向的代码库，可多员工共享
- 启动 Claude CLI 时：以个人 workspace 为 `cwd`，用 `--add-dir` 挂载项目代码库
- 成长记忆写在个人 workspace，代码修改发生在共享项目 workspace

---

## 四、群聊上下文丢失问题的解决方案

### 4.1 问题根源

当前：截取最近 50 条消息注入。当对话很长时：
- 早期的需求讨论、关键决策会被截断
- Agent 每次"失忆"，重复询问已经回答过的问题
- 协作链断裂

### 4.2 三重防线方案

**防线一：主动检查点（Checkpoint）**

每隔 N 条消息，或每当检测到重要决策时，自动触发摘要写入：

```
触发条件：
- 每 20 条消息自动归档一次
- 检测到 [decision] / [requirement] / [task_assigned] 关键词时立即写入
- Agent 可主动调用 save_memory() 工具

写入目标：
- 会话级：MemoryStore（已有）
- 个人日志：workspaces/{agent_id}/memory/{today}.md
```

**防线二：滚动摘要（Rolling Summary）**

维护一个会话级的"活跃摘要"，始终注入上下文头部：

```
[会话摘要 - 自动维护]
- 项目目标：开发用户管理模块
- 已完成：数据库 schema 设计（developer 完成于 10:30）
- 当前任务：前端表单验证（assigned to developer）
- 关键决策：使用 JWT 鉴权（architect 决定于 09:50）
```

```python
# 在 ContextBuilder 中的注入顺序（按 Token 优先级）

1. role_prompt / SOUL.md      （~200 tokens，固定）
2. session_rolling_summary    （~300 tokens，动态维护）
3. agent_personal_memory      （~300 tokens，近期日志）
4. recent_messages            （剩余 token 预算，倒序取最新）
5. session_structured_memory  （top-5 相关条目）
```

**防线三：Agent 主动记忆工具**

给 Agent 提供写记忆的能力（通过 system prompt 引导）：

```markdown
## 记忆守则

当你做出重要决定、接受任务、或发现关键信息时，主动调用记忆保存：
- 用 <!--SAVE_MEMORY:{"type":"decision","content":"..."}-->  标记需要保存的信息
- 用 <!--SAVE_TO_PERSONAL:{"content":"..."}-->  记录个人学习笔记

编排器会解析这些标记并写入对应的记忆存储。
```

---

## 五、记忆成长机制（Heartbeat）

### 5.1 每日/每次会话结束时的记忆蒸馏

```
会话结束 → 触发 Heartbeat
  ↓
读取今日 daily log（workspaces/{agent_id}/memory/{today}.md）
  ↓
AI 提炼：哪些值得长期记住？
  ↓
更新 MEMORY.md（精华记忆）
  ↓
（可选）更新 CLAUDE.md / SOUL.md（角色成长）
```

### 5.2 记忆蒸馏 Prompt 模板

```
你是 {agent_name}，今天工作结束。请回顾今日日志，提炼值得长期记住的内容：

## 今日工作日志
{today_log}

## 现有长期记忆
{current_memory_md}

请输出更新后的 MEMORY.md 内容，格式：
- 保留仍然相关的旧记忆
- 追加今日学到的新模式/技巧/教训
- 删除已过时的信息
- 总长度控制在 500 token 以内
```

---

## 六、群聊中多 Agent 的记忆共享与分工

### 本系统的特性：单一用户，无隐私壁垒

所有 Agent 都服务于同一个用户，因此：
- Agent A 的记忆 Agent B 可以读到 → 完全合理，有助于协作
- 关键区分不是"谁能看"，而是"谁负责写"

### 建议的记忆归属模型

```
群聊公共记忆（session_memory）    → 任何成员可写，全体成员可读
  ├── 用途：项目决策、需求变更、任务分配、阶段摘要
  └── 存储：data/memory/session_{group_id}.json（现有 MemoryStore）

Agent 个人成长记忆（personal）    → 仅自身写，但群聊中也会注入（所有人可读）
  ├── 用途：个人技能提升、习惯偏好、工作模式、教训
  └── 存储：workspaces/{agent_id}/MEMORY.md + memory/{date}.md
```

**实际效果**：开发者 A 在 MEMORY.md 里记下"这个项目用 JWT 鉴权"，架构师 B 下次回复时也能看到这个上下文，协作更顺畅。

---

## 七、推荐实施路径

### Phase 1：补全个人记忆存储（低成本，高价值）

1. 在每个 `workspaces/{agent_id}/` 下创建 `memory/` 目录
2. 修改 `ContextBuilder` 加载 Agent 个人今日/昨日日志
3. 修改 Agent 的 system prompt，引导其用注释标记写记忆
4. 在 Orchestrator 解析 Agent 输出时提取记忆标记并写文件

### Phase 2：滚动摘要（解决长对话丢失）

1. 在 `MemoryStore` 中增加 `rolling_summary` 特殊条目
2. 在 `ContextBuilder` 中优先注入 rolling_summary
3. 当消息数超过阈值时，触发摘要更新

### Phase 3：Heartbeat 成长机制

1. 增加会话结束/每日定时 API
2. 调用蒸馏 Prompt，让 Agent 更新自己的 MEMORY.md
3. 可通过前端展示每个员工的"成长日志"

---

## 八、关键设计决策对比

| 决策点 | 选项 A | 选项 B（推荐） | 理由 |
|--------|--------|-------------|------|
| 个人记忆存储 | 数据库统一管理 | 文件系统（workspace内） | 与 Claude CLI 天然集成，Agent 可直接读写 |
| 群聊加载个人记忆 | 只加载近期日志 | 完整加载 MEMORY.md | 单用户场景，无隐私顾虑，精华记忆价值更高 |
| Workspace 策略 | 完全共享 | 个人独立 + 项目可选共享 | 成长记忆独立 + 代码协作兼顾 |
| 长对话处理 | 简单截断（现有） | 滚动摘要 + 检查点 | 防止关键上下文丢失 |
| 记忆写入 | 仅上层主动写 | 上层 + Agent 主动标记 | 成长记忆需要 Agent 自己判断价值 |

---

## 九、文件结构全景

```
Agent Arena/
├── workspaces/
│   ├── developer/
│   │   ├── CLAUDE.md          # 角色定义（现有）
│   │   ├── MEMORY.md          # 精华长期记忆（新增，每次调用都注入）
│   │   └── memory/
│   │       ├── 2026-02-26.md  # 今日工作日志（新增）
│   │       └── 2026-02-25.md  # 昨日日志
│   ├── tester/
│   │   └── ...（同上结构）
│   └── shared/                # 可选：共享项目代码库（--add-dir 挂载）
│       └── ...（项目代码）
│
├── data/
│   └── memory/
│       ├── session_{group_id}.json    # 群聊结构化记忆（现有 MemoryStore）
│       └── summary_{group_id}.md     # 群聊滚动摘要（新增，解决长对话截断）
│
└── agents/
    └── developer.yaml         # 可增加 project_workspace 字段
```
