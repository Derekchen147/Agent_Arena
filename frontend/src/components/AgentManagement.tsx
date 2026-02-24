import { useState, useEffect, useCallback } from 'react';
import type { AgentProfile, UpdateAgentRequest } from '../types';
import {
  updateAgent,
  onboardAgent,
  deleteAgent,
  getWorkspaceConfig,
  updateWorkspaceConfig,
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
  role_prompt: string;
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
  role_prompt: '',
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
    role_prompt: p.role_prompt,
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
    role_prompt: f.role_prompt,
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
  const [workspaceContent, setWorkspaceContent] = useState('');
  const [workspaceFilename, setWorkspaceFilename] = useState('');
  const [originalWorkspaceContent, setOriginalWorkspaceContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Load agent details when selecting
  const loadAgent = useCallback(
    async (agentId: string) => {
      const agent = agents.find((a) => a.agent_id === agentId);
      if (!agent) return;
      setForm(profileToForm(agent));
      try {
        const wc = await getWorkspaceConfig(agentId);
        setWorkspaceContent(wc.content);
        setOriginalWorkspaceContent(wc.content);
        setWorkspaceFilename(wc.filename);
      } catch {
        setWorkspaceContent('');
        setOriginalWorkspaceContent('');
        setWorkspaceFilename(agent.cli_config.cli_type === 'cursor' ? '.cursor/rules/role.mdc' : 'CLAUDE.md');
      }
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
    setWorkspaceContent('');
    setOriginalWorkspaceContent('');
    setWorkspaceFilename('CLAUDE.md');
    setStatusMsg(null);
  };

  const updateField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    if (key === 'cli_type') {
      setWorkspaceFilename(value === 'cursor' ? '.cursor/rules/role.mdc' : 'CLAUDE.md');
    }
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
          role_prompt: form.role_prompt.trim() || undefined,
          skills: form.skills.split(',').map((s) => s.trim()).filter(Boolean),
          cli_type: form.cli_type,
          priority_keywords: form.priority_keywords.split(',').map((s) => s.trim()).filter(Boolean),
        });
        onAgentsChanged();
        setSelectedAgentId(form.agent_id.trim());
        setMode('edit');
        setStatusMsg({ type: 'success', text: '员工创建成功' });
      } else {
        if (!selectedAgentId) return;
        const req = formToUpdateRequest(form);
        await updateAgent(selectedAgentId, req);

        // Save workspace config if changed
        if (workspaceContent !== originalWorkspaceContent) {
          await updateWorkspaceConfig(selectedAgentId, workspaceContent);
          setOriginalWorkspaceContent(workspaceContent);
        }

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
    if (!confirm(`确定删除员工「${form.name || selectedAgentId}」？此操作不可撤销。`)) return;

    try {
      await deleteAgent(selectedAgentId);
      onAgentsChanged();
      setSelectedAgentId(null);
      setMode('edit');
      setForm(EMPTY_FORM);
      setStatusMsg({ type: 'success', text: '已删除' });
    } catch (err) {
      setStatusMsg({ type: 'error', text: `删除失败: ${err}` });
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
          + 新建员工
        </button>
      </div>

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
                <button className="am-btn am-btn-danger" onClick={handleDelete}>
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
              <>
                <div className="am-form-row">
                  <label className="am-form-label">工作目录</label>
                  <input
                    className="am-form-input"
                    value={selectedAgent.workspace_dir}
                    readOnly
                  />
                </div>
                {selectedAgent.repo_url && (
                  <div className="am-form-row">
                    <label className="am-form-label">Git 仓库</label>
                    <input
                      className="am-form-input"
                      value={selectedAgent.repo_url}
                      readOnly
                    />
                  </div>
                )}
              </>
            )}
          </div>

          {/* Role & Skills */}
          <div className="am-section">
            <div className="am-section-title">角色与技能</div>
            <div className="am-form-row">
              <label className="am-form-label">角色描述 / Role Prompt</label>
              <textarea
                className="am-form-textarea"
                value={form.role_prompt}
                onChange={(e) => updateField('role_prompt', e.target.value)}
                placeholder="描述该员工的角色定位和职责..."
                rows={5}
              />
              <div className="am-form-hint">
                此内容会写入 YAML 配置的 role_prompt 字段，并在每次调用时注入给 Agent
              </div>
            </div>
            <div className="am-form-row">
              <label className="am-form-label">技能标签（逗号分隔）</label>
              <input
                className="am-form-input"
                value={form.skills}
                onChange={(e) => updateField('skills', e.target.value)}
                placeholder="架构设计, 需求分析, 技术选型"
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
                <label htmlFor="auto_respond">自动响应（may_reply 时自动判断是否回复）</label>
              </div>
            </div>
            <div className="am-form-row-inline">
              <div className="am-form-row">
                <label className="am-form-label">相关性阈值（0~1）</label>
                <input
                  className="am-form-input"
                  type="number"
                  min={0}
                  max={1}
                  step={0.1}
                  value={form.response_threshold}
                  onChange={(e) => updateField('response_threshold', parseFloat(e.target.value) || 0)}
                />
              </div>
              <div className="am-form-row">
                <label className="am-form-label">最大输出 Token</label>
                <input
                  className="am-form-input"
                  type="number"
                  min={100}
                  step={100}
                  value={form.max_output_tokens}
                  onChange={(e) => updateField('max_output_tokens', parseInt(e.target.value) || 2000)}
                />
              </div>
            </div>
            <div className="am-form-row">
              <label className="am-form-label">优先关键词（逗号分隔）</label>
              <input
                className="am-form-input"
                value={form.priority_keywords}
                onChange={(e) => updateField('priority_keywords', e.target.value)}
                placeholder="架构, 设计, 方案"
              />
            </div>
          </div>

          {/* CLI Config */}
          <div className="am-section">
            <div className="am-section-title">CLI 配置</div>
            <div className="am-form-row-inline">
              <div className="am-form-row">
                <label className="am-form-label">CLI 类型</label>
                <select
                  className="am-form-select"
                  value={form.cli_type}
                  onChange={(e) => updateField('cli_type', e.target.value)}
                >
                  <option value="claude">Claude CLI</option>
                  <option value="cursor">Cursor CLI</option>
                  <option value="generic">Generic CLI</option>
                </select>
              </div>
              <div className="am-form-row">
                <label className="am-form-label">超时（秒）</label>
                <input
                  className="am-form-input"
                  type="number"
                  min={10}
                  step={10}
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
                  placeholder={form.cli_type === 'cursor' ? 'agent（默认）或完整路径' : '可执行文件路径'}
                />
                <div className="am-form-hint">
                  {form.cli_type === 'cursor'
                    ? '若 PATH 中无 agent 命令，请填完整路径，如 C:/Users/.../agent.exe'
                    : '自定义 CLI 的可执行文件路径'}
                </div>
              </div>
            )}
            <div className="am-form-row">
              <label className="am-form-label">额外参数（逗号分隔）</label>
              <input
                className="am-form-input"
                value={form.extra_args}
                onChange={(e) => updateField('extra_args', e.target.value)}
                placeholder="--flag1, --flag2=value"
              />
            </div>
            <div className="am-form-row">
              <label className="am-form-label">环境变量（每行一个 KEY=VALUE）</label>
              <textarea
                className="am-form-textarea"
                value={form.env}
                onChange={(e) => updateField('env', e.target.value)}
                placeholder={'HTTP_PROXY=http://127.0.0.1:7897\nHTTPS_PROXY=http://127.0.0.1:7897'}
                rows={3}
              />
            </div>
          </div>

          {/* Workspace Config File */}
          {mode === 'edit' && selectedAgentId && (
            <div className="am-section">
              <div className="am-section-title">Workspace 配置文件</div>
              <div className="am-workspace-header">
                <span className="am-workspace-filename">{workspaceFilename}</span>
                <div className="am-form-hint">
                  {form.cli_type === 'cursor'
                    ? 'Cursor 会自动加载 .cursor/rules/*.mdc 作为 system prompt'
                    : 'Claude CLI 会读取工作目录中的 CLAUDE.md 作为上下文'}
                </div>
              </div>
              <textarea
                className="am-workspace-editor"
                value={workspaceContent}
                onChange={(e) => setWorkspaceContent(e.target.value)}
                placeholder="在此编辑 workspace 角色配置文件内容..."
                rows={12}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
