import { useEffect, useRef, useCallback, useState } from "react";
import type { StoredMessage, WsIncoming, AgentStatus } from "@/types/api";

const getWsUrl = (groupId: string) => {
  const path = `/ws/${groupId}`;
  if (typeof window === "undefined") return "";
  const base = window.location.origin.replace(/^http/, "ws");
  if (base.includes("localhost") || base.includes("127.0.0.1"))
    return `ws://localhost:8000${path}`;
  return `${base.replace(/^https?/, "wss")}${path}`;
};

export interface UseGroupWebSocketCallbacks {
  onUserMessage?: (message: StoredMessage) => void;
  onAgentMessage?: (payload: { agent_id: string; content: string; turn_id: string }) => void;
  onSystemMessage?: (content: string) => void;
  onAgentStatus?: (agentId: string, status: AgentStatus) => void;
}

export function useGroupWebSocket(
  groupId: string | null,
  callbacks: UseGroupWebSocketCallbacks = {}
) {
  const [connected, setConnected] = useState(false);
  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentStatus>>({});
  const wsRef = useRef<WebSocket | null>(null);
  const callbacksRef = useRef(callbacks);
  callbacksRef.current = callbacks;

  useEffect(() => {
    if (!groupId) {
      setConnected(false);
      return;
    }

    const url = getWsUrl(groupId);
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WsIncoming;
        const c = callbacksRef.current;
        switch (data.type) {
          case "user_message":
            c.onUserMessage?.(data.message);
            break;
          case "agent_message":
            c.onAgentMessage?.({
              agent_id: data.agent_id,
              content: data.content,
              turn_id: data.turn_id,
            });
            break;
          case "agent_status":
            setAgentStatuses((prev) => ({ ...prev, [data.agent_id]: data.status }));
            c.onAgentStatus?.(data.agent_id, data.status);
            break;
          case "system_message":
            c.onSystemMessage?.(data.content);
            break;
        }
      } catch {
        // ignore parse errors
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [groupId]);

  const sendMessage = useCallback(
    (content: string, mentions?: string[]) => {
      if (!groupId || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
      wsRef.current.send(
        JSON.stringify({
          type: "send_message",
          content,
          mentions: mentions ?? [],
          author_id: "human",
          author_name: "用户",
        })
      );
    },
    [groupId]
  );

  return { connected, agentStatuses, sendMessage };
}
