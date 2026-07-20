// SPDX-License-Identifier: GPL-2.0-only

import { Bug, Plus, RefreshCw, StepForward, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  getDebugStatus,
  getRegisters,
  readMemory,
  setBreakpoint,
  stepSession,
} from "../../lib/api";
import type { ElfSymbolIndex } from "../../lib/elf";
import type { DebugStatus, MemoryRead, SimulationSession } from "../../lib/types";
import { resolvedSymbol, SymbolDecoder } from "./SymbolDecoder";

interface DebugInspectorProps {
  session: SimulationSession | null;
  symbols: ElfSymbolIndex | null;
}

function parseAddress(value: string): number | null {
  if (!/^(?:0x)?[0-9a-f]+$/i.test(value.trim())) return null;
  const parsed = Number.parseInt(value.trim().replace(/^0x/i, ""), 16);
  return Number.isSafeInteger(parsed) && parsed <= 0xffffffff ? parsed : null;
}

function formatRegister(value: number | null): string {
  return value === null ? "unavailable" : `0x${value.toString(16).padStart(8, "0")}`;
}

function formatMemory(memory: MemoryRead | null): string[] {
  if (!memory) return [];
  const bytes = memory.data_hex.match(/.{1,2}/g) ?? [];
  const lines: string[] = [];
  for (let index = 0; index < bytes.length; index += 8) {
    const address = memory.address + index;
    lines.push(
      `0x${address.toString(16).padStart(8, "0")}: ${bytes
        .slice(index, index + 8)
        .join(" ")}`,
    );
  }
  return lines;
}

