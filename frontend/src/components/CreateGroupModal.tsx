import { useState } from "react";
import "./CreateGroupModal.css";

interface CreateGroupModalProps {
  onClose: () => void;
  onCreate: (name: string, description: string) => Promise<void>;
}

export function CreateGroupModal({ onClose, onCreate }: CreateGroupModalProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("请输入群组名称");
      return;
    }
    setError("");
    setLoading(true);
    try {
      await onCreate(trimmed, description.trim());
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose} role="presentation">
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog">
        <div className="modal-title">新建群组</div>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="group-name">名称</label>
            <input
              id="group-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如：项目A"
              autoFocus
            />
          </div>
          <div className="form-group">
            <label htmlFor="group-desc">描述（可选）</label>
            <input
              id="group-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="简要描述群组用途"
            />
          </div>
          {error ? <div className="modal-error">{error}</div> : null}
          <div className="modal-actions">
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              取消
            </button>
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? "创建中…" : "创建"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
