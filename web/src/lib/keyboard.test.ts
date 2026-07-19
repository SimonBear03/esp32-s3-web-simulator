// SPDX-License-Identifier: GPL-2.0-only

import { boardKeyFromDomKey } from "./keyboard";

describe("boardKeyFromDomKey", () => {
  it("maps browser keys to stable board identifiers", () => {
    expect(boardKeyFromDomKey("A")).toBe("a");
    expect(boardKeyFromDomKey("Enter")).toBe("enter");
    expect(boardKeyFromDomKey(" ")).toBe("space");
    expect(boardKeyFromDomKey("ArrowUp")).toBeNull();
  });
});
