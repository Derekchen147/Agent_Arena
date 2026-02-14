import type { Group } from "@/types/api";
import "./GroupSidebar.css";

interface GroupSidebarProps {
  groups: Group[];
  currentId: string | null;
  onSelect: (id: string) => void;
  onAddGroup: () => void;
}

export function GroupSidebar({ groups, currentId, onSelect, onAddGroup }: GroupSidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <span className="sidebar-title">Agent Arena</span>
        <button type="button" className="btn btn-ghost" onClick={onAddGroup} aria-label="新建群组">
          + 群组
        </button>
      </div>
      <div className="sidebar-list">
        {groups.length === 0 ? (
          <div className="empty-state">暂无群组，点击上方创建</div>
        ) : (
          groups.map((g) => (
            <button
              key={g.id}
              type="button"
              className={`group-item ${currentId === g.id ? "active" : ""}`}
              onClick={() => onSelect(g.id)}
            >
              <div className="group-item-name">{g.name || "未命名"}</div>
              {g.description ? (
                <div className="group-item-desc">{g.description}</div>
              ) : null}
            </button>
          ))
        )}
      </div>
    </aside>
  );
}
