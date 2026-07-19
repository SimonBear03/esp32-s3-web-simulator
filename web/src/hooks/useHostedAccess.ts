// SPDX-License-Identifier: GPL-2.0-only

import { useCallback, useEffect, useState } from "react";

import { getHostedAccessConfig } from "../lib/api";
import type { HostedAccessConfig } from "../lib/types";

export type HostedAccessState =
  | "loading"
  | "standalone"
  | "authorized"
  | "challenge"
  | "error";

export interface HostedAccessController {
  state: HostedAccessState;
  config: HostedAccessConfig | null;
  error: string | null;
  verified: () => void;
  retry: () => void;
}

export function useHostedAccess(): HostedAccessController {
  const [state, setState] = useState<HostedAccessState>("loading");
  const [config, setConfig] = useState<HostedAccessConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    setError(null);
    void getHostedAccessConfig(controller.signal)
      .then((next) => {
        if (controller.signal.aborted) return;
        setConfig(next);
        if (next === null || !next.enabled) {
          setState("standalone");
        } else if (next.authorized) {
          setState("authorized");
        } else if (next.site_key && next.action) {
          setState("challenge");
        } else {
          setError("Anonymous access is not fully configured on this host.");
          setState("error");
        }
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
    return () => controller.abort();
  }, [generation]);

  return {
    state,
    config,
    error,
    verified: useCallback(() => setState("authorized"), []),
    retry: useCallback(() => setGeneration((value) => value + 1), []),
  };
}
