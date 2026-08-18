# Agent Notes

English | [中文](README.zh.md)

Agent Notes preserve durable proposals and decisions for this repository. They
own why a choice exists, which genuine alternatives lost, what the choice gives
up, and how the result is verified.

## Layout And Classes

Use `{lifecycle}/{class}/yyyy-mm-dd-topic.md`.

- `proposed`: intended decision, acceptance criteria, and risks.
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

Proposed notes contain `Problem`, `Proposal`, `Alternatives considered`,
`Acceptance criteria`, and `Risks`. Implemented notes contain `Problem`,
`Decision`, `Alternatives considered`, `Consequences`, and `Verification`.
Rejected notes keep the proposed body and use
`Status: rejected — <reason>`.

Partly implemented work remains proposed. Implemented notes stay factually
current when paths or defaults move. Superseding decisions get new cross-linked
notes; do not rewrite an old decision into its opposite. Archived triplets are
frozen and are not current authority.
