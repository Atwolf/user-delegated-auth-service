"use client";

import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
  type Dispatch,
  type SetStateAction
} from "react";
import type { Auth0BrowserSession } from "@/lib/auth0-config";

type WorkflowState = Record<string, unknown>;

type WorkflowContextValue = {
  activeWorkflow: WorkflowState | null;
  auth0Session: Auth0BrowserSession | null;
  setActiveWorkflow: Dispatch<SetStateAction<WorkflowState | null>>;
  setAuth0Session: Dispatch<SetStateAction<Auth0BrowserSession | null>>;
  setWorkflowCandidateId: Dispatch<SetStateAction<string | null>>;
  workflowCandidateId: string | null;
};

const WorkflowContext = createContext<WorkflowContextValue | null>(null);

export function WorkflowContextProvider({ children }: { children: ReactNode }) {
  const [auth0Session, setAuth0Session] = useState<Auth0BrowserSession | null>(null);
  const [activeWorkflow, setActiveWorkflow] = useState<WorkflowState | null>(null);
  const [workflowCandidateId, setWorkflowCandidateId] = useState<string | null>(null);

  const value = useMemo(
    () => ({
      activeWorkflow,
      auth0Session,
      setActiveWorkflow,
      setAuth0Session,
      setWorkflowCandidateId,
      workflowCandidateId
    }),
    [activeWorkflow, auth0Session, workflowCandidateId]
  );

  return <WorkflowContext.Provider value={value}>{children}</WorkflowContext.Provider>;
}

export function useWorkflowContext() {
  const value = useContext(WorkflowContext);
  if (!value) {
    throw new Error("useWorkflowContext must be used inside WorkflowContextProvider");
  }
  return value;
}
