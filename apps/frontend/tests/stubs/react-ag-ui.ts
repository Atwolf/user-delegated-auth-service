export type AgUiRuntimeOptions = {
  adapters?: {
    threadList?: {
      onSwitchToNewThread?: () => Promise<void>;
      onSwitchToThread?: (threadId: string) => Promise<unknown>;
      threadId: string;
    };
  };
  agent: unknown;
  onError?: (error: Error) => void;
};

export const agUiRuntimeCalls: AgUiRuntimeOptions[] = [];
export const agUiRuntimeThreadCalls: {
  loadedStates: unknown[];
  resets: unknown[][];
} = {
  loadedStates: [],
  resets: []
};

export function useAgUiRuntime(options: AgUiRuntimeOptions) {
  agUiRuntimeCalls.push(options);
  return {
    type: "ag-ui-runtime",
    options,
    thread: {
      reset: (messages: unknown[]) => {
        agUiRuntimeThreadCalls.resets.push(messages);
      },
      unstable_loadExternalState: (state: unknown) => {
        agUiRuntimeThreadCalls.loadedStates.push(state);
      }
    }
  };
}
