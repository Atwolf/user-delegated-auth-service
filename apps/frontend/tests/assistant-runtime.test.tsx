import { useEffect, type PropsWithChildren } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HttpAgent } from "@ag-ui/client";
import {
  agUiRuntimeCalls,
  agUiRuntimeThreadCalls
} from "@assistant-ui/react-ag-ui";
import { AssistantRoot, useAssistantThread } from "@/components/assistant-root";
import { useWorkflowContext } from "@/components/workflow-context";

vi.mock("@assistant-ui/react", async () => ({
  AssistantRuntimeProvider: ({ children }: PropsWithChildren) => (
    <div data-testid="runtime-provider">{children}</div>
  )
}));

describe("AssistantRoot AG-UI runtime", () => {
  beforeEach(() => {
    HttpAgent.instances.length = 0;
    agUiRuntimeCalls.length = 0;
    agUiRuntimeThreadCalls.loadedStates.length = 0;
    agUiRuntimeThreadCalls.resets.length = 0;
    window.sessionStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses the frontend AG-UI proxy as the only runtime endpoint", async () => {
    render(
      <AssistantRoot>
        <div>runtime child</div>
      </AssistantRoot>
    );

    expect(await screen.findByText("runtime child")).toBeInTheDocument();
    expect(HttpAgent.instances).toHaveLength(1);
    expect(HttpAgent.instances[0]?.url).toBe("/api/ag-ui");
    expect(agUiRuntimeCalls).toHaveLength(1);
    expect(agUiRuntimeCalls[0]?.adapters?.threadList?.threadId).toBeUndefined();
  });

  it("restores the sticky thread snapshot after login", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/threads/thread-1") {
        return Response.json({
          messages: [
            {
              id: "msg-1",
              role: "user",
              content: [{ type: "text", text: "Check VM" }]
            }
          ],
          state: { workflow: { workflow_id: "workflow-1", status: "ready" } },
          threadId: "thread-1"
        });
      }
      return Response.json({ error: "unexpected" }, { status: 500 });
    });
    vi.stubGlobal("fetch", fetchMock);
    window.sessionStorage.setItem(
      "magnum-opus:assistant-thread:auth0-session-1",
      "thread-1"
    );

    render(
      <AssistantRoot>
        <AuthenticatedChild />
      </AssistantRoot>
    );

    await screen.findByText("runtime child");
    await waitFor(() => {
      expect(HttpAgent.instances.at(-1)?.threadId).toBe("thread-1");
    });
    await waitFor(() => {
      expect(agUiRuntimeThreadCalls.resets).toHaveLength(1);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/threads/thread-1",
      expect.objectContaining({ method: "POST" })
    );
    expect(agUiRuntimeThreadCalls.resets[0]?.[0]).toMatchObject({
      id: "msg-1",
      role: "user"
    });
    expect(agUiRuntimeThreadCalls.loadedStates[0]).toMatchObject({
      workflow: { workflow_id: "workflow-1" }
    });
  });

  it("surfaces sticky thread restore failure instead of creating a fallback thread", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/threads/thread-missing") {
        return Response.json({ error: "missing" }, { status: 404 });
      }
      return Response.json({ error: "unexpected fallback" }, { status: 500 });
    });
    vi.stubGlobal("fetch", fetchMock);
    window.sessionStorage.setItem(
      "magnum-opus:assistant-thread:auth0-session-1",
      "thread-missing"
    );

    render(
      <AssistantRoot>
        <AuthenticatedThreadProbe />
      </AssistantRoot>
    );

    await waitFor(() => {
      expect(screen.getByTestId("thread-error")).toHaveTextContent("HTTP 404");
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/threads/thread-missing",
      expect.objectContaining({ method: "POST" })
    );
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/threads",
      expect.objectContaining({ method: "POST" })
    );
    expect(screen.getByTestId("thread-id")).toHaveTextContent("");
  });

  it("reloads the active thread snapshot after a run finishes", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/threads") {
        return Response.json({
          messages: [],
          state: {},
          threadId: "thread-1"
        });
      }
      if (url === "/api/threads/thread-1") {
        return Response.json({
          messages: [
            {
              id: "assistant-1",
              role: "assistant",
              content: [{ type: "text", text: "Restarting VM." }]
            }
          ],
          state: {
            workflow: {
              status: "awaiting_approval",
              workflow_id: "workflow-approval-1"
            }
          },
          threadId: "thread-1"
        });
      }
      return Response.json({ error: "unexpected" }, { status: 500 });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AssistantRoot>
        <AuthenticatedChild />
      </AssistantRoot>
    );

    await waitFor(() => {
      expect(HttpAgent.instances.at(-1)?.threadId).toBe("thread-1");
    });

    HttpAgent.instances.at(-1)?.emitRunFinished();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/threads/thread-1",
        expect.objectContaining({ method: "POST" })
      );
    });
    await waitFor(() => {
      expect(agUiRuntimeThreadCalls.loadedStates.at(-1)).toMatchObject({
        workflow: { workflow_id: "workflow-approval-1" }
      });
    });
    expect(agUiRuntimeThreadCalls.resets.at(-1)?.[0]).toMatchObject({
      id: "assistant-1",
      role: "assistant"
    });
  });

  it("surfaces AG-UI run errors on the thread status boundary", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/threads") {
        return Response.json({
          messages: [],
          state: {},
          threadId: "thread-1"
        });
      }
      return Response.json({ error: "unexpected" }, { status: 500 });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AssistantRoot>
        <AuthenticatedThreadProbe />
      </AssistantRoot>
    );

    await waitFor(() => {
      expect(HttpAgent.instances.at(-1)?.threadId).toBe("thread-1");
    });
    await waitFor(() => {
      expect(HttpAgent.instances.at(-1)?.subscribers.length).toBeGreaterThan(0);
    });

    act(() => {
      HttpAgent.instances.at(-1)?.emitRunError({
        type: "RUN_ERROR",
        message: "Agent runtime timed out"
      });
    });

    await waitFor(() => {
      expect(screen.getByTestId("thread-error")).toHaveTextContent("Agent runtime timed out");
    });
  });
});

