// SPDX-License-Identifier: GPL-2.0-only

import {
  Check,
  Pencil,
  Play,
  RefreshCw,
  Save,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

import type { SavedAppsController } from "../hooks/useSavedApps";
import { shortBoardLabel } from "../lib/boards";
import { formatBytes } from "../lib/firmware";
import type { BoardProfile, SavedApp } from "../lib/types";

interface SavedAppsSectionProps {
  board: BoardProfile;
  file: File | null;
  fileValid: boolean;
  sessionActive: boolean;
  sessionStarting: boolean;
  savedApps: SavedAppsController;
  onRun: (app: SavedApp) => Promise<void>;
}

function suggestedName(file: File): string {
  const withoutExtension = file.name.replace(/\.(?:merged\.)?bin$/i, "").trim();
  return (withoutExtension || "Firmware app").slice(0, 64);
}

function updatedLabel(value: string): string {
  const date = value.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : "recently";
}

export function SavedAppsSection({
  board,
  file,
  fileValid,
  sessionActive,
  sessionStarting,
  savedApps,
  onRun,
}: SavedAppsSectionProps) {
  const [name, setName] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [replaceId, setReplaceId] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);

  useEffect(() => {
    setName(file ? suggestedName(file) : "");
    setReplaceId(null);
  }, [file]);

  const storageBusy = savedApps.busy !== null;
  const canSave =
    Boolean(file) &&
    fileValid &&
    name.trim().length > 0 &&
    savedApps.apps.length < savedApps.limit &&
    !sessionActive &&
    !storageBusy;

  return (
    <section className="rail-section saved-apps-section" aria-labelledby="saved-apps-title">
      <div className="saved-apps-heading">
        <div className="rail-heading" id="saved-apps-title">
          Saved apps
        </div>
        <span aria-label={`${savedApps.apps.length} of ${savedApps.limit} saved app slots used`}>
          {savedApps.apps.length}/{savedApps.limit}
        </span>
      </div>

      <p className="saved-apps-privacy">
        Encrypted account storage. Normal sessions stay unsaved.
      </p>

      <div className="saved-app-create">
        <label htmlFor="saved-app-name">App name</label>
        <input
          id="saved-app-name"
          maxLength={64}
          onChange={(event) => setName(event.target.value)}
          placeholder="Choose firmware first"
          type="text"
          value={name}
        />
        <button
          className="secondary-button saved-app-save"
          disabled={!canSave}
          onClick={() => {
            if (!file) return;
            void savedApps.create(name.trim(), board.id, file);
          }}
          type="button"
        >
          <Save size={13} />
          {savedApps.busy === "create" ? "Saving…" : "Save selected"}
        </button>
      </div>

      {savedApps.error ? (
        <div className="saved-app-error" role="alert">
          <span>{savedApps.error}</span>
          <button
            aria-label="Dismiss saved app error"
            onClick={savedApps.clearError}
            type="button"
          >
            <X size={12} />
          </button>
        </div>
      ) : null}

      {savedApps.loading ? (
        <p className="rail-empty saved-app-loading">Loading encrypted library…</p>
      ) : savedApps.apps.length === 0 ? (
        <p className="rail-empty">No saved apps yet. Saving is always explicit.</p>
      ) : (
        <ul className="saved-app-list">
          {savedApps.apps.map((app) => {
            const editing = editingId === app.id;
            const replacing = replaceId === app.id;
            const deleting = deleteId === app.id;
            const itemBusy = savedApps.busy?.startsWith(`${app.id}:`) ?? false;
            return (
              <li key={app.id}>
                {editing ? (
                  <div className="saved-app-inline-form">
                    <label className="visually-hidden" htmlFor={`rename-${app.id}`}>
                      Rename {app.name}
                    </label>
                    <input
                      autoFocus
                      id={`rename-${app.id}`}
                      maxLength={64}
                      onChange={(event) => setEditName(event.target.value)}
                      type="text"
                      value={editName}
                    />
                    <button
                      aria-label={`Save new name for ${app.name}`}
                      disabled={!editName.trim() || itemBusy}
                      onClick={() => {
                        void savedApps.rename(app, editName.trim()).then((renamed) => {
                          if (renamed) setEditingId(null);
                        });
                      }}
                      type="button"
                    >
                      <Check size={13} />
                    </button>
                    <button
                      aria-label={`Cancel renaming ${app.name}`}
                      disabled={itemBusy}
                      onClick={() => setEditingId(null)}
                      type="button"
                    >
                      <X size={13} />
                    </button>
                  </div>
                ) : (
                  <div className="saved-app-summary">
                    <strong>{app.name}</strong>
                    <span>
                      {shortBoardLabel(app.board_id)} · {formatBytes(app.source_size_bytes)} ·{" "}
                      {updatedLabel(app.updated_at)}
                    </span>
                  </div>
                )}

                {replacing ? (
                  <div className="saved-app-confirm" role="group" aria-label={`Replace ${app.name}`}>
                    <span>Replace with selected {shortBoardLabel(board.id)} image?</span>
                    <button
                      disabled={!file || !fileValid || itemBusy}
                      onClick={() => {
                        if (!file) return;
                        void savedApps.replace(app, board.id, file).then((replaced) => {
                          if (replaced) setReplaceId(null);
                        });
                      }}
                      type="button"
                    >
                      Confirm
                    </button>
                    <button
                      disabled={itemBusy}
                      onClick={() => setReplaceId(null)}
                      type="button"
                    >
                      Cancel
                    </button>
                  </div>
                ) : deleting ? (
                  <div className="saved-app-confirm" role="group" aria-label={`Delete ${app.name}`}>
                    <span>Delete this saved copy?</span>
                    <button
                      className="danger-text"
                      disabled={itemBusy}
                      onClick={() => {
                        void savedApps.remove(app).then((removed) => {
                          if (removed) setDeleteId(null);
                        });
                      }}
                      type="button"
                    >
                      Delete
                    </button>
                    <button
                      disabled={itemBusy}
                      onClick={() => setDeleteId(null)}
                      type="button"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div className="saved-app-actions">
                    <button
                      aria-label={`Run ${app.name}`}
                      disabled={sessionActive || sessionStarting || storageBusy}
                      onClick={() => void onRun(app)}
                      title="Run in a fresh temporary worker"
                      type="button"
                    >
                      <Play size={12} /> Run
                    </button>
                    <button
                      aria-label={`Replace ${app.name} with selected firmware`}
                      disabled={!file || !fileValid || sessionActive || storageBusy}
                      onClick={() => {
                        setDeleteId(null);
                        setReplaceId(app.id);
                      }}
                      title="Replace with the currently selected firmware"
                      type="button"
                    >
                      <RefreshCw size={12} />
                    </button>
                    <button
                      aria-label={`Rename ${app.name}`}
                      disabled={storageBusy}
                      onClick={() => {
                        setEditName(app.name);
                        setEditingId(app.id);
                      }}
                      type="button"
                    >
                      <Pencil size={12} />
                    </button>
                    <button
                      aria-label={`Delete ${app.name}`}
                      disabled={storageBusy}
                      onClick={() => {
                        setReplaceId(null);
                        setDeleteId(app.id);
                      }}
                      type="button"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
