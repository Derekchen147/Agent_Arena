import { useRef, useEffect } from "react";
import type { StoredMessage, AgentProfile } from "@/types/api";
import "./ChatArea.css";

interface ChatAreaProps {
  groupName: string;
  messages: StoredMessage[];
  systemMessage: string | null;
  agents: AgentProfile[];
  connected: boolean;
  onSend: (content: string, mentions?: string[]) => void;
}

function formatTime(ts: string) {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function getAvatar(msg: StoredMessage, agents: AgentProfile[]): string {
  if (msg.author_type === "human") return "🧑";
  const agent = agents.find((a) => a.agent_id === msg.author_id);
  return agent?.avatar || "🤖";
}

export function ChatArea({
  groupName,
  messages,
  systemMessage,
  agents,
  connected,
  onSend,
}: ChatAreaProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, systemMessage]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const el = textareaRef.current;
    if (!el) return;
    const content = el.value.trim();
    if (!content) return;
    const mentions = (content.match(/@(\S+)/g) || []).map((m) => m.slice(1));
    const agentIds = agents.map((a) => a.agent_id);
    const resolved = mentions
      .filter((m) => m !== "all" && m !== "所有人")
      .map((m) => {
        if (m === "@all" || m === "all") return "@all";
        const byId = agentIds.find((id) => id === m);
        if (byId) return byId;
        const byName = agents.find((a) => a.name === m);
        return byName?.agent_id ?? m;
      });
    onSend(content, resolved.length ? resolved : undefined);
    el.value = "";
    el.style.height = "auto";
  };

  return (
    <section className="chat-area">
      <div className="chat-header">
        <span className="chat-header-title">{groupName || "选择群组"}</span>
        <span
          className={`ws-indicator ${connected ? "connected" : ""}`}
          title={connected ? "已连接" : "未连接"}
        />
      </div>

      <div className="messages">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`message ${msg.author_type === "human" ? "human" : msg.author_type}`}
          >
            <div className="message-meta">
              <span className="message-avatar">{getAvatar(msg, agents)}</span>
              <span>{msg.author_name || msg.author_id}</span>
              <span>{formatTime(msg.timestamp)}</span>
            </div>
            <div className="message-content">{msg.content}</div>
          </div>
        ))}
        {systemMessage ? (
          <div className="message system">{systemMessage}</div>
        ) : null}
        <div ref={messagesEndRef} />
      </div>

      <form className="input-area" onSubmit={handleSubmit}>
        <div className="input-row">
          <div className="input-wrap">
            <span className="mention-trigger">@</span>
            <textarea
              ref={textareaRef}
              className="input-field"
              placeholder="输入消息，使用 @agent_id 或 @名称 指定回复人..."
              rows={1}
              disabled={!groupName}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
              onInput={(e) => {
                const t = e.target as HTMLTextAreaElement;
                t.style.height = "auto";
                t.style.height = `${Math.min(t.scrollHeight, 160)}px`;
              }}
            />
          </div>
          <button type="submit" className="btn btn-primary" disabled={!groupName}>
            发送
          </button>
        </div>
      </form>
    </section>
  );
}
