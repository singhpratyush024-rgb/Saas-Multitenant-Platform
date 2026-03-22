// lib/api/billing.ts

import api from "@/lib/axios";

export interface Plan {
  key: string;
  name: string;
  price_usd_cents: number;
  price_display: string;
  limits: Record<string, unknown>;
  current: boolean;
  trial_available: boolean;
}

export interface BillingStatus {
  plan: string;
  plan_name: string;
  limits: Record<string, unknown>;
  stripe_subscription_status: string | null;
  trial: { active: boolean; ends_at: string; days_left: number } | null;
  grace_period: { active: boolean; ends_at: string; days_left: number } | null;
}

export interface UsageSummary {
  plan: string;
  usage: {
    members: { used: number; limit: number; percent: number };
    projects: { used: number; limit: number; percent: number };
    tasks: { used: number; limit: null; percent: null };
    storage_mb: { used: number; limit: number; percent: number };
  };
  features: {
    can_use_api: boolean;
    max_members: number;
    max_projects: number;
    max_storage_mb: number;
  };
}

export async function getPlans(): Promise<Plan[]> {
  const res = await api.get<{ data: Plan[] }>("/billing/plans");
  return res.data.data;
}

export async function getBillingStatus(): Promise<BillingStatus> {
  const res = await api.get<{ data: BillingStatus }>("/billing/status");
  return res.data.data;
}

export async function getUsage(): Promise<UsageSummary> {
  const res = await api.get<{ data: UsageSummary }>("/billing/usage");
  return res.data.data;
}

export async function subscribe(data: {
  plan_key: string;
  trial?: boolean;
}): Promise<{ checkout_url: string; session_id: string }> {
  const res = await api.post<{ data: { checkout_url: string; session_id: string } }>(
    "/billing/subscribe",
    data
  );
  return res.data.data;
}

export async function cancelSubscription(): Promise<{ message: string }> {
  const res = await api.post<{ data: { message: string } }>("/billing/cancel");
  return res.data.data;
}