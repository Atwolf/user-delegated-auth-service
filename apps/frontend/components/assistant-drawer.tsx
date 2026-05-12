"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  AppBar as MuiAppBar,
  Box,
  Button,
  Chip,
  Divider,
  Drawer,
  IconButton,
  LinearProgress,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Stack,
  Toolbar,
  Typography
} from "@mui/material";
import {
  Bot,
  CheckCircle2,
  Loader2,
  MessageSquare,
  Plus,
  Send,
  Square,
  ShieldCheck,
  Wrench,
  X
} from "lucide-react";
import {
  AuiIf,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
  type ReasoningMessagePartProps,
  type TextMessagePartProps,
  type ToolCallMessagePartProps
} from "@assistant-ui/react";
import { SessionControls } from "@/components/session-controls";
import { useAssistantThread } from "@/components/assistant-root";
import { useWorkflowContext } from "@/components/workflow-context";

type WorkflowState = Record<string, unknown>;

type WorkflowApprovalResponse = {
  workflow?: WorkflowState;
};

export function AssistantDrawer() {
  const [open, setOpen] = useState(true);

  return (
    <>
      <button
        className="fixed bottom-5 right-5 z-30 inline-flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg"
        onClick={() => setOpen(true)}
        type="button"
        title="Open assistant"
      >
        <MessageSquare className="h-5 w-5" />
      </button>

      <Drawer
        anchor="right"
        open={open}
        variant="persistent"
        PaperProps={{
          "aria-label": "Assistant drawer",
          className:
            "flex w-full max-w-[480px] flex-col border-l border-border bg-[hsl(0_0%_97%)] shadow-2xl sm:w-[460px]"
        }}
      >
        <AppBar onClose={() => setOpen(false)} />
        <StatusBar />
        <MessageList />
        <MessageInput />
      </Drawer>
    </>
  );
}

function AppBar({ onClose }: { onClose: () => void }) {
  const { auth0Session } = useWorkflowContext();
  const { createThread, loading } = useAssistantThread();

  return (
    <MuiAppBar className="shrink-0" color="primary" elevation={3} position="static">
      <Toolbar className="flex min-h-16 justify-between gap-3 px-4">
        <div className="flex min-w-0 items-center gap-3">
          <Box className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-white/15">
            <Bot className="h-5 w-5" />
          </Box>
          <div className="min-w-0">
            <Typography className="truncate" component="h1" variant="subtitle1">
              Magnum Opus Assistant
            </Typography>
            <Typography className="truncate text-primary-foreground/80" variant="caption">
              {auth0Session ? auth0Session.persona.displayName : "Auth0 session required"}
            </Typography>
          </div>
        </div>

        <Stack direction="row" spacing={1}>
          <IconButton
            className="bg-white/10 text-primary-foreground disabled:opacity-50"
            disabled={!auth0Session || loading}
            onClick={() => void createThread()}
            size="small"
            title="New thread"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
          </IconButton>
          <IconButton
            className="bg-white/10 text-primary-foreground"
            onClick={onClose}
            size="small"
            title="Close assistant"
          >
            <X className="h-4 w-4" />
          </IconButton>
        </Stack>
      </Toolbar>
    </MuiAppBar>
  );
}

function StatusBar() {
  const { auth0Session } = useWorkflowContext();
  const { error, loading, threadId } = useAssistantThread();
  const status = auth0Session
    ? threadId
      ? "Thread ready"
      : loading
        ? "Creating thread"
        : "Thread pending"
    : "Logged out";

  return (
    <Box component="section" className="shrink-0 border-b border-border bg-muted/70 px-4 py-3">
      <div className="mb-3 flex items-center justify-between gap-3 text-xs">
        <Chip
          className="min-w-0 max-w-full justify-start"
          color={auth0Session ? "success" : "default"}
          label={status}
          size="small"
          variant="outlined"
        />
        {error ? <span className="truncate font-medium text-red-700">{error}</span> : null}
      </div>
      {loading ? <LinearProgress className="mb-3" /> : null}
      <SessionControls />
    </Box>
  );
}

