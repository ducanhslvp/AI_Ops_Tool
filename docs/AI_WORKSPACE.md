# AI Workspace Architecture

## Purpose

Each System owns a persistent, secret-free filesystem projection. AI adapters receive a bounded
selection from this workspace and never query the application database. The database remains the
transactional source for inventory, policy, audit, searchable memory metadata, and Web UI records.

## Layout

```text
data/workspaces/<SYSTEM_CODE>/
  docs/ uploads/ runbooks/ skills/
  generated/ discovery/ inventory/ reports/
  memory/{daily,incidents,operations,summaries,decisions,archive}/
  conversations/YYYY-MM/ summaries/ history/ context/
  servers.yaml policy.yaml tools.md system_prompt.md README.md
  architecture.md topology.md dependencies.md services.md inventory.md
```

`uploads/` contains immutable originals. Converted text belongs in `generated/`. Knowledge and
Memory are separate: Knowledge comes from users, Inventory, or Discovery; Memory is learned from
governed AI work. `WorkspaceBuilder` uses safe System codes, containment checks, atomic replacement,
per-System locks, and explicit field allowlists. Credentials, SSH configuration, command templates,
tokens, private keys, and encrypted payloads are never projected.

## Synchronization

Inventory, Knowledge, Runbook, Policy, Tool, Discovery, and Report mutations call the builder before
commit. Startup reconciliation repairs a projection after an interrupted database/filesystem update.
Original uploads are never removed by refresh or rebuild. `Rebuild Workspace` deletes only generated
and context artifacts, then projects current database state again.

## Extension

Add a generated artifact through `WorkspaceBuilder`, keep its source-of-truth owner explicit, apply a
secret-free allowlist, and include it in `WorkspaceContextBuilder` only when it is useful and bounded.
Never let provider code read ORM models or construct paths outside `WorkspaceStorage`.
