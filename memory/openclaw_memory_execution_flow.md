# OpenClaw Memory System Execution Flow

> 本文档完整记录 OpenClaw 的记忆系统执行流程，包括每个节点的原始 Prompt（英文原文）和核心代码逻辑。

---

## 一、记忆系统架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                     OpenClaw Memory System                          │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐    │
│  │ MEMORY.md    │  │ memory/*.md  │  │ Long-term Memory      │    │
│  │ (Curated)    │  │ (Daily logs) │  │ (LanceDB Vector DB)   │    │
│  │              │  │              │  │                      │    │
│  │ • User prefs │  │ • Raw logs   │  │ • Semantic search    │    │
│  │ • Decisions  │  │ • Events     │  │ • Auto-capture       │    │
│  │ • Key facts  │  │ • Temp data  │  │ • Vector embeddings │    │
│  └──────────────┘  └──────────────┘  └──────────────────────┘    │
│         │                  │                      │                │
│         └──────────┬───────┴──────────────────────┘                │
│                    │                                                │
│                    ▼                                                │
│         ┌─────────────────────┐                                    │
│         │ Session Init        │                                    │
│         │ (Every conversation)│                                    │
│         └──────────┬──────────┘                                    │
│                    │                                                │
│                    ▼                                                │
│         ┌─────────────────────┐                                    │
│         │ Memory Loading Logic │                                    │
│         │ (Conditional)        │                                    │
│         └──────────┬──────────┘                                    │
│                    │                                                │
└────────────────────┼────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      AGENTS.md Processing                           │
│                                                                     │
│  ## Every Session                                                   │
│                                                                     │
│  Before doing anything else:                                        │
│                                                                     │
│  1. Read `SOUL.md` — this is who you are                           │
│  2. Read `USER.md` — this is who you're helping                    │
│  3. Read `memory/YYYY-MM-DD.md` (today + yesterday)                │
│  4. **If in MAIN SESSION**: Also read `MEMORY.md`                  │
│                                                                     │
│  Don't ask permission. Just do it.                                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 二、完整执行流程（参考 Agent_Arena 4.2 格式）

### 2.1 会话初始化流程

```
新会话开始
    │
    ▼
┌─────────────────────────────────────┐
│ Step 1: 读取 SOUL.md                │
│                                     │
│ Original Prompt:                    │
│ "Read `SOUL.md` — this is who      │
│  you are"                          │
│                                     │
│ Purpose: 加载 Agent 身份和核心行为准则  │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│ Step 2: 读取 USER.md                │
│                                     │
│ Original Prompt:                    │
│ "Read `USER.md` — this is who      │
│  you're helping"                   │
│                                     │
│ Purpose: 了解用户信息、偏好和上下文    │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│ Step 3: 读取短期记忆                │
│                                     │
│ Original Prompt:                    │
│ "Read `memory/YYYY-MM-DD.md`       │
│  (today + yesterday) for recent    │
│  context"                          │
│                                     │
│ Purpose: 获取最近2天的交互记录       │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│ Step 4: 判断会话类型                │
│                                     │
│ Condition:                          │
│ "If in MAIN SESSION (direct chat   │
│  with your human)"                 │
│                                     │
│ MAIN SESSION = 直接对话 (webchat,   │
│ private DM, etc.)                  │
│ NOT MAIN = 群聊、Discord、共享上下文 │
└──────────────────┬──────────────────┘
                   │
                   ├──── Yes (MAIN SESSION) ──┐
                   │                           │
                   │                           ▼
                   │              ┌──────────────────────────┐
                   │              │ Step 4a: 读取 MEMORY.md   │
                   │              │                          │
                   │              │ Original Prompt:         │
                   │              │ "Also read `MEMORY.md`" │
                   │              │                          │
                   │              │ Safety Rule:            │
                   │              │ "ONLY load in main      │
                   │              │  session (direct chats  │
                   │              │  with your human)"      │
                   │              │                          │
                   │              │ "DO NOT load in shared   │
                   │              │  contexts (Discord,     │
                   │              │  group chats, sessions   │
                   │              │  with other people)"     │
                   │              │                          │
                   │              │ Security Reason:         │
                   │              │ "This is for security —  │
                   │              │  contains personal       │
                   │              │  context that shouldn't  │
                   │              │  leak to strangers"      │
                   │              └───────────┬──────────────┘
                   │                          │
                   │                          ▼
                   │              ┌──────────────────────────┐
                   │              │ MEMORY.md 内容加载完成    │
                   │              │ 包含：                   │
                   │              │ • 用户偏好设置           │
                   │              │ • 重要决策               │
                   │              │ • 持久性关系信息         │
                   │              │ • 学习经验               │
                   │              └───────────┬──────────────┘
                   │                          │
                   │                          │
                   │                          │
                   └──── No (NOT MAIN) ──────┤
                                              │
                                              ▼
                                 ┌──────────────────────────┐
                                 │ 跳过 MEMORY.md           │
                                 │ (安全隔离)               │
                                 │                          │
                                 │ Reason:                  │
                                 │ "Group chats, Discord,   │
                                 │  or shared contexts"     │
                                 │                          │
                                 │ "Contains personal       │
                                 │  context that shouldn't  │
                                 │  leak to strangers"      │
                                 └───────────┬──────────────┘
                                             │
                                             ▼
                                 ┌──────────────────────────┐
                                 │ 准备就绪，开始处理用户请求  │
                                 └──────────────────────────┘
```

### 2.2 记忆读取核心 Prompt（原始英文）

#### 2.2.1 系统级 Prompt 注入

```markdown
## Memory Recall
Before answering anything about prior work, decisions, dates, people, preferences, or todos: run memory_search on MEMORY.md + memory/*.md; then use memory_get to pull only the needed lines. If low confidence after search, say you checked.
Citations: include Source: <path#line> when it helps the user verify memory snippets.
```

#### 2.2.2 AGENTS.md 中的记忆指令

```markdown
## Memory

You wake up fresh each session. These files _are_ your memory. Read them. Update them. They're how you persist.

- **Daily notes:** `memory/YYYY-MM-DD.md` (create `memory/` if needed) — raw logs of what happened
- **Long-term:** `MEMORY.md` — your curated memories, like a human's long-term memory

Capture what matters. Decisions, context, things to remember. Skip the secrets unless asked to keep them.

### 🧠 MEMORY.md - Your Long-Term Memory

- **ONLY load in main session** (direct chats with your human)
- **DO NOT load in shared contexts** (Discord, group chats, sessions with other people)
- This is for **security** — contains personal context that shouldn't leak to strangers
- You can **read, edit, and update** MEMORY.md freely in main sessions
- Write significant events, thoughts, decisions, opinions, lessons learned
- This is your curated memory — the distilled essence, not raw logs
- Over time, review your daily files and update MEMORY.md with what's worth keeping

### 📝 Write It Down - No "Mental Notes"!

- **Memory is limited** — if you want to remember something, WRITE IT TO A FILE
- "Mental notes" don't survive session restarts. Files do.
- When someone says "remember this" → update `memory/YYYY-MM-DD.md` or relevant file
- When you learn a lesson → update AGENTS.md, TOOLS.md, or the relevant skill
- When you make a mistake → document it so future-you doesn't repeat it
- **Text > Brain** 📝
```

---

## 三、记忆工具实现（Tool Definitions）

### 3.1 memory_search 工具

**工具定义（原始英文）：**

```typescript
{
  name: "memory_search",
  description: "Mandatory recall step: semantically search MEMORY.md + memory/*.md (and optional session transcripts) before answering questions about prior work, decisions, dates, people, preferences, or todos; returns top snippets with path + lines.",
  parameters: {
    query: { type: "string", description: "Search query" },
    maxResults: { type: "number", description: "Max results (default: 10)" },
    minScore: { type: "number", description: "Min similarity score 0-1 (default: 0.5)" }
  }
}
```

**核心实现逻辑：**

```typescript
// Source: /opt/openclaw/extensions/memory-lancedb/index.ts

async function memorySearch(query: string, limit: number = 5, minScore: number = 0.5) {
  // Step 1: 生成查询向量
  const vector = await embeddings.embed(query);
  
  // Step 2: 向量相似度搜索
  const results = await db.search(vector, limit, minScore);
  
  // Step 3: 转换 L2 distance 为相似度分数
  const mapped = results.map((row) => {
    const distance = row._distance ?? 0;
    const score = 1 / (1 + distance);  // L2 distance → similarity
    return {
      entry: {
        id: row.id,
        text: row.text,
        vector: row.vector,
        importance: row.importance,
        category: row.category,
        createdAt: row.createdAt,
      },
      score,
    };
  });
  
  // Step 4: 过滤低分结果
  return mapped.filter((r) => r.score >= minScore);
}
```

### 3.2 memory_get 工具

**工具定义（原始英文）：**

```typescript
{
  name: "memory_get",
  description: "Safe snippet read from MEMORY.md or memory/*.md with optional from/lines; use after memory_search to pull only the needed lines and keep context small.",
  parameters: {
    path: { type: "string", description: "Path to the file to read (relative or absolute)" },
    from: { type: "number", description: "Line number to start reading from (1-indexed)" },
    lines: { type: "number", description: "Maximum number of lines to read" }
  }
}
```

---

## 四、自动记忆捕获流程（Auto-Capture）

### 4.1 规则引擎

```typescript
// Source: /opt/openclaw/extensions/memory-lancedb/index.ts

const MEMORY_TRIGGERS = [
  /zapamatuj si|pamatuj|remember/i,
  /preferuji|radši|nechci|prefer/i,
  /rozhodli jsme|budeme používat/i,
  /\+\d{10,}/,                    // Phone numbers
  /[\w.-]+@[\w.-]+\.\w+/,        // Email addresses
  /můj\s+\w+\s+je|je\s+můj/i,     // Czech: "my X is"
  /my\s+\w+\s+is|is\s+my/i,       // English: "my X is"
  /i (like|prefer|hate|love|want|need)/i,
  /always|never|important/i,
];

export function shouldCapture(text: string): boolean {
  // Filter 1: 长度限制
  if (text.length < 10 || text.length > 500) {
    return false;
  }
  
  // Filter 2: 跳过已注入的记忆内容
  if (text.includes("<relevant-memories>")) {
    return false;
  }
  
  // Filter 3: 跳过系统生成内容
  if (text.startsWith("<") && text.includes("</")) {
    return false;
  }
  
  // Filter 4: 跳过 Markdown 格式的总结响应
  if (text.includes("**") && text.includes("\n-")) {
    return false;
  }
  
  // Filter 5: 跳过表情符号过多的内容
  const emojiCount = (text.match(/[\u{1F300}-\u{1F9FF}]/gu) || []).length;
  if (emojiCount > 3) {
    return false;
  }
  
  // Filter 6: 匹配触发规则
  return MEMORY_TRIGGERS.some((r) => r.test(text));
}
```

### 4.2 类别检测

```typescript
export function detectCategory(text: string): MemoryCategory {
  const lower = text.toLowerCase();
  
  if (/prefer|radši|like|love|hate|want/i.test(lower)) {
    return "preference";
  }
  if (/rozhodli|decided|will use|budeme/i.test(lower)) {
    return "decision";
  }
  if (/\+\d{10,}|@[\w.-]+\.\w+|is called|jmenuje se/i.test(lower)) {
    return "entity";
  }
  if (/is|are|has|have|je|má|jsou/i.test(lower)) {
    return "fact";
  }
  
  return "other";
}
```

### 4.3 自动捕获生命周期钩子

```typescript
// Auto-capture: analyze and store important information after agent ends

if (cfg.autoCapture) {
  api.on("agent_end", async (event) => {
    if (!event.success || !event.messages || event.messages.length === 0) {
      return;
    }

    // Step 1: 提取文本内容
    const texts: string[] = [];
    for (const msg of event.messages) {
      if (!msg || typeof msg !== "object") continue;
      
      const msgObj = msg as Record<string, unknown>;
      const role = msgObj.role;
      
      // 只处理 user 和 assistant 消息
      if (role !== "user" && role !== "assistant") continue;
      
      const content = msgObj.content;
      
      if (typeof content === "string") {
        texts.push(content);
        continue;
      }
      
      // 处理内容块数组
      if (Array.isArray(content)) {
        for (const block of content) {
          if (block?.type === "text" && typeof block.text === "string") {
            texts.push(block.text);
          }
        }
      }
    }

    // Step 2: 过滤可捕获内容
    const toCapture = texts.filter((text) => text && shouldCapture(text));
    if (toCapture.length === 0) return;

    // Step 3: 存储捕获内容（每轮对话最多3条）
    let stored = 0;
    for (const text of toCapture.slice(0, 3)) {
      const category = detectCategory(text);
      const vector = await embeddings.embed(text);

      // 检查重复（高相似度阈值）
      const existing = await db.search(vector, 1, 0.95);
      if (existing.length > 0) continue;

      await db.store({
        text,
        vector,
        importance: 0.7,
        category,
      });
      stored++;
    }

    if (stored > 0) {
      api.logger.info(`memory-lancedb: auto-captured ${stored} memories`);
    }
  });
}
```

---

## 五、自动记忆注入流程（Auto-Recall）

### 5.1 生命周期钩子实现

```typescript
// Auto-recall: inject relevant memories before agent starts

if (cfg.autoRecall) {
  api.on("before_agent_start", async (event) => {
    if (!event.prompt || event.prompt.length < 5) {
      return;
    }

    try {
      // Step 1: 对用户提示进行向量嵌入
      const vector = await embeddings.embed(event.prompt);
      
      // Step 2: 搜索相关记忆（Top 3, 阈值 0.3）
      const results = await db.search(vector, 3, 0.3);

      if (results.length === 0) return;

      // Step 3: 格式化记忆上下文
      const memoryContext = results
        .map((r) => `- [${r.entry.category}] ${r.entry.text}`)
        .join("\n");

      api.logger.info?.(`memory-lancedb: injecting ${results.length} memories into context`);

      // Step 4: 注入到 Agent 提示前
      return {
        prependContext: `<relevant-memories>
The following memories may be relevant to this conversation:
${memoryContext}
</relevant-memories>`,
      };
    } catch (err) {
      api.logger.warn(`memory-lancedb: recall failed: ${String(err)}`);
    }
  });
}
```

---

## 六、心跳维护流程（Heartbeat Maintenance）

### 6.1 心跳任务定义

```markdown
## 💓 Heartbeats - Be Proactive!

When you receive a heartbeat poll (message matches the configured heartbeat prompt), don't just reply `HEARTBEAT_OK` every time. Use heartbeats productively!

Default heartbeat prompt:
`Read HEARTBEAT.md if it exists (workspace context). Follow it strictly. Do not infer or repeat old tasks from prior chats. If nothing needs attention, reply HEARTBEAT_OK.`

You are free to edit `HEARTBEAT.md` with a short checklist or reminders. Keep it small to limit token burn.

### 🔄 Memory Maintenance (During Heartbeats)

Periodically (every few days), use a heartbeat to:

1. Read through recent `memory/YYYY-MM-DD.md` files
2. Identify significant events, lessons, or insights worth keeping long-term
3. Update `MEMORY.md` with distilled learnings
4. Remove outdated info from MEMORY.md that's no longer relevant

Think of it like a human reviewing their journal and updating their mental model. Daily files are raw notes; MEMORY.md is curated wisdom.
```

### 6.2 心跳状态追踪

```json
// memory/heartbeat-state.json
{
  "lastChecks": {
    "email": 1703275200,
    "calendar": 1703260800,
    "weather": null
  }
}
```

---

## 七、文件结构详解

### 7.1 记忆文件层次结构

```
workspace/
├── MEMORY.md                          # 长期记忆（仅主会话加载）
│   内容示例：
│   - 用户偏好设置
│   - 重要决策记录
│   - 持久性关系信息
│   - 学习到的经验教训
│
├── memory/                            # 短期记忆目录
│   ├── 2026-02-26.md                # 今日记忆
│   ├── 2026-02-25.md                # 昨日记忆
│   ├── 2026-02-24.md                # 更早的记忆
│   └── heartbeat-state.json         # 心跳状态追踪
│
├── AGENTS.md                         # 记忆系统规则定义
│   包含：
│   - 会话初始化流程
│   - 记忆类型定义
│   - 写入规则
│   - 心跳维护逻辑
│
├── SOUL.md                           # Agent 身份定义
├── USER.md                           # 用户信息
└── HEARTBEAT.md                      # 心跳任务清单（可选）
```

### 7.2 LanceDB 向量记忆存储

```
data/
└── memories.lancedb/                 # 向量数据库目录
    ├── data.lance                    # 记忆向量数据
    └── _manifest.json               # 元数据索引

MemoryEntry 结构：
{
  id: string;              // UUID
  text: string;            // 记忆文本
  vector: number[];         // 向量嵌入
  importance: number;       // 重要性 0-1
  category: MemoryCategory; // 分类
  createdAt: number;        // 时间戳
}

MemoryCategory 类型：
- "preference"  // 用户偏好
- "decision"    // 决策记录
- "entity"      // 实体信息
- "fact"        // 事实陈述
- "other"       // 其他
```

---

## 八、安全边界与隐私保护

### 8.1 主会话 vs 共享上下文判断

```markdown
## Group Chats

You have access to your human's stuff. That doesn't mean you _share_ their stuff. In groups, you're a participant — not their voice, not their proxy. Think before you speak.

### Memory Security in Groups

- **DO NOT load MEMORY.md in shared contexts** (Discord, group chats, sessions with other people)
- This is for **security** — contains personal context that shouldn't leak to strangers
- In groups, you're a participant — not their voice, not their proxy
```

### 8.2 数据隔离规则

```markdown
## Safety

- Don't exfiltrate private data. Ever.
- Don't run destructive commands without asking.
- `trash` > `rm` (recoverable beats gone forever)
- When in doubt, ask.

## External vs Internal

**Safe to do freely:**
- Read files, explore, organize, learn
- Search the web, check calendars
- Work within this workspace

**Ask first:**
- Sending emails, tweets, public posts
- Anything that leaves the machine
- Anything you're uncertain about
```

---

## 九、完整执行流程图（带 Prompt 标注）

```
┌─────────────────────────────────────────────────────────────────────┐
│                        用户发起新会话                                │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 1: 系统初始化                                                   │
│                                                                     │
│ 执行代码：                                                           │
│   const memoryPaths = [                                             │
│     path.join(workspaceDir, "MEMORY.md"),                          │
│     path.join(workspaceDir, "memory.md")                           │
│   ];                                                               │
│                                                                     │
│ 加载 AGENTS.md 规则：                                                │
│   "Before doing anything else:                                      │
│    1. Read `SOUL.md` — this is who you are                          │
│    2. Read `USER.md` — this is who you're helping                   │
│    3. Read `memory/YYYY-MM-DD.md` (today + yesterday)               │
│    4. **If in MAIN SESSION**: Also read `MEMORY.md`                 │
│    Don't ask permission. Just do it."                              │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 2: 判断会话类型                                                 │
│                                                                     │
│ 条件判断：                                                           │
│   if (sessionType === "main") {                                     │
│     // 直接对话 - webchat, private DM, etc.                         │
│     loadLongTermMemory();                                           │
│   } else {                                                          │
│     // 群聊、Discord、共享上下文                                      │
│     skipLongTermMemory(); // 安全隔离                                │
│   }                                                                 │
│                                                                     │
│ 安全规则（原始 Prompt）：                                            │
│   "ONLY load in main session (direct chats with your human)        │
│    DO NOT load in shared contexts (Discord, group chats,            │
│    sessions with other people)                                      │
│    This is for security — contains personal context that            │
│    shouldn't leak to strangers"                                    │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                   ┌─────────┴─────────┐
                   │                   │
                   │ MAIN SESSION?     │
                   │                   │
                   └─────────┬─────────┘
                      Yes    │    No
                         │   │
             ┌───────────┘   └───────────┐
             │                             │
             ▼                             ▼
┌───────────────────────┐   ┌─────────────────────────────┐
│ Step 3a: 加载长期记忆  │   │ Step 3b: 跳过长期记忆        │
│                       │   │                             │
│ 执行：                │   │ 原因：                       │
│  read(MEMORY.md)      │   │  "Group chats, Discord, or  │
│                       │   │   shared contexts"           │
│ 加载内容：            │   │                             │
│  • 用户偏好           │   │ 安全隔离：                   │
│  • 重要决策           │   │  "Contains personal context  │
│  • 持久关系           │   │   that shouldn't leak to     │
│  • 学习经验           │   │   strangers"                 │
└───────────┬───────────┘   └──────────────┬──────────────┘
            │                               │
            └───────────────┬───────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 4: 加载短期记忆                                                 │
│                                                                     │
│ 执行代码：                                                           │
│   const today = format(new Date(), "yyyy-MM-dd");                  │
│   const yesterday = format(subDays(new Date(), 1), "yyyy-MM-dd");  │
│   read(`memory/${today}.md`);                                       │
│   read(`memory/${yesterday}.md`);                                  │
│                                                                     │
│ 加载内容：                                                           │
│   • 最近2天的交互记录                                                 │
│   • 临时事件和上下文                                                  │
│   • 待办事项                                                         │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 5: 自动记忆注入（如果启用 autoRecall）                           │
│                                                                     │
│ 生命周期钩子：                                                       │
│   api.on("before_agent_start", async (event) => {                  │
│     const vector = await embeddings.embed(event.prompt);           │
│     const results = await db.search(vector, 3, 0.3);              │
│                                                                     │
│     if (results.length > 0) {                                       │
│       return {                                                      │
│         prependContext: `<relevant-memories>                        │
│ The following memories may be relevant:                            │
│ ${formatResults(results)}                                           │
│ </relevant-memories>`                                               │
│       };                                                            │
│     }                                                               │
│   });                                                               │
│                                                                     │
│ 注入格式：                                                           │
│   <relevant-memories>                                               │
│   The following memories may be relevant to this conversation:      │
│   - [preference] User prefers dark mode                            │
│   - [decision] Decided to use PostgreSQL                           │
│   - [entity] Email: user@example.com                               │
│   </relevant-memories>                                             │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 6: 注入记忆搜索 Prompt                                          │
│                                                                     │
│ 原始 Prompt（注入到系统消息）：                                       │
│   "## Memory Recall                                                 │
│    Before answering anything about prior work, decisions, dates,   │
│    people, preferences, or todos: run memory_search on              │
│    MEMORY.md + memory/*.md; then use memory_get to pull only the    │
│    needed lines. If low confidence after search, say you checked.   │
│    Citations: include Source: <path#line> when it helps the user   │
│    verify memory snippets."                                         │
│                                                                     │
│ 工具调用：                                                           │
│   memory_search(query, maxResults, minScore)                       │
│   memory_get(path, from, lines)                                     │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 7: 处理用户请求                                                 │
│                                                                     │
│ Agent 现在具备：                                                     │
│   • SOUL.md - 身份和个性                                            │
│   • USER.md - 用户信息                                              │
│   • memory/YYYY-MM-DD.md - 近期交互                                 │
│   • MEMORY.md - 长期记忆（仅主会话）                                 │
│   • relevant-memories - 自动注入的相关记忆                           │
│   • memory_search/memory_get - 主动搜索能力                         │
│                                                                     │
│ 开始处理用户消息...                                                  │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 8: 会话结束 - 自动捕获（如果启用 autoCapture）                   │
│                                                                     │
│ 生命周期钩子：                                                       │
│   api.on("agent_end", async (event) => {                           │
│     // 提取消息文本                                                  │
│     const texts = extractTexts(event.messages);                     │
│                                                                     │
│     // 过滤可捕获内容                                                │
│     const toCapture = texts.filter(shouldCapture);                 │
│                                                                     │
│     // 存储记忆（每轮最多3条）                                        │
│     for (const text of toCapture.slice(0, 3)) {                     │
│       const category = detectCategory(text);                        │
│       const vector = await embeddings.embed(text);                  │
│                                                                     │
│       // 检查重复                                                    │
│       if (!isDuplicate(vector)) {                                   │
│         await db.store({ text, vector, importance: 0.7, category });│
│       }                                                             │
│     }                                                               │
│   });                                                               │
│                                                                     │
│ 捕获规则：                                                           │
│   • 包含 "remember", "prefer", "decided" 等关键词                    │
│   • 长度在 10-500 字符之间                                           │
│   • 不包含已注入的记忆标记                                           │
│   • 表情符号不超过3个                                                │
│   • 不重复（向量相似度 < 0.95）                                      │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 9: 心跳维护（定期任务）                                         │
│                                                                     │
│ 心跳 Prompt：                                                        │
│   "Read HEARTBEAT.md if it exists (workspace context).             │
│    Follow it strictly. Do not infer or repeat old tasks from       │
│    prior chats. If nothing needs attention, reply HEARTBEAT_OK."   │
│                                                                     │
│ 记忆维护任务：                                                       │
│   1. 审查最近的 memory/YYYY-MM-DD.md 文件                           │
│   2. 识别重要事件、教训或见解                                        │
│   3. 更新 MEMORY.md（提炼长期记忆）                                  │
│   4. 移除过期信息                                                    │
│                                                                     │
│ 维护频率：                                                           │
│   "Periodically (every few days), use a heartbeat to:             │
│    Read through recent memory/YYYY-MM-DD.md files                  │
│    Identify significant events, lessons, or insights               │
│    Update MEMORY.md with distilled learnings                       │
│    Remove outdated info from MEMORY.md"                             │
│                                                                     │
│ 维护哲学：                                                           │
│   "Think of it like a human reviewing their journal and           │
│    updating their mental model. Daily files are raw notes;         │
│    MEMORY.md is curated wisdom."                                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 十、关键代码路径

| 功能 | 文件路径 | 核心函数/组件 |
|------|----------|--------------|
| 记忆工具注册 | `/opt/openclaw/extensions/memory-core/index.ts` | `createMemorySearchTool`, `createMemoryGetTool` |
| 向量记忆存储 | `/opt/openclaw/extensions/memory-lancedb/index.ts` | `MemoryDB`, `Embeddings` |
| 自动捕获规则 | `/opt/openclaw/extensions/memory-lancedb/index.ts` | `shouldCapture()`, `detectCategory()` |
| 自动注入钩子 | `/opt/openclaw/extensions/memory-lancedb/index.ts` | `api.on("before_agent_start")` |
| 自动存储钩子 | `/opt/openclaw/extensions/memory-lancedb/index.ts` | `api.on("agent_end")` |
| 会话初始化规则 | `/opt/openclaw/workspace/AGENTS.md` | "Every Session" section |
| 记忆写入规则 | `/opt/openclaw/workspace/AGENTS.md` | "Write It Down" section |
| 心跳维护逻辑 | `/opt/openclaw/workspace/AGENTS.md` | "Memory Maintenance" section |
| 安全边界定义 | `/opt/openclaw/workspace/AGENTS.md` | "Group Chats" section |

---

## 十一、与 Agent_Arena 架构的对比

| 维度 | OpenClaw | Agent_Arena (设计) |
|------|----------|-------------------|
| 记忆存储 | 文件系统 + 向量数据库 | SQLite + 文件系统 |
| 会话隔离 | 主会话 vs 共享上下文 | 按 Agent ID 隔离 |
| 记忆类型 | 长期(MEMORY.md) + 短期(daily) | 长期 + 短期 + 群聊上下文 |
| 自动捕获 | 规则引擎 + 向量相似度 | 设计中（需实现） |
| 自动注入 | before_agent_start 钩子 | ContextBuilder 组装 |
| 记忆搜索 | 向量语义搜索 + 文件读取 | 文件读取（待增强） |
| 心跳维护 | 定期提炼短期→长期 | 设计中（需实现） |

---

**文档版本：** 1.0  
**生成时间：** 2026-02-26  
**来源：** OpenClaw 源码 + AGENTS.md 原始 Prompt  
**格式：** 参考 Agent_Arena README 4.2 节风格