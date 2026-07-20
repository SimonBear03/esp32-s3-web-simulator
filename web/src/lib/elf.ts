// SPDX-License-Identifier: GPL-2.0-only

const ELF_HEADER_BYTES = 52;
const ELF_SECTION_HEADER_BYTES = 40;
const ELF_SYMBOL_BYTES = 16;
const ELFCLASS32 = 1;
const ELFDATA2LSB = 1;
const EV_CURRENT = 1;
const EM_XTENSA = 94;
const SHT_SYMTAB = 2;
const SHT_STRTAB = 3;
const SHF_EXECINSTR = 0x4;
const STT_NOTYPE = 0;
const STT_FUNC = 2;
const MAX_SECTION_HEADERS = 4096;
const MAX_SYMBOL_ENTRIES = 100_000;
const MAX_SYMBOL_NAME_BYTES = 512;
const MAX_DECODE_ADDRESSES = 64;

export const MAX_ELF_SYMBOL_FILE_BYTES = 32 * 1024 * 1024;

export class ElfSymbolError extends Error {}

interface ElfSection {
  type: number;
  flags: number;
  address: number;
  offset: number;
  size: number;
  link: number;
  entrySize: number;
}

interface RawSymbol {
  sectionIndex: number;
  address: number;
  size: number;
  name: string;
  type: number;
  binding: number;
}

export interface ElfSymbol {
  address: number;
  endAddress: number;
  name: string;
}

export interface ElfSymbolIndex {
  fileName: string;
  fileSize: number;
  sha256: string;
  symbolCount: number;
  symbols: readonly ElfSymbol[];
}

export interface SymbolicatedAddress {
  address: number;
  symbol: string | null;
  offset: number | null;
}

function boundedRange(offset: number, size: number, total: number, label: string): void {
  if (
    !Number.isSafeInteger(offset) ||
    !Number.isSafeInteger(size) ||
    offset < 0 ||
    size < 0 ||
    offset > total ||
    size > total - offset
  ) {
    throw new ElfSymbolError(`ELF ${label} is outside the uploaded file`);
  }
}

function readSections(view: DataView): ElfSection[] {
  const sectionOffset = view.getUint32(32, true);
  const sectionEntrySize = view.getUint16(46, true);
  const sectionCount = view.getUint16(48, true);
  if (
    sectionCount < 1 ||
    sectionCount > MAX_SECTION_HEADERS ||
    sectionEntrySize < ELF_SECTION_HEADER_BYTES
  ) {
    throw new ElfSymbolError("ELF section table is unsupported or unbounded");
  }
  boundedRange(
    sectionOffset,
    sectionEntrySize * sectionCount,
    view.byteLength,
    "section table",
  );

  const sections: ElfSection[] = [];
  for (let index = 0; index < sectionCount; index += 1) {
    const offset = sectionOffset + index * sectionEntrySize;
    sections.push({
      type: view.getUint32(offset + 4, true),
      flags: view.getUint32(offset + 8, true),
      address: view.getUint32(offset + 12, true),
      offset: view.getUint32(offset + 16, true),
      size: view.getUint32(offset + 20, true),
      link: view.getUint32(offset + 24, true),
      entrySize: view.getUint32(offset + 36, true),
    });
  }
  return sections;
}

function readSymbolName(bytes: Uint8Array, offset: number): string | null {
  if (offset <= 0 || offset >= bytes.length) return null;
  const limit = Math.min(bytes.length, offset + MAX_SYMBOL_NAME_BYTES);
  let end = offset;
  while (end < limit && bytes[end] !== 0) end += 1;
  if (end === offset || end === limit) return null;
  const name = new TextDecoder().decode(bytes.subarray(offset, end));
  if (/\p{C}/u.test(name)) return null;
  return name;
}

function preferSymbol(candidate: RawSymbol, current: RawSymbol): boolean {
  if (candidate.type !== current.type) return candidate.type === STT_FUNC;
  if (candidate.binding !== current.binding) return candidate.binding !== 0;
  if (candidate.size !== current.size) return candidate.size > current.size;
  return candidate.name.length < current.name.length;
}

