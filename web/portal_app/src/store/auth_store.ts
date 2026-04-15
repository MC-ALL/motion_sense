import { create } from 'zustand';

import { login_backend, logout_backend } from '../api/backend_client';
import type { AuthSession } from '../types/backend';
import { get_auth_session } from '../utils/auth_session';

interface AuthStoreState {
  session: AuthSession | null;
  loading: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hydrate: () => void;
}

export const use_auth_store = create<AuthStoreState>((set) => ({
  session: get_auth_session(),
  loading: false,
  error: null,
  login: async (username: string, password: string) => {
    set({ loading: true, error: null });
    try {
      await login_backend({ username, password });
      set({ session: get_auth_session(), loading: false });
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : 'login failed'
      });
    }
  },
  logout: async () => {
    set({ loading: true, error: null });
    try {
      await logout_backend();
    } finally {
      set({ session: null, loading: false });
    }
  },
  hydrate: () => {
    set({ session: get_auth_session() });
  }
}));
