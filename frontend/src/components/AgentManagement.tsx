import { useState, useEffect, useCallback } from 'react';
import type { AgentProfile, UpdateAgentRequest, SkillDefinition, McpServerConfig, McpReadiness } from '../types';
import ConfirmModal from './ConfirmModal';
import {
  updateAgent,
  onboardAgent,
  deleteAgent,
  getOpenClawFile,
  updateOpenClawFile,
  getAgentMcp,
  updateAgentMcpEnv,
  createSkill,
  deleteSkill,
  addMcpServer,
  deleteMcpServer,
} from '../api/client';
import './AgentManagement.css';

interface Props {
  agents: AgentProfile[];
  onAgentsChanged: () => void;
  onBack: () => void;
}

interface FormState {
  agent_id: string;
  name: string;
  avatar: string;
  skills: string;
  cli_type: string;
  command: string;
  timeout: number;
  extra_args: string;
  env: string;
  auto_respond: boolean;
  response_threshold: number;
  priority_keywords: string;
  max_output_tokens: number;
}

const EMPTY_FORM: FormState = {
  agent_id: '',
  name: '',
  avatar: '',
  skills: '',
  cli_type: 'claude',
  command: '',
  timeout: 300,
  extra_args: '',
  env: '',
  auto_respond: true,
  response_threshold: 0.6,
  priority_keywords: '',
  max_output_tokens: 2000,
};

function profileToForm(p: AgentProfile): FormState {
  return {
    agent_id: p.agent_id,
    name: p.name,
    avatar: p.avatar,
    skills: p.skills.join(', '),
    cli_type: p.cli_config.cli_type,
    command: p.cli_config.command,
    timeout: p.cli_config.timeout,
    extra_args: p.cli_config.extra_args.join(', '),
    env: Object.entries(p.cli_config.env || {})
      .map(([k, v]) => `${k}=${v}`)
      .join('\n'),
    auto_respond: p.response_config.auto_respond,
    response_threshold: p.response_config.response_threshold,
    priority_keywords: p.response_config.priority_keywords.join(', '),
    max_output_tokens: p.max_output_tokens,
  };
}

