export type HttpAgentOptions = {
  threadId?: string;
  url: string;
};

export type AgentSubscriber = {
  onCustomEvent?: (payload: { event: unknown }) => void;
  onRunErrorEvent?: (payload: { event: unknown }) => void;
  onRunFinishedEvent?: (payload: { event: unknown }) => void;
  onStateDeltaEvent?: (payload: {
    event: unknown;
    state: Record<string, unknown>;
  }) => void;
  onStateChanged?: (payload: { state: Record<string, unknown> }) => void;
};

export class HttpAgent {
  static instances: HttpAgent[] = [];

  readonly threadId?: string;
  readonly subscribers: AgentSubscriber[] = [];
  state: Record<string, unknown> = {};
  readonly url: string;

  constructor(options: HttpAgentOptions) {
    this.threadId = options.threadId;
    this.url = options.url;
    HttpAgent.instances.push(this);
  }

  subscribe(subscriber: AgentSubscriber) {
    this.subscribers.push(subscriber);
    return {
      unsubscribe: () => {
        const index = this.subscribers.indexOf(subscriber);
        if (index >= 0) this.subscribers.splice(index, 1);
      }
    };
  }

  emitCustomEvent(event: unknown) {
    for (const subscriber of this.subscribers) {
      subscriber.onCustomEvent?.({ event });
    }
  }

  emitState(state: Record<string, unknown>) {
    this.state = state;
    for (const subscriber of this.subscribers) {
      subscriber.onStateChanged?.({ state });
    }
  }

  emitStateDelta(event: unknown, state: Record<string, unknown>) {
    this.state = state;
    for (const subscriber of this.subscribers) {
      subscriber.onStateDeltaEvent?.({ event, state });
    }
  }

  emitRunFinished(event: unknown = { type: "RUN_FINISHED" }) {
    for (const subscriber of this.subscribers) {
      subscriber.onRunFinishedEvent?.({ event });
    }
  }

  emitRunError(event: unknown = { type: "RUN_ERROR", message: "run failed" }) {
    for (const subscriber of this.subscribers) {
      subscriber.onRunErrorEvent?.({ event });
    }
  }
}
