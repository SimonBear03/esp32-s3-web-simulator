// SPDX-License-Identifier: GPL-2.0-only

import type { SupabaseClient } from "@supabase/supabase-js";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  exchangeSupabaseSession,
  getHostedAccessConfig,
  logoutHostedSession,
} from "../lib/api";
import type { HostedAccessConfig } from "../lib/types";

export type HostedAccessState =
  | "loading"
  | "standalone"
  | "authorized"
  | "account"
  | "challenge"
  | "error";

export interface HostedAccessController {
  state: HostedAccessState;
  config: HostedAccessConfig | null;
  error: string | null;
  submitting: boolean;
  verified: () => void;
  retry: () => void;
  useAnonymous: () => void;
  useAccount: () => void;
  signIn: (email: string, password: string) => Promise<boolean>;
  signOut: () => Promise<void>;
}

async function configuredClient(config: HostedAccessConfig): Promise<SupabaseClient | null> {
  if (
    config.auth_mode !== "supabase" ||
    !config.supabase_url ||
    !config.supabase_publishable_key
  ) {
    return null;
  }
  const { createClient } = await import("@supabase/supabase-js");
  return createClient(config.supabase_url, config.supabase_publishable_key, {
    auth: {
      autoRefreshToken: true,
      detectSessionInUrl: false,
      persistSession: true,
    },
  });
}

export function useHostedAccess(): HostedAccessController {
  const [state, setState] = useState<HostedAccessState>("loading");
  const [config, setConfig] = useState<HostedAccessConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [generation, setGeneration] = useState(0);
  const clientRef = useRef<SupabaseClient | null>(null);

  const establishGatewaySession = useCallback(async (accessToken: string) => {
    await exchangeSupabaseSession(accessToken);
    const refreshed = await getHostedAccessConfig();
    if (!refreshed?.authorized || refreshed.access_kind !== "account") {
      throw new Error("The simulator did not establish the account session.");
    }
    setConfig(refreshed);
    setState("authorized");
  }, []);

  const clearAccountState = useCallback(() => {
    setConfig((current) =>
      current
        ? {
            ...current,
            access_kind: null,
            authorized: false,
            capability: false,
            saved_app_limit: null,
            saved_apps_enabled: false,
          }
        : current,
    );
    setState("account");
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let subscription: { unsubscribe: () => void } | null = null;
    setState("loading");
    setError(null);
    void getHostedAccessConfig(controller.signal)
      .then(async (next) => {
        if (controller.signal.aborted) return;
        setConfig(next);
        if (next === null || !next.enabled) {
          setState("standalone");
          return;
        }
        if (next.authorized) {
          setState("authorized");
        }
        const client = await configuredClient(next);
        clientRef.current = client;
        if (!client) {
          if (next.authorized) return;
          if (next.anonymous_enabled !== false && next.site_key && next.action) {
            setState("challenge");
          } else {
            throw new Error("Hosted account access is not fully configured.");
          }
          return;
        }

        if (new URLSearchParams(window.location.search).get("signout") === "1") {
          await Promise.allSettled([
            client.auth.signOut({ scope: "local" }),
            logoutHostedSession(),
          ]);
          window.history.replaceState({}, "", window.location.pathname);
          if (!controller.signal.aborted) clearAccountState();
        } else if (!next.authorized) {
          const { data, error: sessionError } = await client.auth.getSession();
          if (sessionError) throw sessionError;
          if (data.session?.access_token) {
            await establishGatewaySession(data.session.access_token);
          } else if (!controller.signal.aborted) {
            setState("account");
          }
        }

        const listener = client.auth.onAuthStateChange((event, session) => {
          if (event === "TOKEN_REFRESHED" && session?.access_token) {
            void establishGatewaySession(session.access_token).catch(() => {
              setError("The simulator account session could not be refreshed.");
              setState("account");
            });
          } else if (event === "SIGNED_OUT") {
            void logoutHostedSession().catch(() => undefined);
            clearAccountState();
          }
        });
        subscription = listener.data.subscription;
      })
      .catch((accessError: unknown) => {
        if (controller.signal.aborted) return;
        setError(
          accessError instanceof Error
            ? accessError.message
            : "Hosted access could not be checked.",
        );
        setState("error");
      });
    return () => {
      controller.abort();
      subscription?.unsubscribe();
    };
  }, [clearAccountState, establishGatewaySession, generation]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      const client = clientRef.current;
      if (!client) return false;
      setSubmitting(true);
      setError(null);
      try {
        const { data, error: signInError } = await client.auth.signInWithPassword({
          email,
          password,
        });
        if (signInError) throw signInError;
        if (!data.session?.access_token) throw new Error("Supabase did not return a session.");
        await establishGatewaySession(data.session.access_token);
        return true;
      } catch (signInError) {
        setError(
          signInError instanceof Error ? signInError.message : "Account sign-in failed.",
        );
        return false;
      } finally {
        setSubmitting(false);
      }
    },
    [establishGatewaySession],
  );

  const signOut = useCallback(async () => {
    setSubmitting(true);
    try {
      await Promise.allSettled([
        clientRef.current?.auth.signOut({ scope: "local" }) ?? Promise.resolve(),
        logoutHostedSession(),
      ]);
      clearAccountState();
      setGeneration((value) => value + 1);
    } finally {
      setSubmitting(false);
    }
  }, [clearAccountState]);

  return {
    state,
    config,
    error,
    submitting,
    signIn,
    signOut,
    verified: useCallback(() => setState("authorized"), []),
    retry: useCallback(() => setGeneration((value) => value + 1), []),
    useAnonymous: useCallback(() => setState("challenge"), []),
    useAccount: useCallback(() => setState("account"), []),
  };
}
