import { useState, useEffect } from 'react';
import type { CallLog, TurnLogMeta, AgentProfile } from '../types';
import './LogPanel.css';

interface Props {
  groupId: string | null;
  agents: AgentProfile[];
  turnLogMap: Record<string, TurnLogMeta>;
}

export default function LogPanel({ groupId, agents, turnLogMap }: Props) {
  const [logs, setLogs] = useState<CallLog[]>([]);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!groupId) {
      setLogs([]);
      return;
    }
    loadLogs();
  }, [groupId]);

  // Refresh when new turn log arrives
  useEffect(() => {
    if (groupId && Object.keys(turnLogMap).length > 0) {
      loadLogs();
    }
  }, [turnLogMap]);

  const loadLogs = async () => {
    if (!groupId) return;
    try {
      setLoading(true);
      const res = await fetch(`/api/messages/logs/${groupId}`);
      const data = await res.json();
      setLogs(data.logs || []);
    } catch (err) {
      console.error('Failed to load logs:', err);
    } finally {
      setLoading(false);
    }
  };

  const toggleExpand = (logId: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(logId)) next.delete(logId);
      else next.add(logId);
      return next;
    });
  };

  const getAgentAvatar = (agentId: string) => {
    return agents.find(a => a.agent_id === agentId)?.avatar || '🤖';
  };

  const formatDuration = (ms: number) => {
    if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
    return `${ms}ms`;
  };

  const formatCost = (usd: number) => {
    if (usd === 0) return null;
    if (usd < 0.001) return `$${(usd * 1000).toFixed(2)}m`;
    return `$${usd.toFixed(4)}`;
  };

  const formatTime = (iso: string) => {
    return new Date(iso).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  if (!groupId) {
    return (
      <div className="log-panel empty">
        <div className="log-empty-state">选择群组后查看调用日志</div>
      </div>
    );
  }

  return (
    <div className="log-panel">
      <div className="log-panel-header">
        <span className="log-panel-title">📋 调用日志</span>
        <button className="log-refresh-btn" onClick={loadLogs} disabled={loading}>
          {loading ? '⟳' : '↻'}
        </button>
      </div>

      {logs.length === 0 && !loading && (
        <div className="log-empty-state">暂无调用记录</div>
      )}

      <div className="log-entries">
        {logs.map((log) => {
          const isExpanded = expandedIds.has(log.log_id);
          const cost = formatCost(log.cost_usd);
          return (
            <div key={log.log_id} className={`log-entry ${log.is_error ? 'error' : ''}`}>
              <div className="log-entry-header" onClick={() => toggleExpand(log.log_id)}>
                <div className="log-entry-title">
                  <span className="log-agent-avatar">{getAgentAvatar(log.agent_id)}</span>
                  <span className="log-agent-name">{log.agent_name}</span>
                  {log.model_name && <span className="log-model-name">{log.model_name}</span>}
                  <span className="log-time">{formatTime(log.timestamp)}</span>
                  {log.is_error && <span className="log-badge error">错误</span>}
                </div>
                <div className="log-entry-meta">
                  {log.duration_ms > 0 && (
                    <span className="log-badge duration">⏱ {formatDuration(log.duration_ms)}</span>
                  )}
                  {log.num_turns > 0 && (
                    <span className="log-badge turns">🔄 {log.num_turns}步</span>
                  )}
                  {log.input_tokens > 0 && (
                    <span className="log-badge tokens">🔢 {(log.input_tokens + log.output_tokens).toLocaleString()} tok</span>
                  )}
                  {cost && (
                    <span className="log-badge cost">💰 {cost}</span>
                  )}
                  <span className={`log-chevron ${isExpanded ? 'open' : ''}`}>▾</span>
                </div>
              </div>

              {isExpanded && (
                <div className="log-entry-detail">
                  {/* Tool Calls */}
                  {log.tool_calls.length > 0 && (
                    <div className="log-section">
                      <div className="log-section-title">🔧 工具调用 ({log.tool_calls.length})</div>
                      <div className="log-tool-calls">
                        {log.tool_calls.map((tc, i) => (
                          <div key={i} className="log-tool-call">
                            <div className="log-tool-name">
                              <code>{tc.name}</code>
                              {tc.input && Object.keys(tc.input).length > 0 && (
                                <span className="log-tool-input">
                                  ({Object.entries(tc.input).map(([k, v]) =>
                                    `${k}: ${JSON.stringify(v).slice(0, 50)}`
                                  ).join(', ')})
                                </span>
                              )}
                            </div>
                            {tc.output && (
                              <div className="log-tool-output">→ {tc.output}</div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Prompt Preview */}
                  {log.prompt_preview && (
                    <div className="log-section">
                      <div className="log-section-title">📤 发送的 Prompt</div>
                      <pre className="log-code-block">{log.prompt_preview}</pre>
                    </div>
                  )}

                  {/* Raw Output */}
                  {log.raw_output_preview && (
                    <div className="log-section">
                      <div className="log-section-title">
                        📥 原始 CLI 输出
                        <button 
                          className="log-copy-btn" 
                          onClick={(e) => {
                            e.stopPropagation();
                            navigator.clipboard.writeText(log.raw_output_preview);
                          }}
                        >
                          复制
                        </button>
                      </div>
                      <pre className="log-code-block">{log.raw_output_preview}</pre>
                    </div>
                  )}

                  {/* Parse Response Preview (Optional, keep it if you want to see the extracted content) */}
                  {log.content_preview && (
                    <div className="log-section">
                      <div className="log-section-title">📄 解析后的回复内容</div>
                      <pre className="log-code-block">{log.content_preview}</pre>
                    </div>
                  )}

                  {/* Token Details */}
                  <div className="log-section log-token-detail">
                    <span>输入: {log.input_tokens.toLocaleString()} tok</span>
                    <span>输出: {log.output_tokens.toLocaleString()} tok</span>
                    {log.cost_usd > 0 && <span>费用: ${log.cost_usd.toFixed(6)}</span>}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
