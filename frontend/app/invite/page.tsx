"use client";
// app/invite/page.tsx
// Reads ?token= and ?tenant= from URL, shows set-password form,
// calls /invitations/accept, then logs the user in.

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth.store";
import { acceptInvite } from "@/lib/api/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { Loader2, Flower2, Mail } from "lucide-react";

export default function InvitePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setAuth } = useAuthStore();
  const { toast } = useToast();

  const inviteToken = searchParams.get("token") ?? "";
  const tenantSlug = searchParams.get("tenant") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  useEffect(() => {
    if (!inviteToken || !tenantSlug) {
      toast({
        variant: "destructive",
        title: "Invalid invite link",
        description: "This invite link is missing required parameters.",
      });
    }
  }, [inviteToken, tenantSlug]);

  const mutation = useMutation({
    mutationFn: () => {
      if (password !== confirm) throw new Error("Passwords do not match");
      return acceptInvite({ token: inviteToken, password, tenantSlug });
    },
    onSuccess: (data) => {
      const payload = JSON.parse(atob(data.access_token.split(".")[1]));
      setAuth({
        user: {
          id: payload.user_id,
          email: payload.email ?? "",
          role: payload.role,
          tenant_id: payload.tenant_id,
        },
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
        tenantSlug,
      });
      document.cookie = `access_token=${data.access_token}; path=/; max-age=${60 * 60 * 24}; SameSite=Lax`;
      toast({ title: "Welcome!", description: "Your account has been created." });
      router.push("/dashboard");
    },
    onError: (error: any) => {
      toast({
        variant: "destructive",
        title: "Failed to accept invite",
        description: error?.response?.data?.detail ?? error?.message,
      });
    },
  });

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-8">
      <div className="w-full max-w-sm space-y-8 animate-fade-in">
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center">
              <Flower2 className="w-4 h-4 text-primary-foreground" />
            </div>
            <span className="font-semibold">SaaS Platform</span>
          </div>

          <div className="bg-primary/5 border border-primary/20 rounded-xl p-4 flex items-start gap-3">
            <Mail className="w-5 h-5 text-primary mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-medium text-foreground">
                You've been invited
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Joining workspace:{" "}
                <span className="font-mono font-medium text-foreground">
                  {tenantSlug || "—"}
                </span>
              </p>
            </div>
          </div>

          <div>
            <h2 className="text-2xl font-bold tracking-tight">Set your password</h2>
            <p className="text-muted-foreground text-sm mt-1">
              Create a password to complete your account setup.
            </p>
          </div>
        </div>

        <form
          onSubmit={(e) => { e.preventDefault(); mutation.mutate(); }}
          className="space-y-4"
        >
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={mutation.isPending}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="confirm">Confirm password</Label>
            <Input
              id="confirm"
              type="password"
              placeholder="••••••••"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              disabled={mutation.isPending}
            />
          </div>

          <Button
            type="submit"
            className="w-full"
            disabled={mutation.isPending || !inviteToken || !tenantSlug}
          >
            {mutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Creating account…
              </>
            ) : (
              "Accept invite & get started"
            )}
          </Button>
        </form>
      </div>
    </div>
  );
}