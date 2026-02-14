import { useEffect, useRef, useCallback, useState } from 'react';
import type { WSEvent, AgentStatus } from '../types';

export interface AgentStatusMap {
  [agentId: string]: { status: AgentStatus; detail: string };
}

interface UseWebSocketOptions {
  groupId: string | null;
  onUserMessage?: (event: WSEvent & { type: 'user_message' }) => void;
  onAgentMessage?: (event: WSEvent & { type: 'agent_message' }) => void;
  onSystemMessage?: (event: WSEvent & { type: 'system_message' }) => void;
}

export function useWebSocket({
  groupId,
  onUserMessage,
  onAgentMessage,
  onSystemMessage,
}: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [agentStatuses, setAgentStatuses] = useState<AgentStatusMap>({});
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (!groupId) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const ws = new WebSocket(`${protocol}//${host}/ws/${groupId}`);

    ws.onopen = () => {
      setConnected(true);
    };

    ws.onclose = () => {
      setConnected(false);
      // Auto reconnect after 3s
      reconnectTimer.current = setTimeout(() => {
        connect();
      }, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };

    ws.onmessage = (e) => {
      try {
        const event: WSEvent = JSON.parse(e.data);
        switch (event.type) {
          case 'user_message':
            onUserMessage?.(event);
            break;
          case 'agent_message':
            onAgentMessage?.(event);
            break;
          case 'agent_status':
            setAgentStatuses((prev) => ({
              ...prev,
              [event.agent_id]: { status: event.status, detail: event.detail },
            }));
            break;
          case 'system_message':
            onSystemMessage?.(event);
            break;
        }
      } catch {
        // ignore malformed messages
      }
    };

    wsRef.current = ws;
  }, [groupId, onUserMessage, onAgentMessage, onSystemMessage]);

  useEffect(() => {
    // Close previous connection
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
    }

    setAgentStatuses({});
    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
      }
    };
  }, [connect]);

  const sendWsMessage = useCallback(
    (content: string, mentions: string[], authorName = '用户') => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
      wsRef.current.send(
        JSON.stringify({
          type: 'send_message',
          author_id: 'human',
          author_name: authorName,
          content,
          mentions,
        }),
      );
    },
    [],
  );

  return { connected, agentStatuses, sendWsMessage };
}
