# 配置可运行的 Agent CLI（含 Claude Code 与代理）

本文说明如何把**本地已启动的 Claude Code CLI** 接入 Agent Arena，完成真实的输入输出。

---

## 一、前置条件

1. **已安装 Claude Code CLI**，且 `claude` 在系统 PATH 中（在终端能直接执行 `claude --version`）。
2. **代理**：若你通过代理访问 Claude API，需要让「调用 CLI 的子进程」也走代理（见下文）。

---

## 二、代理配置（二选一）

调用 Claude Code CLI 时如需走代理，可用下面任一方式。

### 方式 A：启动服务前在终端设代理（推荐）

在**启动 Agent Arena 的同一个终端**里，先执行你的代理脚本，再启动服务。子进程会继承当前环境变量。

**PowerShell（与 `ipset.sh` 一致）：**

```powershell
$env:HTTP_PROXY="http://127.0.0.1:7897"
$env:HTTPS_PROXY="http://127.0.0.1:7897"
$env:ALL_PROXY="socks5://127.0.0.1:7897"
cd D:\projects\Agent_Arena
uvicorn src.main:app --reload
```

若你已有 `ipset.ps1`（或 `ipset.sh` 里是 PowerShell 命令），可先执行：

```powershell
.\ipset.ps1
uvicorn src.main:app --reload
```

### 方式 B：在 Agent 的 YAML 里写死代理

在 `agents/<agent_id>.yaml` 的 `cli_config` 下增加 `env`，例如：

```yaml
cli_config:
  cli_type: "claude"
  timeout: 300
  env:
    HTTP_PROXY: "http://127.0.0.1:7897"
    HTTPS_PROXY: "http://127.0.0.1:7897"
    ALL_PROXY: "socks5://127.0.0.1:7897"
```

端口 `7897` 请改成你本地代理实际端口（与 ipset 中一致）。  
这样即使用户没有在启动服务的 shell 里设代理，每次调用该 Agent 的 CLI 时也会自动带上这些环境变量。

---

## 三、工作目录与 CLAUDE.md

每个 Agent 的回复是在其 **workspace 目录**下执行 `claude -p "..." --output-format json` 完成的；Claude CLI 会读取该目录下的 **CLAUDE.md** 作为角色/上下文。

- **workspace 路径**：由 `agents/<agent_id>.yaml` 里的 `workspace_dir` 指定，例如 `workspaces/architect`。
- 若该目录不存在，需要先创建并写好 `CLAUDE.md`（或通过「接入 Agent」流程自动创建）。

**做法 1：已有 YAML、缺 workspace**

例如 `agents/architect.yaml` 已存在且 `workspace_dir: "workspaces/architect"`，则：

1. 创建目录：`workspaces/architect`。
2. 在该目录下创建 `CLAUDE.md`，内容可为该 Agent 的 `role_prompt`（与 YAML 里一致即可），例如：

   ```markdown
   你是一位资深软件架构师。你的职责是：
   1. 分析用户需求，拆解成具体的技术任务
   2. 设计系统架构和技术方案
   3. 评估技术选型和可行性
   回复要求：简洁、结构化、用列表和代码块。
   ```

**做法 2：通过 API 接入新 Agent（自动建 workspace + CLAUDE.md）**

调用 `POST /api/agents/onboard`，传入 `agent_id`、`name`、`role_prompt` 等；系统会创建 `workspaces/<agent_id>` 并写入 `CLAUDE.md`。之后只需在 YAML 中按需加上 `cli_config.env` 代理即可。

---

## 四、配置小结

| 项目 | 说明 |
|------|------|
| **CLI 命令** | 系统在 Agent 的 `workspace_dir` 下执行 `claude -p "..." --output-format json`，无需你手动起 CLI 进程。 |
| **代理** | 方式 A：启动 uvicorn 前在同一终端执行 ipset（或设 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY）；方式 B：在 `agents/xxx.yaml` 的 `cli_config.env` 里配置。 |
| **workspace** | 每个 Agent 对应 `workspaces/<agent_id>`，且目录内需有 `CLAUDE.md`。 |
| **端口** | 代理端口与 ipset 中一致（如 7897）。 |

---

## 五、验证

1. 启动服务（若用方式 A，先执行 ipset 再启动）：
   ```powershell
   .\ipset.ps1
   uvicorn src.main:app --reload
   ```
2. 创建群组并把对应 Agent 加入成员。
3. 在群组里发一条消息并 @ 该 Agent（如 @架构师）。
4. 若配置正确，该 Agent 会通过 Claude Code CLI 生成回复并出现在对话中；若报错 `claude 命令未找到` 或超时，请检查 PATH 与代理。

---

**说明**：你本地「正在运行的 Claude Code CLI」一般是交互式会话；Agent Arena 是**按需在后台用 subprocess 执行** `claude -p "..."`，两者可并存。只要 `claude` 在 PATH 且代理正确，即可完成接入。
