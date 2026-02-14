import { useState } from 'react';
import type { Group } from '../types';
import { createGroup, deleteGroup } from '../api/client';
import './GroupSidebar.css';

interface Props {
  groups: Group[];
  selectedGroupId: string | null;
  onSelectGroup: (id: string) => void;
  onGroupsChanged: () => void;
}

export default function GroupSidebar({
  groups,
  selectedGroupId,
  onSelectGroup,
  onGroupsChanged,
}: Props) {
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const group = await createGroup({ name: newName.trim(), description: newDesc.trim() });
      setNewName('');
      setNewDesc('');
      setShowCreate(false);
      onGroupsChanged();
      onSelectGroup(group.id);
    } catch (err) {
      alert(`创建失败: ${err}`);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent, groupId: string) => {
    e.stopPropagation();
    if (!confirm('确定删除该群组?')) return;
    try {
      await deleteGroup(groupId);
      onGroupsChanged();
    } catch (err) {
      alert(`删除失败: ${err}`);
    }
  };

  return (
    <div className="group-sidebar">
      <div className="sidebar-header">
        <h2>Agent Arena</h2>
        <button className="btn-icon" onClick={() => setShowCreate(true)} title="新建群组">
          +
        </button>
      </div>

      <div className="group-list">
        {groups.map((g) => (
          <div
            key={g.id}
            className={`group-item ${selectedGroupId === g.id ? 'active' : ''}`}
            onClick={() => onSelectGroup(g.id)}
          >
            <div className="group-info">
              <span className="group-name">{g.name}</span>
              <span className="group-members">{g.members.length} 成员</span>
            </div>
            <button
              className="btn-delete"
              onClick={(e) => handleDelete(e, g.id)}
              title="删除群组"
            >
              &times;
            </button>
          </div>
        ))}
        {groups.length === 0 && (
          <div className="empty-hint">暂无群组，点击 + 创建</div>
        )}
      </div>

      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>新建群组</h3>
            <input
              type="text"
              placeholder="群组名称"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            />
            <input
              type="text"
              placeholder="描述（可选）"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            />
            <div className="modal-actions">
              <button onClick={() => setShowCreate(false)}>取消</button>
              <button className="btn-primary" onClick={handleCreate} disabled={creating}>
                {creating ? '创建中...' : '创建'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
