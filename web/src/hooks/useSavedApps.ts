// SPDX-License-Identifier: GPL-2.0-only

import { useCallback, useEffect, useState } from "react";

import {
  createSavedApp,
  deleteSavedApp,
  listSavedApps,
  renameSavedApp,
  replaceSavedApp,
} from "../lib/api";
import type { BoardId, SavedApp } from "../lib/types";

export interface SavedAppsController {
  apps: SavedApp[];
  limit: number;
  loading: boolean;
  busy: string | null;
  error: string | null;
  create: (
    name: string,
    boardId: BoardId,
    firmware: File,
  ) => Promise<boolean>;
  replace: (
    app: SavedApp,
    boardId: BoardId,
    firmware: File,
  ) => Promise<boolean>;
  rename: (app: SavedApp, name: string) => Promise<boolean>;
  remove: (app: SavedApp) => Promise<boolean>;
  clearError: () => void;
}

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "The saved app request failed";
}

export function useSavedApps(enabled: boolean): SavedAppsController {
  const [apps, setApps] = useState<SavedApp[]>([]);
  const [limit, setLimit] = useState(10);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
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
    void listSavedApps(controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setApps(result.apps);
        setLimit(result.limit);
      })
      .catch((loadError: unknown) => {
        if (!controller.signal.aborted) setError(messageFromError(loadError));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [enabled]);

  const create = useCallback(
    async (name: string, boardId: BoardId, firmware: File) => {
      setBusy("create");
      setError(null);
      try {
        const saved = await createSavedApp(name, boardId, firmware);
        setApps((current) => [saved, ...current]);
        return true;
      } catch (saveError) {
        setError(messageFromError(saveError));
        return false;
      } finally {
        setBusy(null);
      }
    },
    [],
  );

  const replace = useCallback(
    async (app: SavedApp, boardId: BoardId, firmware: File) => {
      setBusy(`${app.id}:replace`);
      setError(null);
      try {
        const saved = await replaceSavedApp(app.id, app.name, boardId, firmware);
        setApps((current) => [saved, ...current.filter((item) => item.id !== app.id)]);
        return true;
      } catch (replaceError) {
        setError(messageFromError(replaceError));
        return false;
      } finally {
        setBusy(null);
      }
    },
    [],
  );

  const rename = useCallback(async (app: SavedApp, name: string) => {
    setBusy(`${app.id}:rename`);
    setError(null);
    try {
      const saved = await renameSavedApp(app.id, name);
      setApps((current) =>
        current.map((item) => (item.id === app.id ? saved : item)),
      );
      return true;
    } catch (renameError) {
      setError(messageFromError(renameError));
      return false;
    } finally {
      setBusy(null);
    }
  }, []);

  const remove = useCallback(async (app: SavedApp) => {
    setBusy(`${app.id}:delete`);
    setError(null);
    try {
      await deleteSavedApp(app.id);
      setApps((current) => current.filter((item) => item.id !== app.id));
      return true;
    } catch (deleteError) {
      setError(messageFromError(deleteError));
      return false;
    } finally {
      setBusy(null);
    }
  }, []);

  return {
    apps,
    limit,
    loading,
    busy,
    error,
    create,
    replace,
    rename,
    remove,
    clearError: useCallback(() => setError(null), []),
  };
}
