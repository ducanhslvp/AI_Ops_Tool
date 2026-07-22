# AI Session Manager

## Lifecycle

`AiSessionManager` scopes execution by System and conversation, serializes concurrent turns with an
in-process lock, and persists `busy`, `idle`, or `error`, last activity, context size, Workspace path,
and provider session ID. Existing chat session IDs and APIs remain compatible.

For Codex CLI, persistence uses the documented `codex exec resume <SESSION_ID>` transport. The first
turn starts a read-only Codex thread in the selected System Workspace; subsequent turns resume that
thread. A non-interactive CLI subprocess exists only for the duration of a turn. This is safer and
more recoverable than keeping an unbounded interactive process alive. If resume fails, the adapter
starts a replacement thread using rebuilt Workspace context and stores its new thread ID.

Other adapters may map `provider_session_id` to their native conversation/thread identifier or ignore
it. The service layer does not import a concrete provider. Tool execution remains Backend Tool
Gateway -> Policy -> Approval -> SSH Gateway -> Audit.

## Status

`GET /api/v1/ai/systems/{system_id}/session-status` returns current provider, connection state,
logical session status, last activity, Workspace path, context size, Memory size, and conversation
count. Backend restart does not erase these fields or Workspace context.
