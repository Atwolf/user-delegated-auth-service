"use client";

import { useMemo, type ReactNode } from "react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import {
  AssistantChatTransport,
  useChatRuntime
} from "@assistant-ui/react-ai-sdk";
import { WorkflowContextProvider } from "@/components/workflow-context";

export function AssistantRoot({ children }: { children: ReactNode }) {
  return (
    <WorkflowContextProvider>
      <AssistantRuntimeBoundary>{children}</AssistantRuntimeBoundary>
    </WorkflowContextProvider>
  );
}

function AssistantRuntimeBoundary({ children }: { children: ReactNode }) {
  const transport = useMemo(
    () =>
      new AssistantChatTransport({
        api: "/api/chat"
      }),
    []
  );
  const runtime = useChatRuntime({ transport });

  return <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>;
}
