import { useState, useEffect, useCallback, useMemo } from 'react';
import type { Group, StoredMessage, AgentProfile, WSEvent, UserInfoResponse } from './types';
import { listGroups, getGroup, listAgents, sendMessage } from './api/client';
import { getAuthStatus, getUserInfo, logout } from './api/authClient';
import { useWebSocket } from './hooks/useWebSocket';
import GroupSidebar from './components/GroupSidebar';
import ChatArea from './components/ChatArea';
import AgentPanel from './components/AgentPanel';
import AgentManagement from './components/AgentManagement';
import LogPanel from './components/LogPanel';
import LoginModal from './components/LoginModal';
import './App.css';

// 测试开关：设为 true 可跳过登录
const SKIP_AUTH = true;

export default function App() {
  const [view, setView] = useState<'chat' | 'agents'>('chat');
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [userInfo, setUserInfo] = useState<UserInfoResponse | null>(null);
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [groups, setGroups] = useState<Group[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<Group | null>(null);
  const [messageCounts, setMessageCounts] = useState<Record<string, number>>({});
  const [agents, setAgents] = useState<AgentProfile[]>([]);
  const [messages, setMessages] = useState<StoredMessage[]>([]);
  const [rightPanel, setRightPanel] = useState<'members' | 'logs'>('members');
  const [historyLogMap, setHistoryLogMap] = useState<Record<string, any>>({});

  // Check auth status on mount
  useEffect(() => {
    checkAuthStatus();
  }, []);

  const loadLogs = useCallback(async (groupId: string) => {
    try {
      const res = await fetch(`/api/messages/logs/${groupId}`);
      const data = await res.json();
      const logs = data.logs || [];
      const map: Record<string, any> = {};
      logs.forEach((log: any) => {
        map[log.turn_id] = log;
      });
      setHistoryLogMap(map);
    } catch (err) {
      console.error('Failed to load logs:', err);
    }
  }, []);

  // Check auth status on mount
  const checkAuthStatus = async () => {
    if (SKIP_AUTH) {
      setIsLoggedIn(true);
      loadGroups();
      loadAgents();
      return;
    }

    try {
      const status = await getAuthStatus();
      setIsLoggedIn(status.is_logged_in);

      if (status.is_logged_in) {
        const info = await getUserInfo();
        setUserInfo(info);
        loadGroups();
        loadAgents();
      } else {
        setShowLoginModal(true);
      }
    } catch (err) {
      console.error('Failed to check auth status:', err);
      setShowLoginModal(true);
    }
  };

  const handleLoginSuccess = () => {
    setIsLoggedIn(true);
    setShowLoginModal(false);
    checkAuthStatus();
  };

  const handleLogout = async () => {
    try {
      await logout();
      setIsLoggedIn(false);
      setUserInfo(null);
      setShowLoginModal(true);
    } catch (err) {
      console.error('Failed to logout:', err);
    }
  };

  const loadGroups = async () => {
    try {
      const g = await listGroups();
      setGroups(g);
    } catch (err) {
      console.error('Failed to load groups:', err);
    }
  };

  const loadAgents = async () => {
    try {
      const a = await listAgents();
      setAgents(a);
    } catch (err) {
      console.error('Failed to load agents:', err);
    }
  };

  // Load group details when selection changes
  useEffect(() => {
    setMessages([]); // 切换群组时立即清空消息，解决残留问题
    setHistoryLogMap({});
    setMessageCounts({});

    if (!selectedGroupId) {
      setSelectedGroup(null);
      return;
    }

    let isSubscribed = true; // 用于处理竞态请求

    getGroup(selectedGroupId)
      .then((res) => {
        if (isSubscribed) {
          setSelectedGroup(res.group);
          setMessageCounts(res.message_counts);
        }
      })
      .catch(console.error);

    loadLogs(selectedGroupId);

    return () => {
      isSubscribed = false;
    };
  }, [selectedGroupId, loadLogs]);

  // WebSocket callbacks
  const onUserMessage = useCallback(
    (event: WSEvent & { type: 'user_message' }) => {
      setMessages((prev) => {
        // 基于 ID 去重
        if (prev.some((m) => m.id === event.message.id)) return prev;
        return [...prev, event.message];
      });
    },
    [],
  );

  const onAgentMessage = useCallback(
    (event: WSEvent & { type: 'agent_message' }) => {
      // 如果消息不属于当前选中的群组，忽略（防止异步导致的群组错位）
      // 注意：这里的 selectedGroupId 可能不是最新的，但在 setMessages 内部可以通过 logic 规避
      const msgId = `${event.turn_id}-${event.agent_id}`; 
      
      setMessages((prev) => {
        // 基于确定性生成的 ID 去重，解决重复回答问题
        if (prev.some((m) => m.id.startsWith(msgId))) return prev;

        const msg: StoredMessage = {
          id: `${msgId}-${Date.now()}`,
          group_id: selectedGroupId ?? '',
          turn_id: event.turn_id,
          author_id: event.agent_id,
          author_type: 'agent',
          author_name:
            agents.find((a) => a.agent_id === event.agent_id)?.name ?? event.agent_id,
          content: event.content,
          mentions: [],
          attachments: [],
          timestamp: new Date().toISOString(),
          metadata: {},
        };
        return [...prev, msg];
      });
    },
    [selectedGroupId, agents],
  );

  const onSystemMessage = useCallback(
    (event: WSEvent & { type: 'system_message' }) => {
      setMessages((prev) => {
        const msg: StoredMessage = {
          id: `system-${Date.now()}-${Math.random()}`,
          group_id: selectedGroupId ?? '',
          turn_id: '',
          author_id: 'system',
          author_type: 'system',
          author_name: '系统',
          content: event.content,
          mentions: [],
          attachments: [],
          timestamp: new Date().toISOString(),
          metadata: {},
        };
        return [...prev, msg];
      });
    },
    [selectedGroupId],
  );

  const { connected, agentStatuses, turnLogMap } = useWebSocket({
    groupId: selectedGroupId,
    onUserMessage,
    onAgentMessage,
    onSystemMessage,
  });

  const combinedLogMap = useMemo(() => {
    return { ...historyLogMap, ...turnLogMap };
  }, [historyLogMap, turnLogMap]);

  const handleSendMessage = async (content: string, mentions: string[]) => {
    if (!selectedGroupId) return;
    try {
      await sendMessage({
        group_id: selectedGroupId,
        content,
        mentions,
      });
    } catch (err) {
      console.error('Failed to send message:', err);
    }
  };

  const handleGroupChanged = () => {
    loadGroups();
    if (selectedGroupId) {
      getGroup(selectedGroupId)
        .then((res) => {
          setSelectedGroup(res.group);
          setMessageCounts(res.message_counts);
        })
        .catch(console.error);
    }
  };

  if (view === 'agents') {
    return (
      <div className="app-layout">
        <AgentManagement
          agents={agents}
          onAgentsChanged={loadAgents}
          onBack={() => setView('chat')}
        />
      </div>
    );
  }

  return (
    <div className="app-layout">
      {showLoginModal && (
        <LoginModal
          onLoginSuccess={handleLoginSuccess}
        />
      )}

      {isLoggedIn && (
        <div className="app-header">
          <div className="header-left"></div>
          <div className="header-right">
            <span className="user-info">{userInfo?.username}</span>
            <button className="logout-button" onClick={handleLogout}>
              退出登录
            </button>
          </div>
        </div>
      )}

      <div className="app-main">
        <GroupSidebar
          groups={groups}
          selectedGroupId={selectedGroupId}
          onSelectGroup={setSelectedGroupId}
          onGroupsChanged={loadGroups}
        />
        <ChatArea
          group={selectedGroup}
          agents={agents}
          messages={messages}
          setMessages={setMessages}
          onSendMessage={handleSendMessage}
          connected={connected}
          turnLogMap={combinedLogMap}
        />
        <div className="right-panel-wrapper">
          <div className="right-panel-tabs">
            <button
              className={`right-tab ${rightPanel === 'members' ? 'active' : ''}`}
              onClick={() => setRightPanel('members')}
            >
              👥 成员
            </button>
            <button
              className={`right-tab ${rightPanel === 'logs' ? 'active' : ''}`}
              onClick={() => setRightPanel('logs')}
            >
              📋 日志
            </button>
          </div>
          {rightPanel === 'members' ? (
            <AgentPanel
              agents={agents}
              group={selectedGroup}
              agentStatuses={agentStatuses}
              onGroupChanged={handleGroupChanged}
              onAgentsChanged={loadAgents}
              onViewAgents={() => setView('agents')}
            />
          ) : (
            <LogPanel
              groupId={selectedGroupId}
              agents={agents}
              turnLogMap={combinedLogMap}
            />
          )}
        </div>
      </div>
    </div>
  );
}
