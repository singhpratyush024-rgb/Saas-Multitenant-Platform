"use client";
// app/(dashboard)/dashboard/settings/page.tsx

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth.store";
import { useRole } from "@/hooks/use-role";
import { useToast } from "@/hooks/use-toast";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import api from "@/lib/axios";
import { Loader2, User, Building2, Shield, LogOut } from "lucide-react";
import { useRouter } from "next/navigation";

function Section({ title, description, children }: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-card border border-border rounded-2xl overflow-hidden">
      <div className="px-6 py-5 border-b border-border">
        <h2 className="font-semibold text-foreground">{title}</h2>
        <p className="text-sm text-muted-foreground mt-0.5">{description}</p>
      </div>
      <div className="px-6 py-5">{children}</div>
    </div>
  );
}

export default function SettingsPage() {
  const { user, tenantSlug, logout } = useAuthStore();
  const { isOwner } = useRole();
  const { toast } = useToast();
  const router = useRouter();

  const [profileForm, setProfileForm] = useState({
    email: user?.email ?? "",
  });
  const [passwordForm, setPasswordForm] = useState({
    current: "",
    new: "",
    confirm: "",
  });
  const [logoutAllOpen, setLogoutAllOpen] = useState(false);

  const updateProfileMutation = useMutation({
    mutationFn: async (data: { email: string }) => {
      const res = await api.patch("/members/me", data);
      return res.data;
    },
    onSuccess: () => toast({ title: "Profile updated" }),
    onError: (e: any) =>
      toast({ variant: "destructive", title: "Failed", description: e?.response?.data?.detail }),
  });

  const updatePasswordMutation = useMutation({
    mutationFn: async (data: { current_password: string; new_password: string }) => {
      const res = await api.post("/auth/change-password", data);
      return res.data;
    },
    onSuccess: () => {
      setPasswordForm({ current: "", new: "", confirm: "" });
      toast({ title: "Password updated" });
    },
    onError: (e: any) =>
      toast({ variant: "destructive", title: "Failed", description: e?.response?.data?.detail }),
  });

  const handlePasswordSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (passwordForm.new !== passwordForm.confirm) {
      toast({ variant: "destructive", title: "Passwords don't match" });
      return;
    }
    updatePasswordMutation.mutate({
      current_password: passwordForm.current,
      new_password: passwordForm.new,
    });
  };

  const handleLogout = () => {
    logout();
    document.cookie = "access_token=; path=/; max-age=0";
    router.push("/login");
  };

  return (
    <div
      className="space-y-6 animate-fade-in max-w-2xl"
      style={{ fontFamily: "'DM Sans', system-ui, sans-serif" }}
    >
      <div>
        <h1 className="text-2xl font-bold tracking-tight" style={{ letterSpacing: "-0.025em" }}>
          Settings
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          Manage your profile and workspace settings
        </p>
      </div>

      {/* Profile */}
      <Section title="Your profile" description="Update your account details">
        <form
          onSubmit={(e) => { e.preventDefault(); updateProfileMutation.mutate(profileForm); }}
          className="space-y-4"
        >
          <div className="flex items-center gap-4 mb-5">
            <div className="w-14 h-14 rounded-full bg-rose-100 flex items-center justify-center shrink-0">
              <span className="text-xl font-bold text-rose-700">
                {user?.email?.[0]?.toUpperCase()}
              </span>
            </div>
            <div>
              <p className="font-medium text-foreground">{user?.email}</p>
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full capitalize ${
                user?.role === "owner"
                  ? "bg-rose-100 text-rose-700"
                  : user?.role === "admin"
                  ? "bg-blue-100 text-blue-700"
                  : "bg-gray-100 text-gray-600"
              }`}>
                {user?.role}
              </span>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">Email address</Label>
            <Input
              id="email"
              type="email"
              value={profileForm.email}
              onChange={(e) => setProfileForm({ email: e.target.value })}
              disabled={updateProfileMutation.isPending}
            />
          </div>

          <Button type="submit" size="sm" disabled={updateProfileMutation.isPending}>
            {updateProfileMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save changes
          </Button>
        </form>
      </Section>

      {/* Password */}
      <Section title="Password" description="Change your login password">
        <form onSubmit={handlePasswordSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="current">Current password</Label>
            <Input
              id="current"
              type="password"
              placeholder="••••••••"
              value={passwordForm.current}
              onChange={(e) => setPasswordForm({ ...passwordForm, current: e.target.value })}
              disabled={updatePasswordMutation.isPending}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="new-password">New password</Label>
            <Input
              id="new-password"
              type="password"
              placeholder="••••••••"
              value={passwordForm.new}
              onChange={(e) => setPasswordForm({ ...passwordForm, new: e.target.value })}
              disabled={updatePasswordMutation.isPending}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirm-password">Confirm new password</Label>
            <Input
              id="confirm-password"
              type="password"
              placeholder="••••••••"
              value={passwordForm.confirm}
              onChange={(e) => setPasswordForm({ ...passwordForm, confirm: e.target.value })}
              disabled={updatePasswordMutation.isPending}
            />
          </div>
          <Button type="submit" size="sm" disabled={updatePasswordMutation.isPending}>
            {updatePasswordMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Update password
          </Button>
        </form>
      </Section>

      {/* Workspace */}
      <Section
        title="Workspace"
        description="Information about your current workspace"
      >
        <div className="space-y-4">
          <div className="flex items-center gap-3 p-4 bg-muted/40 rounded-xl">
            <Building2 className="w-5 h-5 text-muted-foreground shrink-0" />
            <div>
              <p className="text-sm font-medium text-foreground">{tenantSlug}</p>
              <p className="text-xs text-muted-foreground">Workspace slug</p>
            </div>
          </div>
          <div className="flex items-center gap-3 p-4 bg-muted/40 rounded-xl">
            <Shield className="w-5 h-5 text-muted-foreground shrink-0" />
            <div>
              <p className="text-sm font-medium text-foreground capitalize">{user?.role}</p>
              <p className="text-xs text-muted-foreground">Your role in this workspace</p>
            </div>
          </div>
        </div>
      </Section>

      {/* Session */}
      <Section title="Session" description="Manage your active sessions">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">Sign out</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Sign out of your current session
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleLogout}
            className="gap-2"
          >
            <LogOut className="w-4 h-4" />
            Sign out
          </Button>
        </div>
      </Section>

      {/* Danger zone */}
      <div className="bg-card border border-destructive/30 rounded-2xl overflow-hidden">
        <div className="px-6 py-5 border-b border-destructive/20 bg-destructive/5">
          <h2 className="font-semibold text-destructive">Danger zone</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Irreversible and destructive actions
          </p>
        </div>
        <div className="px-6 py-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-foreground">Delete account</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Permanently delete your account and all associated data
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="text-destructive border-destructive/30 hover:bg-destructive/5"
              disabled={!isOwner}
              title={!isOwner ? "Only owners can delete accounts" : undefined}
            >
              Delete account
            </Button>
          </div>

          {isOwner && (
            <div className="flex items-center justify-between pt-4 border-t border-border">
              <div>
                <p className="text-sm font-medium text-foreground">Delete workspace</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Permanently delete this workspace and all its data
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="text-destructive border-destructive/30 hover:bg-destructive/5"
              >
                Delete workspace
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}