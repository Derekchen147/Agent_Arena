import type {
  LoginRequest,
  LoginResponse,
  LogoutResponse,
  UserInfoResponse,
  OpenLibingAuthCallback,
  AuthStatusResponse,
} from '../types';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export async function login(request: LoginRequest): Promise<LoginResponse> {
  // 获取当前端口的回调地址
  const redirectUri = `${window.location.origin}/callback`;

  const response = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      ...request,
      redirect_uri: redirectUri,
    }),
  });

  if (!response.ok) {
    throw new Error(`Login failed: ${response.statusText}`);
  }

  return response.json();
}

export async function logout(): Promise<LogoutResponse> {
  const response = await fetch(`${API_BASE}/api/auth/logout`, {
    method: 'POST',
  });

  if (!response.ok) {
    throw new Error(`Logout failed: ${response.statusText}`);
  }

  return response.json();
}

export async function getUserInfo(): Promise<UserInfoResponse> {
  const response = await fetch(`${API_BASE}/api/auth/userinfo`);

  if (!response.ok) {
    throw new Error(`Get user info failed: ${response.statusText}`);
  }

  return response.json();
}

export async function getAuthStatus(): Promise<AuthStatusResponse> {
  const response = await fetch(`${API_BASE}/api/auth/status`);

  if (!response.ok) {
    throw new Error(`Get auth status failed: ${response.statusText}`);
  }

  return response.json();
}

export async function handleOpenlibingCallback(
  callback: OpenLibingAuthCallback,
): Promise<boolean> {
  const response = await fetch(`${API_BASE}/api/auth/callback/openlibing`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(callback),
  });

  if (!response.ok) {
    throw new Error(`Handle callback failed: ${response.statusText}`);
  }

  const data = await response.json();
  return data.success;
}

export async function refreshToken(): Promise<boolean> {
  const response = await fetch(`${API_BASE}/api/auth/refresh`, {
    method: 'POST',
  });

  if (!response.ok) {
    throw new Error(`Refresh token failed: ${response.statusText}`);
  }

  const data = await response.json();
  return data.success;
}

export async function getValidToken(): Promise<string> {
  const response = await fetch(`${API_BASE}/api/auth/token`);

  if (!response.ok) {
    throw new Error(`Get valid token failed: ${response.statusText}`);
  }

  const data = await response.json();
  return data.token;
}
