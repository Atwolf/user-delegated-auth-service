"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, RefreshCw } from "lucide-react";
import { ApprovalCard } from "@/components/approval-card";
import type { WorkflowRecord } from "@/lib/workflow-types";

export function WorkflowMonitor() {
  const [workflow, setWorkflow] = useState<WorkflowRecord | null>(null);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const response = await fetch("/api/workflows", { cache: "no-store" });
    if (!response.ok) return;
    const payload = (await response.json()) as { workflow: WorkflowRecord | null };
    setWorkflow(payload.workflow);
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, 1200);
    return () => window.clearInterval(timer);
  }, [refresh]);

  async function approve() {
    if (!workflow) return;
    setApproving(true);
    setError(null);
    try {
      const response = await fetch(`/api/workflows/${workflow.workflow_id}/approve`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({})
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = (await response.json()) as { workflow: WorkflowRecord };
      setWorkflow(payload.workflow);
    } catch (approvalError) {
      setError(approvalError instanceof Error ? approvalError.message : "Approval failed");
    } finally {
      setApproving(false);
    }
  }

  return (
    <aside className="flex min-h-0 flex-col border-l border-border bg-[hsl(0_0%_97%)]">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Activity className="h-4 w-4 text-accent" />
          Workflow
        </div>
        <button
          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border"
          onClick={() => void refresh()}
          type="button"
          title="Refresh workflow"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {workflow ? (
          <ApprovalCard workflow={workflow} approving={approving} onApprove={approve} />
        ) : (
          <div className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
            No workflow manifest yet.
          </div>
        )}
        {error ? <div className="mt-3 text-sm font-medium text-red-700">{error}</div> : null}
      </div>
    </aside>
  );
}
