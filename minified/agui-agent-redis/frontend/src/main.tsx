import React, { FormEvent, useMemo, useRef, useState } from "react";
import { EventType } from "@ag-ui/client";
import { createRoot, Root } from "react-dom/client";
import { AgUiEvent, streamAgentRun } from "./a2aClient";
import "./styles.css";

type Message = {
  role: "user" | "assistant";
  content: string;
};

declare global {
  interface Window {
    __minifiedAguiRoot?: Root;
  }
}

function App() {
  const [userId, setUserId] = useState("demo-user");
  const [threadId, setThreadId] = useState("thread-001");
  const [token, setToken] = useState("local-demo-token");
  const [prompt, setPrompt] = useState("Show me the Redis-backed thread state path.");
  const [messages, setMessages] = useState<Message[]>([]);
  const [events, setEvents] = useState<AgUiEvent[]>([]);
  const [stateJson, setStateJson] = useState("{}");
  const [status, setStatus] = useState<"idle" | "streaming" | "done" | "error">("idle");
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

  return (
    <main className="shell">
      <section className="toolbar" aria-label="Run configuration">
        <div>
          <h1>Minified AG-UI Client</h1>
          <p>React uses HttpAgent subscribers to render the AG-UI event stream.</p>
        </div>
        <div className={`status status-${status}`} data-testid="run-status">
          {status} / {lastEventType}
        </div>
      </section>

      <section className="layout">
        <form className="panel controls" onSubmit={submit}>
          <label>
            User ID
            <input value={userId} onChange={(event) => setUserId(event.target.value)} />
          </label>
          <label>
            Thread ID
            <input value={threadId} onChange={(event) => setThreadId(event.target.value)} />
          </label>
          <label>
            Opaque bearer token
            <input value={token} onChange={(event) => setToken(event.target.value)} />
          </label>
          <label>
            Prompt
            <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} />
          </label>
          <button disabled={status === "streaming"} type="submit" data-testid="send-run">
            {status === "streaming" ? "Streaming" : "Send run"}
          </button>
        </form>

        <section className="panel transcript" aria-label="Transcript">
          <h2>Transcript</h2>
          {messages.length === 0 ? (
            <p className="empty">No run has been sent.</p>
          ) : (
            messages.map((message, index) => (
              <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
                <span>{message.role}</span>
                <p>{message.content || "..."}</p>
              </article>
            ))
          )}
        </section>

        <section className="panel event-log" aria-label="AG-UI events">
          <h2>AG-UI Events</h2>
          <ol>
            {events.map((event, index) => (
              <li key={index}>{String(event.type)}</li>
            ))}
          </ol>
        </section>

        <section className="panel state" aria-label="State delta">
          <h2>State Delta</h2>
          <pre>{stateJson}</pre>
        </section>
      </section>
    </main>
  );
}

const container = document.getElementById("root")!;
window.__minifiedAguiRoot ??= createRoot(container);
window.__minifiedAguiRoot.render(<App />);
