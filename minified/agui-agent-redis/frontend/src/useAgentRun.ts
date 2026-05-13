import { EventType } from "@ag-ui/client";
import { FormEvent, useMemo, useRef, useState } from "react";
import { AgUiEvent, streamAgentRun } from "./aguiClient";

export type Message = {
  role: "user" | "assistant";
  content: string;
};

export type RunStatus = "idle" | "streaming" | "done" | "error";

export function useAgentRun() {
  const [userId, setUserId] = useState("demo-user");
  const [threadId, setThreadId] = useState("thread-001");
  const [token, setToken] = useState("demo-token");
  const [prompt, setPrompt] = useState("Confirm ADK streaming and show the thread metadata.");
  const [messages, setMessages] = useState<Message[]>([]);
  const [events, setEvents] = useState<AgUiEvent[]>([]);
  const [stateJson, setStateJson] = useState("{}");
  const [status, setStatus] = useState<RunStatus>("idle");
  const abortRef = useRef<AbortController | null>(null);

  const lastEventType = useMemo(() => {
    const event = events.at(-1);
    return typeof event?.type === "string" ? event.type : "none";
  }, [events]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setStatus("streaming");
    setEvents([]);
    setStateJson("{}");
    setMessages([{ role: "user", content: prompt }, { role: "assistant", content: "" }]);

    try {
      await streamAgentRun(
        { userId, token, threadId, prompt },
        (streamEvent) => {
          setEvents((current) => [...current, streamEvent]);
          if (streamEvent.type === "TEXT_MESSAGE_CONTENT" && "delta" in streamEvent) {
            setMessages((current) => {
              const next = [...current];
              const last = next.at(-1);
              if (last?.role === "assistant") {
                last.content += streamEvent.delta;
              }
              return next;
            });
          }
          if (streamEvent.type === "STATE_DELTA") {
            setStateJson(JSON.stringify(streamEvent.delta, null, 2));
          }
          if (streamEvent.type === "RUN_ERROR") {
            setStatus("error");
          }
        },
        controller.signal,
      );
      setStatus((current) => (current === "error" ? "error" : "done"));
    } catch (error) {
      setStatus("error");
      setEvents((current) => [
        ...current,
        {
          type: EventType.RUN_ERROR,
          message: error instanceof Error ? error.message : "Unknown client error",
        },
      ]);
    }
  }

  return {
    events,
    lastEventType,
    messages,
    prompt,
    setPrompt,
    setThreadId,
    setToken,
    setUserId,
    stateJson,
    status,
    submit,
    threadId,
    token,
    userId,
  };
}
