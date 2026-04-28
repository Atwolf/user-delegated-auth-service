"use client";

import { Send } from "lucide-react";
import {
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive
} from "@assistant-ui/react";

export function Thread() {
  return (
    <ThreadPrimitive.Root className="flex h-full min-h-0 flex-col bg-white">
      <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto px-5 py-4">
        <ThreadPrimitive.Empty>
          <div className="rounded-lg border border-border bg-muted p-4 text-sm text-muted-foreground">
            Waiting for workflow request.
          </div>
        </ThreadPrimitive.Empty>
        <ThreadPrimitive.Messages
          components={{
            UserMessage,
            AssistantMessage
          }}
        />
      </ThreadPrimitive.Viewport>

      <ComposerPrimitive.Root className="border-t border-border p-4">
        <div className="grid grid-cols-[1fr_auto] gap-2">
          <ComposerPrimitive.Input
            asChild
            placeholder="Ask the supervisor to plan a workflow..."
          >
            <textarea
              className="min-h-20 resize-none rounded-md border border-border px-3 py-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
              aria-label="Workflow chat input"
            />
          </ComposerPrimitive.Input>
          <ComposerPrimitive.Send asChild>
            <button
              className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-primary text-primary-foreground disabled:opacity-50"
              type="button"
              title="Send message"
            >
              <Send className="h-4 w-4" />
            </button>
          </ComposerPrimitive.Send>
        </div>
      </ComposerPrimitive.Root>
    </ThreadPrimitive.Root>
  );
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="mb-3 flex justify-end">
      <div className="max-w-[82%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
        <MessagePrimitive.Content />
      </div>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="mb-3 flex justify-start">
      <div className="max-w-[88%] whitespace-pre-wrap rounded-lg border border-border bg-white px-3 py-2 text-sm shadow-sm">
        <MessagePrimitive.Content />
      </div>
    </MessagePrimitive.Root>
  );
}
