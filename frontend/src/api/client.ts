import type {
  Group,
  StoredMessage,
  AgentProfile,
  CreateGroupRequest,
  SendMessageRequest,
  AddMemberRequest,
  OnboardAgentRequest,
  UpdateAgentRequest,
  GroupMember,
} from '../types';

const BASE = '/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Health ──

export async function healthCheck(): Promise<{ status: string; agents_loaded: number }> {
  return request('/health');
}

// ── Groups ──

export async function listGroups(): Promise<Group[]> {
  const data = await request<{ groups: Group[] }>('/groups');
  return data.groups;
}

export async function getGroup(groupId: string): Promise<Group> {
  const data = await request<{ group: Group }>(`/groups/${groupId}`);
  return data.group;
}

export async function createGroup(req: CreateGroupRequest): Promise<Group> {
  const data = await request<{ group: Group }>('/groups', {
    method: 'POST',
    body: JSON.stringify(req),
  });
  return data.group;
}

export async function deleteGroup(groupId: string): Promise<void> {
  await request(`/groups/${groupId}`, { method: 'DELETE' });
}

export async function addMember(groupId: string, req: AddMemberRequest): Promise<GroupMember> {
  const data = await request<{ member: GroupMember }>(`/groups/${groupId}/members`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
  return data.member;
}

export async function removeMember(groupId: string, memberId: string): Promise<void> {
  await request(`/groups/${groupId}/members/${memberId}`, { method: 'DELETE' });
}

// ── Messages ──

export async function getMessages(
  groupId: string,
  limit = 50,
  before?: string,
): Promise<StoredMessage[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (before) params.set('before', before);
  const data = await request<{ messages: StoredMessage[] }>(
    `/messages/${groupId}?${params}`,
  );
  return data.messages;
}

export async function sendMessage(req: SendMessageRequest): Promise<StoredMessage> {
  const data = await request<{ message: StoredMessage }>('/messages/send', {
    method: 'POST',
    body: JSON.stringify(req),
  });
  return data.message;
}

// ── Agents ──

export async function listAgents(): Promise<AgentProfile[]> {
  const data = await request<{ agents: AgentProfile[] }>('/agents');
  return data.agents;
}

export async function getAgent(agentId: string): Promise<AgentProfile> {
  const data = await request<{ agent: AgentProfile }>(`/agents/${agentId}`);
  return data.agent;
}

export async function onboardAgent(req: OnboardAgentRequest): Promise<AgentProfile> {
  const data = await request<{ agent: AgentProfile }>('/agents/onboard', {
    method: 'POST',
    body: JSON.stringify(req),
  });
  return data.agent;
}

export async function updateAgent(agentId: string, req: UpdateAgentRequest): Promise<AgentProfile> {
  const data = await request<{ agent: AgentProfile }>(`/agents/${agentId}`, {
    method: 'PUT',
    body: JSON.stringify(req),
  });
  return data.agent;
}

export async function deleteAgent(agentId: string): Promise<void> {
  await request(`/agents/${agentId}`, { method: 'DELETE' });
}

export async function getWorkspaceConfig(agentId: string): Promise<{ content: string; filename: string }> {
  return request(`/agents/${agentId}/workspace-config`);
}

export async function updateWorkspaceConfig(agentId: string, content: string): Promise<void> {
  await request(`/agents/${agentId}/workspace-config`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  });
}

export async function reloadAgents(): Promise<{ ok: boolean; count: number }> {
  return request('/agents/reload', { method: 'POST' });
}
