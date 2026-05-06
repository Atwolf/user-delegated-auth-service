"use client";

import { CheckCircle2, Play, ShieldCheck } from "lucide-react";
import type { WorkflowRecord } from "@/lib/workflow-types";

export function ApprovalCard({
  workflow,
  approving,
  onApprove
}: {
  workflow: WorkflowRecord;
  approving?: boolean;
  onApprove: () => void;
}) {
  const status = workflow.status.status;
  const executable = status === "awaiting_approval";
  const requiresHitl = status === "awaiting_approval" || status === "approved" || status === "executing";

  return (
    <article
      className="rounded-lg border border-border bg-white p-4 shadow-sm"
      data-testid="approval-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-primary">
            <ShieldCheck className="h-4 w-4" />
            {requiresHitl ? "HITL Approval" : "Workflow Manifest"}
          </div>
          <h2 className="mt-1 text-base font-semibold">{workflow.workflow_id}</h2>
          <p className="mt-1 break-all text-xs text-muted-foreground">{workflow.plan_hash}</p>
        </div>
        <span className="rounded-md border border-border px-2 py-1 text-xs font-semibold uppercase">
          {status.replace("_", " ")}
        </span>
      </div>

      <div className="mt-4 grid gap-3">
        {workflow.plan.steps.map((step, index) => (
          <section key={step.step_id} className="rounded-md border border-border p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-semibold">
                {index + 1}. {step.action}
              </div>
              <div className="text-xs text-muted-foreground">{step.target_agent}</div>
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              {step.operation_type ? (
                <span className="rounded-md bg-slate-100 px-2 py-1 font-medium text-slate-800">
                  {step.operation_type}
                </span>
              ) : null}
              {step.blast_radius ? (
                <span className="rounded-md bg-amber-50 px-2 py-1 font-medium text-amber-900">
                  Blast radius: {step.blast_radius}
                </span>
              ) : null}
            </div>
            {step.hitl_description ? (
              <p className="mt-2 text-sm text-muted-foreground">{step.hitl_description}</p>
            ) : null}
            <pre className="mt-2 overflow-x-auto rounded-md bg-muted p-2 text-xs">
              {JSON.stringify(JSON.parse(step.input_payload_json), null, 2)}
            </pre>
            <div className="mt-2 flex flex-wrap gap-2">
              {step.required_scopes.map((scope) => (
                <span
                  className="rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-800"
                  key={scope}
                >
                  {scope}
                </span>
              ))}
            </div>
          </section>
        ))}
      </div>

      <div className="mt-4 border-t border-border pt-3">
        <div className="flex flex-wrap gap-2">
          {workflow.authorization.scopes.map((scope) => (
            <span
              className="rounded-md bg-cyan-50 px-2 py-1 text-xs font-medium text-cyan-900"
              key={scope}
            >
              {scope}
            </span>
          ))}
        </div>
      </div>

      <button
        className="mt-4 inline-flex h-10 items-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-accent-foreground disabled:opacity-50"
        disabled={!executable || approving}
        onClick={onApprove}
        type="button"
        title="Approve workflow"
      >
        {status === "completed" ? <CheckCircle2 className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        {status === "completed" ? "Completed" : approving ? "Approving" : "Approve workflow"}
      </button>
    </article>
  );
}
