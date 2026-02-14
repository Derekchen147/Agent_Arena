/** Types aligned with backend Pydantic models. */

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
  type: "human" | "agent";
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

export type AuthorType = "human" | "agent" | "system";

export interface StoredMessage {
  id: string;
  group_id: string;
  turn_id: string;
  author_id: string;
  author_type: AuthorType;
  author_name: string;
  content: string;
  mentions: string[];
  attachments: unknown[];
  timestamp: string;
  metadata: Record<string, unknown>;
}

export interface AgentProfile {
  agent_id: string;
  name: string;
  avatar: string;
  workspace_dir: string;
  repo_url: string;
  role_prompt: string;
  skills: string[];
  response_config: { auto_respond: boolean; response_threshold: number; priority_keywords: string[] };
  cli_config: { cli_type: string; command: string; timeout: number; extra_args: string[] };
  max_output_tokens: number;
}

export type AgentStatus =
  | "idle"
  | "analyzing"
  | "reading_memory"
  | "calling_tool"
  | "generating"
  | "reviewing"
  | "waiting"
  | "done"
  | "error"
  | "timeout";

/** WebSocket incoming payloads */
export interface WsUserMessage {
  type: "user_message";
  message: StoredMessage;
}

export interface WsAgentMessage {
  type: "agent_message";
  agent_id: string;
  content: string;
  turn_id: string;
}

export interface WsAgentStatus {
  type: "agent_status";
  agent_id: string;
  status: AgentStatus;
  detail?: string;
}

export interface WsSystemMessage {
  type: "system_message";
  content: string;
}

export type WsIncoming = WsUserMessage | WsAgentMessage | WsAgentStatus | WsSystemMessage;

/** WebSocket outgoing */
export interface WsSendMessage {
  type: "send_message";
  content: string;
  mentions?: string[];
  author_id?: string;
  author_name?: string;
}
