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
import type { Auth0UserSession } from "@/lib/auth0-config";

type WorkflowContextValue = {
  auth0Session: Auth0UserSession | null;
  setAuth0Session: Dispatch<SetStateAction<Auth0UserSession | null>>;
};

const WorkflowContext = createContext<WorkflowContextValue | null>(null);

export function WorkflowContextProvider({ children }: { children: ReactNode }) {
  const [auth0Session, setAuth0Session] = useState<Auth0UserSession | null>(null);

  const value = useMemo(
    () => ({
      auth0Session,
      setAuth0Session
    }),
    [auth0Session]
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
