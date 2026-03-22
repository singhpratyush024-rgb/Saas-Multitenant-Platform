"use client";
// hooks/use-websocket.ts
// Connects to the backend WebSocket using the current access token.
// Automatically reconnects on disconnect (except auth errors).
// Fires toasts and invalidates TanStack Query caches on events.

import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth.store";
import { useToast } from "@/hooks/use-toast";

const WS_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
  .replace(/^http/, "ws");

const EVENT_LABELS: Record<string, string> = {
  "project.created": "New project created",
  "project.updated": "Project updated",
  "project.deleted": "Project deleted",
  "task.created": "New task created",
  "task.updated": "Task updated",
  "task.deleted": "Task deleted",
  "member.joined": "New member joined",
  "member.removed": "Member removed",
  "member.role_changed": "Member role changed",
  "billing.plan_changed": "Billing plan changed",
  "billing.payment_failed": "Payment failed",
};

const QUERY_INVALIDATIONS: Record<string, string[]> = {
  "project.created": ["projects"],
  "project.updated": ["projects"],
  "project.deleted": ["projects"],
  "task.created": ["tasks"],
  "task.updated": ["tasks"],
  "task.deleted": ["tasks"],
  "member.joined": ["members"],
  "member.removed": ["members"],
  "member.role_changed": ["members"],
  "billing.plan_changed": ["billing-usage", "billing-status"],
};

export function useWebSocket() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { isAuthenticated, tenantSlug } = useAuthStore();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const unmountedRef = useRef(false);

  useEffect(() => {
    if (!isAuthenticated || !tenantSlug) return;
    unmountedRef.current = false;

    function getToken(): string | null {
      // Always read fresh from localStorage so we get the latest refreshed token
      return localStorage.getItem("access_token");
    }

    function connect() {
      if (unmountedRef.current) return;

      const token = getToken();
      if (!token) return;

      const url = `${WS_BASE}/ws/connect?token=${token}&tenant=${tenantSlug}`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      let pingInterval: ReturnType<typeof setInterval> | null = null;

      ws.onopen = () => {
        console.log("[WS] connected");
        pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, 25_000);
      };

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data) as {
            event: string;
            data: Record<string, unknown>;
            actor_id?: number;
          };

          if (msg.event === "connected" || msg.event === "pong") return;

          const label = EVENT_LABELS[msg.event];
          if (label) {
            const name =
              (msg.data?.name as string) ??
              (msg.data?.email as string) ??
              (msg.data?.title as string) ??
              "";
            toast({ title: label, description: name || undefined, duration: 4000 });
          }

          const keys = QUERY_INVALIDATIONS[msg.event];
          if (keys) {
            keys.forEach((key) => queryClient.invalidateQueries({ queryKey: [key] }));
          }
        } catch {
          // ignore malformed frames
        }
      };

      ws.onclose = (evt) => {
        if (pingInterval) clearInterval(pingInterval);
        console.log("[WS] closed", evt.code, evt.reason);

        // 4001 = invalid token, 4003 = forbidden — don't reconnect
        if (!unmountedRef.current && evt.code !== 4001 && evt.code !== 4003) {
          reconnectTimer.current = setTimeout(connect, 5000);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    return () => {
      unmountedRef.current = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [isAuthenticated, tenantSlug]);
}