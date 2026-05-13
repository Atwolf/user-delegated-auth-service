import { AgUiEvent } from "./aguiClient";
import { Message } from "./useAgentRun";

type TranscriptPanelProps = {
  messages: Message[];
};

export function TranscriptPanel({ messages }: TranscriptPanelProps) {
  return (
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
  );
}

type EventLogPanelProps = {
  events: AgUiEvent[];
};

export function EventLogPanel({ events }: EventLogPanelProps) {
  return (
    <section className="panel event-log" aria-label="AG-UI events">
      <h2>AG-UI Events</h2>
      <ol>
        {events.map((event, index) => (
          <li key={index}>{String(event.type)}</li>
        ))}
      </ol>
    </section>
  );
}

type StateDeltaPanelProps = {
  stateJson: string;
};

export function StateDeltaPanel({ stateJson }: StateDeltaPanelProps) {
  return (
    <section className="panel state" aria-label="State delta">
      <h2>State Delta</h2>
      <pre>{stateJson}</pre>
    </section>
  );
}
