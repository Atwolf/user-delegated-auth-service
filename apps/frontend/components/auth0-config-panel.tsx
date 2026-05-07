"use client";

import { useCallback, useEffect, useState } from "react";
import { LogIn, LogOut, RefreshCw, ShieldCheck } from "lucide-react";
import { parseScopeString, type Auth0UserSession } from "@/lib/auth0-config";
import { useWorkflowContext } from "@/components/workflow-context";

export function Auth0ConfigPanel() {
  const { auth0Session, setAuth0Session } = useWorkflowContext();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshSession = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/auth/session", { cache: "no-store" });
      const payload = (await response.json().catch(() => ({}))) as {
        session?: Auth0UserSession | null;
      };
      setAuth0Session(response.ok ? payload.session ?? null : null);
    } catch {
      setAuth0Session(null);
    } finally {
      setLoading(false);
    }
  }, [setAuth0Session]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const auth0Error = params.get("auth0_error");
    if (auth0Error) setError(auth0Error);
    void refreshSession();
  }, [refreshSession]);

  const scopes = auth0Session ? parseScopeString(auth0Session.scope) : [];

  return (
    <section className="flex h-full flex-col border-r border-border bg-white">
      <div className="border-b border-border px-5 py-4">
        <h1 className="text-lg font-semibold">Auth0 User Login</h1>
      </div>

      <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-5 py-5">
        <div className="flex items-center gap-3">
          <a
            aria-disabled={Boolean(auth0Session)}
            className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground aria-disabled:pointer-events-none aria-disabled:opacity-50"
            href="/api/auth/login"
            title="Log in with Auth0"
          >
            <LogIn className="h-4 w-4" />
            Log in with Auth0
          </a>
          <button
            className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-border disabled:opacity-50"
            type="button"
            onClick={() => void refreshSession()}
            disabled={loading}
            title="Refresh session"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>

        <div className="flex items-center justify-between rounded-md border border-border bg-muted px-3 py-2">
          <span className="min-w-0 truncate text-sm text-muted-foreground" role="status">
            {auth0Session
              ? `Logged in as ${auth0Session.userEmail ?? auth0Session.userId}`
              : loading
                ? "Checking session."
                : "Logged out."}
          </span>
          {auth0Session ? (
            <a
              className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-white px-3 text-xs font-semibold"
              href="/api/auth/logout"
              title="Log out"
            >
              <LogOut className="h-3.5 w-3.5" />
              Log out
            </a>
          ) : null}
        </div>

        {auth0Session ? (
          <div className="grid gap-3 rounded-md border border-border p-3 text-xs">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <ShieldCheck className="h-4 w-4 text-primary" />
              {auth0Session.persona.displayName}
            </div>
            <div className="text-muted-foreground">{auth0Session.persona.headline}</div>
            {scopes.length ? (
              <TokenList label="Scopes" items={scopes} tone="cyan" />
            ) : null}
            {auth0Session.allowedTools.length ? (
              <TokenList label="Tools" items={auth0Session.allowedTools} tone="emerald" />
            ) : null}
          </div>
        ) : null}

        {error ? <div className="text-sm font-medium text-red-700">{error}</div> : null}
      </div>
    </section>
  );
}

function TokenList({
  label,
  items,
  tone
}: {
  label: string;
  items: string[];
  tone: "cyan" | "emerald";
}) {
  const className =
    tone === "cyan"
      ? "rounded-md bg-cyan-50 px-2 py-1 text-cyan-900"
      : "rounded-md bg-emerald-50 px-2 py-1 text-emerald-900";

  return (
    <div>
      <span className="font-semibold">{label}</span>
      <div className="mt-1 flex flex-wrap gap-1">
        {items.map((item) => (
          <span className={className} key={item}>
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}
