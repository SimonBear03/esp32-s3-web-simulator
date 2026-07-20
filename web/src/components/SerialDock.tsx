// SPDX-License-Identifier: GPL-2.0-only

import { Braces, ChevronDown, Terminal, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { openSessionSocket } from "../lib/api";
import { decodeBacktrace, type ElfSymbolIndex } from "../lib/elf";

interface SerialDockProps {
  sessionId: string | null;
  streamGeneration: number;
  symbols: ElfSymbolIndex | null;
}

const MAX_SERIAL_CHARACTERS = 96 * 1024;
const MAX_SYMBOL_SCAN_CHARACTERS = 16 * 1024;

async function serialChunk(data: unknown, decoder: TextDecoder): Promise<string> {
  if (typeof data === "string") return data;
  if (data instanceof ArrayBuffer) return decoder.decode(data, { stream: true });
  if (data instanceof Blob) return decoder.decode(await data.arrayBuffer(), { stream: true });
  return "";
}

export function SerialDock({ sessionId, streamGeneration, symbols }: SerialDockProps) {
  const [text, setText] = useState("");
  const [follow, setFollow] = useState(true);
  const [collapsed, setCollapsed] = useState(false);
  const [connected, setConnected] = useState(false);
  const [command, setCommand] = useState("");
  const socketRef = useRef<WebSocket | null>(null);
  const pendingRef = useRef("");
  const flushTimerRef = useRef<number | null>(null);
  const outputRef = useRef<HTMLPreElement>(null);
  const resolvedAddresses = useMemo(
    () =>
      symbols
        ? decodeBacktrace(text.slice(-MAX_SYMBOL_SCAN_CHARACTERS), symbols).filter(
            (result) => result.symbol !== null,
          )
        : [],
    [symbols, text],
  );

  useEffect(() => {
    setText("");
    setConnected(false);
    if (!sessionId) return;
    const decoder = new TextDecoder();
    const socket = openSessionSocket(sessionId, "serial");
    socket.binaryType = "arraybuffer";
    socketRef.current = socket;
    const flush = () => {
      flushTimerRef.current = null;
      const pending = pendingRef.current;
      pendingRef.current = "";
      if (!pending) return;
      setText((current) => `${current}${pending}`.slice(-MAX_SERIAL_CHARACTERS));
    };
    socket.addEventListener("open", () => {
      if (socketRef.current === socket) setConnected(true);
    });
    socket.addEventListener("close", () => {
      if (socketRef.current === socket) setConnected(false);
    });
    socket.addEventListener("message", (event) => {
      void serialChunk(event.data, decoder).then((chunk) => {
        if (socketRef.current !== socket) return;
        pendingRef.current += chunk;
        if (flushTimerRef.current === null) {
          flushTimerRef.current = window.setTimeout(flush, 50);
        }
      });
    });
    return () => {
      socket.close();
      if (flushTimerRef.current !== null) window.clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
      pendingRef.current = "";
      if (socketRef.current === socket) socketRef.current = null;
    };
  }, [sessionId, streamGeneration]);

  useEffect(() => {
    if (follow && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [follow, text]);

  function sendCommand() {
    const socket = socketRef.current;
    if (!command || !socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(new TextEncoder().encode(`${command}\n`));
    setCommand("");
  }

  return (
    <section className="serial-dock" data-collapsed={collapsed} aria-label="Serial console">
      <header className="serial-header">
        <div>
          <Terminal size={16} />
          <strong>Serial</strong>
          <span className="serial-connection" data-connected={connected}>
            {connected ? "live" : sessionId ? "connecting" : "idle"}
          </span>
        </div>
        <div>
          <button
            className="tool-button compact"
            disabled={!text}
            onClick={() => setText("")}
            type="button"
          >
            <Trash2 size={13} />
            Clear
          </button>
          <label className="follow-toggle">
            <input
              checked={follow}
              onChange={(event) => setFollow(event.target.checked)}
              type="checkbox"
            />
            <span>Follow output</span>
          </label>
          <button
            aria-label={collapsed ? "Expand serial console" : "Collapse serial console"}
            className="icon-button collapse-button"
            onClick={() => setCollapsed((value) => !value)}
            type="button"
          >
            <ChevronDown size={15} />
          </button>
        </div>
      </header>
      <div className="serial-body">
        <pre ref={outputRef}>
          {text ||
            "[simulator] Select a board, validate a merged firmware image, and start a session.\n[simulator] UART output will stream here without persisting to disk."}
        </pre>
        {resolvedAddresses.length ? (
          <aside className="serial-symbols" aria-label="Resolved UART addresses">
            <header>
              <span>
                <Braces size={13} aria-hidden="true" />
                Resolved UART addresses
              </span>
              <small>{resolvedAddresses.length}</small>
            </header>
            <ul>
              {resolvedAddresses.map((result) => (
                <li key={result.address}>
                  <code>0x{result.address.toString(16).padStart(8, "0")}</code>
                  <span>
                    {result.symbol}+0x{(result.offset ?? 0).toString(16)}
                  </span>
                </li>
              ))}
            </ul>
          </aside>
        ) : null}
        <form
          className="serial-input"
          onSubmit={(event) => {
            event.preventDefault();
            sendCommand();
          }}
        >
          <span aria-hidden="true">&gt;</span>
          <input
            aria-label="Serial command"
            autoComplete="off"
            disabled={!connected}
            onChange={(event) => setCommand(event.target.value)}
            placeholder={connected ? "Send UART input" : "UART input unavailable"}
            spellCheck={false}
            value={command}
          />
        </form>
      </div>
    </section>
  );
}