function MessageList() {
  return (
    <ThreadPrimitive.Root className="flex min-h-0 flex-1 flex-col bg-white">
      <ThreadPrimitive.Viewport className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <ThreadPrimitive.Empty>
          <AssistantWelcome />
        </ThreadPrimitive.Empty>
        <ThreadPrimitive.Messages
          components={{
            UserMessage,
            AssistantMessage
          }}
        />
        <WorkflowApprovalPanel />
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  );
}

function AssistantWelcome() {
  const { auth0Session } = useWorkflowContext();

  return (
    <Box
      className="rounded-md border border-border bg-muted px-3 py-3 text-sm"
      component="section"
    >
      <div className="font-semibold text-foreground">
        {auth0Session ? auth0Session.persona.greeting : "Waiting for user session."}
      </div>
      <div className="mt-1 text-muted-foreground">
        {auth0Session
          ? sessionHeadline(auth0Session)
          : "Log in with Auth0 before sending an agent request."}
      </div>
    </Box>
  );
}

function UserMessage() {
  return <MessageBubble role="user" />;
}

function AssistantMessage() {
  return <StreamingBubble />;
}

function MessageBubble({ role }: { role: "assistant" | "user" }) {
  const isUser = role === "user";

  return (
    <MessagePrimitive.Root
      className={["mb-3 flex", isUser ? "justify-end" : "justify-start"].join(" ")}
    >
      <div
        className={[
          "max-w-[88%] rounded-md px-3 py-2 text-sm shadow-sm",
          isUser
            ? "bg-primary text-primary-foreground"
            : "border border-border bg-white text-foreground"
        ].join(" ")}
      >
        <MessagePrimitive.Content
          components={{
            Reasoning: ReasoningPart,
            Text: TextPart,
            tools: {
              Fallback: ToolCallChip
            }
          }}
        />
      </div>
    </MessagePrimitive.Root>
  );
}

function StreamingBubble() {
  return (
    <MessageBubble role="assistant" />
  );
}

function TextPart({ text }: TextMessagePartProps) {
  if (isWorkflowStatusText(text)) return null;
  return <div className="whitespace-pre-wrap leading-6">{text}</div>;
}

function ReasoningPart({ text }: ReasoningMessagePartProps) {
  return (
    <details className="mb-2 rounded border border-border bg-muted px-2 py-1 text-xs">
      <summary className="cursor-pointer font-semibold text-muted-foreground">Reasoning</summary>
      <div className="mt-1 whitespace-pre-wrap text-muted-foreground">{text}</div>
    </details>
  );
}

