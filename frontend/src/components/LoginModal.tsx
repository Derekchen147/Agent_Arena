import { useState } from 'react';
import { login, handleOpenlibingCallback, getAuthStatus } from '../api/authClient';
import type { LoginResponse } from '../types';

interface LoginModalProps {
  onLoginSuccess: () => void;
}

export default function LoginModal({ onLoginSuccess }: LoginModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async () => {
    setLoading(true);
    setError(null);

    try {
      const response: LoginResponse = await login({
        login_type: 'openlibing',
        client_name: 'agent_arena',
      });

      if (response.success && response.login_url) {
        // 打开登录页面
        window.open(response.login_url, '_blank');

        // 监听回调
        const handleCallback = async (event: MessageEvent) => {
          if (event.data.type === 'auth_callback') {
            console.log('收到登录回调消息:', event.data);
            onLoginSuccess();
            window.removeEventListener('message', handleCallback);
          }
        };

        window.addEventListener('message', handleCallback);
      } else {
        setError(response.message || '登录失败');
      }
    } catch (err) {
      setError('登录失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div className="modal-header">
          <h2>登录到 Agent Arena</h2>
        </div>

        <div className="modal-body">
          <p>请登录以使用 Agent Arena 的全部功能</p>

          {error && <div className="error-message">{error}</div>}

          <button
            className="login-button"
            onClick={handleLogin}
            disabled={loading}
          >
            {loading ? '正在登录...' : '登录'}
          </button>
        </div>
      </div>
    </div>
  );
}
