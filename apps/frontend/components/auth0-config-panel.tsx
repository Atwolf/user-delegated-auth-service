"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { RefreshCw, Save, Trash2 } from "lucide-react";
import {
  clearPublicConfig,
  DEFAULT_AUTH0_CONFIG,
  deriveAuth0Endpoints,
  loadPublicConfig,
  savePublicConfig,
  toPublicConfig,
  validateAuth0Config,
  type Auth0Config,
  type Auth0PublicConfig
} from "@/lib/auth0-config";
import { useWorkflowContext } from "@/components/workflow-context";

export function Auth0ConfigPanel() {
  const { setAuth0Config, setAuth0ConfigValid } = useWorkflowContext();
  const [publicConfig, setPublicConfig] =
    useState<Auth0PublicConfig>(DEFAULT_AUTH0_CONFIG);
  const [clientSecret, setClientSecret] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setPublicConfig(loadPublicConfig(window.localStorage));
  }, []);

  const fullConfig: Auth0Config = useMemo(
    () => ({ ...publicConfig, clientSecret }),
    [publicConfig, clientSecret]
  );
  const validation = validateAuth0Config(fullConfig);

  useEffect(() => {
    savePublicConfig(window.localStorage, publicConfig);
  }, [publicConfig]);

  useEffect(() => {
    setAuth0Config(fullConfig);
    setAuth0ConfigValid(validation.valid);
  }, [fullConfig, setAuth0Config, setAuth0ConfigValid, validation.valid]);

  function update<K extends keyof Auth0PublicConfig>(key: K, value: Auth0PublicConfig[K]) {
    setSaved(false);
    setPublicConfig((current) => ({ ...current, [key]: value }));
  }

  function useDiscoveryDocument() {
    const endpoints = deriveAuth0Endpoints(publicConfig.domain);
    setPublicConfig((current) => ({ ...current, ...endpoints }));
  }

  function clearConfig() {
    clearPublicConfig(window.localStorage);
    setClientSecret("");
    setPublicConfig(DEFAULT_AUTH0_CONFIG);
    setSaved(false);
  }

  function saveConfig() {
    savePublicConfig(window.localStorage, toPublicConfig(fullConfig));
    setSaved(true);
  }

  return (
    <section className="flex h-full flex-col border-r border-border bg-white">
      <div className="border-b border-border px-5 py-4">
        <h1 className="text-lg font-semibold">OpenID Connect Configuration</h1>
      </div>

      <form
        className="flex flex-1 flex-col gap-4 overflow-y-auto px-5 py-5"
        onSubmit={(event) => {
          event.preventDefault();
          saveConfig();
        }}
      >
        <Field label="Server Template">
          <select
            className="input"
            value={publicConfig.serverTemplate}
            onChange={() => update("serverTemplate", "Auth0")}
          >
            <option>Auth0</option>
          </select>
        </Field>

        <Field label="Auth0 domain" error={validation.errors.domain}>
          <div className="grid grid-cols-[1fr_auto]">
            <input
              aria-label="Auth0 domain"
              className="input rounded-r-none"
              value={publicConfig.domain}
              onChange={(event) => update("domain", event.target.value)}
              placeholder="samples.auth0.com"
            />
            <button
              className="inline-flex items-center gap-2 rounded-l-none border border-l-0 border-border px-3 text-xs font-semibold uppercase tracking-wide"
              type="button"
              title="Use Auth0 discovery document"
              onClick={useDiscoveryDocument}
            >
              <RefreshCw className="h-4 w-4" />
              Discover
            </button>
          </div>
        </Field>

        <Field label="Authorization Token Endpoint">
          <input
            className="input bg-muted"
            value={`https://${publicConfig.domain.replace(/^https?:\/\//, "")}/authorize`}
            readOnly
          />
        </Field>

        <Field label="Token Endpoint" error={validation.errors.tokenEndpoint}>
          <input
            aria-label="Token Endpoint"
            className="input"
            value={publicConfig.tokenEndpoint}
            onChange={(event) => update("tokenEndpoint", event.target.value)}
          />
        </Field>

        <Field label="Token Keys Endpoint" error={validation.errors.jwksEndpoint}>
          <input
            aria-label="Token Keys Endpoint"
            className="input"
            value={publicConfig.jwksEndpoint}
            onChange={(event) => update("jwksEndpoint", event.target.value)}
          />
        </Field>

        <Field label="OIDC Client ID" error={validation.errors.clientId}>
          <input
            aria-label="OIDC Client ID"
            className="input"
            value={publicConfig.clientId}
            onChange={(event) => update("clientId", event.target.value)}
            placeholder="client id"
          />
        </Field>

        <Field label="OIDC Client Secret" error={validation.errors.clientSecret}>
          <input
            aria-label="OIDC Client Secret"
            className="input"
            type="password"
            value={clientSecret}
            onChange={(event) => {
              setSaved(false);
              setClientSecret(event.target.value);
            }}
            placeholder="kept in memory only"
          />
        </Field>

        <Field label="Scope" error={validation.errors.scope}>
          <input
            aria-label="Scope"
            className="input"
            value={publicConfig.scope}
            onChange={(event) => update("scope", event.target.value)}
          />
        </Field>

        <Field label="Audience (optional)">
          <input
            aria-label="Audience"
            className="input"
            value={publicConfig.audience}
            onChange={(event) => update("audience", event.target.value)}
            placeholder="https://api.example.com"
          />
        </Field>

        <div className="mt-2 flex items-center gap-3">
          <button
            className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground disabled:opacity-50"
            type="submit"
            disabled={!validation.valid}
            title="Save non-secret configuration"
          >
            <Save className="h-4 w-4" />
            Save
          </button>
          <button
            className="inline-flex h-10 items-center gap-2 rounded-md border border-border px-4 text-sm font-semibold"
            type="button"
            onClick={clearConfig}
            title="Clear local config"
          >
            <Trash2 className="h-4 w-4" />
            Clear local config
          </button>
          <span className="text-sm text-muted-foreground" role="status">
            {saved ? "Non-secret config saved." : validation.valid ? "Ready." : "Incomplete."}
          </span>
        </div>
      </form>
    </section>
  );
}

function Field({
  label,
  error,
  children
}: {
  label: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="grid gap-2">
      <span className="text-sm font-medium text-muted-foreground">{label}</span>
      {children}
      {error ? <span className="text-xs font-medium text-red-700">{error}</span> : null}
    </label>
  );
}