function AuthenticatedChild() {
  const { setAuth0Session } = useWorkflowContext();

  useEffect(() => {
    setAuth0Session({
      allowedTools: ["inspect_vm"],
      audience: "https://api.example.test",
      expiresAt: Date.now() + 3600_000,
      persona: {
        displayName: "sample",
        greeting: "Welcome back.",
        headline: "sample is cleared for workflow tools.",
        traits: []
      },
      scope: "read:apps",
      sessionId: "auth0-session-1",
      tokenRef: "auth0:sample",
      userEmail: "sample@example.com",
      userId: "auth0|user-1"
    });
  }, [setAuth0Session]);

  return <div>runtime child</div>;
}

function AuthenticatedThreadProbe() {
  const { setAuth0Session } = useWorkflowContext();
  const { error, loading, threadId } = useAssistantThread();

  useEffect(() => {
    setAuth0Session({
      allowedTools: ["inspect_vm"],
      audience: "https://api.example.test",
      expiresAt: Date.now() + 3600_000,
      persona: {
        displayName: "sample",
        greeting: "Welcome back.",
        headline: "sample is cleared for workflow tools.",
        traits: []
      },
      scope: "read:apps",
      sessionId: "auth0-session-1",
      tokenRef: "auth0:sample",
      userEmail: "sample@example.com",
      userId: "auth0|user-1"
    });
  }, [setAuth0Session]);

  return (
    <div>
      <div data-testid="thread-error">{error ?? ""}</div>
      <div data-testid="thread-id">{threadId ?? ""}</div>
      <div data-testid="thread-loading">{String(loading)}</div>
    </div>
  );
}
