import type { WorkflowRecord } from "@/lib/workflow-types";

type WorkflowCache = {
  latest: WorkflowRecord | null;
  byId: Map<string, WorkflowRecord>;
};

const globalWorkflowCache = globalThis as typeof globalThis & {
  __magnumOpusWorkflowCache?: WorkflowCache;
};

function cache(): WorkflowCache {
  if (!globalWorkflowCache.__magnumOpusWorkflowCache) {
    globalWorkflowCache.__magnumOpusWorkflowCache = {
      latest: null,
      byId: new Map()
    };
  }
  return globalWorkflowCache.__magnumOpusWorkflowCache;
}

export function rememberWorkflow(record: WorkflowRecord) {
  const store = cache();
  store.latest = record;
  store.byId.set(record.workflow_id, record);
}

export function getLatestWorkflow() {
  return cache().latest;
}

export function getWorkflow(workflowId: string) {
  return cache().byId.get(workflowId) ?? null;
}
