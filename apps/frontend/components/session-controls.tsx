"use client";

import { useCallback, useEffect, useState } from "react";
import { LogIn, LogOut, RefreshCw, ShieldCheck } from "lucide-react";
import { parseScopeString, type Auth0BrowserSession } from "@/lib/auth0-config";
import { useWorkflowContext } from "@/components/workflow-context";

export function SessionControls() {
  const { auth0Session, setAuth0Session } = useWorkflowContext();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshSession = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/auth/session", { cache: "no-store" });
      const payload = (await response.json().catch(() => ({}))) as {
        session?: Auth0BrowserSession | null;
      };
      setAuth0Session(response.ok ? payload.session ?? null : null);
    } catch {
      setAuth0Session(null);
      setError("Session refresh failed.");
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
    <div className="grid gap-3" data-testid="session-controls">
      <div className="flex flex-wrap items-center gap-2">
        <a
          aria-disabled={Boolean(auth0Session)}
          className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-xs font-semibold text-primary-foreground shadow-sm aria-disabled:pointer-events-none aria-disabled:opacity-50"
          href="/api/auth/login"
          title="Log in with Auth0"
        >
          <LogIn className="h-4 w-4" />
          Log in with Auth0
        </a>
        <button
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-white text-foreground shadow-sm disabled:opacity-50"
          type="button"
          onClick={() => void refreshSession()}
          disabled={loading}
          title="Refresh session"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
        {auth0Session ? (
          <a
            className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-white px-3 text-xs font-semibold shadow-sm"
            href="/api/auth/logout"
            title="Log out"
          >
            <LogOut className="h-4 w-4" />
            Log out
          </a>
        ) : null}
      </div>

      <div className="rounded-md border border-border bg-white px-3 py-2 shadow-sm">
        <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground">
          <ShieldCheck className="h-4 w-4 text-primary" />
          <span role="status">
            {auth0Session
              ? `Logged in as ${auth0Session.userEmail ?? auth0Session.userId}`
              : loading
                ? "Checking session."
                : "Logged out."}
          </span>
        </div>
        {auth0Session ? (
          <div className="mt-2 grid gap-2 text-xs">
            <div>
              <div className="font-semibold text-foreground">{auth0Session.persona.displayName}</div>
              <div className="text-muted-foreground">{sessionHeadline(auth0Session)}</div>
            </div>
            {scopes.length ? <TokenList label="Scopes" items={scopes} tone="cyan" /> : null}
            {auth0Session.allowedTools.length ? (
              <TokenList
                formatter={toolLabel}
                label="Tools"
                items={auth0Session.allowedTools}
                tone="emerald"
              />
            ) : null}
          </div>
        ) : null}
      </div>

      {error ? <div className="text-xs font-medium text-red-700">{error}</div> : null}
    </div>
  );
}

function TokenList({
  formatter = (item) => item,
  label,
  items,
  tone
}: {
  formatter?: (item: string) => string;
  label: string;
  items: string[];
  tone: "cyan" | "emerald";
}) {
  const className =
    tone === "cyan"
      ? "rounded bg-cyan-50 px-2 py-1 font-medium text-cyan-900"
      : "rounded bg-emerald-50 px-2 py-1 font-medium text-emerald-900";

  return (
    <div>
      <span className="font-semibold text-foreground">{label}</span>
      <div className="mt-1 flex flex-wrap gap-1">
        {items.map((item) => (
          <span className={className} key={item}>
            {formatter(item)}
          </span>
        ))}
      </div>
    </div>
  );
}

function toolLabel(value: string): string {
  const normalized = value.toLowerCase();
  const labels: Record<string, string> = {
    inspect_dns_record: "Inspect DNS record",
    inspect_vm: "Inspect virtual machine state",
    inspect_vm_state: "Inspect virtual machine state",
    restart_vm: "Restart virtual machine",
    rotate_vpn_credential: "Rotate VPN credential",
    update_firewall_rule: "Update firewall rule",
    update_iam_binding: "Update IAM binding",
    vm_restart: "Restart virtual machine"
  };
  return labels[normalized] ?? humanizeIdentifier(value);
}

function sessionHeadline(session: Auth0BrowserSession): string {
  if (session.allowedTools.length > 0) {
    return `Cleared for ${session.allowedTools.length} workflow tools.`;
  }
  return session.persona.headline;
}

function humanizeIdentifier(value: string): string {
  return value
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .split(/[_:\s-]+/)
    .filter(Boolean)
    .map((part) => {
      const lower = part.toLowerCase();
      if (["id", "vm", "api", "url", "uri", "mcp", "dns", "vpn", "iam"].includes(lower)) {
        return lower.toUpperCase();
      }
      return lower.charAt(0).toUpperCase() + lower.slice(1);
    })
    .join(" ");
}
