import { HttpAgent, type AgentSubscriber, type BaseEvent, type Message } from "@ag-ui/client";

export type AgUiMessage = {
  role: "user" | "assistant";
  content: string;
};

export type AgUiEvent = BaseEvent;

export type RunInput = {
  userId: string;
  token: string;
  threadId: string;
  prompt: string;
};

export async function streamAgentRun(
  input: RunInput,
  onEvent: (event: AgUiEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const runId = `run-${crypto.randomUUID()}`;
  const userMessage: Message = {
    id: `${runId}:user`,
    role: "user",
    content: input.prompt,
  };
  const abortController = linkedAbortController(signal);
  const agent = new HttpAgent({
    url: "/agent",
    threadId: input.threadId,
    initialMessages: [userMessage],
    headers: {
      Authorization: `Bearer ${input.token}`,
      "X-User-Id": input.userId,
    },
  });
  const subscriber: AgentSubscriber = {
    onEvent: ({ event }) => {
      onEvent(event);
    },
  };

  try {
    await agent.runAgent({ runId, abortController }, subscriber);
  } finally {
    abortController.signal.onabort = null;
  }
}

function linkedAbortController(signal?: AbortSignal): AbortController {
  const controller = new AbortController();
  if (!signal) {
    return controller;
  }
  if (signal.aborted) {
    controller.abort(signal.reason);
    return controller;
  }
  signal.addEventListener(
    "abort",
    () => {
      controller.abort(signal.reason);
    },
    { once: true },
  );
  return controller;
}
