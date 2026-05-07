"use client";

import { Auth0ConfigPanel } from "@/components/auth0-config-panel";
import { AssistantModal } from "@/components/assistant-modal";
import { Thread } from "@/components/thread";
import { WorkflowMonitor } from "@/components/workflow-monitor";

export function WorkflowSample() {
  return (
    <main className="grid min-h-screen grid-cols-1 bg-background lg:grid-cols-[440px_minmax(0,1fr)]">
      <Auth0ConfigPanel />
      <section className="grid min-h-screen min-w-0 grid-rows-[minmax(0,1fr)] lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="flex min-h-0 flex-col">
          <div className="border-b border-border bg-white px-5 py-4">
            <h2 className="text-lg font-semibold">Supervisor Chat</h2>
          </div>
          <Thread />
        </div>
        <WorkflowMonitor />
      </section>
      <AssistantModal />
    </main>
  );
}
