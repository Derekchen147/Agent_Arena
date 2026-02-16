import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import type { StoredMessage, AgentProfile, Group } from '../types';
import { getMessages } from '../api/client';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import './ChatArea.css';

interface Props {
  group: Group | null;
  agents: AgentProfile[];
  messages: StoredMessage[];
  setMessages: React.Dispatch<React.SetStateAction<StoredMessage[]>>;
  onSendMessage: (content: string, mentions: string[]) => void;
  connected: boolean;
}

export default function ChatArea({
  group,
  agents,
  messages,
  setMessages,
  onSendMessage,
  connected,
}: Props) {
  const [input, setInput] = useState('');
  const [showMentions, setShowMentions] = useState(false);
  const [mentionFilter, setMentionFilter] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const loadedRef = useRef<string | null>(null);

  // Load message history when group changes
  useEffect(() => {
    if (!group || loadedRef.current === group.id) return;
    loadedRef.current = group.id;
    getMessages(group.id).then((msgs) => {
      setMessages(msgs);
    });
  }, [group, setMessages]);

  // Auto scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Reset loaded ref when group changes
  useEffect(() => {
    loadedRef.current = null;
  }, [group?.id]);

  const parseMentions = useCallback(
    (text: string): string[] => {
      const mentions: string[] = [];
      const mentionRegex = /@(\S+)/g;
      let match;
      while ((match = mentionRegex.exec(text)) !== null) {
        const name = match[1];
        if (name === '所有人' || name === 'all') {
          // @all: mention all agents in the group
          const groupAgentIds = group?.members
            .filter((m) => m.type === 'agent' && m.agent_id)
            .map((m) => m.agent_id!) ?? [];
          mentions.push(...groupAgentIds);
        } else {
          // Find agent by name or id
          const agent = agents.find(
            (a) => a.name === name || a.agent_id === name,
          );
          if (agent) mentions.push(agent.agent_id);
        }
      }
      return [...new Set(mentions)];
    },
    [agents, group],
  );

  const handleSend = () => {
    const text = input.trim();
    if (!text || !group) return;
    const mentions = parseMentions(text);
    onSendMessage(text, mentions);
    setInput('');
    setShowMentions(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setInput(val);

    // Detect @ trigger
    const cursorPos = e.target.selectionStart;
    const textBefore = val.slice(0, cursorPos);
    const atMatch = textBefore.match(/@(\S*)$/);
    if (atMatch) {
      setShowMentions(true);
      setMentionFilter(atMatch[1].toLowerCase());
    } else {
      setShowMentions(false);
    }
  };

  const insertMention = (name: string) => {
    const cursorPos = inputRef.current?.selectionStart ?? input.length;
    const textBefore = input.slice(0, cursorPos);
    const textAfter = input.slice(cursorPos);
    const atIdx = textBefore.lastIndexOf('@');
    const newText = textBefore.slice(0, atIdx) + `@${name} ` + textAfter;
    setInput(newText);
    setShowMentions(false);
    inputRef.current?.focus();
  };

  const getGroupAgents = (): AgentProfile[] => {
    if (!group) return [];
    const agentIds = group.members
      .filter((m) => m.type === 'agent' && m.agent_id)
      .map((m) => m.agent_id!);
    return agents.filter((a) => agentIds.includes(a.agent_id));
  };

  const filteredMentions = getGroupAgents().filter(
    (a) =>
      a.name.toLowerCase().includes(mentionFilter) ||
      a.agent_id.toLowerCase().includes(mentionFilter),
  );

  const getAuthorAvatar = (msg: StoredMessage): string => {
    if (msg.author_type === 'human') return '🧑';
    if (msg.author_type === 'system') return '⚙️';
    const agent = agents.find((a) => a.agent_id === msg.author_id);
    return agent?.avatar || '🤖';
  };

  const formatTime = (ts: string): string => {
    const d = new Date(ts);
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  };

  const markdownComponents = useMemo(() => ({
    // Custom code block with syntax highlighting
    code({ className, children, ...props }: React.ComponentProps<'code'> & { inline?: boolean }) {
      const match = /language-(\w+)/.exec(className || '');
      const codeString = String(children).replace(/\n$/, '');
      // Inline code vs block code: block code lives inside <pre>
      const isInline = !className && !codeString.includes('\n');
      if (isInline) {
        return <code className="inline-code" {...props}>{children}</code>;
      }
      return (
        <SyntaxHighlighter
          style={oneLight}
          language={match?.[1] || 'text'}
          PreTag="div"
          customStyle={{ margin: 0, borderRadius: '8px', fontSize: '13px' }}
        >
          {codeString}
        </SyntaxHighlighter>
      );
    },
    // Open links in new tab
    a({ children, ...props }: React.ComponentProps<'a'>) {
      return <a {...props} target="_blank" rel="noopener noreferrer">{children}</a>;
    },
  }), []);

  const renderContent = (content: string, authorType: string): React.ReactNode => {
    // Human messages: simple rendering; Agent messages: full markdown
    if (authorType === 'human') {
      const parts = content.split(/(@\S+)/g);
      return parts.map((part, i) => {
        if (part.startsWith('@')) {
          return (
            <span key={i} className="mention-tag">
              {part}
            </span>
          );
        }
        return part;
      });
    }

    // Normalize whitespace: collapse 3+ newlines to 2 to avoid huge gaps in markdown
    const normalized = content
      .trim()
      .replace(/\n{3,}/g, '\n\n');
    const processed = normalized.replace(
      /@(\S+)/g,
      '<span class="mention-tag">@$1</span>',
    );

    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        allowedElements={undefined}
        unwrapDisallowed={false}
        skipHtml={false}
        rehypePlugins={[rehypeRaw]}
        components={markdownComponents}
      >
        {processed}
      </ReactMarkdown>
    );
  };

  if (!group) {
    return (
      <div className="chat-area empty">
        <div className="empty-state">
          <div className="empty-icon">💬</div>
          <h3>选择一个群组开始对话</h3>
          <p>在左侧选择群组，或创建新群组</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-area">
      <div className="chat-header">
        <div className="chat-title">
          <h3>{group.name}</h3>
          <span className="chat-desc">{group.description}</span>
        </div>
        <div className="chat-status">
          <span className={`status-dot ${connected ? 'online' : 'offline'}`} />
          {connected ? '已连接' : '连接中...'}
        </div>
      </div>

      <div className="messages-container">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`message ${msg.author_type}`}
          >
            {msg.author_type === 'system' ? (
              <div className="system-notice">{msg.content}</div>
            ) : (
              <>
                <div className="message-avatar">{getAuthorAvatar(msg)}</div>
                <div className="message-body">
                  <div className="message-meta">
                    <span className="message-author">{msg.author_name}</span>
                    <span className="message-time">{formatTime(msg.timestamp)}</span>
                  </div>
                  <div className={`message-bubble ${msg.author_type !== 'human' ? 'markdown-body' : ''}`}>
                    {renderContent(msg.content, msg.author_type)}
                  </div>
                </div>
              </>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="input-area">
        {showMentions && filteredMentions.length > 0 && (
          <div className="mention-popup">
            <div className="mention-item" onClick={() => insertMention('所有人')}>
              <span className="mention-avatar">📢</span>
              <span>所有人</span>
            </div>
            {filteredMentions.map((a) => (
              <div
                key={a.agent_id}
                className="mention-item"
                onClick={() => insertMention(a.name)}
              >
                <span className="mention-avatar">{a.avatar || '🤖'}</span>
                <span>{a.name}</span>
                <span className="mention-id">{a.agent_id}</span>
              </div>
            ))}
          </div>
        )}
        <textarea
          ref={inputRef}
          placeholder="输入消息，用 @ 提及员工..."
          value={input}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          rows={1}
        />
        <button className="btn-send" onClick={handleSend} disabled={!input.trim()}>
          发送
        </button>
      </div>
    </div>
  );
}
