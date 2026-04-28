"use client";

import { useMemo, type ReactNode } from "react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import {
  AssistantChatTransport,
  useChatRuntime
} from "@assistant-ui/react-ai-sdk";
import { encodeAuth0ConfigHeader } from "@/lib/auth0-config";
import {
  useWorkflowContext,
  WorkflowContextProvider
} from "@/components/workflow-context";

export function AssistantRoot({ children }: { children: ReactNode }) {
  return (
    <WorkflowContextProvider>
      <AssistantRuntimeBoundary>{children}</AssistantRuntimeBoundary>
    </WorkflowContextProvider>
  );
}

function AssistantRuntimeBoundary({ children }: { children: ReactNode }) {
  const { auth0Config, auth0ConfigValid } = useWorkflowContext();
  const encodedConfig = useMemo(() => {
    if (!auth0Config || !auth0ConfigValid) return null;
    return encodeAuth0ConfigHeader(auth0Config);
  }, [auth0Config, auth0ConfigValid]);

  const transport = useMemo(
    () =>
      new AssistantChatTransport({
        api: "/api/chat",
        headers: encodedConfig ? { "x-auth0-config": encodedConfig } : undefined
      }),
    [encodedConfig]
  );
  const runtime = useChatRuntime({ transport });

  return <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>;
}
