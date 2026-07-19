// SPDX-License-Identifier: GPL-2.0-only

import { Cpu, PanelsTopLeft, Terminal } from "lucide-react";

export type MobilePanel = "device" | "serial" | "inspector";

interface MobilePanelNavProps {
  panel: MobilePanel;
  onChange: (panel: MobilePanel) => void;
}

const PANELS = [
  { id: "device", label: "Device", Icon: Cpu },
  { id: "serial", label: "Serial", Icon: Terminal },
  { id: "inspector", label: "Inspector", Icon: PanelsTopLeft },
] as const;

export function MobilePanelNav({ panel, onChange }: MobilePanelNavProps) {
  return (
    <nav className="mobile-panel-nav" aria-label="Workbench panel">
      {PANELS.map(({ id, label, Icon }) => (
        <button
          aria-current={panel === id ? "page" : undefined}
          key={id}
          onClick={() => onChange(id)}
          type="button"
        >
          <Icon size={17} />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
}
