import { useState } from 'react';
import type { AgentProfile, Group, AgentStatus } from '../types';
import type { AgentStatusMap } from '../hooks/useWebSocket';
import { addMember, removeMember, onboardAgent, deleteAgent } from '../api/client';
import ConfirmModal from './ConfirmModal';
import './AgentPanel.css';

interface Props {
  agents: AgentProfile[];
  group: Group | null;
  agentStatuses: AgentStatusMap;
  messageCounts?: Record<string, number>;
  onGroupChanged: () => void;
  onAgentsChanged: () => void;
  onViewAgents?: () => void;
}

const STATUS_CONFIG: Record<AgentStatus, { label: string; color: string; icon: string }> = {
  idle: { label: '空闲', color: '#666', icon: '○' },
  analyzing: { label: '分析中', color: '#3498db', icon: '◉' },
  reading_memory: { label: '读取记忆', color: '#9b59b6', icon: '📖' },
  calling_tool: { label: '调用工具', color: '#e67e22', icon: '⚙️' },
  generating: { label: '生成中', color: '#2ecc71', icon: '✍️' },
  reviewing: { label: '审查中', color: '#1abc9c', icon: '🔍' },
  waiting: { label: '等待中', color: '#f39c12', icon: '⏳' },
  done: { label: '完成', color: '#27ae60', icon: '✓' },
  error: { label: '出错', color: '#e74c3c', icon: '✗' },
  timeout: { label: '超时', color: '#f1c40f', icon: '⚠' },
};

