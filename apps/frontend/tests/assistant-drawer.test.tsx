import {
  cloneElement,
  isValidElement,
  type ComponentType,
  type HTMLAttributes,
  type PropsWithChildren,
  type TextareaHTMLAttributes
} from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssistantDrawer } from "@/components/assistant-drawer";
import { WorkflowContextProvider } from "@/components/workflow-context";

const mockAui = vi.hoisted(() => ({
  isRunning: false,
  messages: [] as unknown[],
  toolCall: null as null | {
    argsText?: string;
    isError?: boolean;
    result?: string;
    status?: { type: string };
    toolName: string;
  },
  threadId: null as string | null,
  threadState: {} as Record<string, unknown>
}));

vi.mock("@/components/assistant-root", () => ({
  useAssistantThread: () => ({
    createThread: vi.fn(),
    error: null,
    loading: false,
    threadId: mockAui.threadId
  })
}));

vi.mock("@assistant-ui/react", () => {
  const Container = ({ children, ...props }: PropsWithChildren<HTMLAttributes<HTMLDivElement>>) => (
    <div {...props}>{children}</div>
  );
  const Slot = ({ children }: PropsWithChildren) => <>{children}</>;

  return {
    AuiIf: ({ children, condition }: PropsWithChildren<{ condition: (state: { thread: { isRunning: boolean } }) => boolean }>) =>
      condition({ thread: { isRunning: mockAui.isRunning } }) ? <>{children}</> : null,
    ComposerPrimitive: {
      Cancel: Slot,
      Input: ({
        children,
        placeholder
      }: PropsWithChildren<TextareaHTMLAttributes<HTMLTextAreaElement>>) =>
        isValidElement(children) ? cloneElement(children, { placeholder }) : children,
      Root: Container,
      Send: Slot
    },
    MessagePrimitive: {
      Content: ({ components }: { components: { tools?: { Fallback?: ComponentType<Record<string, unknown>> } } }) => {
        const Fallback = components.tools?.Fallback;
        return (
          <div data-testid="message-content">
            {Fallback && mockAui.toolCall ? (
              <Fallback
                argsText={mockAui.toolCall.argsText}
                isError={mockAui.toolCall.isError ?? false}
                result={mockAui.toolCall.result}
                status={mockAui.toolCall.status ?? { type: "complete" }}
                toolName={mockAui.toolCall.toolName}
              />
            ) : null}
          </div>
        );
      },
      Root: Container
    },
    ThreadPrimitive: {
      Empty: Container,
      Messages: ({ components }: { components: { AssistantMessage?: ComponentType } }) => {
        const AssistantMessage = components.AssistantMessage;
        return <div data-testid="message-list">{AssistantMessage ? <AssistantMessage /> : null}</div>;
      },
      Root: Container,
      Viewport: Container
    },
    useAuiState: <T,>(selector: (state: {
      thread: {
        isRunning: boolean;
        messages: unknown[];
        state: Record<string, unknown>;
      };
    }) => T) =>
      selector({
        thread: {
          isRunning: mockAui.isRunning,
          messages: mockAui.messages,
          state: mockAui.threadState
        }
      })
  };
});

const sessionPayload = {
  sessionId: "auth0-session-1",
  tokenRef: "auth0:sample",
  scope: "write:vm:vm-sample",
  audience: null,
  expiresAt: Date.now() + 3600_000,
  userId: "auth0|user-1",
  userEmail: "sample@example.com",
  allowedTools: ["restart_vm"],
  persona: {
    displayName: "sample@example.com",
    greeting: "Welcome back.",
    headline: "sample@example.com is cleared for 1 workflow tools: restart_vm.",
    traits: []
  }
};

const awaitingWorkflow = {
  workflow_id: "wf-1",
  plan_hash: "hash-1",
  status: "awaiting_approval",
  policy: {
    human_description: "Approve VM restart",
    required_scopes: ["write:vm:vm-sample"]
  },
  proposal: {
    steps: [
      {
        action: "restart_vm",
        arguments: { vm_id: "vm-sample" }
      }
    ]
  }
};

const readyWorkflow = {
  workflow_id: "wf-ready",
  plan_hash: "hash-ready",
  status: "ready",
  policy: {
    human_description: "Inspect virtual machine state",
    required_scopes: ["read:vm:vm-sample"]
  },
  proposal: {
    steps: [
      {
        action: "inspect_vm",
        arguments: { vm_id: "vm-sample" }
      }
    ]
  }
};

