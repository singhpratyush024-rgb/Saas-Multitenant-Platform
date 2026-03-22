// lib/api/auth.ts

import api from "@/lib/axios";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface LoginPayload {
  tenantSlug: string;
  email: string;
  password: string;
}

export interface RegisterPayload {
  tenantSlug: string;
  email: string;
  password: string;
}

// Login — tenant slug sent as header via interceptor after being set
export async function login(payload: LoginPayload): Promise<AuthResponse> {
  // Set tenant before the request so interceptor picks it up
  localStorage.setItem("tenant_slug", payload.tenantSlug);

  const res = await api.post<AuthResponse>("/auth/login", {
    email: payload.email,
    password: payload.password,
  });
  return res.data;
}

export async function register(payload: RegisterPayload): Promise<{ message: string }> {
  localStorage.setItem("tenant_slug", payload.tenantSlug);

  const res = await api.post<{ message: string }>("/auth/register", {
    email: payload.email,
    password: payload.password,
  });
  return res.data;
}

export async function logout(token: string): Promise<void> {
  await api.post("/auth/logout", null, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export interface InviteAcceptPayload {
  token: string;
  password: string;
  tenantSlug: string;
}

export async function acceptInvite(payload: InviteAcceptPayload): Promise<AuthResponse> {
  localStorage.setItem("tenant_slug", payload.tenantSlug);
  const res = await api.post<AuthResponse>(`/invitations/accept`, {
    token: payload.token,
    password: payload.password,
  });
  return res.data;
}

export interface MeResponse {
  id: number;
  email: string;
  role: string;
  role_id: number;
  tenant_id: number;
  is_active: boolean;
  permissions: string[];
}

export async function getMe(): Promise<MeResponse> {
  const res = await api.get<{ data: MeResponse }>("/members/me");
  return res.data.data;
}