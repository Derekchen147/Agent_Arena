import { useEffect, useState, useCallback } from "react";
import { listGroups, getMessages, sendMessage, listAgents, createGroup } from "@/api/client";
import type { Group, StoredMessage, AgentProfile } from "@/types/api";
import { useGroupWebSocket } from "@/hooks/useGroupWebSocket";
import { GroupSidebar } from "@/components/GroupSidebar";
import { ChatArea } from "@/components/ChatArea";
import { AgentPanel } from "@/components/AgentPanel";
import { CreateGroupModal } from "@/components/CreateGroupModal";
import "./App.css";

export default function App() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [agents, setAgents] = useState<AgentProfile[]>([]);
  const [currentGroupId, setCurrentGroupId] = useState<string | null>(null);
  const [messages, setMessages] = useState<StoredMessage[]>([]);
  const [systemMessage, setSystemMessage] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [loading, setLoading] = useState(true);

  const currentGroup = groups.find((g) => g.id === currentGroupId) ?? null;
  const memberAgentIds = currentGroup?.members
    ?.filter((m) => m.type === "agent" && m.agent_id)
    .map((m) => m.agent_id!) ?? [];

  const mergeMessage = useCallback((msg: StoredMessage) => {
    setMessages((prev) => {
      if (prev.some((m) => m.id === msg.id)) return prev;
      return [...prev, msg];
    });
  }, []);

  const { connected, agentStatuses, sendMessage: wsSend } = useGroupWebSocket(currentGroupId, {
    onUserMessage: mergeMessage,
    onAgentMessage: useCallback(
      (payload) => {
        const agent = agents.find((a) => a.agent_id === payload.agent_id);
        const synthetic: StoredMessage = {
          id: `agent-${payload.turn_id}-${payload.agent_id}-${Date.now()}`,
          group_id: currentGroupId!,
          turn_id: payload.turn_id,
          author_id: payload.agent_id,
          author_type: "agent",
          author_name: agent?.name ?? payload.agent_id,
          content: payload.content,
          mentions: [],
          attachments: [],
          timestamp: new Date().toISOString(),
          metadata: {},
        };
        setMessages((prev) => [...prev, synthetic]);
      },
      [agents, currentGroupId]
    ),
    onSystemMessage: setSystemMessage,
  });

  useEffect(() => {
    (async () => {
      try {
        const [gRes, aRes] = await Promise.all([listGroups(), listAgents()]);
        setGroups(gRes.groups);
        setAgents(aRes.agents);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!currentGroupId) {
      setMessages([]);
      setSystemMessage(null);
      return;
    }
    setSystemMessage(null);
    getMessages(currentGroupId, { limit: 50 })
      .then((res) => setMessages(res.messages))
      .catch((e) => console.error(e));
  }, [currentGroupId]);

  const handleSend = useCallback(
    async (content: string, mentions?: string[]) => {
      if (!currentGroupId) return;
      try {
        const res = await sendMessage({
          group_id: currentGroupId,
          content,
          mentions,
        });
        mergeMessage(res.message);
      } catch (e) {
        console.error(e);
      }
    },
    [currentGroupId, mergeMessage]
  );

  const handleCreateGroup = useCallback(async (name: string, description: string) => {
    const res = await createGroup({ name, description });
    setGroups((prev) => [...prev, res.group]);
    setCurrentGroupId(res.group.id);
  }, []);

  if (loading) {
    return (
      <div className="app-loading">
        <span>加载中…</span>
      </div>
    );
  }

  return (
    <div className="app">
      <GroupSidebar
        groups={groups}
        currentId={currentGroupId}
        onSelect={setCurrentGroupId}
        onAddGroup={() => setShowCreateModal(true)}
      />
      <ChatArea
        groupName={currentGroup?.name ?? ""}
        messages={messages}
        systemMessage={systemMessage}
        agents={agents}
        connected={connected}
        onSend={handleSend}
      />
      <AgentPanel
        agents={agents}
        statuses={agentStatuses}
        memberIds={memberAgentIds}
      />
      {showCreateModal ? (
        <CreateGroupModal
          onClose={() => setShowCreateModal(false)}
          onCreate={handleCreateGroup}
        />
      ) : null}
    </div>
  );
}
