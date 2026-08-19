# Agent Notes

English | [中文](README.zh.md)

Agent Notes preserve durable proposals and decisions for this repository. They
own why a choice exists, which genuine alternatives lost, what the choice gives
up, and how the result is verified.

## Layout And Classes

Use `{lifecycle}/{class}/yyyy-mm-dd-topic.md`.

- `proposed`: shaped proposal awaiting explicit implementation authorization.
- `building`: explicitly authorized work that is not ready for acceptance.
- `review`: candidate implementation with verification awaiting Simon.
- `implemented`: present-tense shipped rationale, consequences, and evidence.
- `rejected`: declined proposal kept only while it prevents a plausible error.
- `archived`: frozen, low-future-value implemented notes only.

Classes are `feature`, `bug-fix`, `simplification`, `architecture`, `process`,
and `testing`. `refactor` is not a class; name the purpose. The directory tree
and search are the inventory; do not maintain a central index.

## Trigger And Exemption

Add or update a note for durable changes to behavior, architecture, shared
contracts, process or tooling, testing strategy, configuration, durable or wire
formats, or another decision likely to be revisited. Purely mechanical or local
edits changing none of those are exempt. Update an existing owning note instead
of creating a duplicate.

## Bilingual Contract

Every note is an equal-authority `.md`, `.zh.md`, and `.i18n.yaml` triplet.
Either language may be authored first. Both sides mirror headings, lists,
tables, links, and code blocks. The unsuffixed English path is an ecosystem
default, not a higher authority.

## Required Format

Proposed and building notes contain `Problem`, `Proposal`, `Alternatives
considered`, `Acceptance criteria`, and `Risks`. Review notes retain that
structure and add `Verification` after `Risks`. Implemented notes contain
`Problem`, `Decision`, `Alternatives considered`, `Consequences`, and
`Verification`. Rejected notes keep the proposed body and use
`Status: rejected — <reason>`.

Proposed does not authorize implementation. Explicit approval moves the complete
triplet to building. Partly implemented work remains building. A verified
candidate moves to review; requested changes return it to building. Only
Simon-accepted shipped work is rewritten and moved to implemented. The folder
and matching status line are the only lifecycle authority; do not shadow them
in a task or database. Every move includes both languages and the sidecar and
repairs inbound links. Archived triplets are frozen and are not current
authority.
