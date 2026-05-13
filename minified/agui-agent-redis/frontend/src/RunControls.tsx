import { FormEvent } from "react";
import { RunStatus } from "./useAgentRun";

type RunControlsProps = {
  userId: string;
  threadId: string;
  token: string;
  prompt: string;
  status: RunStatus;
  onUserIdChange: (value: string) => void;
  onThreadIdChange: (value: string) => void;
  onTokenChange: (value: string) => void;
  onPromptChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export function RunControls({
  userId,
  threadId,
  token,
  prompt,
  status,
  onUserIdChange,
  onThreadIdChange,
  onTokenChange,
  onPromptChange,
  onSubmit,
}: RunControlsProps) {
  return (
    <form className="panel controls" onSubmit={onSubmit}>
      <label>
        User ID
        <input value={userId} onChange={(event) => onUserIdChange(event.target.value)} />
      </label>
      <label>
        Thread ID
        <input value={threadId} onChange={(event) => onThreadIdChange(event.target.value)} />
      </label>
      <label>
        Opaque bearer token
        <input value={token} onChange={(event) => onTokenChange(event.target.value)} />
      </label>
      <label>
        Prompt
        <textarea value={prompt} onChange={(event) => onPromptChange(event.target.value)} />
      </label>
      <button disabled={status === "streaming"} type="submit" data-testid="send-run">
        {status === "streaming" ? "Streaming" : "Send run"}
      </button>
    </form>
  );
}
