"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode
} from "react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import type { ThreadMessage } from "@assistant-ui/react";
import { HttpAgent, type AgentSubscriber } from "@ag-ui/client";
import { useAgUiRuntime } from "@assistant-ui/react-ag-ui";
import type { ReadonlyJSONValue } from "assistant-stream/utils";
import {
  useWorkflowContext,
  WorkflowContextProvider
} from "@/components/workflow-context";

type ThreadSnapshot = {
  messages?: ThreadMessage[];
  state?: ReadonlyJSONValue;
  threadId: string;
  title?: string | null;
};

type AssistantThreadContextValue = {
  createThread: () => Promise<void>;
  error: string | null;
  loading: boolean;
  threadId: string | null;
};

const AssistantThreadContext = createContext<AssistantThreadContextValue | null>(null);
const THREAD_STORAGE_PREFIX = "magnum-opus:assistant-thread:";

export function AssistantRoot({ children }: { children: ReactNode }) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <WorkflowContextProvider>
        <div className="min-h-screen bg-background" />
      </WorkflowContextProvider>
    );
  }

  return (
    <WorkflowContextProvider>
      <AssistantRuntimeBoundary>{children}</AssistantRuntimeBoundary>
    </WorkflowContextProvider>
  );
}

function AssistantRuntimeBoundary({ children }: { children: ReactNode }) {
  const {
    auth0Session,
    setActiveWorkflow,
    setWorkflowCandidateId
  } = useWorkflowContext();
  const [threadId, setThreadId] = useState<string | null>(null);
  const [threadSnapshot, setThreadSnapshot] = useState<ThreadSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hydratedThreadSnapshotRef = useRef<ThreadSnapshot | null>(null);
  const storageKey = auth0Session?.sessionId
    ? `${THREAD_STORAGE_PREFIX}${auth0Session.sessionId}`
    : null;
  const agent = useMemo(
    () =>
      new HttpAgent({
        url: "/api/ag-ui",
        ...(threadId ? { threadId } : {})
      }),
    [threadId]
  );

  const activateThread = useCallback(
    (snapshot: ThreadSnapshot) => {
      setThreadId(snapshot.threadId);
      setThreadSnapshot(snapshot);
      if (storageKey) writeStoredThreadId(storageKey, snapshot.threadId);
    },
    [storageKey]
  );

  const createThread = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const snapshot = await fetchThread("/api/threads");
      activateThread(snapshot);
    } catch (threadError) {
      setError(threadError instanceof Error ? threadError.message : "Thread creation failed");
    } finally {
      setLoading(false);
    }
  }, [activateThread]);

  const restoreThread = useCallback(
    async (nextThreadId: string) => {
      const snapshot = await fetchThread(`/api/threads/${encodeURIComponent(nextThreadId)}`);
      activateThread(snapshot);
      return snapshot;
    },
    [activateThread]
  );

  const initializeThread = useCallback(async () => {
    setLoading(true);
    setError(null);

    const storedThreadId = storageKey ? readStoredThreadId(storageKey) : null;
    try {
      const snapshot = storedThreadId
        ? await fetchThread(`/api/threads/${encodeURIComponent(storedThreadId)}`)
        : await fetchThread("/api/threads");
      activateThread(snapshot);
    } catch (threadError) {
      if (storedThreadId && storageKey) {
        forgetStoredThreadId(storageKey);
      }
      setError(threadError instanceof Error ? threadError.message : "Thread restore failed");
    } finally {
      setLoading(false);
    }
  }, [activateThread, storageKey]);

  const threadListAdapter = useMemo(
    () => ({
      threadId: threadId ?? undefined,
      onSwitchToNewThread: createThread,
      onSwitchToThread: async (nextThreadId: string) => {
        const snapshot = await restoreThread(nextThreadId);
        return {
          messages: snapshot.messages ?? [],
          ...(snapshot.state !== undefined ? { state: snapshot.state } : {})
        };
      }
    }),
    [createThread, restoreThread, threadId]
  );
  const runtimeAdapters = useMemo(
    () => ({
      threadList: threadListAdapter
    }),
    [threadListAdapter]
  );
  const handleRuntimeError = useCallback(
    (runtimeError: Error) => setError(runtimeError.message),
    []
  );

  useEffect(() => {
    if (!auth0Session) {
      setThreadId(null);
      setThreadSnapshot(null);
      hydratedThreadSnapshotRef.current = null;
      return;
    }
    if (!threadId && !loading && !error) {
      void initializeThread();
    }
  }, [auth0Session, error, initializeThread, loading, threadId]);

  useEffect(() => {
    setActiveWorkflow(null);
    setWorkflowCandidateId(null);

    if (!auth0Session) return;

    const subscriber: AgentSubscriber = {
      onCustomEvent: ({ event }) => {
        const workflowId = workflowIdFromCustomEvent(event);
        if (workflowId) setWorkflowCandidateId(workflowId);
      },
      onStateDeltaEvent: ({ event, state }) => {
        const workflow = workflowFromStateDeltaEvent(event) ?? workflowFromAgentState(state);
        if (workflow) {
          setActiveWorkflow(workflow);
          setWorkflowCandidateId(stringField(workflow, "workflow_id"));
        }
      },
      onStateChanged: ({ state }) => {
        const workflow = workflowFromAgentState(state);
        if (workflow) {
          setActiveWorkflow(workflow);
          setWorkflowCandidateId(stringField(workflow, "workflow_id"));
        }
      },
      onRunFinishedEvent: () => {
        if (threadId) void restoreThread(threadId);
      },
      onRunErrorEvent: ({ event }) => {
        const message = isRecord(event) && typeof event.message === "string"
          ? event.message
          : "Agent run failed";
        setError(message);
      }
    };
    const subscription = agent.subscribe(subscriber);
    const workflow = workflowFromAgentState(agent.state);
    if (workflow) {
      setActiveWorkflow(workflow);
      setWorkflowCandidateId(stringField(workflow, "workflow_id"));
    }
    return () => subscription.unsubscribe();
  }, [
    agent,
    auth0Session,
    restoreThread,
    setActiveWorkflow,
    setWorkflowCandidateId,
    threadId
  ]);

  const runtime = useAgUiRuntime({
    agent,
    adapters: runtimeAdapters,
    onError: handleRuntimeError
  });

  useEffect(() => {
    if (!threadSnapshot || hydratedThreadSnapshotRef.current === threadSnapshot) {
      return;
    }

    hydratedThreadSnapshotRef.current = threadSnapshot;
    runtime.thread.reset(threadSnapshot.messages ?? []);
    if (threadSnapshot.state !== undefined) {
      runtime.thread.unstable_loadExternalState(threadSnapshot.state);
      const workflow = workflowFromAgentState(threadSnapshot.state);
      if (workflow) {
        setActiveWorkflow(workflow);
        setWorkflowCandidateId(stringField(workflow, "workflow_id"));
      }
    }
  }, [runtime, setActiveWorkflow, setWorkflowCandidateId, threadSnapshot]);

  const threadContext = useMemo(
    () => ({
      createThread,
      error,
      loading,
      threadId
    }),
    [createThread, error, loading, threadId]
  );

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <AssistantThreadContext.Provider value={threadContext}>
        {children}
      </AssistantThreadContext.Provider>
    </AssistantRuntimeProvider>
  );
}

