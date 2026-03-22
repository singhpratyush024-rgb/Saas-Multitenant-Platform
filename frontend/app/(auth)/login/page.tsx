"use client";
// app/(auth)/login/page.tsx

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useMutation } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth.store";
import { login } from "@/lib/api/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { Loader2 } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setAuth } = useAuthStore();
  const { toast } = useToast();

  const [form, setForm] = useState({ tenantSlug: "", email: "", password: "" });

  const mutation = useMutation({
    mutationFn: login,
    onSuccess: (data) => {
      const payload = JSON.parse(atob(data.access_token.split(".")[1]));
      setAuth({
        user: { id: payload.user_id, email: form.email, role: payload.role, tenant_id: payload.tenant_id },
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
        tenantSlug: form.tenantSlug,
      });
      document.cookie = `access_token=${data.access_token}; path=/; max-age=${60 * 60 * 24}; SameSite=Lax`;
      router.push(searchParams.get("next") ?? "/dashboard");
    },
    onError: (error: any) => {
      toast({
        variant: "destructive",
        title: "Sign in failed",
        description: error?.response?.data?.detail ?? "Check your credentials and try again.",
      });
    },
  });

  return (
    <div className="min-h-screen flex" style={{ fontFamily: "'DM Sans', system-ui, sans-serif" }}>

      {/* ── Left panel ─────────────────────────────────────────── */}
      <div
        className="hidden lg:flex lg:w-[52%] relative overflow-hidden flex-col justify-between p-14"
        style={{ background: "#fdf4f5" }}
      >
        {/* Subtle SVG background */}
        <svg className="absolute inset-0 w-full h-full" viewBox="0 0 600 800" preserveAspectRatio="xMidYMid slice">
          {/* Soft rose circle top-right */}
          <circle cx="560" cy="120" r="320" fill="rgba(225,29,72,0.06)" />
          <circle cx="560" cy="120" r="200" fill="rgba(225,29,72,0.05)" />
          {/* Dot grid */}
          {Array.from({ length: 10 }).map((_, row) =>
            Array.from({ length: 7 }).map((_, col) => (
              <circle
                key={`${row}-${col}`}
                cx={col * 90 + 45}
                cy={row * 84 + 50}
                r="1.5"
                fill="rgba(225,29,72,0.12)"
              />
            ))
          )}
          {/* Bottom arc */}
          <circle cx="60" cy="780" r="180" fill="none" stroke="rgba(225,29,72,0.1)" strokeWidth="1" />
          <circle cx="60" cy="780" r="120" fill="none" stroke="rgba(225,29,72,0.08)" strokeWidth="1" />
        </svg>

        {/* Logo */}
        <div className="relative z-10 flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center bg-rose-600">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path d="M9 2L16 6V12L9 16L2 12V6L9 2Z" fill="white" fillOpacity="0.95" />
              <path d="M9 6L13 8.5V11.5L9 14L5 11.5V8.5L9 6Z" fill="white" fillOpacity="0.35" />
            </svg>
          </div>
          <span className="font-semibold text-gray-900 tracking-tight">SaaS Platform</span>
        </div>

        {/* Centre content */}
        <div className="relative z-10 space-y-6">
          <div
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium"
            style={{ background: "rgba(225,29,72,0.08)", color: "rgba(180,20,55,0.9)" }}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse inline-block" />
            Multi-tenant · Role-based · Real-time
          </div>

          <h1
            className="font-bold text-gray-900 leading-tight"
            style={{ fontSize: "clamp(30px, 3.5vw, 46px)", letterSpacing: "-0.03em" }}
          >
            Your team's<br />
            <span style={{ color: "hsl(346.8 77.2% 49.8%)" }}>command centre</span>
          </h1>

          <p className="text-gray-500 leading-relaxed" style={{ fontSize: "15px", maxWidth: "320px" }}>
            Projects, tasks, members and billing — all in one place, isolated per workspace.
          </p>

          {/* Single stat row */}
          <div className="flex items-center gap-6 pt-2">
            {[
              { value: "4", label: "Permission levels" },
              { value: "∞", label: "Workspaces" },
              { value: "Live", label: "WebSocket sync" },
            ].map((s) => (
              <div key={s.label}>
                <p className="font-bold text-gray-900" style={{ fontSize: "20px", letterSpacing: "-0.02em" }}>
                  {s.value}
                </p>
                <p className="text-gray-400" style={{ fontSize: "12px" }}>{s.label}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Bottom */}
        <div className="relative z-10">
          <p className="text-gray-400" style={{ fontSize: "12px" }}>
            FastAPI · Next.js · PostgreSQL · Stripe
          </p>
        </div>
      </div>

      {/* ── Right panel — form ──────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center p-8 bg-background">
        <div className="w-full max-w-[380px] space-y-7 animate-fade-in">

          {/* Mobile logo */}
          <div className="flex items-center gap-2 lg:hidden">
            <div className="w-8 h-8 rounded-xl flex items-center justify-center bg-rose-600">
              <svg width="16" height="16" viewBox="0 0 18 18" fill="none">
                <path d="M9 2L16 6V12L9 16L2 12V6L9 2Z" fill="white" fillOpacity="0.95" />
              </svg>
            </div>
            <span className="font-semibold text-foreground">SaaS Platform</span>
          </div>

          <div className="space-y-1.5">
            <h2
              className="font-bold text-foreground"
              style={{ fontSize: "26px", letterSpacing: "-0.03em" }}
            >
              Welcome back
            </h2>
            <p className="text-muted-foreground text-sm">
              No account?{" "}
              <Link
                href="/register"
                className="font-medium underline underline-offset-4"
                style={{ color: "hsl(346.8 77.2% 49.8%)" }}
              >
                Create one free
              </Link>
            </p>
          </div>

          <form
            onSubmit={(e) => { e.preventDefault(); mutation.mutate(form); }}
            className="space-y-4"
          >
            <div className="space-y-1.5">
              <Label htmlFor="tenant" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Workspace
              </Label>
              <Input
                id="tenant"
                placeholder="your-company"
                value={form.tenantSlug}
                onChange={(e) => setForm({ ...form, tenantSlug: e.target.value })}
                required
                disabled={mutation.isPending}
                className="h-11"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="email" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Email
              </Label>
              <Input
                id="email"
                type="email"
                placeholder="you@company.com"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                required
                disabled={mutation.isPending}
                className="h-11"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Password
              </Label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                required
                disabled={mutation.isPending}
                className="h-11"
              />
            </div>

            <Button
              type="submit"
              className="w-full h-11 font-semibold text-sm"
              disabled={mutation.isPending}
              style={{ background: "hsl(346.8 77.2% 49.8%)", color: "white" }}
            >
              {mutation.isPending ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Signing in…</>
              ) : (
                "Sign in →"
              )}
            </Button>
          </form>

          <p className="text-xs text-center text-muted-foreground">
            By signing in you agree to our{" "}
            <span className="underline underline-offset-2 cursor-pointer">Terms</span>
            {" & "}
            <span className="underline underline-offset-2 cursor-pointer">Privacy</span>
          </p>
        </div>
      </div>
    </div>
  );
}