import { create } from "zustand";
import { authApi, User } from "../api/client";

interface AuthState {
  user: User | null;
  loading: boolean;
  checked: boolean; // have we done the initial /auth/me check?
  checkAuth: () => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: true,
  checked: false,

  checkAuth: async () => {
    set({ loading: true });
    try {
      const { data } = await authApi.me();
      set({ user: data, loading: false, checked: true });
    } catch {
      set({ user: null, loading: false, checked: true });
    }
  },

  logout: async () => {
    try {
      await authApi.logout();
    } finally {
      set({ user: null });
      window.location.href = "/login";
    }
  },
}));
