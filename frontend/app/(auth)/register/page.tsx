"use client";
// app/(auth)/register/page.tsx

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useMutation } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth.store";
import { register, login } from "@/lib/api/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { Loader2, Flower2 } from "lucide-react";

export default function RegisterPage() {
  const router = useRouter();
  const { setAuth } = useAuthStore();
  const { toast } = useToast();

  const [form, setForm] = useState({
    tenantSlug: "",
    email: "",
    password: "",
    confirmPassword: "",
  });

  const mutation = useMutation({
    mutationFn: async () => {
      if (form.password !== form.confirmPassword) {
        throw new Error("Passwords do not match");
      }
      // Register then immediately log in
      await register({
        tenantSlug: form.tenantSlug,
        email: form.email,
        password: form.password,
      });
      return login({
        tenantSlug: form.tenantSlug,
        email: form.email,
        password: form.password,
      });
    },
    onSuccess: (data) => {
      const payload = JSON.parse(atob(data.access_token.split(".")[1]));
      setAuth({
        user: {
          id: payload.user_id,
          email: form.email,
          role: payload.role,
          tenant_id: payload.tenant_id,
        },
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
        tenantSlug: form.tenantSlug,
      });
      document.cookie = `access_token=${data.access_token}; path=/; max-age=${60 * 60 * 24}; SameSite=Lax`;
      router.push("/dashboard");
    },
    onError: (error: any) => {
      toast({
        variant: "destructive",
        title: "Registration failed",
        description: error?.response?.data?.detail ?? error?.message ?? "Something went wrong.",
      });
    },
  });

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-8">
      <div className="w-full max-w-sm space-y-8 animate-fade-in">
        <div className="space-y-2">
          <div className="flex items-center gap-2 mb-6">
            <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center">
              <Flower2 className="w-4 h-4 text-primary-foreground" />
            </div>
            <span className="font-semibold text-foreground">SaaS Platform</span>
          </div>
          <h2 className="text-2xl font-bold tracking-tight">Create account</h2>
          <p className="text-muted-foreground text-sm">
            Already have an account?{" "}
            <Link href="/login" className="text-primary hover:underline font-medium">
              Sign in
            </Link>
          </p>
        </div>

        <form
          onSubmit={(e) => { e.preventDefault(); mutation.mutate(); }}
          className="space-y-4"
        >
          <div className="space-y-2">
            <Label htmlFor="tenant">Workspace</Label>
            <Input
              id="tenant"
              placeholder="your-company"
              value={form.tenantSlug}
              onChange={(e) => setForm({ ...form, tenantSlug: e.target.value })}
              required
              disabled={mutation.isPending}
            />
            <p className="text-xs text-muted-foreground">
              Your organization's unique workspace ID
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="you@company.com"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
              disabled={mutation.isPending}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              placeholder="••••••••"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
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
              value={form.confirmPassword}
              onChange={(e) => setForm({ ...form, confirmPassword: e.target.value })}
              required
              disabled={mutation.isPending}
            />
          </div>

          <Button type="submit" className="w-full" disabled={mutation.isPending}>
            {mutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Creating account…
              </>
            ) : (
              "Create account"
            )}
          </Button>
        </form>
      </div>
    </div>
  );
}