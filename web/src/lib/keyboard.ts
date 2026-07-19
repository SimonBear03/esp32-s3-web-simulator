// SPDX-License-Identifier: GPL-2.0-only

export interface VirtualKey {
  id: string;
  label: string;
  width?: number;
}

export const CARDPUTER_KEY_ROWS: VirtualKey[][] = [
  [
    { id: "grave", label: "`" },
    ...Array.from({ length: 10 }, (_, index) => ({
      id: String((index + 1) % 10),
      label: String((index + 1) % 10),
    })),
    { id: "minus", label: "−" },
    { id: "equals", label: "=" },
    { id: "backspace", label: "del", width: 1.35 },
  ],
  [
    { id: "tab", label: "tab", width: 1.25 },
    ...[..."qwertyuiop"].map((letter) => ({ id: letter, label: letter })),
    { id: "bracket-left", label: "[" },
    { id: "bracket-right", label: "]" },
    { id: "backslash", label: "\\" },
  ],
  [
    { id: "fn", label: "fn", width: 1.2 },
    { id: "shift", label: "shift", width: 1.45 },
    ...[..."asdfghjkl"].map((letter) => ({ id: letter, label: letter })),
    { id: "semicolon", label: ";" },
    { id: "apostrophe", label: "'" },
    { id: "enter", label: "enter", width: 1.5 },
  ],
  [
    { id: "ctrl", label: "ctrl", width: 1.25 },
    { id: "opt", label: "opt", width: 1.15 },
    { id: "alt", label: "alt", width: 1.15 },
    ...[..."zxcvbnm"].map((letter) => ({ id: letter, label: letter })),
    { id: "comma", label: "," },
    { id: "period", label: "." },
    { id: "slash", label: "/" },
    { id: "space", label: "space", width: 4 },
  ],
];

const DOM_KEY_TO_BOARD_KEY: Record<string, string> = {
  "`": "grave",
  "-": "minus",
  "=": "equals",
  Backspace: "backspace",
  Tab: "tab",
  "[": "bracket-left",
  "]": "bracket-right",
  "\\": "backslash",
  Shift: "shift",
  ";": "semicolon",
  "'": "apostrophe",
  Enter: "enter",
  Control: "ctrl",
  Meta: "opt",
  Alt: "alt",
  ",": "comma",
  ".": "period",
  "/": "slash",
  " ": "space",
};

export function boardKeyFromDomKey(key: string): string | null {
  const normalized = key.length === 1 ? key.toLowerCase() : key;
  if (/^[a-z0-9]$/.test(normalized)) return normalized;
  return DOM_KEY_TO_BOARD_KEY[key] ?? null;
}
