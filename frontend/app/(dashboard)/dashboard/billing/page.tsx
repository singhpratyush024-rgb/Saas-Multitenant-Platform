"use client";
// app/(dashboard)/dashboard/billing/page.tsx

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getPlans,
  getBillingStatus,
  getUsage,
  subscribe,
  cancelSubscription,
  type Plan,
} from "@/lib/api/billing";
import { useRole } from "@/hooks/use-role";
import { useToast } from "@/hooks/use-toast";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import {
  Loader2,
  Check,
  CreditCard,
  Zap,
  AlertTriangle,
  TrendingUp,
  ExternalLink,
  FileText,
} from "lucide-react";

function UsageBar({
  label,
  used,
  limit,
  percent,
}: {
  label: string;
  used: number;
  limit: number;
  percent: number | null;
}) {
  const pct = Math.min(percent ?? 0, 100);
  const unlimited = limit === -1;
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium text-foreground">
          {used}
          {!unlimited && (
            <span className="text-muted-foreground font-normal"> / {limit}</span>
          )}
        </span>
      </div>
      {!unlimited && (
        <div className="h-1.5 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{
              width: `${pct}%`,
              background:
                pct > 90
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

export default function BillingPage() {
  const { can } = useRole();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [cancelOpen, setCancelOpen] = useState(false);
  const [subscribingPlan, setSubscribingPlan] = useState<string | null>(null);

  const { data: plans = [], isLoading: plansLoading } = useQuery({
    queryKey: ["billing-plans"],
    queryFn: getPlans,
  });

  const { data: status } = useQuery({
    queryKey: ["billing-status"],
    queryFn: getBillingStatus,
  });

  const { data: usage } = useQuery({
    queryKey: ["billing-usage"],
    queryFn: getUsage,
  });

  const subscribeMutation = useMutation({
    mutationFn: subscribe,
    onSuccess: (data) => {
      window.location.href = data.checkout_url;
    },
    onError: (e: any) => {
      setSubscribingPlan(null);
      toast({
        variant: "destructive",
        title: "Subscription failed",
        description: e?.response?.data?.detail ?? "Please check your Stripe configuration.",
      });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: cancelSubscription,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["billing-status"] });
      setCancelOpen(false);
      toast({
        title: "Subscription cancelled",
        description: "Access continues until the end of your billing period.",
      });
    },
    onError: (e: any) =>
      toast({ variant: "destructive", title: "Cancellation failed", description: e?.response?.data?.detail }),
  });

  const handleSubscribe = (planKey: string) => {
    setSubscribingPlan(planKey);
    subscribeMutation.mutate({ plan_key: planKey });
  };

  return (
    <div
      className="space-y-8 animate-fade-in max-w-5xl"
      style={{ fontFamily: "'DM Sans', system-ui, sans-serif" }}
    >
      <div>
        <h1 className="text-2xl font-bold tracking-tight" style={{ letterSpacing: "-0.025em" }}>
          Billing
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          Manage your subscription, usage and invoices
        </p>
      </div>

      {/* Status card */}
      {status && (
        <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-rose-100 rounded-xl flex items-center justify-center">
                <CreditCard className="w-5 h-5 text-rose-600" />
              </div>
              <div>
                <p className="font-semibold text-foreground">{status.plan_name} plan</p>
                <p className="text-sm text-muted-foreground capitalize">
                  {status.stripe_subscription_status ?? "No active subscription"}
                </p>
              </div>
            </div>
            {can.manageBilling && status.stripe_subscription_status === "active" && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCancelOpen(true)}
                className="text-destructive border-destructive/30 hover:bg-destructive/5"
              >
                Cancel subscription
              </Button>
            )}
          </div>

          {status.trial?.active && (
            <div className="flex items-center gap-2 text-sm bg-amber-50 border border-amber-200 text-amber-700 rounded-xl px-4 py-3">
              <Zap className="w-4 h-4 shrink-0" />
              Trial active — {status.trial.days_left} days remaining until{" "}
              {new Date(status.trial.ends_at).toLocaleDateString()}
            </div>
          )}

          {status.grace_period?.active && (
            <div className="flex items-center gap-2 text-sm bg-red-50 border border-red-200 text-destructive rounded-xl px-4 py-3">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              Payment failed — grace period ends in {status.grace_period.days_left} days
            </div>
          )}
        </div>
      )}

      {/* Usage */}
      {usage && (
        <div className="bg-card border border-border rounded-2xl p-6 space-y-5">
          <div className="flex items-center gap-3 mb-1">
            <TrendingUp className="w-4 h-4 text-muted-foreground" />
            <h2 className="font-semibold text-foreground">Usage</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
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
              label="Storage (MB)"
              used={usage.usage.storage_mb.used}
              limit={usage.usage.storage_mb.limit}
              percent={usage.usage.storage_mb.percent}
            />
            <div className="space-y-1.5">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">API access</span>
                <span
                  className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                    usage.features.can_use_api
                      ? "bg-green-100 text-green-700"
                      : "bg-muted text-muted-foreground"
                  }`}
                >
                  {usage.features.can_use_api ? "Enabled" : "Not available"}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Plans */}
      <div className="space-y-4">
        <h2 className="font-semibold text-foreground">Plans</h2>
        {plansLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {plans.map((plan) => {
              const isCurrent = plan.current;
              const limits = plan.limits as Record<string, unknown>;
              const isSubscribing = subscribingPlan === plan.key;

              return (
                <div
                  key={plan.key}
                  className={`bg-card border rounded-2xl p-5 flex flex-col gap-4 ${
                    isCurrent
                      ? "border-rose-300 shadow-sm ring-1 ring-rose-100"
                      : "border-border"
                  }`}
                >
                  {isCurrent && (
                    <span className="text-xs font-semibold text-rose-600 bg-rose-50 px-2.5 py-1 rounded-full w-fit border border-rose-200">
                      Current plan
                    </span>
                  )}
                  <div>
                    <p className="font-bold text-foreground" style={{ fontSize: "15px" }}>
                      {plan.name}
                    </p>
                    <p className="text-2xl font-bold text-foreground mt-1" style={{ letterSpacing: "-0.025em" }}>
                      {plan.price_display}
                    </p>
                  </div>

                  <ul className="space-y-2 flex-1">
                    {[
                      `${limits.max_members === -1 ? "Unlimited" : limits.max_members} members`,
                      `${limits.max_projects === -1 ? "Unlimited" : limits.max_projects} projects`,
                      `${limits.max_storage_mb === -1 ? "Unlimited" : limits.max_storage_mb} MB storage`,
                      limits.can_use_api ? "API access" : null,
                    ]
                      .filter(Boolean)
                      .map((feat) => (
                        <li
                          key={feat as string}
                          className="flex items-center gap-2 text-sm text-muted-foreground"
                        >
                          <Check className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                          {feat}
                        </li>
                      ))}
                  </ul>

                  {can.manageBilling && !isCurrent && plan.key !== "free" && (
                    <Button
                      size="sm"
                      className="w-full"
                      disabled={subscribeMutation.isPending}
                      onClick={() => handleSubscribe(plan.key)}
                    >
                      {isSubscribing ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        `Upgrade to ${plan.name}`
                      )}
                    </Button>
                  )}

                  {can.manageBilling && !isCurrent && plan.key !== "free" && plan.trial_available && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-full"
                      disabled={subscribeMutation.isPending}
                      onClick={() =>
                        subscribeMutation.mutate({ plan_key: plan.key, trial: true })
                      }
                    >
                      Start free trial
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Invoices placeholder */}
      <div className="bg-card border border-border rounded-2xl p-6">
        <div className="flex items-center gap-3 mb-4">
          <FileText className="w-4 h-4 text-muted-foreground" />
          <h2 className="font-semibold text-foreground">Invoices</h2>
        </div>
        {status?.stripe_subscription_status ? (
          <p className="text-sm text-muted-foreground">
            Invoice history is available in your{" "}
            <button className="text-foreground underline underline-offset-2 inline-flex items-center gap-1">
              Stripe billing portal <ExternalLink style={{ width: "12px", height: "12px" }} />
            </button>
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">
            No invoices yet. Subscribe to a paid plan to see your billing history.
          </p>
        )}
      </div>

      {/* Cancel confirm */}
      <ConfirmDialog
        open={cancelOpen}
        onOpenChange={setCancelOpen}
        title="Cancel subscription"
        description="Your subscription will be cancelled at the end of the current billing period. You'll retain access until then."
        confirmLabel="Cancel subscription"
        destructive
        loading={cancelMutation.isPending}
        onConfirm={() => cancelMutation.mutate()}
      />
    </div>
  );
}