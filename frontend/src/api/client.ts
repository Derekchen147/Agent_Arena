/** REST API client for Agent Arena backend. */

import type { Group, GroupMember, StoredMessage, AgentProfile } from "@/types/api";

const BASE = "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ─── Groups ───
export async function listGroups(): Promise<{ groups: Group[] }> {
  return request("/api/groups");
}

export async function getGroup(groupId: string): Promise<{ group: Group }> {
  return request(`/api/groups/${groupId}`);
}

export async function createGroup(params: {
  name: string;
  description?: string;
}): Promise<{ group: Group }> {
  return request("/api/groups", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function deleteGroup(groupId: string): Promise<{ ok: boolean }> {
  return request(`/api/groups/${groupId}`, { method: "DELETE" });
}

export async function addMember(
  groupId: string,
  params: { agent_id: string; display_name?: string; role_in_group?: string }
): Promise<{ member: GroupMember }> {
  return request(`/api/groups/${groupId}/members`, {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function removeMember(groupId: string, memberId: string): Promise<{ ok: boolean }> {
  return request(`/api/groups/${groupId}/members/${memberId}`, { method: "DELETE" });
}

// ─── Messages ───
export async function getMessages(
  groupId: string,
  opts?: { limit?: number; before?: string }
): Promise<{ messages: StoredMessage[] }> {
  const params = new URLSearchParams();
  if (opts?.limit != null) params.set("limit", String(opts.limit));
  if (opts?.before) params.set("before", opts.before);
  const q = params.toString();
  return request(`/api/messages/${groupId}${q ? `?${q}` : ""}`);
}

export async function sendMessage(params: {
  group_id: string;
  content: string;
  author_id?: string;
  author_name?: string;
  mentions?: string[];
}): Promise<{ message: StoredMessage; status: string }> {
  return request("/api/messages/send", {
    method: "POST",
    body: JSON.stringify({
      group_id: params.group_id,
      content: params.content,
      author_id: params.author_id ?? "human",
      author_name: params.author_name ?? "用户",
      mentions: params.mentions ?? [],
    }),
  });
}

// ─── Agents ───
export async function listAgents(): Promise<{ agents: AgentProfile[] }> {
  return request("/api/agents");
}

export async function getAgent(agentId: string): Promise<{ agent: AgentProfile }> {
  return request(`/api/agents/${agentId}`);
}

export async function searchAgentsBySkill(keyword: string): Promise<{ agents: AgentProfile[] }> {
  return request(`/api/agents/search/skill?keyword=${encodeURIComponent(keyword)}`);
}
