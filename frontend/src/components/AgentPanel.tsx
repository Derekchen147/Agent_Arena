import type { AgentProfile } from "@/types/api";
import type { AgentStatus } from "@/types/api";
import "./AgentPanel.css";

interface AgentPanelProps {
  agents: AgentProfile[];
  statuses: Record<string, AgentStatus>;
  /** Agent IDs that are members of the current group (to highlight) */
  memberIds?: string[];
}

const STATUS_LABELS: Record<AgentStatus, string> = {
  idle: "空闲",
  analyzing: "分析中",
  reading_memory: "读记忆中",
  calling_tool: "调用工具",
  generating: "生成中",
  reviewing: "审查中",
  waiting: "等待中",
  done: "完成",
  error: "错误",
  timeout: "超时",
};

export function AgentPanel({ agents, statuses, memberIds = [] }: AgentPanelProps) {
  return (
    <aside className="panel">
      <div className="panel-header">员工状态</div>
      <div className="panel-list">
        {agents.length === 0 ? (
          <div className="empty-state">暂无已注册员工</div>
        ) : (
          agents.map((agent) => {
            const status = statuses[agent.agent_id] ?? "idle";
            const inGroup = memberIds.includes(agent.agent_id);
            return (
              <div
                key={agent.agent_id}
                className={`agent-card ${inGroup ? "in-group" : ""}`}
              >
                <div className="agent-card-header">
                  <span className="agent-avatar">{agent.avatar || "🤖"}</span>
                  <span className="agent-name">{agent.name || agent.agent_id}</span>
                  <span className={`agent-status-badge ${status}`}>
                    {STATUS_LABELS[status]}
                  </span>
                </div>
                {agent.skills?.length > 0 ? (
                  <div className="agent-skills">
                    {agent.skills.slice(0, 3).join(" · ")}
                  </div>
                ) : null}
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
