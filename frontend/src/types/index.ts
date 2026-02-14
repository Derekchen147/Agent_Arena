// ── Group & Session Models ──

export interface GroupConfig {
  max_responders: number;
  turn_timeout_seconds: number;
  chain_depth_limit: number;
  re_invoke_already_replied: boolean;
  supervisor_enabled: boolean;
  supervisor_agent_id: string;
  auto_summary_interval: number;
}

export interface GroupMember {
  id: string;
  type: 'human' | 'agent';
  agent_id: string | null;
  display_name: string;
  joined_at: string;
  role_in_group: string | null;
}

export interface Group {
  id: string;
  name: string;
  description: string;
  created_at: string;
  members: GroupMember[];
  config: GroupConfig;
}

// ── Message Models ──

export interface StoredMessage {
  id: string;
  group_id: string;
  turn_id: string;
  author_id: string;
  author_type: 'human' | 'agent' | 'system';
  author_name: string;
  content: string;
  mentions: string[];
  attachments: unknown[];
  timestamp: string;
  metadata: Record<string, unknown>;
}

// ── Agent Models ──

export interface ResponseConfig {
  auto_respond: boolean;
  response_threshold: number;
  priority_keywords: string[];
}

export interface CliConfig {
  cli_type: string;
  command: string;
  timeout: number;
  extra_args: string[];
}

export interface AgentProfile {
  agent_id: string;
  name: string;
  avatar: string;
  workspace_dir: string;
  repo_url: string;
  role_prompt: string;
  skills: string[];
  response_config: ResponseConfig;
  cli_config: CliConfig;
  max_output_tokens: number;
}

// ── WebSocket Event Types ──

export type WSEvent =
  | { type: 'user_message'; message: StoredMessage }
  | { type: 'agent_message'; agent_id: string; content: string; turn_id: string }
  | { type: 'agent_status'; agent_id: string; status: AgentStatus; detail: string }
  | { type: 'system_message'; content: string };

export type AgentStatus =
  | 'idle'
  | 'analyzing'
  | 'reading_memory'
  | 'calling_tool'
  | 'generating'
  | 'reviewing'
  | 'waiting'
  | 'done'
  | 'error'
  | 'timeout';

// ── API Request Types ──

export interface CreateGroupRequest {
  name: string;
  description?: string;
  config?: Partial<GroupConfig>;
}

export interface SendMessageRequest {
  group_id: string;
  content: string;
  author_id?: string;
  author_name?: string;
  mentions?: string[];
}

export interface AddMemberRequest {
  agent_id: string;
  display_name?: string;
  role_in_group?: string | null;
}

export interface OnboardAgentRequest {
  agent_id: string;
  name: string;
  repo_url?: string;
  role_prompt?: string;
  skills?: string[];
  cli_type?: string;
  avatar?: string;
  priority_keywords?: string[];
}
