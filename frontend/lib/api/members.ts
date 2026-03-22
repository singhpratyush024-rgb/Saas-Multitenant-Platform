// lib/api/members.ts

import api from "@/lib/axios";

export interface Member {
  id: number;
  email: string;
  role: string;
  role_id: number;
  tenant_id: number;
  is_active: boolean;
}

export interface PaginatedMembers {
  total: number;
  page: number;
  page_size: number;
  items: Member[];
}

export async function getMembers(page = 1, pageSize = 20): Promise<PaginatedMembers> {
  const res = await api.get<{ data: PaginatedMembers }>("/members", {
    params: { page, page_size: pageSize },
  });
  return res.data.data;
}

export async function changeMemberRole(
  memberId: number,
  roleId: number
): Promise<Member> {
  const res = await api.patch<{ data: Member } | Member>(
    `/members${memberId}/role`,
    { role_id: roleId }
  );
  const d = res.data as any;
  return d?.data ?? d;
}

export async function deleteMember(memberId: number): Promise<void> {
  await api.delete(`/members${memberId}`);
}

// To this
export interface InvitePayload {
  email: string;
  role_id: number;
}

export async function inviteMember(data: InvitePayload): Promise<{ message: string }> {
  const res = await api.post<{ message: string }>("/invitations/", data);
  return res.data;
}

export interface Role {
  id: number;
  name: string;
  tenant_id: number;
}

export async function getRoles(): Promise<Role[]> {
  const res = await api.get<{ data: Role[] } | Role[]>("/members/roles");
  const d = res.data as any;
  return Array.isArray(d) ? d : d?.data ?? [];
}