"use client";

import {
  createContext,
  useContext,
  useMemo,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction
} from "react";
import type { Auth0Config } from "@/lib/auth0-config";

type WorkflowContextValue = {
  auth0Config: Auth0Config | null;
  auth0ConfigValid: boolean;
  tokenRef: string | null;
  setAuth0Config: Dispatch<SetStateAction<Auth0Config | null>>;
  setAuth0ConfigValid: Dispatch<SetStateAction<boolean>>;
  setTokenRef: Dispatch<SetStateAction<string | null>>;
};

const WorkflowContext = createContext<WorkflowContextValue | null>(null);

export function WorkflowContextProvider({ children }: { children: ReactNode }) {
  const [auth0Config, setAuth0Config] = useState<Auth0Config | null>(null);
  const [auth0ConfigValid, setAuth0ConfigValid] = useState(false);
  const [tokenRef, setTokenRef] = useState<string | null>(null);

  const value = useMemo(
    () => ({
      auth0Config,
      auth0ConfigValid,
      tokenRef,
      setAuth0Config,
      setAuth0ConfigValid,
      setTokenRef
    }),
    [auth0Config, auth0ConfigValid, tokenRef]
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
