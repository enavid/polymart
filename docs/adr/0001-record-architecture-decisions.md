# ADR 0001 — Record architecture decisions

- Status: Accepted
- Date: 2026-06-27

## Context
We need a lightweight, durable record of significant architecture decisions so
that future contributors (human or AI) understand *why* the system is shaped the
way it is, not just *how*.

## Decision
We will keep Architecture Decision Records (ADRs) as Markdown files in
`docs/adr/`, numbered sequentially. Each ADR captures context, the decision, and
its consequences. ADRs are immutable once accepted; a superseding decision gets a
new ADR that references the old one.

## Consequences
- Every substantial architectural choice gets an ADR.
- The roadmap and CLAUDE.md reference ADRs instead of duplicating rationale.
