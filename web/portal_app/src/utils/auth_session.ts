import type { AuthSession, AuthTokenPair } from '../types/backend';

const storage_key = 'motion_sense_backend_auth_session';

function can_use_storage(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

export function get_auth_session(): AuthSession | null {
  if (!can_use_storage()) {
    return null;
  }

  const raw = window.localStorage.getItem(storage_key);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as AuthSession;
  } catch {
    window.localStorage.removeItem(storage_key);
    return null;
  }
}

export function save_auth_session(token_pair: AuthTokenPair): AuthSession {
  const session: AuthSession = {
    ...token_pair,
    issued_at_ms: Date.now()
  };

  if (can_use_storage()) {
    window.localStorage.setItem(storage_key, JSON.stringify(session));
  }

  return session;
}

export function clear_auth_session(): void {
  if (can_use_storage()) {
    window.localStorage.removeItem(storage_key);
  }
}