export function useAssistantThread() {
  const value = useContext(AssistantThreadContext);
  if (!value) {
    throw new Error("useAssistantThread must be used inside AssistantRoot");
  }
  return value;
}

async function fetchThread(url: string): Promise<ThreadSnapshot> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({}),
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  return (await response.json()) as ThreadSnapshot;
}

function readStoredThreadId(storageKey: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.sessionStorage.getItem(storageKey);
    return value && value.trim().length > 0 ? value : null;
  } catch {
    return null;
  }
}

function writeStoredThreadId(storageKey: string, threadId: string): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(storageKey, threadId);
  } catch {
    return;
  }
}

function forgetStoredThreadId(storageKey: string): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(storageKey);
  } catch {
    return;
  }
}

function workflowFromAgentState(state: unknown): Record<string, unknown> | null {
  if (!isRecord(state)) return null;
  const workflow = state.workflow;
  return isWorkflow(workflow) ? workflow : null;
}

function workflowFromStateDeltaEvent(event: unknown): Record<string, unknown> | null {
  if (!isRecord(event) || !Array.isArray(event.delta)) return null;
  for (let index = event.delta.length - 1; index >= 0; index -= 1) {
    const operation = event.delta[index];
    if (!isRecord(operation)) continue;
    if (operation.path !== "/workflow") continue;
    const workflow = operation.value;
    if (isWorkflow(workflow)) return workflow;
  }
  return null;
}

function workflowIdFromCustomEvent(event: unknown): string | null {
  if (!isRecord(event)) return null;
  const directWorkflow = isWorkflow(event.workflow) ? event.workflow : null;
  if (directWorkflow) return stringField(directWorkflow, "workflow_id");

  const value = event.value;
  if (!isRecord(value)) return null;
  const nestedWorkflow = isWorkflow(value.workflow) ? value.workflow : null;
  return nestedWorkflow
    ? stringField(nestedWorkflow, "workflow_id")
    : stringField(value, "workflow_id") ?? stringField(value, "workflowId");
}

function isWorkflow(value: unknown): value is Record<string, unknown> {
  return Boolean(isRecord(value) && stringField(value, "workflow_id"));
}

function stringField(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
