"use client";
// context/auth.context.tsx
// Provides auth state to the entire app.
// Hydrates user profile from /members/me on mount if a token exists.

import React, { createContext, useContext, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth.store";
import { getMe, type MeResponse } from "@/lib/api/auth";

interface AuthContextValue {
  user: MeResponse | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  refetchUser: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  isLoading: true,
  isAuthenticated: false,
  refetchUser: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, setUser, logout } = useAuthStore();
  const queryClient = useQueryClient();

  const {
    data: user,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ["me"],
    queryFn: getMe,
    enabled: isAuthenticated,
    retry: false,
    staleTime: 1000 * 60 * 5, // 5 min
    // If /members/me returns 401, clear auth
    throwOnError: false,
  });

  // Sync fetched user into Zustand store
  useEffect(() => {
    if (user) setUser(user);
  }, [user, setUser]);

  // Handle failed /me fetch — clear auth
  const handleLogout = () => {
    logout();
    queryClient.clear();
  };

  return (
    <AuthContext.Provider
      value={{
        user: user ?? null,
        isLoading: isAuthenticated ? isLoading : false,
        isAuthenticated,
        refetchUser: refetch,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}