export default function AgentPanel({
  agents,
  group,
  agentStatuses,
  messageCounts = {},
  onGroupChanged,
  onAgentsChanged,
  onViewAgents,
}: Props) {
  const [showOnboard, setShowOnboard] = useState(false);
  const [form, setForm] = useState({
    agent_id: '',
    name: '',
    avatar: '',
    role_prompt: '',
    skills: '',
    cli_type: 'claude',
  });
  const [onboarding, setOnboarding] = useState(false);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);

  const groupAgentIds = new Set(
    group?.members.filter((m) => m.type === 'agent').map((m) => m.agent_id) ?? [],
  );

  const groupAgents = agents.filter((a) => groupAgentIds.has(a.agent_id));
  const availableAgents = agents.filter((a) => !groupAgentIds.has(a.agent_id));

  // 找出在这个群里发过言的人类或未知发送者
  const humanStats = Object.entries(messageCounts)
    .filter(([id]) => id === 'human' || !agents.some(a => a.agent_id === id))
    .map(([id, count]) => ({ id, count }));

  const getStatus = (agentId: string) => {
    return agentStatuses[agentId]?.status ?? 'idle';
  };

  const getStatusDetail = (agentId: string) => {
    return agentStatuses[agentId]?.detail ?? '';
  };

  const handleAddToGroup = async (agentId: string) => {
    if (!group) return;
    const agent = agents.find((a) => a.agent_id === agentId);
    try {
      await addMember(group.id, {
        agent_id: agentId,
        display_name: agent?.name,
      });
      onGroupChanged();
    } catch (err) {
      alert(`添加失败: ${err}`);
    }
  };

  const handleRemoveFromGroup = async (agentId: string) => {
    if (!group) return;
    const member = group.members.find((m) => m.agent_id === agentId);
    if (!member) return;
    try {
      await removeMember(group.id, member.id);
      onGroupChanged();
    } catch (err) {
      alert(`移除失败: ${err}`);
    }
  };

  const handleOnboard = async () => {
    if (!form.agent_id.trim() || !form.name.trim()) return;
    setOnboarding(true);
    try {
      await onboardAgent({
        agent_id: form.agent_id.trim(),
        name: form.name.trim(),
        avatar: form.avatar.trim() || undefined,
        role_prompt: form.role_prompt.trim() || undefined,
        skills: form.skills
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        cli_type: form.cli_type,
      });
      setForm({ agent_id: '', name: '', avatar: '', role_prompt: '', skills: '', cli_type: 'claude' });
      setShowOnboard(false);
      onAgentsChanged();
    } catch (err) {
      alert(`创建失败: ${err}`);
    } finally {
      setOnboarding(false);
    }
  };

  const handleDeleteAgent = async () => {
    if (!deleteTargetId) return;
    const agentId = deleteTargetId;
    setDeleteTargetId(null);
    try {
      await deleteAgent(agentId);
      onAgentsChanged();
    } catch (err) {
      alert(`删除失败: ${err}`);
    }
  };

  return (
    <div className="agent-panel">
      <div className="panel-header">
        <h3>员工</h3>
        <div style={{ display: 'flex', gap: '4px' }}>
          {onViewAgents && (
            <button className="btn-icon" onClick={onViewAgents} title="管理员工">
              &#9881;
            </button>
          )}
          <button className="btn-icon" onClick={() => setShowOnboard(true)} title="新增员工">
            +
          </button>
        </div>
      </div>

      {group && (
        <>
          <div className="panel-section">
            <div className="section-title">群组成员</div>
            {groupAgents.length === 0 && humanStats.length === 0 && (
              <div className="empty-hint">暂无成员，添加员工到群组</div>
            )}
            
            {/* 1. Agent 成员 */}
            {groupAgents.map((agent) => {
              const status = getStatus(agent.agent_id);
              const cfg = STATUS_CONFIG[status];
              const detail = getStatusDetail(agent.agent_id);
              const count = messageCounts[agent.agent_id] || 0;
              return (
                <div key={agent.agent_id} className="agent-card">
                  <div className="agent-avatar">{agent.avatar || '🤖'}</div>
                  <div className="agent-info">
                    <div className="agent-name-row" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <div className="agent-name">{agent.name}</div>
                      {count > 0 && <span className="message-count-badge" title="累计发言数">{count}</span>}
                    </div>
                    <div className="agent-status" style={{ color: cfg.color }}>
                      <span className={`status-indicator ${status !== 'idle' ? 'active' : ''}`} style={{ color: cfg.color }}>
                        {cfg.icon}
                      </span>
                      {cfg.label}
                      {detail && <span className="status-detail">{detail}</span>}
                    </div>
                    {agent.skills.length > 0 && (
                      <div className="agent-skills">
                        {agent.skills.slice(0, 3).map((s) => (
                          <span key={s} className="skill-tag">{s}</span>
                        ))}
                      </div>
                    )}
                  </div>
                  <button
                    className="btn-small btn-remove"
                    onClick={() => handleRemoveFromGroup(agent.agent_id)}
                    title="从群组移除"
                  >
                    −
                  </button>
                </div>
              );
            })}

            {/* 2. 人类用户 */}
            {humanStats.map((h) => (
              <div key={h.id} className="agent-card human-member">
                <div className="agent-avatar">🧑</div>
                <div className="agent-info">
                  <div className="agent-name-row" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <div className="agent-name">{h.id === 'human' ? '用户' : h.id}</div>
                    <span className="message-count-badge" title="累计发言数">{h.count}</span>
                  </div>
                  <div className="agent-status">在线</div>
                </div>
              </div>
            ))}
          </div>

          {availableAgents.length > 0 && (
            <div className="panel-section">
              <div className="section-title">可添加</div>
              {availableAgents.map((agent) => (
                <div key={agent.agent_id} className="agent-card available">
                  <div className="agent-avatar">{agent.avatar || '🤖'}</div>
                  <div className="agent-info">
                    <div className="agent-name">{agent.name}</div>
                    <div className="agent-id">{agent.agent_id}</div>
                  </div>
                  <button
                    className="btn-small btn-add"
                    onClick={() => handleAddToGroup(agent.agent_id)}
                    title="添加到群组"
                  >
                    +
                  </button>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {!group && (
        <div className="panel-section">
          <div className="section-title">全部员工</div>
          {agents.map((agent) => (
            <div key={agent.agent_id} className="agent-card">
              <div className="agent-avatar">{agent.avatar || '🤖'}</div>
              <div className="agent-info">
                <div className="agent-name">{agent.name}</div>
                <div className="agent-id">{agent.agent_id}</div>
                {agent.skills.length > 0 && (
                  <div className="agent-skills">
                    {agent.skills.slice(0, 3).map((s) => (
                      <span key={s} className="skill-tag">{s}</span>
                    ))}
                  </div>
                )}
              </div>
              <button
                className="btn-small btn-remove"
                onClick={() => setDeleteTargetId(agent.agent_id)}
                title="删除员工"
              >
                &times;
              </button>
            </div>
          ))}
          {agents.length === 0 && (
            <div className="empty-hint">暂无员工</div>
          )}
        </div>
      )}

      {showOnboard && (
        <div className="modal-overlay" onClick={() => setShowOnboard(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>新增员工</h3>
            <input
              placeholder="员工 ID（英文）"
              value={form.agent_id}
              onChange={(e) => setForm({ ...form, agent_id: e.target.value })}
              autoFocus
            />
            <input
              placeholder="员工名称"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <input
              placeholder="头像 emoji（可选）"
              value={form.avatar}
              onChange={(e) => setForm({ ...form, avatar: e.target.value })}
            />
            <textarea
              placeholder="角色描述 / System Prompt（可选）"
              value={form.role_prompt}
              onChange={(e) => setForm({ ...form, role_prompt: e.target.value })}
              rows={3}
              className="modal-textarea"
            />
            <input
              placeholder="技能标签（逗号分隔，可选）"
              value={form.skills}
              onChange={(e) => setForm({ ...form, skills: e.target.value })}
            />
            <select
              value={form.cli_type}
              onChange={(e) => setForm({ ...form, cli_type: e.target.value })}
              className="modal-select"
            >
              <option value="claude">Claude CLI</option>
              <option value="cursor">Cursor CLI</option>
              <option value="generic">Generic CLI</option>
            </select>
            <div className="modal-actions">
              <button onClick={() => setShowOnboard(false)}>取消</button>
              <button className="btn-primary" onClick={handleOnboard} disabled={onboarding}>
                {onboarding ? '创建中...' : '创建'}
              </button>
            </div>
          </div>
        </div>
      )}
      {deleteTargetId && (
        <ConfirmModal
          title="删除员工"
          message={`确定要删除「${agents.find(a => a.agent_id === deleteTargetId)?.name || deleteTargetId}」？工作区将移入回收站，可手动恢复。`}
          confirmLabel="确认删除"
          onConfirm={handleDeleteAgent}
          onCancel={() => setDeleteTargetId(null)}
        />
      )}
    </div>
  );
}
