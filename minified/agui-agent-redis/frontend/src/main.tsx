import React from "react";
import { createRoot, Root } from "react-dom/client";
import { EventLogPanel, StateDeltaPanel, TranscriptPanel } from "./Panels";
import { RunControls } from "./RunControls";
import { useAgentRun } from "./useAgentRun";
import "./styles.css";

declare global {
  interface Window {
    __aguiAgentRoot?: Root;
  }
}

function App() {
  const run = useAgentRun();

  return (
    <main className="shell">
      <section className="toolbar" aria-label="Run configuration">
        <div>
          <h1>AG-UI Agent Client</h1>
          <p>React uses HttpAgent subscribers to render the AG-UI event stream.</p>
        </div>
        <div className={`status status-${run.status}`} data-testid="run-status">
          {run.status} / {run.lastEventType}
        </div>
      </section>

      <section className="layout">
        <RunControls
          userId={run.userId}
          threadId={run.threadId}
          token={run.token}
          prompt={run.prompt}
          status={run.status}
          onUserIdChange={run.setUserId}
          onThreadIdChange={run.setThreadId}
          onTokenChange={run.setToken}
          onPromptChange={run.setPrompt}
          onSubmit={run.submit}
        />
        <TranscriptPanel messages={run.messages} />
        <EventLogPanel events={run.events} />
        <StateDeltaPanel stateJson={run.stateJson} />
      </section>
    </main>
  );
}

const container = document.getElementById("root")!;
window.__aguiAgentRoot ??= createRoot(container);
window.__aguiAgentRoot.render(<App />);
