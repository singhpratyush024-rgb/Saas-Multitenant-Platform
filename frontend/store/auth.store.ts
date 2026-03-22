// store/auth.store.ts
// Zustand store for auth state.
// Syncs access_token, refresh_token, tenant_slug to localStorage
// so the Axios interceptor can read them on every request.

import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface AuthUser {
  id: number;
  email: string;
  role: string;
  tenant_id: number;
}

interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
  refreshToken: string | null;
  tenantSlug: string | null;
  isAuthenticated: boolean;

  setAuth: (params: {
    user: AuthUser;
    accessToken: string;
    refreshToken: string;
    tenantSlug: string;
  }) => void;

  setUser: (user: AuthUser) => void;
  setAccessToken: (token: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      tenantSlug: null,
      isAuthenticated: false,

      setAuth: ({ user, accessToken, refreshToken, tenantSlug }) => {
        // Mirror to raw localStorage so Axios interceptor can read without
        // waiting for Zustand hydration
        localStorage.setItem("access_token", accessToken);
        localStorage.setItem("refresh_token", refreshToken);
        localStorage.setItem("tenant_slug", tenantSlug);

        set({
          user,
          accessToken,
          refreshToken,
          tenantSlug,
          isAuthenticated: true,
        });
      },

      setUser: (user) => set({ user }),

      setAccessToken: (token) => {
        localStorage.setItem("access_token", token);
        set({ accessToken: token });
      },

      logout: () => {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("tenant_slug");
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          tenantSlug: null,
          isAuthenticated: false,
        });
      },
    }),
    {
      name: "auth-storage",
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        tenantSlug: state.tenantSlug,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);