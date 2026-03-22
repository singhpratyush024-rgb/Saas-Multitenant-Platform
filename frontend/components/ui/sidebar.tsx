"use client";
// components/layout/sidebar.tsx

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import {
  LayoutDashboard,
  FolderKanban,
  CheckSquare,
  Users,
  CreditCard,
  ScrollText,
  Settings,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

const NAV_ITEMS = [
  { label: "Overview", href: "/dashboard", icon: LayoutDashboard, exact: true },
  { label: "Projects", href: "/dashboard/projects", icon: FolderKanban },
  { label: "Tasks", href: "/dashboard/tasks", icon: CheckSquare },
  { label: "Members", href: "/dashboard/members", icon: Users },
  { label: "Billing", href: "/dashboard/billing", icon: CreditCard },
  { label: "Audit Logs", href: "/dashboard/audit", icon: ScrollText, roles: ["owner", "admin"] },
  { label: "Settings", href: "/dashboard/settings", icon: Settings },
];

const ROLE_COLORS: Record<string, string> = {
  owner: "bg-rose-100 text-rose-700",
  admin: "bg-blue-100 text-blue-700",
  member: "bg-gray-100 text-gray-600",
};

export function Sidebar() {
  const pathname = usePathname();
  const { user, tenantSlug } = useAuthStore();
  const [collapsed, setCollapsed] = useState(false);

  const visibleItems = NAV_ITEMS.filter((item) => {
    if (!item.roles) return true;
    return item.roles.includes(user?.role ?? "");
  });

  const isActive = (item: (typeof NAV_ITEMS)[0]) =>
    item.exact ? pathname === item.href : pathname.startsWith(item.href);

  return (
    <aside
      className={cn(
        "relative flex flex-col border-r border-border bg-card transition-all duration-300 ease-in-out shrink-0",
        collapsed ? "w-[64px]" : "w-[220px]"
      )}
      style={{ fontFamily: "'DM Sans', system-ui, sans-serif" }}
    >
      {/* Logo */}
      <div className={cn(
        "flex items-center border-b border-border h-14 px-4 gap-3 overflow-hidden",
      )}>
        <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-rose-600 shrink-0">
          <svg width="16" height="16" viewBox="0 0 18 18" fill="none">
            <path d="M9 2L16 6V12L9 16L2 12V6L9 2Z" fill="white" fillOpacity="0.95" />
            <path d="M9 6L13 8.5V11.5L9 14L5 11.5V8.5L9 6Z" fill="white" fillOpacity="0.35" />
          </svg>
        </div>
        {!collapsed && (
          <div className="min-w-0 overflow-hidden">
            <p className="font-semibold text-sm text-foreground truncate leading-tight">
              SaaS Platform
            </p>
            <p className="text-xs text-muted-foreground truncate font-mono leading-tight mt-0.5">
              {tenantSlug}
            </p>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
        {visibleItems.map((item) => {
          const Icon = item.icon;
          const active = isActive(item);
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all duration-150",
                collapsed ? "justify-center" : "",
                active
                  ? "bg-rose-50 text-rose-700 font-medium"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground font-normal"
              )}
            >
              <Icon className={cn("shrink-0", active ? "text-rose-600" : "text-muted-foreground")}
                style={{ width: "16px", height: "16px" }} />
              {!collapsed && <span className="truncate">{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* User pill */}
      {!collapsed && user && (
        <div className="px-3 py-3 border-t border-border">
          <div className="flex items-center gap-2.5 px-1">
            <div className="w-7 h-7 rounded-full bg-rose-100 flex items-center justify-center shrink-0">
              <span className="text-xs font-bold text-rose-700">
                {user.email[0].toUpperCase()}
              </span>
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-foreground truncate leading-tight">
                {user.email}
              </p>
              <span className={cn(
                "text-xs px-1.5 py-0.5 rounded-full font-medium capitalize leading-none inline-block mt-0.5",
                ROLE_COLORS[user.role] ?? ROLE_COLORS.member
              )}>
                {user.role}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-3 top-[52px] w-6 h-6 bg-background border border-border rounded-full flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors shadow-sm z-10"
      >
        {collapsed
          ? <ChevronRight style={{ width: "12px", height: "12px" }} />
          : <ChevronLeft style={{ width: "12px", height: "12px" }} />
        }
      </button>
    </aside>
  );
}