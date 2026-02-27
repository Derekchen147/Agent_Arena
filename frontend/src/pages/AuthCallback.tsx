import { useEffect, useRef } from 'react';
import { handleOpenlibingCallback } from '../api/authClient';

export default function AuthCallback() {
  const processedRef = useRef(false);

  useEffect(() => {
    const handleCallback = async () => {
      if (processedRef.current) {
        return;
      }
      processedRef.current = true;

      const urlParams = new URLSearchParams(window.location.search);
      const code = urlParams.get('code');
      const state = urlParams.get('state');

      if (code && state) {
        try {
          const success = await handleOpenlibingCallback({ code, state });

          if (success) {
            // 通知父窗口登录成功
            window.opener?.postMessage(
              {
                type: 'auth_callback',
                code,
                state,
              },
              '*',
            );

            // 关闭当前窗口
            setTimeout(() => window.close(), 500);
          } else {
            alert('登录失败，请重试');
            setTimeout(() => window.close(), 500);
          }
        } catch (err) {
          console.error('Handle callback failed:', err);
          alert('登录失败，请重试');
          setTimeout(() => window.close(), 500);
        }
      } else {
        alert('参数错误，请重新登录');
        setTimeout(() => window.close(), 500);
      }
    };

    handleCallback();
  }, []);

  return (
    <div style={{
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      height: '100vh',
      background: '#1a1a2e',
      color: '#eee',
    }}>
      <div style={{ textAlign: 'center' }}>
        <h2>正在处理登录...</h2>
        <p>请稍候，窗口将自动关闭</p>
      </div>
    </div>
  );
}