export function DebugInspector({ session, symbols }: DebugInspectorProps) {
  const [status, setStatus] = useState<DebugStatus | null>(null);
  const [registers, setRegisters] = useState<Record<string, number | null>>({});
  const [memoryAddress, setMemoryAddress] = useState("0x42000000");
  const [memoryLength, setMemoryLength] = useState(64);
  const [memory, setMemory] = useState<MemoryRead | null>(null);
  const [breakpointAddress, setBreakpointAddress] = useState("0x42000000");
  const [breakpoints, setBreakpoints] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const paused = session?.state === "paused";
  const workerDebugAllowed = Boolean(session && !session.anonymous);
  const sessionId = session?.id ?? null;

  const refresh = useCallback(async () => {
    if (!sessionId || !paused || !workerDebugAllowed) return;
    setBusy(true);
    setError(null);
    try {
      const [nextStatus, nextRegisters] = await Promise.all([
        getDebugStatus(sessionId),
        getRegisters(sessionId),
      ]);
      setStatus(nextStatus);
      setRegisters(nextRegisters);
      if (typeof nextRegisters.pc === "number") {
        const pc = `0x${nextRegisters.pc.toString(16).padStart(8, "0")}`;
        setMemoryAddress(pc);
        setBreakpointAddress(pc);
      }
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Debugger unavailable");
    } finally {
      setBusy(false);
    }
  }, [paused, sessionId, workerDebugAllowed]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function inspectMemory() {
    if (!session) return;
    const address = parseAddress(memoryAddress);
    if (address === null) {
      setError("Memory address must be a 32-bit hexadecimal value");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setMemory(await readMemory(session.id, address, memoryLength));
    } catch (memoryError) {
      setError(memoryError instanceof Error ? memoryError.message : "Memory read failed");
    } finally {
      setBusy(false);
    }
  }

  async function addBreakpoint() {
    if (!session) return;
    const address = parseAddress(breakpointAddress);
    if (address === null) {
      setError("Breakpoint address must be a 32-bit hexadecimal value");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await setBreakpoint(session.id, address, true);
      setBreakpoints((current) =>
        current.includes(address) ? current : [...current, address],
      );
    } catch (breakpointError) {
      setError(
        breakpointError instanceof Error
          ? breakpointError.message
          : "Breakpoint could not be added",
      );
    } finally {
      setBusy(false);
    }
  }

  async function removeBreakpoint(address: number) {
    if (!session) return;
    setBusy(true);
    try {
      await setBreakpoint(session.id, address, false);
      setBreakpoints((current) => current.filter((item) => item !== address));
    } catch (breakpointError) {
      setError(
        breakpointError instanceof Error
          ? breakpointError.message
          : "Breakpoint could not be removed",
      );
    } finally {
      setBusy(false);
    }
  }

  async function step() {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      await stepSession(session.id);
      await refresh();
    } catch (stepError) {
      setError(stepError instanceof Error ? stepError.message : "Single-step failed");
    } finally {
      setBusy(false);
    }
  }

  const registerEntries = Object.entries(registers);
  const pcSymbol = resolvedSymbol(symbols, registers.pc);
  return (
    <div className="debug-inspector">
      <SymbolDecoder programCounter={registers.pc} symbols={symbols} />
      {!session ? (
        <div className="inspector-section debug-worker-empty empty-inspector">
          <Bug size={24} />
          <strong>No active worker</strong>
          <p>Start a firmware session, then pause it to inspect CPU state.</p>
        </div>
      ) : !workerDebugAllowed ? (
        <div className="inspector-section debug-worker-empty empty-inspector">
          <Bug size={24} />
          <strong>Temporary symbol tools only</strong>
          <p>Hosted anonymous sessions expose local ELF decoding without worker memory access.</p>
        </div>
      ) : !paused ? (
        <div className="inspector-section debug-worker-empty empty-inspector">
          <Bug size={24} />
          <strong>Pause to inspect</strong>
          <p>Registers, memory, breakpoints, and single-step are available only while paused.</p>
        </div>
      ) : (
        <>
      <div className="debug-heading">
        <div>
          <span className="rail-heading">CPU state</span>
          <strong>{status?.stop_reason ?? "Paused by user"}</strong>
        </div>
        <button
          aria-label="Refresh debugger"
          className="icon-button"
          disabled={busy}
          onClick={() => void refresh()}
          type="button"
        >
          <RefreshCw size={15} />
        </button>
      </div>

      <div className="pc-value">
        <span>PC</span>
        <div>
          <code>{formatRegister(registers.pc ?? null)}</code>
          {pcSymbol ? <small>{pcSymbol}</small> : null}
        </div>
        <button
          className="secondary-button"
          disabled={busy}
          onClick={() => void step()}
          type="button"
        >
          <StepForward size={14} />
          Step
        </button>
      </div>

      <section className="debug-section">
        <div className="rail-heading">Registers</div>
        <div className="register-grid">
          {registerEntries.length ? (
            registerEntries.map(([name, value]) => (
              <div key={name}>
                <span>{name}</span>
                <code>{formatRegister(value)}</code>
              </div>
            ))
          ) : (
            <p className="rail-empty">Refresh to read the Xtensa core registers.</p>
          )}
        </div>
      </section>

      <section className="debug-section">
        <div className="rail-heading">Memory</div>
        <div className="inline-fields">
          <input
            aria-label="Memory address"
            onChange={(event) => setMemoryAddress(event.target.value)}
            spellCheck={false}
            value={memoryAddress}
          />
          <input
            aria-label="Memory length"
            max={4096}
            min={1}
            onChange={(event) => setMemoryLength(Number(event.target.value))}
            type="number"
            value={memoryLength}
          />
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() => void inspectMemory()}
            type="button"
          >
            Read
          </button>
        </div>
        <pre className="memory-view">
          {formatMemory(memory).join("\n") || "No memory read yet"}
        </pre>
      </section>

      <section className="debug-section breakpoint-section">
        <div className="rail-heading">Breakpoints</div>
        <div className="inline-fields">
          <input
            aria-label="Breakpoint address"
            onChange={(event) => setBreakpointAddress(event.target.value)}
            spellCheck={false}
            value={breakpointAddress}
          />
          <button
            aria-label="Add breakpoint"
            className="icon-button"
            disabled={busy}
            onClick={() => void addBreakpoint()}
            type="button"
          >
            <Plus size={15} />
          </button>
        </div>
        <ul className="breakpoint-list">
          {breakpoints.map((address) => (
            <li key={address}>
              <span className="breakpoint-dot" aria-hidden="true" />
              <code>0x{address.toString(16).padStart(8, "0")}</code>
              <button
                aria-label={`Remove breakpoint 0x${address.toString(16)}`}
                className="icon-button"
                disabled={busy}
                onClick={() => void removeBreakpoint(address)}
                type="button"
              >
                <Trash2 size={13} />
              </button>
            </li>
          ))}
        </ul>
      </section>
        </>
      )}
      {error ? <div className="inline-error">{error}</div> : null}
    </div>
  );
}