function readSymbols(
  view: DataView,
  bytes: Uint8Array,
  sections: readonly ElfSection[],
): ElfSymbol[] {
  const selected = new Map<string, RawSymbol>();
  let totalSymbolEntries = 0;
  for (const symbolSection of sections) {
    if (symbolSection.type !== SHT_SYMTAB) continue;
    if (
      symbolSection.entrySize < ELF_SYMBOL_BYTES ||
      symbolSection.size % symbolSection.entrySize !== 0
    ) {
      throw new ElfSymbolError("ELF symbol table has an invalid entry size");
    }
    const symbolCount = symbolSection.size / symbolSection.entrySize;
    totalSymbolEntries += symbolCount;
    if (totalSymbolEntries > MAX_SYMBOL_ENTRIES) {
      throw new ElfSymbolError("ELF symbol table exceeds the browser safety limit");
    }
    const stringSection = sections[symbolSection.link];
    if (!stringSection || stringSection.type !== SHT_STRTAB) {
      throw new ElfSymbolError("ELF symbol table has no valid string table");
    }
    boundedRange(
      symbolSection.offset,
      symbolSection.size,
      view.byteLength,
      "symbol table",
    );
    boundedRange(
      stringSection.offset,
      stringSection.size,
      view.byteLength,
      "symbol string table",
    );
    const strings = bytes.subarray(
      stringSection.offset,
      stringSection.offset + stringSection.size,
    );

    for (let index = 0; index < symbolCount; index += 1) {
      const offset = symbolSection.offset + index * symbolSection.entrySize;
      const nameOffset = view.getUint32(offset, true);
      const address = view.getUint32(offset + 4, true);
      const size = view.getUint32(offset + 8, true);
      const info = view.getUint8(offset + 12);
      const type = info & 0x0f;
      const binding = info >> 4;
      const sectionIndex = view.getUint16(offset + 14, true);
      const executableSection = sections[sectionIndex];
      if (
        !executableSection ||
        (executableSection.flags & SHF_EXECINSTR) === 0 ||
        (type !== STT_FUNC && type !== STT_NOTYPE) ||
        address < executableSection.address ||
        address >= executableSection.address + executableSection.size
      ) {
        continue;
      }
      const name = readSymbolName(strings, nameOffset);
      if (!name) continue;
      const candidate: RawSymbol = {
        sectionIndex,
        address,
        size,
        name,
        type,
        binding,
      };
      const key = `${sectionIndex}:${address}`;
      const current = selected.get(key);
      if (!current || preferSymbol(candidate, current)) selected.set(key, candidate);
    }
  }

  const grouped = new Map<number, RawSymbol[]>();
  for (const symbol of selected.values()) {
    const group = grouped.get(symbol.sectionIndex) ?? [];
    group.push(symbol);
    grouped.set(symbol.sectionIndex, group);
  }

  const symbols: ElfSymbol[] = [];
  for (const [sectionIndex, group] of grouped) {
    group.sort((left, right) => left.address - right.address);
    const section = sections[sectionIndex];
    const sectionEnd = section.address + section.size;
    for (let index = 0; index < group.length; index += 1) {
      const symbol = group[index];
      const declaredEnd = symbol.size > 0 ? symbol.address + symbol.size : sectionEnd;
      const nextAddress = group[index + 1]?.address ?? sectionEnd;
      const endAddress = Math.min(sectionEnd, declaredEnd, nextAddress);
      if (endAddress <= symbol.address) continue;
      symbols.push({
        address: symbol.address,
        endAddress,
        name: symbol.name,
      });
    }
  }
  symbols.sort((left, right) => left.address - right.address);
  return symbols;
}

export async function inspectElfSymbols(file: File): Promise<ElfSymbolIndex> {
  if (file.size < ELF_HEADER_BYTES || file.size > MAX_ELF_SYMBOL_FILE_BYTES) {
    throw new ElfSymbolError(
      `ELF file must be between ${ELF_HEADER_BYTES} bytes and 32 MiB`,
    );
  }
  const payload = await file.arrayBuffer();
  const bytes = new Uint8Array(payload);
  const view = new DataView(payload);
  if (
    bytes[0] !== 0x7f ||
    bytes[1] !== 0x45 ||
    bytes[2] !== 0x4c ||
    bytes[3] !== 0x46
  ) {
    throw new ElfSymbolError("Debug symbols must use an ELF file");
  }
  if (
    bytes[4] !== ELFCLASS32 ||
    bytes[5] !== ELFDATA2LSB ||
    bytes[6] !== EV_CURRENT ||
    view.getUint16(18, true) !== EM_XTENSA ||
    view.getUint32(20, true) !== EV_CURRENT
  ) {
    throw new ElfSymbolError("Debug symbols must be a 32-bit little-endian Xtensa ELF");
  }

  const symbols = readSymbols(view, bytes, readSections(view));
  if (symbols.length === 0) {
    throw new ElfSymbolError("ELF contains no usable executable symbols");
  }
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", payload));
  return {
    fileName: file.name,
    fileSize: file.size,
    sha256: [...digest]
      .map((value) => value.toString(16).padStart(2, "0"))
      .join(""),
    symbolCount: symbols.length,
    symbols,
  };
}

export function symbolicateAddress(
  index: ElfSymbolIndex,
  address: number,
): SymbolicatedAddress {
  let low = 0;
  let high = index.symbols.length - 1;
  let match: ElfSymbol | null = null;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    const candidate = index.symbols[middle];
    if (candidate.address <= address) {
      match = candidate;
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  if (!match || address >= match.endAddress) {
    return { address, symbol: null, offset: null };
  }
  return { address, symbol: match.name, offset: address - match.address };
}

export function decodeBacktrace(
  input: string,
  index: ElfSymbolIndex,
): SymbolicatedAddress[] {
  const addresses: number[] = [];
  const seen = new Set<number>();
  const pattern = /\b(?:0x)?([0-9a-f]{8})\b/giu;
  for (const match of input.matchAll(pattern)) {
    const address = Number.parseInt(match[1], 16);
    if (!seen.has(address)) {
      seen.add(address);
      addresses.push(address);
    }
    if (addresses.length >= MAX_DECODE_ADDRESSES) break;
  }
  return addresses.map((address) => symbolicateAddress(index, address));
}
