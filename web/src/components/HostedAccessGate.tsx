// SPDX-License-Identifier: GPL-2.0-only

import { RefreshCw, ShieldCheck } from "lucide-react";
import type { FormEvent } from "react";
import { useEffect, useRef, useState } from "react";

import { createAnonymousCapability } from "../lib/api";
import type { HostedAccessController } from "../hooks/useHostedAccess";

const TURNSTILE_SCRIPT =
  "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

interface TurnstileApi {
  render(
    container: HTMLElement,
    options: {
      sitekey: string;
      action: string;
      theme: "dark";
      appearance: "always";
      execution: "render";
      callback: (token: string) => void;
      "error-callback": () => void;
      "expired-callback": () => void;
      "timeout-callback": () => void;
    },
  ): string;
  reset(widgetId: string): void;
  remove(widgetId: string): void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

let scriptPromise: Promise<TurnstileApi> | null = null;

function loadTurnstile(): Promise<TurnstileApi> {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise<TurnstileApi>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      `script[src="${TURNSTILE_SCRIPT}"]`,
    );
    const script = existing ?? document.createElement("script");
    const loaded = () => {
      if (window.turnstile) resolve(window.turnstile);
      else reject(new Error("Browser verification did not initialize."));
    };
    script.addEventListener("load", loaded, { once: true });
    script.addEventListener(
      "error",
      () => reject(new Error("Browser verification could not be loaded.")),
      { once: true },
    );
    if (!existing) {
      script.src = TURNSTILE_SCRIPT;
      script.async = true;
      script.defer = true;
      script.referrerPolicy = "no-referrer";
      document.head.append(script);
    }
  }).catch((error: unknown) => {
    scriptPromise = null;
    throw error;
  });
  return scriptPromise;
}

export function HostedAccessGate({
  access,
}: {
  access: HostedAccessController;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [challengeSubmitting, setChallengeSubmitting] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { config, state, verified } = access;

  useEffect(() => {
    if (state !== "challenge" || !config) return;
    const { action, site_key: siteKey } = config;
    if (!action || !siteKey) return;
    let active = true;
    let widgetId: string | null = null;
    void loadTurnstile()
      .then((turnstile) => {
        if (!active || !containerRef.current) return;
        widgetId = turnstile.render(containerRef.current, {
          sitekey: siteKey,
          action,
          theme: "dark",
          appearance: "always",
          execution: "render",
          callback: (token) => {
            if (!active) return;
            setChallengeSubmitting(true);
            setMessage(null);
            void createAnonymousCapability(token)
              .then(() => {
                if (active) verified();
              })
              .catch((verificationError: unknown) => {
                if (!active) return;
                setMessage(
                  verificationError instanceof Error
                    ? verificationError.message
                    : "Browser verification was not accepted.",
                );
                if (widgetId) turnstile.reset(widgetId);
              })
              .finally(() => {
                if (active) setChallengeSubmitting(false);
              });
          },
          "error-callback": () =>
            setMessage("Browser verification reported an error. Please retry."),
          "expired-callback": () => {
            setMessage("Verification expired. Please complete it again.");
            if (widgetId) turnstile.reset(widgetId);
          },
          "timeout-callback": () =>
            setMessage("Verification timed out. Please try again."),
        });
      })
      .catch((loadError: unknown) => {
        if (active) {
          setMessage(
            loadError instanceof Error
              ? loadError.message
              : "Browser verification could not be loaded.",
          );
        }
      });
    return () => {
      active = false;
      if (widgetId && window.turnstile) window.turnstile.remove(widgetId);
    };
  }, [config, state, verified]);

  if (access.state === "standalone" || access.state === "authorized") return null;
  const lifetimeMinutes = Math.ceil((config?.session_lifetime_seconds ?? 180) / 60);
  const lifetimeLabel = `${lifetimeMinutes} minute${lifetimeMinutes === 1 ? "" : "s"}`;
  const accountMode = state === "account";
  const accountAvailable = config?.auth_mode === "supabase";
  const anonymousAvailable = config?.anonymous_enabled === true;

  function submitAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    void access.signIn(email, password).finally(() => setPassword(""));
  }

  return (
    <div className="access-gate" role="dialog" aria-modal="true" aria-labelledby="gate-title">
      <section className="access-gate-panel">
        <span className="access-gate-icon" aria-hidden="true">
          <ShieldCheck size={24} />
        </span>
        <h1 id="gate-title">
          {accountMode
            ? "Sign in with your Zillion account"
            : "Verify to start a temporary simulator"}
        </h1>
        {accountMode ? (
          <p>
            This uses the same Supabase identity as zillionvisionary.com. Saved
            simulator apps remain encrypted on the simulator VPS.
          </p>
        ) : (
          <p>
            Anonymous runs use one isolated worker, last at most {lifetimeLabel}, and
            are removed after inactivity. Firmware, flash state, and serial output are
            not saved by this website.
          </p>
        )}
        {accountMode ? (
          <form className="gate-auth-form" onSubmit={submitAccount}>
            <label>
              <span>Email</span>
              <input
                autoComplete="email"
                autoCapitalize="none"
                disabled={access.submitting}
                onChange={(event) => setEmail(event.target.value)}
                required
                type="email"
                value={email}
              />
            </label>
            <label>
              <span>Password</span>
              <input
                autoComplete="current-password"
                disabled={access.submitting}
                onChange={(event) => setPassword(event.target.value)}
                required
                type="password"
                value={password}
              />
            </label>
            <button disabled={access.submitting} type="submit">
              {access.submitting ? "Signing in…" : "Sign in and open workbench"}
            </button>
          </form>
        ) : null}
        {access.state === "challenge" ? (
          <div
            className="turnstile-slot"
            ref={containerRef}
            aria-busy={challengeSubmitting}
          />
        ) : null}
        {access.state === "loading" ? (
          <div className="gate-loading" aria-live="polite">Checking hosted access…</div>
        ) : null}
        {message || access.error ? (
          <div className="gate-error" role="alert">{message ?? access.error}</div>
        ) : null}
        {access.state === "error" ? (
          <button className="secondary-button" onClick={access.retry} type="button">
            <RefreshCw size={14} /> Retry access check
          </button>
        ) : null}
        {accountMode && anonymousAvailable ? (
          <button className="gate-mode-button" onClick={access.useAnonymous} type="button">
            Continue with one unsaved anonymous run
          </button>
        ) : null}
        {state === "challenge" && accountAvailable ? (
          <button className="gate-mode-button" onClick={access.useAccount} type="button">
            Sign in with your Zillion account instead
          </button>
        ) : null}
        <small>
          Supabase is used only for identity. Simulator content stays on this VPS;
          anonymous content is discarded after the session.
        </small>
      </section>
    </div>
  );
}
