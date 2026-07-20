// SPDX-License-Identifier: GPL-2.0-only

import { Braces } from "lucide-react";
import { useMemo, useState } from "react";

import {
  decodeBacktrace,
  symbolicateAddress,
  type ElfSymbolIndex,
} from "../../lib/elf";

interface SymbolDecoderProps {
  symbols: ElfSymbolIndex | null;
  programCounter?: number | null;
}

function hexAddress(address: number): string {
  return `0x${address.toString(16).padStart(8, "0")}`;
}

export function resolvedSymbol(
  symbols: ElfSymbolIndex | null,
  address: number | null | undefined,
): string | null {
  if (!symbols || typeof address !== "number") return null;
  const resolved = symbolicateAddress(symbols, address);
  return resolved.symbol === null
    ? null
    : `${resolved.symbol}+0x${(resolved.offset ?? 0).toString(16)}`;
}

export function SymbolDecoder({ symbols, programCounter }: SymbolDecoderProps) {
  const [input, setInput] = useState("");
  const decoded = useMemo(
    () => (symbols && input.trim() ? decodeBacktrace(input, symbols) : []),
    [input, symbols],
  );
  const pcSymbol = resolvedSymbol(symbols, programCounter);

  return (
    <section className="debug-section symbol-decoder">
      <div className="symbol-heading">
        <div>
          <span className="rail-heading">ELF backtrace</span>
          <strong>
            {symbols
              ? `${symbols.symbolCount.toLocaleString()} function symbols`
              : "No ELF attached"}
          </strong>
        </div>
        <Braces size={16} aria-hidden="true" />
      </div>
      {symbols ? (
        <>
          <p className="symbol-contract">
            Paste panic or backtrace addresses. Resolution happens locally from
            {` ${symbols.fileName}`}.
          </p>
          {pcSymbol ? (
            <div className="pc-symbol">
              <span>Current PC</span>
              <code>{pcSymbol}</code>
            </div>
          ) : null}
          <textarea
            aria-label="Panic or backtrace addresses"
            onChange={(event) => setInput(event.target.value)}
            placeholder="Backtrace: 0x42001234:0x3fce0000 …"
            spellCheck={false}
            value={input}
          />
          {input.trim() ? (
            <ul className="symbol-results">
              {decoded.length ? (
                decoded.map((result) => (
                  <li key={result.address} data-resolved={result.symbol !== null}>
                    <code>{hexAddress(result.address)}</code>
                    <span>
                      {result.symbol === null
                        ? "No executable symbol"
                        : `${result.symbol}+0x${(result.offset ?? 0).toString(16)}`}
                    </span>
                  </li>
                ))
              ) : (
                <li className="symbol-empty">No 32-bit addresses found</li>
              )}
            </ul>
          ) : null}
        </>
      ) : (
        <p className="symbol-contract">
          Attach the matching firmware.elf before starting to decode function
          addresses. It is parsed only in this browser.
        </p>
      )}
    </section>
  );
}