describe("AssistantDrawer", () => {
  beforeEach(() => {
    mockAui.isRunning = false;
    mockAui.messages = [];
    mockAui.toolCall = null;
    mockAui.threadId = null;
    mockAui.threadState = {};
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders drawer-contained assistant controls without credential fields", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ session: null })));

    render(
      <WorkflowContextProvider>
        <AssistantDrawer />
      </WorkflowContextProvider>
    );

    expect(screen.getByLabelText(/assistant drawer/i)).toBeInTheDocument();
    expect(screen.getByText(/magnum opus assistant/i)).toBeInTheDocument();
    expect(screen.getByTestId("session-controls")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /log in with auth0/i })).toHaveAttribute(
      "href",
      "/api/auth/login"
    );
    expect(screen.getByLabelText(/assistant message/i)).toBeInTheDocument();
    expect(screen.getByTitle(/send message/i)).toBeInTheDocument();

    expect(screen.queryByLabelText(/oidc client id/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/client secret/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/token endpoint/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/token keys endpoint/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/user password/i)).not.toBeInTheDocument();
  });

  it("approves the visible HITL panel in place", async () => {
    mockAui.threadState = { workflow: awaitingWorkflow };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/auth/session") {
        return Response.json({ session: sessionPayload });
      }
      return Response.json({
        workflow: {
          ...awaitingWorkflow,
          status: "completed"
        }
      });
    }));

    render(
      <WorkflowContextProvider>
        <AssistantDrawer />
      </WorkflowContextProvider>
    );

    expect(await screen.findByText(/workflow approval/i)).toBeInTheDocument();
    expect(screen.getAllByText(/workflow approval/i)).toHaveLength(1);
    expect(screen.getByText(/approve vm restart/i)).toBeInTheDocument();
    expect(screen.getAllByText("Restart virtual machine").length).toBeGreaterThan(0);
    expect(screen.getByText("Target")).toBeInTheDocument();
    expect(screen.getByText("vm-sample")).toBeInTheDocument();
    expect(screen.getByText("Awaiting approval")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^approve$/i }));

    await waitFor(() => expect(fetch).toHaveBeenCalledWith(
      "/api/workflows/wf-1/approve",
      expect.objectContaining({
        body: JSON.stringify({ approved: true, plan_hash: "hash-1" }),
        method: "POST"
      })
    ));
    expect(await screen.findByText("Completed")).toBeInTheDocument();
    expect(screen.getAllByText(/workflow approval/i)).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /^approve$/i })).not.toBeInTheDocument();
  });

  it("restores HITL approval controls when AG-UI state is not exposed", async () => {
    mockAui.messages = [
      {
        role: "assistant",
        content: [
          {
            type: "text",
            text: "Workflow wf-1 is awaiting_approval with 1 planned step(s)."
          }
        ]
      }
    ];
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/auth/session") {
        return Response.json({ session: sessionPayload });
      }
      if (url === "/api/workflows/wf-1") {
        return Response.json({ workflow: awaitingWorkflow });
      }
      if (url === "/api/workflows/wf-1/approve") {
        return Response.json({
          workflow: {
            ...awaitingWorkflow,
            status: "completed"
          }
        });
      }
      throw new Error(`Unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <WorkflowContextProvider>
        <AssistantDrawer />
      </WorkflowContextProvider>
    );

    expect(await screen.findByText(/approve vm restart/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^approve$/i })).toBeEnabled();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workflows/wf-1",
      expect.objectContaining({
        cache: "no-store",
        credentials: "same-origin"
      })
    );
  });

  it("does not persist an approval from an earlier turn after a new user message", async () => {
    mockAui.messages = [
      {
        role: "assistant",
        content: [
          {
            type: "text",
            text: "Workflow wf-1 is awaiting_approval with 1 planned step(s)."
          }
        ]
      }
    ];
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/auth/session") {
        return Response.json({ session: sessionPayload });
      }
      if (url === "/api/workflows/wf-1") {
        return Response.json({ workflow: awaitingWorkflow });
      }
      throw new Error(`Unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const { rerender } = render(
      <WorkflowContextProvider>
        <AssistantDrawer />
      </WorkflowContextProvider>
    );

    expect(await screen.findByText(/approve vm restart/i)).toBeInTheDocument();

    mockAui.messages = [
      ...mockAui.messages,
      {
        role: "user",
        content: [{ type: "text", text: "Start a different inspection." }]
      }
    ];
    rerender(
      <WorkflowContextProvider>
        <AssistantDrawer />
      </WorkflowContextProvider>
    );

    await waitFor(() => {
      expect(screen.queryByText(/workflow approval/i)).not.toBeInTheDocument();
    });
  });

  it("does not render stale terminal runtime workflows without a current approval result", async () => {
    mockAui.threadState = {
      workflow: {
        ...awaitingWorkflow,
        status: "completed"
      }
    };
    mockAui.messages = [
      {
        role: "user",
        content: [{ type: "text", text: "Restart the VM." }]
      },
      {
        role: "assistant",
        content: [{ type: "text", text: "Approved and recorded." }]
      }
    ];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/auth/session") {
        return Response.json({ session: sessionPayload });
      }
      throw new Error(`Unexpected fetch ${url}`);
    }));

    const { rerender } = render(
      <WorkflowContextProvider>
        <AssistantDrawer />
      </WorkflowContextProvider>
    );

    await waitFor(() => {
      expect(screen.queryByText(/workflow approval/i)).not.toBeInTheDocument();
    });
    expect(screen.queryByText("Completed")).not.toBeInTheDocument();

    mockAui.messages = [
      ...mockAui.messages,
      {
        role: "user",
        content: [{ type: "text", text: "hi" }]
      }
    ];
    rerender(
      <WorkflowContextProvider>
        <AssistantDrawer />
      </WorkflowContextProvider>
    );

    await waitFor(() => {
      expect(screen.queryByText(/workflow approval/i)).not.toBeInTheDocument();
    });
  });

  it("hides internal workflow identifiers and raw tool JSON", async () => {
    mockAui.threadState = { workflow: awaitingWorkflow };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/auth/session") {
        return Response.json({ session: sessionPayload });
      }
      throw new Error(`Unexpected fetch ${url}`);
    }));

    const { container } = render(
      <WorkflowContextProvider>
        <AssistantDrawer />
      </WorkflowContextProvider>
    );

    expect(await screen.findByText(/workflow approval/i)).toBeInTheDocument();
    expect(screen.getAllByText("Restart virtual machine").length).toBeGreaterThan(0);
    expect(screen.getByText("Target")).toBeInTheDocument();
    expect(screen.getByText("vm-sample")).toBeInTheDocument();
    expect(container.textContent).not.toContain("wf-1");
    expect(container.textContent).not.toContain("workflow_id");
    expect(container.textContent).not.toContain("restart_vm");
    expect(container.textContent).not.toContain("vm_id");
    expect(container.textContent).not.toContain("{");
  });

  it("summarizes tool activity without exposing raw payload fields", async () => {
    mockAui.toolCall = {
      argsText: JSON.stringify({
        customer_id: "customer-1",
        description: "Find the account support tier",
        options: {
          include_history: true,
          token_ref: "token-secret"
        },
        workflow_id: "wf-hidden"
      }),
      result: JSON.stringify({
        raw_payload: { workflow_id: "wf-hidden" },
        status: "complete",
        summary: "Customer is on the enterprise support tier."
      }),
      status: { type: "complete" },
      toolName: "lookup_customer_record"
    };
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ session: null })));

    const { container } = render(
      <WorkflowContextProvider>
        <AssistantDrawer />
      </WorkflowContextProvider>
    );

    expect(screen.getAllByText("Lookup Customer Record").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Customer").length).toBeGreaterThan(0);
    expect(screen.getAllByText("customer-1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Summary").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Find the account support tier").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/customer is on the enterprise support tier/i).length).toBeGreaterThan(0);
    expect(container.textContent).not.toContain("workflow_id");
    expect(container.textContent).not.toContain("wf-hidden");
    expect(container.textContent).not.toContain("token-secret");
    expect(container.textContent).not.toContain("{");
  });

  it("does not render the approval panel for read-only ready workflows", async () => {
    mockAui.threadState = { workflow: readyWorkflow };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/auth/session") {
        return Response.json({ session: sessionPayload });
      }
      throw new Error(`Unexpected fetch ${url}`);
    }));

    render(
      <WorkflowContextProvider>
        <AssistantDrawer />
      </WorkflowContextProvider>
    );

    await waitFor(() => {
      expect(screen.queryByText(/workflow approval/i)).not.toBeInTheDocument();
    });
    expect(screen.queryByText("Ready")).not.toBeInTheDocument();
    expect(screen.queryByText(/inspect the user request/i)).not.toBeInTheDocument();
  });

  it("does not expose the thread id in the drawer status", async () => {
    mockAui.threadId = "thread-778f";
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ session: sessionPayload })));

    const { container } = render(
      <WorkflowContextProvider>
        <AssistantDrawer />
      </WorkflowContextProvider>
    );

    expect(await screen.findByText("Thread ready")).toBeInTheDocument();
    expect(container.textContent).not.toContain("thread-778f");
  });
});
