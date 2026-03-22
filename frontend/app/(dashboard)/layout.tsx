"use client";
// app/(dashboard)/layout.tsx

import { useWebSocket } from "@/hooks/use-websocket";
import { Sidebar } from "@/components/ui/sidebar";
import { Header } from "@/components/ui/header";

function WebSocketProvider() {
  useWebSocket();
  return null;
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen bg-background overflow-hidden">
      <WebSocketProvider />
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}