"use client";
// hooks/use-role.ts
// Returns helpers for role-based UI rendering.
//
// Usage:
//   const { isOwner, can } = useRole();
//   {can("delete") && <DeleteButton />}

import { useAuthStore } from "@/store/auth.store";

type Role = "owner" | "admin" | "member";

const ROLE_RANK: Record<Role, number> = {
  owner: 3,
  admin: 2,
  member: 1,
};

export function useRole() {
  const user = useAuthStore((s) => s.user);
  const role = (user?.role ?? "member") as Role;

  const isOwner = role === "owner";
  const isAdmin = role === "admin";
  const isMember = role === "member";
  const isAtLeast = (min: Role) => ROLE_RANK[role] >= ROLE_RANK[min];

  // Semantic permission shortcuts
  const can = {
    createProject: isAtLeast("member"),
    deleteProject: isAtLeast("admin"),
    inviteMembers: isAtLeast("admin"),
    changeRoles: isOwner,
    deleteMembers: isAtLeast("admin"),
    viewBilling: isAtLeast("member"),
    manageBilling: isOwner,
    viewAudit: isAtLeast("admin"),
  };

  return { role, isOwner, isAdmin, isMember, isAtLeast, can };
}