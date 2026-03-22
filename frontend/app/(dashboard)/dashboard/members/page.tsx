"use client";
// app/(dashboard)/dashboard/members/page.tsx

import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getMembers,
  deleteMember,
  inviteMember,
  changeMemberRole,
  type Member,
} from "@/lib/api/members";
import { useRole } from "@/hooks/use-role";
import { useAuthStore } from "@/store/auth.store";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SearchInput } from "@/components/ui/search-input";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Users,
  UserPlus,
  Loader2,
  Crown,
  Shield,
  MoreHorizontal,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

const PAGE_SIZE = 10;

const ROLE_STYLE: Record<string, string> = {
  owner: "bg-rose-100 text-rose-700 border-rose-200",
  admin: "bg-blue-100 text-blue-700 border-blue-200",
  member: "bg-gray-100 text-gray-600 border-gray-200",
};

const ROLE_ICON: Record<string, React.ElementType> = {
  owner: Crown,
  admin: Shield,
  member: Users,
};

const ROLE_NAMES = ["owner", "admin", "member"];

function EmptyState({ filtered }: { filtered: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mb-4">
        <Users className="w-8 h-8 text-muted-foreground" />
      </div>
      <h3 className="font-semibold text-foreground mb-1">
        {filtered ? "No matching members" : "No members yet"}
      </h3>
      <p className="text-sm text-muted-foreground">
        {filtered ? "Try a different search." : "Invite your team to get started."}
      </p>
    </div>
  );
}

