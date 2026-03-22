"use client";
// app/(dashboard)/dashboard/page.tsx

import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth.store";
import api from "@/lib/axios";
import { FolderKanban, CheckSquare, Users, Zap, ArrowRight } from "lucide-react";
import Link from "next/link";

function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  href,
  color,
}: {
  label: string;
  value: string | number;
  sub?: string;
  icon: React.ElementType;
  href: string;
  color: string;
}) {
  return (
    <Link href={href} className="group block">
      <div className="bg-card border border-border rounded-2xl p-5 hover:border-rose-200 hover:shadow-sm transition-all duration-200">
        <div className="flex items-start justify-between mb-4">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${color}`}>
            <Icon style={{ width: "18px", height: "18px" }} />
          </div>
          <ArrowRight
            className="text-muted-foreground group-hover:text-foreground group-hover:translate-x-0.5 transition-all"
            style={{ width: "14px", height: "14px" }}
          />
        </div>
        <p className="text-2xl font-bold text-foreground tracking-tight"
          style={{ letterSpacing: "-0.02em" }}>
          {value}
        </p>
        <p className="text-sm font-medium text-foreground mt-0.5">{label}</p>
        {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
      </div>
    </Link>
  );
}

function UsageBar({ label, used, limit, percent }: {
  label: string;
  used: number;
  limit: number;
  percent: number | null;
}) {
  const pct = Math.min(percent ?? 0, 100);
  const unlimited = limit === -1;
  return (
    <div className="space-y-2">
      <div className="flex justify-between items-center">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className="text-sm font-medium text-foreground">
          {used}{!unlimited && <span className="text-muted-foreground font-normal"> / {limit}</span>}
        </span>
      </div>
      {!unlimited && (
        <div className="h-1.5 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{
              width: `${pct}%`,
              background: pct > 90
                ? "hsl(0 84% 60%)"
                : pct > 70
                ? "hsl(38 92% 50%)"
                : "hsl(346.8 77.2% 49.8%)",
            }}
          />
        </div>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const { user, tenantSlug } = useAuthStore();

  const { data: usage } = useQuery({
    queryKey: ["billing-usage"],
    queryFn: async () => {
      const res = await api.get("/billing/usage");
      return res.data.data;
    },
    enabled: !!tenantSlug,
  });

  const greeting = () => {
    const h = new Date().getHours();
    if (h < 12) return "Good morning";
    if (h < 18) return "Good afternoon";
    return "Good evening";
  };

  const name = user?.email?.split("@")[0] ?? "";

  return (
    <div
      className="space-y-8 animate-fade-in max-w-4xl"
      style={{ fontFamily: "'DM Sans', system-ui, sans-serif" }}
    >
      {/* Header */}
      <div className="space-y-1">
        <h1
          className="font-bold text-foreground"
          style={{ fontSize: "24px", letterSpacing: "-0.025em" }}
        >
          {greeting()}{name ? `, ${name}` : ""}
        </h1>
        <p className="text-muted-foreground text-sm">
          Workspace{" "}
          <span
            className="font-mono font-medium text-foreground px-1.5 py-0.5 rounded-md"
            style={{ background: "rgba(225,29,72,0.07)", color: "hsl(346.8 77.2% 49.8%)" }}
          >
            {tenantSlug}
          </span>
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Projects"
          value={usage?.usage?.projects?.used ?? "—"}
          sub={usage?.usage?.projects?.limit > 0 ? `of ${usage.usage.projects.limit} limit` : undefined}
          icon={FolderKanban}
          href="/dashboard/projects"
          color="bg-rose-100 text-rose-600"
        />
        <StatCard
          label="Tasks"
          value={usage?.usage?.tasks?.used ?? "—"}
          sub="Total across all projects"   
          icon={CheckSquare}
          href="/dashboard/tasks"
          color="bg-violet-100 text-violet-600"
        />
        <StatCard
          label="Members"
          value={usage?.usage?.members?.used ?? "—"}
          sub={usage?.usage?.members?.limit > 0 ? `of ${usage.usage.members.limit} limit` : undefined}
          icon={Users}
          href="/dashboard/members"
          color="bg-blue-100 text-blue-600"
        />
        <StatCard
          label="Plan"
          value={usage?.plan
            ? usage.plan.charAt(0).toUpperCase() + usage.plan.slice(1)
            : "—"}
          sub="Current billing plan"
          icon={Zap}
          href="/dashboard/billing"
          color="bg-amber-100 text-amber-600"
        />
      </div>

      {/* Usage */}
      {usage && (
        <div className="bg-card border border-border rounded-2xl p-6 space-y-5">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-foreground" style={{ fontSize: "15px" }}>
              Usage
            </h2>
            <Link
              href="/dashboard/billing"
              className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
            >
              View billing <ArrowRight style={{ width: "12px", height: "12px" }} />
            </Link>
          </div>
          <div className="space-y-4">
            <UsageBar
              label="Members"
              used={usage.usage.members.used}
              limit={usage.usage.members.limit}
              percent={usage.usage.members.percent}
            />
            <UsageBar
              label="Projects"
              used={usage.usage.projects.used}
              limit={usage.usage.projects.limit}
              percent={usage.usage.projects.percent}
            />
            <UsageBar
              label="Storage"
              used={usage.usage.storage_mb.used}
              limit={usage.usage.storage_mb.limit}
              percent={usage.usage.storage_mb.percent}
            />
          </div>
        </div>
      )}

      {/* Quick nav */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {[
          { label: "Create a project", href: "/dashboard/projects", desc: "Organise your work" },
          { label: "Invite a member", href: "/dashboard/members", desc: "Grow your team" },
          { label: "Manage billing", href: "/dashboard/billing", desc: "Plans & usage" },
        ].map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="group flex items-center justify-between bg-card border border-border rounded-xl px-4 py-3.5 hover:border-rose-200 transition-all duration-150"
          >
            <div>
              <p className="text-sm font-medium text-foreground">{item.label}</p>
              <p className="text-xs text-muted-foreground mt-0.5">{item.desc}</p>
            </div>
            <ArrowRight
              className="text-muted-foreground group-hover:text-rose-500 group-hover:translate-x-0.5 transition-all shrink-0"
              style={{ width: "14px", height: "14px" }}
            />
          </Link>
        ))}
      </div>
    </div>
  );
}