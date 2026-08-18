# Agent Note: Adopt repository governance

Status: implemented

English | [中文](2026-08-18-adopt-repository-governance.zh.md)

## Problem

The public simulator core had strong architecture, protocol, security,
conformance, licensing, and worker-isolation documentation, but it lacked a
portable Agent Notes lifecycle, bilingual core architecture, and local
governance checks. General durable rationale had no lightweight owner distinct
from current contracts and specialized evidence records.

## Decision

The repository carries the universal governance protocol locally: a visible,
bilingual Agent Notes lifecycle and local verifiers; equal-authority English and
Chinese versions of the existing architecture owner; and cold-start rules for
lightweight specification, evidence-based simplification, documentation
ownership, change-specific testing, and conditional postmortems. Specialized
security, conformance, licensing, and isolation documents retain their current
contract and evidence ownership.

## Alternatives considered

- Use conformance or security docs as the universal decision history. They own
  specialized current evidence and must not become a catch-all process log.
- Depend only on workspace governance. That fails for an independently cloned
  public open-source repository.
- Add a second architecture summary instead of translating the current owner.
  That would create competing current architecture documents.

## Consequences

General durable rationale gains one lifecycle without weakening GPL/licensing,
untrusted-firmware, emulator, isolation, protocol, or conformance rules. The
architecture remains one current owner in two equal-authority languages.
Foundation checks do not replace QEMU builds, firmware conformance, Bubblewrap
or OCI probes, physical hardware, or rendered browser evidence. No simulator,
protocol, emulator, isolation, licensing, conformance, web, or runtime behavior changes.

## Verification

- `make check` passed: foundation policy and Ruff passed, all 89 Python tests
  passed, TypeScript passed, all 24 web tests passed, and the Vite production
  build completed successfully.
- The full check included the pre-existing curated-demo commit `4699c7f`.
- `node tools/governance/verify_agent_notes.mjs` passed.
- `node tools/governance/verify_bilingual_docs.mjs` passed.
- `git diff --check` passed.
- QEMU, firmware conformance, Bubblewrap/OCI, Playwright, and physical-device
  gates were not run and are not claimed.