function formToUpdateRequest(f: FormState): UpdateAgentRequest {
  const envObj: Record<string, string> = {};
  if (f.env.trim()) {
    for (const line of f.env.split('\n')) {
      const idx = line.indexOf('=');
      if (idx > 0) {
        envObj[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
      }
    }
  }
  return {
    name: f.name,
    avatar: f.avatar,
    role_prompt: '', // Now handled by SOUL.md
    skills: f.skills.split(',').map((s) => s.trim()).filter(Boolean),
    cli_type: f.cli_type,
    command: f.command,
    timeout: f.timeout,
    extra_args: f.extra_args.split(',').map((s) => s.trim()).filter(Boolean),
    env: envObj,
    auto_respond: f.auto_respond,
    response_threshold: f.response_threshold,
    priority_keywords: f.priority_keywords.split(',').map((s) => s.trim()).filter(Boolean),
    max_output_tokens: f.max_output_tokens,
  };
}

export default function AgentManagement({ agents, onAgentsChanged, onBack }: Props) {
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [mode, setMode] = useState<'edit' | 'create'>('edit');
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  
  // OpenClaw MD Files
  const [soulContent, setSoulContent] = useState('');
  const [agentsContent, setAgentsContent] = useState('');
  const [userContent, setUserContent] = useState('');
  
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Skills & MCP state
  const [mcpServers, setMcpServers] = useState<McpServerConfig[]>([]);
  const [mcpReadiness, setMcpReadiness] = useState<McpReadiness[]>([]);
  const [editingMcpEnv, setEditingMcpEnv] = useState<{ serverId: string; env: Record<string, string> } | null>(null);

  // Add skill / MCP modal state
  const [showAddSkill, setShowAddSkill] = useState(false);
  const [newSkill, setNewSkill] = useState({ skill_id: '', name: '', description: '', body: '' });
  const [showAddMcp, setShowAddMcp] = useState(false);
  const [newMcp, setNewMcp] = useState({ server_id: '', server_type: 'external', command: '', args: '', required_env: '', capability: '' });
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Load agent details
  const loadAgent = useCallback(
    async (agentId: string) => {
      const agent = agents.find((a) => a.agent_id === agentId);
      if (!agent) return;
      setForm(profileToForm(agent));
      
      // Parallel load OpenClaw files
      try {
        const [soul, agts, user] = await Promise.all([
          getOpenClawFile(agentId, 'SOUL.md').catch(() => ({ content: '' })),
          getOpenClawFile(agentId, 'AGENTS.md').catch(() => ({ content: '' })),
          getOpenClawFile(agentId, 'USER.md').catch(() => ({ content: '' })),
        ]);
        setSoulContent(soul.content);
        setAgentsContent(agts.content);
        setUserContent(user.content);
      } catch (err) {
        console.error('Failed to load OpenClaw files', err);
      }

      // Load MCP data
      try {
        const mcpData = await getAgentMcp(agentId);
        setMcpServers(mcpData.servers);
        setMcpReadiness(mcpData.readiness);
      } catch {
        setMcpServers([]);
        setMcpReadiness([]);
      }
      setEditingMcpEnv(null);
    },
    [agents],
  );

  useEffect(() => {
    if (selectedAgentId && mode === 'edit') {
      loadAgent(selectedAgentId);
    }
  }, [selectedAgentId, mode, loadAgent]);

  const handleSelectAgent = (agentId: string) => {
    setSelectedAgentId(agentId);
    setMode('edit');
    setStatusMsg(null);
  };

  const handleNewAgent = () => {
    setSelectedAgentId(null);
    setMode('create');
    setForm(EMPTY_FORM);
    setSoulContent('');
    setAgentsContent('');
    setUserContent('');
    setStatusMsg(null);
    setMcpServers([]);
    setMcpReadiness([]);
    setEditingMcpEnv(null);
    setShowAddSkill(false);
    setShowAddMcp(false);
  };

  const updateField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    if (!form.name.trim()) {
      setStatusMsg({ type: 'error', text: '员工名称不能为空' });
      return;
    }

    setSaving(true);
    setStatusMsg(null);

    try {
      if (mode === 'create') {
        if (!form.agent_id.trim()) {
          setStatusMsg({ type: 'error', text: '员工 ID 不能为空' });
          setSaving(false);
          return;
        }
        await onboardAgent({
          agent_id: form.agent_id.trim(),
          name: form.name.trim(),
          avatar: form.avatar.trim() || undefined,
          role_prompt: soulContent.trim() || undefined, // New: use soulContent as role_prompt
          skills: form.skills.split(',').map((s) => s.trim()).filter(Boolean),
          cli_type: form.cli_type,
          priority_keywords: form.priority_keywords.split(',').map((s) => s.trim()).filter(Boolean),
        });
        
        // If created, the SOUL.md is already written by onboardAgent backend logic.
        // We might want to write AGENTS.md and USER.md if they have content.
        if (agentsContent.trim()) {
          await updateOpenClawFile(form.agent_id.trim(), 'AGENTS.md', agentsContent);
        }
        if (userContent.trim()) {
          await updateOpenClawFile(form.agent_id.trim(), 'USER.md', userContent);
        }

        onAgentsChanged();
        setSelectedAgentId(form.agent_id.trim());
        setMode('edit');
        setStatusMsg({ type: 'success', text: '员工创建成功' });
      } else {
        if (!selectedAgentId) return;
        
        // 1. Update YAML metadata
        const req = formToUpdateRequest(form);
        await updateAgent(selectedAgentId, req);

        // 2. Update OpenClaw MD files
        await Promise.all([
          updateOpenClawFile(selectedAgentId, 'SOUL.md', soulContent),
          updateOpenClawFile(selectedAgentId, 'AGENTS.md', agentsContent),
          updateOpenClawFile(selectedAgentId, 'USER.md', userContent),
        ]);

        onAgentsChanged();
        setStatusMsg({ type: 'success', text: '保存成功' });
      }
    } catch (err) {
      setStatusMsg({ type: 'error', text: `保存失败: ${err}` });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedAgentId) return;
    setShowDeleteConfirm(false);
    try {
      await deleteAgent(selectedAgentId);
      onAgentsChanged();
      setSelectedAgentId(null);
      setMode('edit');
      setForm(EMPTY_FORM);
      setStatusMsg({ type: 'success', text: '已移入回收站' });
    } catch (err) {
      setStatusMsg({ type: 'error', text: `删除失败: ${err}` });
    }
  };

  const handleSaveMcpEnv = async () => {
    if (!selectedAgentId || !editingMcpEnv) return;
    try {
      await updateAgentMcpEnv(selectedAgentId, editingMcpEnv.serverId, editingMcpEnv.env);
      const mcpData = await getAgentMcp(selectedAgentId);
      setMcpServers(mcpData.servers);
      setMcpReadiness(mcpData.readiness);
      setEditingMcpEnv(null);
      setStatusMsg({ type: 'success', text: 'MCP 环境变量已保存' });
    } catch (err) {
      setStatusMsg({ type: 'error', text: `MCP 保存失败: ${err}` });
    }
  };

  const refreshAgentData = async () => {
    if (!selectedAgentId) return;
    onAgentsChanged();
    try {
      const mcpData = await getAgentMcp(selectedAgentId);
      setMcpServers(mcpData.servers);
      setMcpReadiness(mcpData.readiness);
    } catch { /* ignore */ }
  };

  const handleCreateSkill = async () => {
    if (!selectedAgentId) return;
    if (!newSkill.skill_id.trim() || !newSkill.name.trim()) {
      setStatusMsg({ type: 'error', text: 'Skill ID 和名称不能为空' });
      return;
    }
    try {
      await createSkill(selectedAgentId, {
        skill_id: newSkill.skill_id.trim(),
        name: newSkill.name.trim(),
        description: newSkill.description.trim(),
        body: newSkill.body.trim() || undefined,
      });
      setShowAddSkill(false);
      setNewSkill({ skill_id: '', name: '', description: '', body: '' });
      setStatusMsg({ type: 'success', text: '技能已创建' });
      await refreshAgentData();
    } catch (err) {
      setStatusMsg({ type: 'error', text: `创建技能失败: ${err}` });
    }
  };

  const handleDeleteSkill = async (skillId: string) => {
    if (!selectedAgentId) return;
    if (!confirm(`确定删除技能「${skillId}」？`)) return;
    try {
      await deleteSkill(selectedAgentId, skillId);
      setStatusMsg({ type: 'success', text: '技能已删除' });
      await refreshAgentData();
    } catch (err) {
      setStatusMsg({ type: 'error', text: `删除技能失败: ${err}` });
    }
  };

  const handleAddMcp = async () => {
    if (!selectedAgentId) return;
    if (!newMcp.server_id.trim() || !newMcp.command.trim()) {
      setStatusMsg({ type: 'error', text: 'Server ID 和命令不能为空' });
      return;
    }
    try {
      await addMcpServer(selectedAgentId, {
        server_id: newMcp.server_id.trim(),
        server_type: newMcp.server_type || 'external',
        command: newMcp.command.trim(),
        args: newMcp.args.trim() ? newMcp.args.split(',').map(s => s.trim()).filter(Boolean) : undefined,
        required_env: newMcp.required_env.trim() ? newMcp.required_env.split(',').map(s => s.trim()).filter(Boolean) : undefined,
        capability: newMcp.capability.trim() || undefined,
      });
      setShowAddMcp(false);
      setNewMcp({ server_id: '', server_type: 'external', command: '', args: '', required_env: '', capability: '' });
      setStatusMsg({ type: 'success', text: 'MCP 服务已添加' });
      await refreshAgentData();
    } catch (err) {
      setStatusMsg({ type: 'error', text: `添加 MCP 失败: ${err}` });
    }
  };

  const handleDeleteMcp = async (serverId: string) => {
    if (!selectedAgentId) return;
    if (!confirm(`确定删除 MCP 服务「${serverId}」？`)) return;
    try {
      await deleteMcpServer(selectedAgentId, serverId);
      setStatusMsg({ type: 'success', text: 'MCP 服务已删除' });
      await refreshAgentData();
    } catch (err) {
      setStatusMsg({ type: 'error', text: `删除 MCP 失败: ${err}` });
    }
  };

  const selectedAgent = agents.find((a) => a.agent_id === selectedAgentId);
  const showEditor = mode === 'create' || selectedAgentId;

  return (
    <div className="agent-management">
      {/* Left: Agent List */}
      <div className="am-sidebar">
        <div className="am-sidebar-header">
          <button className="am-back-btn" onClick={onBack}>
            &larr; 返回
          </button>
          <h3>员工管理</h3>
        </div>
        <div className="am-agent-list">
          {agents.map((agent) => (
            <div
              key={agent.agent_id}
              className={`am-agent-item ${selectedAgentId === agent.agent_id && mode === 'edit' ? 'active' : ''}`}
              onClick={() => handleSelectAgent(agent.agent_id)}
            >
              <div className="am-avatar">{agent.avatar || '🤖'}</div>
              <div className="am-item-info">
                <div className="am-item-name">{agent.name}</div>
                <div className="am-item-id">{agent.agent_id}</div>
              </div>
              <span className="am-item-cli">{agent.cli_config.cli_type}</span>
            </div>
          ))}
        </div>
        <button className="am-new-btn" onClick={handleNewAgent}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ marginRight: '6px' }}>
            <path d="M12 5V19M5 12H19" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          新建员工
        </button>
      </div>

      {showDeleteConfirm && (
        <ConfirmModal
          title="移入回收站"
          message={`确定要将「${form.name || selectedAgentId}」移入回收站？工作目录将被保留，可从 workspaces/trash 恢复。`}
          confirmLabel="移入回收站"
          cancelLabel="取消"
          onConfirm={handleDelete}
          onCancel={() => setShowDeleteConfirm(false)}
        />
      )}

      {/* Right: Edit Form */}
      {!showEditor ? (
        <div className="am-empty">选择一个员工查看详情，或点击「新建员工」</div>
      ) : (
        <div className="am-edit-area">
          <div className="am-edit-header">
            <h2 className="am-edit-title">
              {mode === 'create' ? '新建员工' : `${form.avatar || '🤖'} ${form.name || selectedAgentId}`}
            </h2>
            <div className="am-edit-actions">
              {mode === 'edit' && (
                <button className="am-btn am-btn-danger" onClick={() => setShowDeleteConfirm(true)}>
                  删除
                </button>
              )}
              <button className="am-btn am-btn-primary" onClick={handleSave} disabled={saving}>
                {saving ? '保存中...' : mode === 'create' ? '创建' : '保存'}
              </button>
            </div>
          </div>

          {statusMsg && (
            <div className={`am-status-bar ${statusMsg.type}`}>{statusMsg.text}</div>
          )}

          {/* Basic Info */}
          <div className="am-section">
            <div className="am-section-title">基本信息</div>
            <div className="am-form-row-inline">
              <div className="am-form-row">
                <label className="am-form-label">员工 ID</label>
                <input
                  className="am-form-input"
                  value={form.agent_id}
                  onChange={(e) => updateField('agent_id', e.target.value)}
                  readOnly={mode === 'edit'}
                  placeholder="英文标识，如 architect"
                />
              </div>
              <div className="am-form-row">
                <label className="am-form-label">头像</label>
                <input
                  className="am-form-input"
                  value={form.avatar}
                  onChange={(e) => updateField('avatar', e.target.value)}
                  placeholder="Emoji"
                />
              </div>
            </div>
            <div className="am-form-row">
              <label className="am-form-label">名称</label>
              <input
                className="am-form-input"
                value={form.name}
                onChange={(e) => updateField('name', e.target.value)}
                placeholder="员工显示名称"
              />
            </div>
            {mode === 'edit' && selectedAgent && (
              <div className="am-form-row">
                <label className="am-form-label">工作目录</label>
                <input
                  className="am-form-input"
                  value={selectedAgent.workspace_dir}
                  readOnly
                />
              </div>
            )}
          </div>

          {/* Persona (The Soul) */}
          <div className="am-section">
            <div className="am-section-title">灵魂定义 (SOUL.md)</div>
            <div className="am-form-row">
              <textarea
                className="am-workspace-editor"
                style={{ background: '#f9f9f9', color: '#1d1d1f', border: '1px solid #d2d2d7' }}
                value={soulContent}
                onChange={(e) => setSoulContent(e.target.value)}
                placeholder="我是谁？我的性格和价值观..."
                rows={10}
              />
              <div className="am-form-hint">
                定义员工的角色定位、语气、行为准则。
              </div>
            </div>
          </div>

          {/* Rules & Guidelines (The Agents) */}
          <div className="am-section">
            <div className="am-section-title">运行准则 (AGENTS.md)</div>
            <div className="am-form-row">
              <textarea
                className="am-workspace-editor"
                style={{ background: '#f9f9f9', color: '#1d1d1f', border: '1px solid #d2d2d7' }}
                value={agentsContent}
                onChange={(e) => setAgentsContent(e.target.value)}
                placeholder="如何加载记忆？如何协作？"
                rows={8}
              />
              <div className="am-form-hint">
                定义记忆加载流程、协作格式（如 NEXT_MENTIONS）。
              </div>
            </div>
          </div>

          {/* User Context (The User) */}
          <div className="am-section">
            <div className="am-section-title">用户偏好 (USER.md)</div>
            <div className="am-form-row">
              <textarea
                className="am-workspace-editor"
                style={{ background: '#f9f9f9', color: '#1d1d1f', border: '1px solid #d2d2d7' }}
                value={userContent}
                onChange={(e) => setUserContent(e.target.value)}
                placeholder="关于我的主人..."
                rows={5}
              />
              <div className="am-form-hint">
                记录关于用户的特定信息、偏好、习惯。
              </div>
            </div>
          </div>

          {/* Skills Tags */}
          <div className="am-section">
            <div className="am-section-title">技能标签</div>
            <div className="am-form-row">
              <input
                className="am-form-input"
                value={form.skills}
                onChange={(e) => updateField('skills', e.target.value)}
                placeholder="架构设计, 需求分析, 技术选型"
              />
              <div className="am-form-hint">
                用于自动编排时的匹配关键词（逗号分隔）。
              </div>
            </div>
          </div>

          {/* CLI Config */}
          <div className="am-section">
            <div className="am-section-title">驱动引擎 (CLI)</div>
            <div className="am-form-row-inline">
              <div className="am-form-row">
                <label className="am-form-label">CLI 类型</label>
                <select
                  className="am-form-select"
                  value={form.cli_type}
                  onChange={(e) => updateField('cli_type', e.target.value)}
                >
                  <option value="claude">Claude CLI</option>
                  <option value="gemini">Gemini CLI</option>
                  <option value="cursor">Cursor CLI</option>
                  <option value="generic">Generic CLI</option>
                </select>
              </div>
              <div className="am-form-row">
                <label className="am-form-label">超时（秒）</label>
                <input
                  className="am-form-input"
                  type="number"
                  value={form.timeout}
                  onChange={(e) => updateField('timeout', parseInt(e.target.value) || 300)}
                />
              </div>
            </div>
            {(form.cli_type === 'cursor' || form.cli_type === 'generic') && (
              <div className="am-form-row">
                <label className="am-form-label">命令路径</label>
                <input
                  className="am-form-input"
                  value={form.command}
                  onChange={(e) => updateField('command', e.target.value)}
                  placeholder={form.cli_type === 'cursor' ? 'agent（默认）' : '可执行文件路径'}
                />
              </div>
            )}
            <div className="am-form-row">
              <label className="am-form-label">环境变量</label>
              <textarea
                className="am-form-textarea"
                value={form.env}
                onChange={(e) => updateField('env', e.target.value)}
                placeholder={'HTTP_PROXY=...'}
                rows={2}
              />
            </div>
          </div>

          {/* Response Config */}
          <div className="am-section">
            <div className="am-section-title">响应配置</div>
            <div className="am-form-row">
              <div className="am-form-checkbox">
                <input
                  type="checkbox"
                  id="auto_respond"
                  checked={form.auto_respond}
                  onChange={(e) => updateField('auto_respond', e.target.checked)}
                />
                <label htmlFor="auto_respond">自动响应判断</label>
              </div>
            </div>
            <div className="am-form-row-inline">
              <div className="am-form-row">
                <label className="am-form-label">相关性阈值</label>
                <input
                  className="am-form-input"
                  type="number"
                  step={0.1}
                  value={form.response_threshold}
                  onChange={(e) => updateField('response_threshold', parseFloat(e.target.value) || 0.6)}
                />
              </div>
              <div className="am-form-row">
                <label className="am-form-label">Max Token</label>
                <input
                  className="am-form-input"
                  type="number"
                  value={form.max_output_tokens}
                  onChange={(e) => updateField('max_output_tokens', parseInt(e.target.value) || 2000)}
                />
              </div>
            </div>
          </div>

          {/* Skills (Advanced) */}
          {mode === 'edit' && selectedAgent && (
            <div className="am-section">
              <div className="am-section-title-row">
                <div className="am-section-title" style={{ marginBottom: 0 }}>核心技能 (SKILL.md)</div>
                <button className="am-btn am-btn-sm am-btn-add" onClick={() => setShowAddSkill(true)}>+ 新增</button>
              </div>
              {showAddSkill && (
                <div className="am-add-form">
                  <input className="am-form-input" placeholder="ID" onChange={e=>setNewSkill(s=>({...s, skill_id:e.target.value}))} style={{marginBottom:8}}/>
                  <input className="am-form-input" placeholder="名称" onChange={e=>setNewSkill(s=>({...s, name:e.target.value}))} style={{marginBottom:8}}/>
                  <div className="am-add-form-actions">
                    <button className="am-btn am-btn-primary am-btn-sm" onClick={handleCreateSkill}>创建</button>
                    <button className="am-btn am-btn-sm" onClick={() => setShowAddSkill(false)}>取消</button>
                  </div>
                </div>
              )}
              <div className="am-skills-list">
                {selectedAgent.skill_definitions?.map((skill) => (
                  <div key={skill.skill_id} className="am-skill-card">
                    <div className="am-skill-header">
                      <span className="am-skill-name">{skill.name}</span>
                      <button className="am-btn-icon am-btn-icon-danger" onClick={() => handleDeleteSkill(skill.skill_id)}>&times;</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* MCP Servers */}
          {mode === 'edit' && selectedAgent && (
            <div className="am-section">
              <div className="am-section-title-row">
                <div className="am-section-title" style={{ marginBottom: 0 }}>MCP 服务</div>
                <button className="am-btn am-btn-sm am-btn-add" onClick={() => setShowAddMcp(true)}>+ 新增</button>
              </div>
              <div className="am-mcp-list">
                {mcpServers.map((srv) => (
                  <div key={srv.server_id} className="am-mcp-card">
                    <div className="am-mcp-header">
                      <div className="am-mcp-title-row">
                        <span className="am-mcp-name">{srv.server_id}</span>
                        <button className="am-btn-icon am-btn-icon-danger am-mcp-delete-btn" onClick={() => handleDeleteMcp(srv.server_id)}>&times;</button>
                      </div>
                      <div className="am-mcp-cmd"><code>{srv.command}</code></div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