function ToolCallChip({
  argsText,
  isError,
  result,
  status,
  toolName
}: ToolCallMessagePartProps) {
  const complete = status.type === "complete";
  const toolArgs = parseToolArgs(argsText);
  const toolResult = typeof result === "string" ? summarizeToolResult(result) : null;

  return (
    <Box
      className={[
        "my-2 rounded-md border px-3 py-2 text-xs",
        isError ? "border-red-200 bg-red-50 text-red-900" : "border-border bg-muted text-foreground"
      ].join(" ")}
      component="section"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="inline-flex min-w-0 items-center gap-2 font-semibold">
          <Wrench className="h-4 w-4 shrink-0 text-accent" />
          <span className="truncate">{actionLabel(toolName)}</span>
        </div>
        <span className="inline-flex shrink-0 items-center gap-1 rounded bg-white px-2 py-1 font-medium uppercase text-muted-foreground">
          {complete ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {toolStatusLabel(status.type)}
        </span>
      </div>
      {toolArgs.length > 0 ? (
        <dl className="mt-2 grid gap-1">
          {toolArgs.map((row) => (
            <div className="grid grid-cols-[6rem_1fr] gap-2" key={row.label}>
              <dt className="font-medium text-muted-foreground">{row.label}</dt>
              <dd className="min-w-0 break-words">{row.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {toolResult ? (
        <div className="mt-2 border-t border-border pt-2 text-muted-foreground">{toolResult}</div>
      ) : null}
    </Box>
  );
}

function WorkflowApprovalPanel() {
  const runtimeMessages = useAuiState((state) => state.thread.messages);
  const runtimeWorkflow = useAuiState((state) => workflowFromThreadState(state.thread.state));
  const {
    activeWorkflow,
    auth0Session,
    setActiveWorkflow,
    setWorkflowCandidateId,
    workflowCandidateId
  } = useWorkflowContext();
  const [approvalResult, setApprovalResult] = useState<WorkflowApprovalResponse | null>(null);
  const [restoredWorkflow, setRestoredWorkflow] = useState<WorkflowState | null>(null);
  const [restoringWorkflowId, setRestoringWorkflowId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [clearedUserMessageKey, setClearedUserMessageKey] = useState<string | null>(null);
  const latestUserMessageKey = useMemo(
    () => latestUserMessageCursor(runtimeMessages),
    [runtimeMessages]
  );
  const messageWorkflowId = useMemo(
    () => workflowIdFromMessages(runtimeMessages),
    [runtimeMessages]
  );
  const previousUserMessageKey = useRef(latestUserMessageKey);

  const resultWorkflow = isWorkflow(approvalResult?.workflow) ? approvalResult.workflow : null;
  const runtimeWorkflowId = runtimeWorkflow ? stringField(runtimeWorkflow, "workflow_id") : null;
  const resultWorkflowId = resultWorkflow ? stringField(resultWorkflow, "workflow_id") : null;
  const suppressTerminalWorkflow =
    Boolean(latestUserMessageKey) &&
    clearedUserMessageKey === latestUserMessageKey &&
    !messageWorkflowId;
  const visibleResultWorkflow = resultWorkflow;
  const visibleRuntimeWorkflow =
    suppressTerminalWorkflow && runtimeWorkflow && isTerminalWorkflow(runtimeWorkflow)
      ? null
      : runtimeWorkflow;
  const visibleActiveWorkflow =
    suppressTerminalWorkflow && activeWorkflow && isTerminalWorkflow(activeWorkflow)
      ? null
      : activeWorkflow;
  const visibleRestoredWorkflow =
    suppressTerminalWorkflow && restoredWorkflow && isTerminalWorkflow(restoredWorkflow)
      ? null
      : restoredWorkflow;
  const workflow =
    visibleResultWorkflow && (!runtimeWorkflowId || runtimeWorkflowId === resultWorkflowId)
      ? visibleResultWorkflow
      : visibleRuntimeWorkflow ??
        visibleActiveWorkflow ??
        visibleRestoredWorkflow;
  const candidateWorkflowId =
    (workflow ? stringField(workflow, "workflow_id") : null) ??
    workflowCandidateId ??
    messageWorkflowId;

  useEffect(() => {
    if (previousUserMessageKey.current === latestUserMessageKey) return;
    previousUserMessageKey.current = latestUserMessageKey;
    if (!latestUserMessageKey) return;

    setApprovalResult(null);
    setRestoredWorkflow(null);
    setRestoringWorkflowId(null);
    setError(null);
    setClearedUserMessageKey(latestUserMessageKey);

    if ((!runtimeWorkflow || isTerminalWorkflow(runtimeWorkflow)) && !messageWorkflowId) {
      setActiveWorkflow(null);
      setWorkflowCandidateId(null);
    }
  }, [
    latestUserMessageKey,
    messageWorkflowId,
    runtimeWorkflow,
    setActiveWorkflow,
    setWorkflowCandidateId
  ]);

  useEffect(() => {
    if (!auth0Session || workflow || !candidateWorkflowId) return;

    let cancelled = false;
    setRestoringWorkflowId(candidateWorkflowId);
    setError(null);
    void fetch(`/api/workflows/${encodeURIComponent(candidateWorkflowId)}`, {
      cache: "no-store",
      credentials: "same-origin"
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = (await response.json()) as { workflow?: unknown };
        if (!isWorkflow(payload.workflow)) {
          throw new Error("Workflow restore response did not include a workflow");
        }
        if (!cancelled) {
          setRestoredWorkflow(payload.workflow);
          setActiveWorkflow(payload.workflow);
        }
      })
      .catch((restoreError) => {
        if (!cancelled) {
          setError(
            restoreError instanceof Error
              ? restoreError.message
              : "Workflow restore failed"
          );
        }
      })
      .finally(() => {
        if (!cancelled) setRestoringWorkflowId(null);
      });

    return () => {
      cancelled = true;
    };
  }, [auth0Session, candidateWorkflowId, setActiveWorkflow, workflow]);

  if (!workflow) {
    if (!candidateWorkflowId || (!restoringWorkflowId && !error)) return null;
    return (
      <Alert className="mb-3 rounded-md text-sm" severity={error ? "error" : "info"} variant="outlined">
        <div className="font-semibold">Workflow approval</div>
        <div className="mt-1 text-xs">
          {error ?? "Restoring approval context for the latest requested action."}
        </div>
      </Alert>
    );
  }

  const workflowId = stringField(workflow, "workflow_id");
  const planHash = stringField(workflow, "plan_hash");
  const status = workflowStatus(workflow);
  const awaitingApproval = status === "awaiting_approval";
  const terminalApprovalResult =
    Boolean(resultWorkflow) &&
    isTerminalWorkflow(workflow) &&
    (!workflowId || workflowId === resultWorkflowId);

  if (!awaitingApproval && !terminalApprovalResult) {
    return null;
  }

  const requiredScopes = workflowRequiredScopes(workflow);
  const steps = workflowSteps(workflow);
  const disabled = !auth0Session || !workflowId || !planHash || submitting !== null;

  async function submitApproval(approved: boolean) {
    if (!workflowId || !planHash) return;
    setSubmitting(approved ? "approve" : "reject");
    setError(null);
    try {
      const response = await fetch(
        `/api/workflows/${encodeURIComponent(workflowId)}/approve`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ approved, plan_hash: planHash }),
          cache: "no-store",
          credentials: "same-origin"
        }
      );
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const result = (await response.json()) as WorkflowApprovalResponse;
      setApprovalResult(result);
      if (isWorkflow(result.workflow)) {
        setActiveWorkflow(result.workflow);
      }
    } catch (approvalError) {
      setError(
        approvalError instanceof Error ? approvalError.message : "Workflow approval failed"
      );
    } finally {
      setSubmitting(null);
    }
  }

  return (
    <Box
      className={[
        "mb-3 rounded-md border px-3 py-3 text-sm",
        awaitingApproval
          ? "border-amber-200 bg-amber-50"
          : "border-border bg-muted/60 opacity-85"
      ].join(" ")}
      component="section"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-semibold text-foreground">Workflow approval</div>
          <div className="mt-1 text-xs text-muted-foreground">
            {approvalStatusDescription(status)}
          </div>
        </div>
        <Chip
          color={awaitingApproval ? "warning" : status === "completed" ? "success" : "default"}
          label={approvalStatusLabel(status)}
          size="small"
          variant="outlined"
        />
      </div>

      <Typography className="mt-3 text-muted-foreground" variant="body2">
        {policyDescription(workflow)}
      </Typography>

      {requiredScopes.length > 0 ? (
        <Stack className="mt-3 flex-wrap" direction="row" gap={1}>
          {requiredScopes.map((scope) => (
            <Chip key={scope} label={humanizeScope(scope)} size="small" variant="outlined" />
          ))}
        </Stack>
      ) : null}

      {steps.length > 0 ? (
        <List className="mt-3 rounded-md border border-amber-200 bg-white/70 py-0" dense disablePadding>
          {steps.map((step, index) => (
            <WorkflowStepSummary
              divider={index < steps.length - 1}
              index={index}
              key={`${step.action}-${index}`}
              step={step}
            />
          ))}
        </List>
      ) : null}

      {error ? <div className="mt-3 text-xs font-medium text-red-700">{error}</div> : null}

      {awaitingApproval ? (
        <Stack className="mt-4" direction="row" spacing={1}>
          <Button
            color="success"
            disabled={disabled}
            onClick={() => void submitApproval(true)}
            size="small"
            variant="contained"
          >
            {submitting === "approve" ? "Approving" : "Approve"}
          </Button>
          <Button
            color="inherit"
            disabled={disabled}
            onClick={() => void submitApproval(false)}
            size="small"
            variant="outlined"
          >
            {submitting === "reject" ? "Rejecting" : "Reject"}
          </Button>
        </Stack>
      ) : null}
    </Box>
  );
}

function MessageInput() {
  return (
    <ComposerPrimitive.Root className="shrink-0 border-t border-border bg-white p-4">
      <div className="grid grid-cols-[1fr_auto] gap-2">
        <ComposerPrimitive.Input
          asChild
          placeholder="Ask the agent to plan or inspect work..."
        >
          <textarea
            aria-label="Assistant message"
            className="min-h-20 resize-none rounded-md border border-border px-3 py-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
          />
        </ComposerPrimitive.Input>
        <div className="flex flex-col gap-2">
          <AuiIf condition={({ thread }) => !thread.isRunning}>
            <ComposerPrimitive.Send asChild>
              <button
                className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-primary text-primary-foreground shadow-sm disabled:opacity-50"
                type="button"
                title="Send message"
              >
                <Send className="h-4 w-4" />
              </button>
            </ComposerPrimitive.Send>
          </AuiIf>
          <AuiIf condition={({ thread }) => thread.isRunning}>
            <ComposerPrimitive.Cancel asChild>
              <button
                className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-border bg-white text-foreground shadow-sm disabled:opacity-50"
                type="button"
                title="Stop response"
              >
                <Square className="h-4 w-4" />
              </button>
            </ComposerPrimitive.Cancel>
          </AuiIf>
        </div>
      </div>
    </ComposerPrimitive.Root>
  );
}

function workflowStatus(workflow: WorkflowState): string {
  const rawStatus = workflow.status;
  if (typeof rawStatus === "string") return rawStatus;
  if (isRecord(rawStatus) && typeof rawStatus.status === "string") return rawStatus.status;
  return "planned";
}

function isTerminalWorkflow(workflow: WorkflowState): boolean {
  return ["cancelled", "completed", "failed", "rejected"].includes(workflowStatus(workflow));
}

function approvalStatusLabel(status: string): string {
  switch (status) {
    case "awaiting_approval":
      return "Awaiting approval";
    case "completed":
      return "Completed";
    case "cancelled":
      return "Cancelled";
    case "rejected":
      return "Rejected";
    case "failed":
      return "Failed";
    default:
      return humanizeIdentifier(status);
  }
}

function approvalStatusDescription(status: string): string {
  switch (status) {
    case "awaiting_approval":
      return "Review the requested actions before authorizing execution.";
    case "completed":
      return "Approved and recorded for execution.";
    case "cancelled":
    case "rejected":
      return "Not approved for execution.";
    case "failed":
      return "Approval could not be completed.";
    default:
      return "Workflow approval state is available.";
  }
}

function workflowFromThreadState(threadState: unknown): WorkflowState | null {
  if (!isRecord(threadState)) return null;
  const workflow = threadState.workflow;
  return isWorkflow(workflow) ? workflow : null;
}

function policyDescription(workflow: WorkflowState): string {
  const policy = workflow.policy;
  if (isRecord(policy) && typeof policy.human_description === "string") {
    return policy.human_description;
  }
  return "Review the workflow manifest before authorizing tool execution.";
}

function workflowRequiredScopes(workflow: WorkflowState): string[] {
  const policy = workflow.policy;
  if (!isRecord(policy) || !Array.isArray(policy.required_scopes)) return [];
  return policy.required_scopes.filter((scope): scope is string => typeof scope === "string");
}

function workflowSteps(workflow: WorkflowState): Array<{ action: string; arguments: WorkflowState }> {
  const proposal = workflow.proposal;
  if (!isRecord(proposal) || !Array.isArray(proposal.steps)) return [];
  return proposal.steps.filter(isRecord).map((step) => ({
    action: stringField(step, "action") || "workflow_step",
    arguments: stepArguments(step)
  }));
}

function WorkflowStepSummary({
  divider,
  index,
  step
}: {
  divider: boolean;
  index: number;
  step: { action: string; arguments: WorkflowState };
}) {
  const rows = argumentRows(step.arguments);

  return (
    <>
      <ListItem className="items-start px-2 py-2">
        <ListItemIcon className="min-w-8 pt-0.5">
          <ShieldCheck className="h-4 w-4 text-amber-700" />
        </ListItemIcon>
        <ListItemText
          disableTypography
          primary={
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="font-semibold">{actionLabel(step.action)}</span>
              <span className="shrink-0 rounded bg-amber-100 px-2 py-1 font-medium text-amber-900">
                Step {index + 1}
              </span>
            </div>
          }
          secondary={
            rows.length > 0 ? (
              <dl className="mt-2 grid gap-1 text-xs">
                {rows.map((row) => (
                  <div className="grid grid-cols-[7rem_1fr] gap-2" key={row.label}>
                    <dt className="font-medium text-muted-foreground">{row.label}</dt>
                    <dd className="min-w-0 break-words text-foreground">{row.value}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <span className="mt-2 block text-xs text-muted-foreground">
                No additional inputs required.
              </span>
            )
          }
        />
      </ListItem>
      {divider ? <Divider component="li" /> : null}
    </>
  );
}

function argumentRows(argumentsPayload: WorkflowState): Array<{ label: string; value: string }> {
  return Object.entries(argumentsPayload)
    .filter(([key]) => !isInternalField(key))
    .map(([key, value]) => ({
      label: argumentLabel(key),
      value: summarizeArgumentValue(value)
    }))
    .filter((row) => row.value.length > 0);
}

function parseToolArgs(argsText: string | undefined): Array<{ label: string; value: string }> {
  if (!argsText) return [];
  try {
    const decoded = JSON.parse(argsText) as unknown;
    return isRecord(decoded)
      ? argumentRows(decoded)
      : [{ label: "Input", value: summarizeArgumentValue(decoded) }];
  } catch {
    return [{ label: "Input", value: argsText }];
  }
}

function summarizeToolResult(result: string): string {
  try {
    const decoded = JSON.parse(result) as unknown;
    if (isRecord(decoded)) {
      return summarizeRecord(decoded);
    }
    return summarizeArgumentValue(decoded);
  } catch {
    return truncateSummary(result);
  }
}

function summarizeArgumentValue(value: unknown): string {
  if (typeof value === "string") return truncateSummary(value);
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    return truncateSummary(
      value.map((item) => summarizeArgumentValue(item)).filter(Boolean).join(", ")
    );
  }
  if (isRecord(value)) {
    return summarizeRecord(value);
  }
  return "";
}

function summarizeRecord(record: WorkflowState): string {
  const preferred = preferredSummary(record);
  if (preferred) return preferred;

  return truncateSummary(
    argumentRows(record)
      .map((row) => `${row.label}: ${row.value}`)
      .join("; ")
  );
}

function preferredSummary(record: WorkflowState): string | null {
  for (const key of ["summary", "message", "description", "human_description", "display_name", "name"]) {
    const value = record[key];
    if (typeof value === "string" && value.trim().length > 0) {
      return truncateSummary(value);
    }
  }
  return null;
}

function truncateSummary(value: string): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= 180) return normalized;
  return `${normalized.slice(0, 177).trim()}...`;
}

function isInternalField(key: string): boolean {
  return /(^|_)(workflow|plan|trace|token|auth|secret|credential|raw)(_|$)/i.test(key);
}

function actionLabel(value: string): string {
  const normalized = value.toLowerCase();
  const labels: Record<string, string> = {
    inspect_dns_record: "Inspect DNS record",
    inspect_vm: "Inspect virtual machine state",
    inspect_vm_state: "Inspect virtual machine state",
    restart_vm: "Restart virtual machine",
    rotate_vpn_credential: "Rotate VPN credential",
    update_firewall_rule: "Update firewall rule",
    update_iam_binding: "Update IAM binding",
    vm_restart: "Restart virtual machine"
  };
  return labels[normalized] ?? humanizeIdentifier(value);
}

function toolStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    call: "Running",
    complete: "Complete",
    error: "Failed",
    running: "Running"
  };
  return labels[status.toLowerCase()] ?? humanizeIdentifier(status);
}

function sessionHeadline(session: { allowedTools: string[]; persona: { headline: string } }): string {
  if (session.allowedTools.length > 0) {
    return `Cleared for ${session.allowedTools.length} workflow tools.`;
  }
  return session.persona.headline;
}

function argumentLabel(key: string): string {
  const normalized = key.toLowerCase();
  const labels: Record<string, string> = {
    customer_id: "Customer",
    description: "Summary",
    include_history: "Include history",
    input_payload: "Input",
    input_payload_json: "Input",
    query: "Query",
    vm_id: "Target",
    vm: "Target",
    virtual_machine_id: "Target"
  };
  return labels[normalized] ?? humanizeIdentifier(key);
}

function humanizeScope(value: string): string {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .map((scope) => scope.split(":").map(humanizeIdentifier).join(": "))
    .join(", ");
}

function humanizeIdentifier(value: string): string {
  return value
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .split(/[_:\s-]+/)
    .filter(Boolean)
    .map((part) => {
      const lower = part.toLowerCase();
      if (["id", "vm", "api", "url", "uri", "mcp", "dns", "vpn", "iam"].includes(lower)) {
        return lower.toUpperCase();
      }
      return lower.charAt(0).toUpperCase() + lower.slice(1);
    })
    .join(" ");
}

function stepArguments(step: WorkflowState): WorkflowState {
  const directArguments = step.arguments;
  if (isRecord(directArguments)) return directArguments;

  const inputPayload = step.input_payload;
  if (isRecord(inputPayload)) return inputPayload;

  const inputPayloadJson = step.input_payload_json;
  if (typeof inputPayloadJson !== "string") return {};
  try {
    const decoded = JSON.parse(inputPayloadJson) as unknown;
    return isRecord(decoded) ? decoded : { input_payload: decoded };
  } catch {
    return { input_payload_json: inputPayloadJson };
  }
}

function stringField(record: WorkflowState, key: string): string | null {
  const value = record[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

const AWAITING_WORKFLOW_TEXT_PATTERN =
  /\bWorkflow\s+([A-Za-z0-9][A-Za-z0-9:_-]*)\s+is\s+awaiting_approval\b/i;
const AWAITING_WORKFLOW_JSON_PATTERN =
  /"workflow_id"\s*:\s*"([^"]+)"/i;
const WORKFLOW_STATUS_TEXT_PATTERN =
  /\bWorkflow\s+[A-Za-z0-9][A-Za-z0-9:_-]*\s+is\s+(awaiting_approval|ready|completed|cancelled|rejected)\b/i;

function isWorkflowStatusText(text: string): boolean {
  return WORKFLOW_STATUS_TEXT_PATTERN.test(text);
}

function workflowIdFromMessages(messages: readonly unknown[]): string | null {
  const latestUserIndex = lastUserMessageIndex(messages);
  for (let index = messages.length - 1; index > latestUserIndex; index -= 1) {
    const message = messages[index];
    if (isRecord(message) && message.role && message.role !== "assistant") continue;
    const fragments = collectStringFragments(message);
    for (const fragment of fragments) {
      const textMatch = fragment.match(AWAITING_WORKFLOW_TEXT_PATTERN);
      if (textMatch?.[1]) return textMatch[1];

      if (!fragment.includes("awaiting_approval")) continue;
      const jsonMatch = fragment.match(AWAITING_WORKFLOW_JSON_PATTERN);
      if (jsonMatch?.[1]) return jsonMatch[1];
    }
  }
  return null;
}

function latestUserMessageCursor(messages: readonly unknown[]): string | null {
  const index = lastUserMessageIndex(messages);
  if (index < 0) return null;
  return `${index}:${collectStringFragments(messages[index]).join("|")}`;
}

function lastUserMessageIndex(messages: readonly unknown[]): number {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (isRecord(message) && message.role === "user") return index;
  }
  return -1;
}

function collectStringFragments(value: unknown, depth = 0): string[] {
  if (depth > 6) return [];
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) {
    return value.flatMap((item) => collectStringFragments(item, depth + 1));
  }
  if (!isRecord(value)) return [];
  return Object.values(value).flatMap((item) => collectStringFragments(item, depth + 1));
}

function isWorkflow(value: unknown): value is WorkflowState {
  return Boolean(isRecord(value) && stringField(value, "workflow_id"));
}

function isRecord(value: unknown): value is WorkflowState {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
