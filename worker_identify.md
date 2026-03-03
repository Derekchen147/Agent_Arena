# Worker Identification & Persona (OpenClaw System)

## 一、 核心设计理念

放弃传统的中心化配置（`agents/*.yaml`），转而采用 **“工作区即员工” (Workspace as Worker)** 的去中心化架构。每个数字员工都被视为一个独立的实体，其身份、个性、规则和记忆完全存储在自己的工作区（`workspaces/{agent_id}/`）中。

这种设计参考了 OpenClaw 的 “Soul” 理念，使员工具有：
1. **持久性**：身份和记忆随文件系统持久化。
2. **自检性**：员工在每次启动时通过阅读自己的 `SOUL.md` 和 `AGENTS.md` 重新加载人格。
3. **可移植性**：移动工作区文件夹即移动了整个员工实体。

---

## 二、 目录与文件结构

每个有效的数字员工工作区必须遵循以下文件布局：

```text
workspaces/{agent_id}/
├── agent.yaml              # [核心] 元数据：ID、名称、技能、CLI 驱动配置
├── SOUL.md                 # [人设] 灵魂：定义员工的性格、价值观、沟通风格
├── AGENTS.md               # [规则] 指令：定义运行规则、协作格式、记忆管理
├── USER.md                 # [上下文] 用户：记录用户的偏好、禁忌和特定背景
├── MEMORY.md               # [长期记忆] 蒸馏后的关键决策、事实和经验教训
└── memory/                 # [短期记忆] 按日期记录的原始交互日志
    └── 2026-03-03.md
```

### 关键文件详解：
- **`agent.yaml`**: 存储 `name`, `cli_config` (如 `claude` 或 `cursor`), `skills` 等元数据参数。
- **`SOUL.md`**: 员工的“核心程序”。包含行为准则（如“Be genuinely helpful”）、语气偏好和身份边界。
- **`AGENTS.md`**: 操作指南。包含 OpenClaw 标准的 `Every Session` 加载指令，以及协作协议。

---

## 三、 加载与识别流程

### 1. 注册与初始化 (`AgentRegistry`)
系统启动时，`AgentRegistry` 执行以下逻辑：
- 遍历 `workspaces/` 下所有一级目录。
- 只有包含 `agent.yaml` 的目录才会被识别为有效员工。
- 通过 `AgentProfile.from_workspace()` 静态方法进行加载：
    - 从 `agent.yaml` 读取元数据。
    - 从 `SOUL.md` 实时读取内容并映射为 `role_prompt`。

### 2. 会话引导 (The Loader)
系统通过 Adapter 在每次请求的 Prompt 头部注入 **OpenClaw Loading Instruction**：
> **"Before doing anything else: Read SOUL.md, AGENTS.md, USER.md and memory/*.md..."**

这种方式将“系统提示词”的职责从代码层转移到了文件层。

---

## 四、 适配器 (Adapters) 的演进

为了减少定制化干扰，Adapter 的职责被大幅简化：
- **旧逻辑**: 在代码中拼接复杂的 System Prompt（如群成员列表、回复规则等）。
- **新逻辑**: 
    1. 仅提供动态上下文：当前会话成员、历史消息、当前消息、语义检索片段。
    2. 指令引导：明确告知 Agent 结合工作区下的 `SOUL.md` 和 `AGENTS.md` 进行思考。
    3. 解析输出：识别 `SKIP` 信号和 `NEXT_MENTIONS` 协作格式。

---

## 五、 数据维护

### 1. 自动迁移
通过迁移逻辑，将原有的 YAML 拆解并分发到各工作区目录中。

### 2. 在线更新
通过 API 更新员工信息时：
- 修改元数据会重写 `agent.yaml`。
- 修改 `role_prompt` 会直接重写 `SOUL.md`。
- 修改 `cli_type` 会自动清理并重写引导文件（如 `CLAUDE.md`）。

---

## 六、 总结

这套逻辑将数字员工从“配置对象”提升为了“拥有独立空间的生命体”。它利用了现代 AI CLI 自动读取工作区文档的能力，实现了更自然的人格化管理。
