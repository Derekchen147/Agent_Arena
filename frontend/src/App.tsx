import { useState, useEffect, useCallback } from 'react';
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

export default function App() {
  const [view, setView] = useState<'chat' | 'agents'>('chat');
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [userInfo, setUserInfo] = useState<UserInfoResponse | null>(null);
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [groups, setGroups] = useState<Group[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<Group | null>(null);
  const [agents, setAgents] = useState<AgentProfile[]>([]);
  const [messages, setMessages] = useState<StoredMessage[]>([]);
  const [rightPanel, setRightPanel] = useState<'members' | 'logs'>('members');

  // Check auth status on mount
  useEffect(() => {
    checkAuthStatus();
  }, []);

  const checkAuthStatus = async () => {
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
    if (!selectedGroupId) {
      setSelectedGroup(null);
      setMessages([]);
      return;
    }
    getGroup(selectedGroupId)
      .then((g) => setSelectedGroup(g))
      .catch(console.error);
  }, [selectedGroupId]);

  // WebSocket callbacks
  const onUserMessage = useCallback(
    (event: WSEvent & { type: 'user_message' }) => {
      setMessages((prev) => {
        if (prev.some((m) => m.id === event.message.id)) return prev;
        return [...prev, event.message];
      });
    },
    [],
  );

  const onAgentMessage = useCallback(
    (event: WSEvent & { type: 'agent_message' }) => {
      const msg: StoredMessage = {
        id: `${event.turn_id}-${event.agent_id}-${Date.now()}`,
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
      setMessages((prev) => [...prev, msg]);
    },
    [selectedGroupId, agents],
  );

  const onSystemMessage = useCallback(
    (event: WSEvent & { type: 'system_message' }) => {
      const msg: StoredMessage = {
        id: `system-${Date.now()}`,
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
      setMessages((prev) => [...prev, msg]);
    },
    [selectedGroupId],
  );

  const { connected, agentStatuses, turnLogMap } = useWebSocket({
    groupId: selectedGroupId,
    onUserMessage,
    onAgentMessage,
    onSystemMessage,
  });

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
        .then((g) => setSelectedGroup(g))
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
              turnLogMap={turnLogMap}
            />
          )}
        </div>
      </div>
    </div>
  );
}
