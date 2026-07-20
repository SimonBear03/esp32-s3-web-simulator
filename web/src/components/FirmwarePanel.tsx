// SPDX-License-Identifier: GPL-2.0-only

import { Check, FileCode2, FileSearch, Upload, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import type { SavedAppsController } from "../hooks/useSavedApps";
import {
  formatBytes,
  inspectFirmware,
  type FirmwareInspection,
} from "../lib/firmware";
import {
  inspectElfSymbols,
  MAX_ELF_SYMBOL_FILE_BYTES,
  type ElfSymbolIndex,
} from "../lib/elf";
import type { BoardProfile, SavedApp, SimulationSession } from "../lib/types";
import { SavedAppsSection } from "./SavedAppsSection";

interface FirmwarePanelProps {
  board: BoardProfile;
  session: SimulationSession | null;
  starting: boolean;
  onStart: (file: File, symbols: ElfSymbolIndex | null) => Promise<void>;
  savedApps: SavedAppsController | null;
  onRunSaved: (app: SavedApp) => Promise<void>;
}

export function FirmwarePanel({
  board,
  session,
  starting,
  onStart,
  savedApps,
  onRunSaved,
}: FirmwarePanelProps) {
  const inputId = useId();
  const symbolsInputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const symbolsInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [inspection, setInspection] = useState<FirmwareInspection | null>(null);
  const [symbolsFile, setSymbolsFile] = useState<File | null>(null);
  const [symbols, setSymbols] = useState<ElfSymbolIndex | null>(null);
  const [symbolsError, setSymbolsError] = useState<string | null>(null);
  const [symbolsLoading, setSymbolsLoading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const active = Boolean(
    session && ["starting", "running", "paused"].includes(session.state),
  );
  const wasActive = useRef(false);

  useEffect(() => {
    if (wasActive.current && !active) {
      setSymbolsFile(null);
      setSymbols(null);
      setSymbolsError(null);
      if (symbolsInputRef.current) symbolsInputRef.current.value = "";
    }
    wasActive.current = active;
  }, [active]);

  useEffect(() => {
    if (!file) {
      setInspection(null);
      return;
    }
    let current = true;
    void inspectFirmware(file, board).then((next) => {
      if (current) setInspection(next);
    });
    return () => {
      current = false;
    };
  }, [board, file]);

  useEffect(() => {
    if (!symbolsFile) {
      setSymbols(null);
      setSymbolsError(null);
      setSymbolsLoading(false);
      return;
    }
    let current = true;
    setSymbols(null);
    setSymbolsError(null);
    setSymbolsLoading(true);
    void inspectElfSymbols(symbolsFile)
      .then((next) => {
        if (current) setSymbols(next);
      })
      .catch((error: unknown) => {
        if (current) {
          setSymbolsError(
            error instanceof Error ? error.message : "ELF symbols could not be read",
          );
        }
      })
      .finally(() => {
        if (current) setSymbolsLoading(false);
      });
    return () => {
      current = false;
    };
  }, [symbolsFile]);

  function acceptFile(candidate: File | undefined) {
    if (!candidate || active) return;
    setFile(candidate);
  }

  return (
    <aside className="firmware-panel" aria-label="Firmware setup">
      <section className="rail-section profile-summary">
        <div className="rail-heading">Device profile</div>
        <div className="profile-name">{board.label}</div>
        <dl className="profile-facts">
          <div>
            <dt>MCU</dt>
            <dd>{board.mcu}</dd>
          </div>
          <div>
            <dt>Flash</dt>
            <dd>{formatBytes(board.flash_size_bytes)}</dd>
          </div>
          <div>
            <dt>PSRAM</dt>
            <dd>{board.psram_size_mib ? `${board.psram_size_mib} MiB` : "None"}</dd>
          </div>
        </dl>
      </section>

      <section className="rail-section">
        <div className="rail-heading">Firmware</div>
        <input
          accept=".bin,application/octet-stream"
          className="visually-hidden"
          disabled={Boolean(active)}
          id={inputId}
          onChange={(event) => acceptFile(event.target.files?.[0])}
          ref={inputRef}
          type="file"
        />
        <label
          className="firmware-dropzone"
          data-active={dragActive}
          data-disabled={Boolean(active)}
          htmlFor={inputId}
          onDragEnter={(event) => {
            event.preventDefault();
            if (!active) setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            setDragActive(false);
            acceptFile(event.dataTransfer.files[0]);
          }}
        >
          <Upload size={27} strokeWidth={1.4} aria-hidden="true" />
          <span>Drop merged firmware.bin</span>
          <small>or choose a file · max {formatBytes(board.flash_size_bytes)}</small>
        </label>

        {file ? (
          <div className="firmware-file">
            <FileCode2 size={18} aria-hidden="true" />
            <span>
              <strong>{file.name}</strong>
              <small>{formatBytes(file.size)}</small>
            </span>
            {!active ? (
              <button
                aria-label="Remove firmware"
                className="icon-button"
                onClick={() => {
                  setFile(null);
                  if (inputRef.current) inputRef.current.value = "";
                }}
                type="button"
              >
                <X size={15} />
              </button>
            ) : null}
          </div>
        ) : null}

        <div className="symbols-upload">
          <input
            accept=".elf,application/x-elf"
            className="visually-hidden"
            disabled={Boolean(active)}
            id={symbolsInputId}
            onChange={(event) => setSymbolsFile(event.target.files?.[0] ?? null)}
            ref={symbolsInputRef}
            type="file"
          />
          {!symbolsFile ? (
            <label
              className="symbols-picker"
              data-disabled={Boolean(active)}
              htmlFor={symbolsInputId}
            >
              <FileSearch size={15} aria-hidden="true" />
              <span>Attach matching firmware.elf</span>
              <small>Optional · max {formatBytes(MAX_ELF_SYMBOL_FILE_BYTES)}</small>
            </label>
          ) : (
            <div className="firmware-file symbol-file" data-valid={Boolean(symbols)}>
              <FileSearch size={18} aria-hidden="true" />
              <span>
                <strong>{symbolsFile.name}</strong>
                <small>
                  {symbolsLoading
                    ? "Reading symbols…"
                    : symbolsError ?? `${symbols?.symbolCount ?? 0} functions · browser only`}
                </small>
              </span>
              {!active ? (
                <button
                  aria-label="Remove debug symbols"
                  className="icon-button"
                  onClick={() => {
                    setSymbolsFile(null);
                    if (symbolsInputRef.current) symbolsInputRef.current.value = "";
                  }}
                  type="button"
                >
                  <X size={15} />
                </button>
              ) : null}
            </div>
          )}
          <p className="symbols-privacy">
            Parsed locally for backtraces; the ELF never leaves this browser.
          </p>
        </div>
      </section>

      {savedApps ? (
        <SavedAppsSection
          board={board}
          file={file}
          fileValid={inspection?.valid ?? false}
          onRun={onRunSaved}
          savedApps={savedApps}
          sessionActive={Boolean(active)}
          sessionStarting={starting}
        />
      ) : null}

      <section className="rail-section validation-section">
        <div className="rail-heading">Local checks</div>
        {inspection ? (
          <ul className="validation-list">
            {inspection.checks.map((check) => (
              <li data-valid={check.valid} key={check.label}>
                {check.valid ? <Check size={14} /> : <X size={14} />}
                <span>{check.label}</span>
                <code>{check.value}</code>
              </li>
            ))}
          </ul>
        ) : (
          <p className="rail-empty">Choose a merged flash image to validate it locally.</p>
        )}
      </section>

      {session ? (
        <section className="rail-section session-metadata">
          <div className="rail-heading">Worker image</div>
          <dl className="profile-facts">
            <div>
              <dt>Source</dt>
              <dd>{formatBytes(session.firmware.source_size_bytes)}</dd>
            </div>
            <div>
              <dt>Flash copy</dt>
              <dd>{formatBytes(session.firmware.flash_size_bytes)}</dd>
            </div>
            <div>
              <dt>SHA-256</dt>
              <dd className="hash-value">{session.firmware.source_sha256.slice(0, 12)}…</dd>
            </div>
          </dl>
        </section>
      ) : null}

      <div className="rail-action">
        <button
          className="primary-button"
          disabled={
            !file ||
            !inspection?.valid ||
            Boolean(active) ||
            starting ||
            symbolsLoading ||
            Boolean(symbolsFile && !symbols)
          }
          onClick={() => file && void onStart(file, symbols)}
          type="button"
        >
          <span className="play-glyph" aria-hidden="true" />
          {starting ? "Starting…" : active ? "Session active" : "Start session"}
        </button>
      </div>
    </aside>
  );
}
