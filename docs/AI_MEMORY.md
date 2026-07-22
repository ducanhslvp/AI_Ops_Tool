# AI Memory

## Model

`AiMemory` stores searchable metadata: System, optional conversation, category, topic, summary,
source references, file path, occurrence time, and archive time. The corresponding JSON file is the
AI-readable record. Categories are `summaries`, `operations`, `incidents`, `decisions`, and `daily`.

Memory creation is backend-owned and deterministic. A successful turn always creates a summary;
tool use creates an operation; tool errors create an incident; policy outcomes create a decision.
The backend stores only normalized tool name, decision, approval reference, and redacted error in
Memory. Raw tool output and mapped SSH commands remain in immutable Audit.

## Conversations

The database remains the Web conversation source. A redacted JSONL projection is written under
`conversations/YYYY-MM/`, and its latest summary under `summaries/`. It includes user message, AI
response, normalized tool events, timestamp, and Audit session reference. This provides continuity
without exposing credentials or raw execution evidence to an adapter.

## Lifecycle Operations

- Reset Conversation deletes System conversation messages and sessions, but detaches and preserves Memory.
- Reset Memory deletes learned Memory and history, but preserves conversations and all Knowledge.
- Refresh Memory rebuilds deterministic summaries from retained conversations.
- Archive Memory moves active files to `memory/archive` and excludes them from default context.
- Refresh Knowledge regenerates converted and projected material from retained sources.
- Rebuild Workspace regenerates only derived files and never deletes original uploads.

Every destructive or rebuilding API requires the exact System code as confirmation. Access uses the
existing `ai:chat` permission and remains auditable through normal API logging.