export default function MembersPage() {
  const { can, isOwner } = useRole();
  const { user } = useAuthStore();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteForm, setInviteForm] = useState({ email: "", role: "member" });
  const [deleteTarget, setDeleteTarget] = useState<Member | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["members", page],
    queryFn: () => getMembers(page, PAGE_SIZE),
  });

  const members = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const roleIdMap = useMemo(() => {
    const map: Record<string, number> = {
      owner: 1,
      admin: 2,
      member: 3,
    };
    members.forEach((m) => { if (m.role_id) map[m.role] = m.role_id; });
    return map;
  }, [members]);

  const filtered = useMemo(
    () => members.filter((m) => m.email.toLowerCase().includes(search.toLowerCase())),
    [members, search]
  );

  const inviteMutation = useMutation({
    mutationFn: inviteMember,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["members"] });
      setInviteOpen(false);
      setInviteForm({ email: "", role: "member" });
      toast({ title: "Invitation sent", description: `Invite sent to ${inviteForm.email}` });
    },
    onError: (e: any) =>
      toast({ variant: "destructive", title: "Failed to invite", description: e?.response?.data?.detail }),
  });

  const roleMutation = useMutation({
    mutationFn: ({ memberId, roleId }: { memberId: number; roleId: number }) =>
      changeMemberRole(memberId, roleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["members"] });
      toast({ title: "Role updated" });
    },
    onError: (e: any) =>
      toast({ variant: "destructive", title: "Failed to update role", description: e?.response?.data?.detail }),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteMember,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["members"] });
      setDeleteTarget(null);
      toast({ title: "Member removed" });
    },
    onError: (e: any) =>
      toast({ variant: "destructive", title: "Failed to remove", description: e?.response?.data?.detail }),
  });

  const getRoleId = (roleName: string): number | null => {
    return roleIdMap[roleName] ?? null;
  };

  return (
    <div className="space-y-6 animate-fade-in" style={{ fontFamily: "'DM Sans', system-ui, sans-serif" }}>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ letterSpacing: "-0.025em" }}>
            Members
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            {total} member{total !== 1 ? "s" : ""} in this workspace
          </p>
        </div>
        {can.inviteMembers && (
          <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
            <DialogTrigger asChild>
              <Button size="sm" className="gap-2">
                <UserPlus className="w-4 h-4" />
                Invite member
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Invite a member</DialogTitle>
              </DialogHeader>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  inviteMutation.mutate({
                    email: inviteForm.email,
                    role_id: roleIdMap[inviteForm.role] ?? 3,
                  });
                }}
                className="space-y-4 mt-2"
              >
                <div className="space-y-2">
                  <Label>Email address</Label>
                  <Input
                    type="email"
                    placeholder="colleague@company.com"
                    value={inviteForm.email}
                    onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })}
                    required
                    disabled={inviteMutation.isPending}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Role</Label>
                  <select
                    className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                    value={inviteForm.role}
                    onChange={(e) => setInviteForm({ ...inviteForm, role: e.target.value })}
                    disabled={inviteMutation.isPending}
                  >
                    <option value="member">Member</option>
                    <option value="admin">Admin</option>
                    {isOwner && <option value="owner">Owner</option>}
                  </select>
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <Button type="button" variant="outline" onClick={() => setInviteOpen(false)}>
                    Cancel
                  </Button>
                  <Button type="submit" disabled={inviteMutation.isPending}>
                    {inviteMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Send invite
                  </Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        )}
      </div>

      <SearchInput
        value={search}
        onChange={(v) => { setSearch(v); setPage(1); }}
        placeholder="Search members…"
        className="max-w-xs"
      />

      {isLoading ? (
        <div className="flex items-center justify-center py-24">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState filtered={!!search} />
      ) : (
        <div className="bg-card border border-border rounded-2xl overflow-hidden">
          <div className="grid grid-cols-[1fr,auto,auto] gap-4 px-5 py-3 border-b border-border bg-muted/30">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Member</p>
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Role</p>
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground w-8" />
          </div>

          {filtered.map((member, i) => {
            const RoleIcon = ROLE_ICON[member.role] ?? Users;
            const isSelf = member.id === user?.id;
            const isOwnerMember = member.role === "owner";

            return (
              <div
                key={member.id}
                className={`grid grid-cols-[1fr,auto,auto] gap-4 items-center px-5 py-3.5 ${
                  i !== filtered.length - 1 ? "border-b border-border" : ""
                }`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-full bg-rose-100 flex items-center justify-center shrink-0">
                    <span className="text-xs font-bold text-rose-700">
                      {member.email[0].toUpperCase()}
                    </span>
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {member.email}
                      {isSelf && (
                        <span className="ml-1.5 text-xs text-muted-foreground font-normal">(you)</span>
                      )}
                    </p>
                  </div>
                </div>

                <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border ${ROLE_STYLE[member.role] ?? ROLE_STYLE.member}`}>
                  <RoleIcon style={{ width: "11px", height: "11px" }} />
                  {member.role.charAt(0).toUpperCase() + member.role.slice(1)}
                </span>

                {!isSelf && (can.changeRoles || can.deleteMembers) ? (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button className="w-8 h-8 flex items-center justify-center rounded-md hover:bg-accent text-muted-foreground hover:text-foreground transition-colors">
                        <MoreHorizontal style={{ width: "16px", height: "16px" }} />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-44">
                      {can.changeRoles && !isOwnerMember && (
                        <>
                          {ROLE_NAMES.filter((r) => r !== member.role && r !== "owner").map((roleName) => {
                            const roleId = getRoleId(roleName);
                            return (
                              <DropdownMenuItem
                                key={roleName}
                                onClick={() => roleId && roleMutation.mutate({ memberId: member.id, roleId })}
                                disabled={!roleId}
                              >
                                Make {roleName}
                              </DropdownMenuItem>
                            );
                          })}
                          <DropdownMenuSeparator />
                        </>
                      )}
                      {can.deleteMembers && !isOwnerMember && (
                        <DropdownMenuItem
                          className="text-destructive focus:text-destructive"
                          onClick={() => setDeleteTarget(member)}
                        >
                          Remove member
                        </DropdownMenuItem>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                ) : (
                  <div className="w-8" />
                )}
              </div>
            );
          })}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-2">
          <p className="text-sm text-muted-foreground">
            Page {page} of {totalPages} · {total} total
          </p>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}>
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Remove member"
        description={`Remove ${deleteTarget?.email} from this workspace? They will lose all access immediately.`}
        confirmLabel="Remove"
        destructive
        loading={deleteMutation.isPending}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
      />
    </div>
  );
}