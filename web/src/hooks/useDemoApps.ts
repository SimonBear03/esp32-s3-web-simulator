// SPDX-License-Identifier: GPL-2.0-only

import { useEffect, useState } from "react";

import { listDemoApps } from "../lib/api";
import type { DemoApp } from "../lib/types";

export interface DemoAppsController {
  apps: DemoApp[];
  loading: boolean;
  error: string | null;
}

export function useDemoApps(enabled: boolean): DemoAppsController {
  const [apps, setApps] = useState<DemoApp[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) {
      setApps([]);
      setLoading(false);
      setError(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void listDemoApps(controller.signal)
      .then((result) => setApps(result.demos))
      .catch((requestError: unknown) => {
        if (controller.signal.aborted) return;
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Demo apps could not be loaded",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [enabled]);

  return { apps, loading, error };
}
