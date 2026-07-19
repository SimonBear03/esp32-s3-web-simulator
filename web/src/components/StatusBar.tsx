// SPDX-License-Identifier: GPL-2.0-only

import { Signal } from "lucide-react";

interface StatusBarProps {
  inputConnected: boolean;
  expiresAt: string | null;
}

export function StatusBar({ inputConnected, expiresAt }: StatusBarProps) {
  const expiry = expiresAt
    ? new Intl.DateTimeFormat(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }).format(new Date(expiresAt))
    : null;

  return (
    <footer className="status-bar">
      <div>
        <span className="status-signal" data-active={inputConnected} aria-hidden="true" />
        <span>QEMU · ESP32-S3 · NVS persistent</span>
      </div>
      <div>
        {expiry ? <span>Session expires {expiry}</span> : null}
        <span>UART0 @ 115200</span>
        <span>8N1</span>
        <Signal size={16} data-active={inputConnected} aria-label="Input connection state" />
      </div>
    </footer>
  );
}
