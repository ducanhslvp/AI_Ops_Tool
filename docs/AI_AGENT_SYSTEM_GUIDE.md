# AIOps Platform - Complete Guide for AI Agents and Engineers

> Canonical implementation guide for `D:\CODE\AI_Ops_Tool`.
> Last verified: 2026-07-22. Read this before changing architecture, APIs, security,
> AI adapters, Workspace behavior, database models, or frontend navigation.

## 1. Product and Non-Negotiable Boundary

This repository is an enterprise AI Infrastructure Operations Platform, not a Web SSH client. The
browser manages Systems, servers, Knowledge, policies, approvals, discovery, reports, conversations,
and AI Memory. AI providers plan and interpret evidence, but cannot read credentials, connect to
infrastructure, query the application database, or submit arbitrary shell.

```text
User -> React Web -> FastAPI -> RBAC -> Tool Registry -> Policy Engine
     -> Approval when required -> Secret Manager -> SSH Gateway -> Target
     -> bounded result -> Audit -> AI response -> System Workspace Memory
```

The backend is a Workspace Builder, Security Gateway, Tool Gateway, and Audit/Lifecycle Service.
It does not perform vector RAG or independent AI reasoning. Provider adapters receive bounded files
selected from one System Workspace and may request only registered tools.

## 2. Repository Map

```text
D:\CODE\AI_Ops_Tool\
  backend/
    app/
      ai/                     provider contracts, manager, gateway, adapters
      api/v1/routes/          REST and SSE controllers
      core/                   settings, JWT, errors, logging, telemetry
      db/                     SQLAlchemy base and async sessions
      domain/models/          ORM entities and enums
      middleware/             rate limit, request context, security headers
      repositories/           persistence abstractions
      schemas/                Pydantic API contracts
      services/               application/security/tool/session services
      workers/                scheduled workflows
      workspace/              secure storage, builder, context selector
    alembic/versions/         database migrations
    config/providers.yaml     bootstrap provider configuration
    data/aiops.db             local SQLite database
    data/workspaces/          persistent per-System AI workspaces
    tests/                    backend tests
  ShadcnTemplateFE/           production React frontend
    src/components/           shared UI and layout
    src/features/aiops/       product screens
    src/routes/               TanStack file routes
    src/lib/api-client.ts     authenticated HTTP and SSE transport
    src/routeTree.gen.ts      generated route tree; do not hand-edit
  docs/                       architecture and operating documentation
  scripts/                    setup, run, seed, reset, scheduler scripts
  docker/                     container assets
  shadcn-admin/               UI reference only, not the production frontend
```

Always modify `ShadcnTemplateFE/` for product UI. Do not create a second frontend. Use
`shadcn-admin/` only as the reference for DataTable and administrative interaction patterns.

## 3. Technology and Runtime

### Backend

- Python, FastAPI, async endpoints, async SQLAlchemy, Pydantic, Alembic.
- SQLite through `sqlite+aiosqlite:///./data/aiops.db`; ORM/migrations remain PostgreSQL-portable.
- Migration head at this verification point: `202607220001`.
- JWT access tokens and rotating hashed refresh sessions.
- bcrypt passwords; encrypted credentials behind the Secret Manager abstraction.
- Structured logging, request IDs, health, metrics, OpenTelemetry hooks, gzip, strict CORS,
  security headers, and rate limiting are installed in `app/main.py`.

### Frontend

- React 19, TypeScript, Vite, TanStack Router/Query/Table.
- Shadcn/Radix UI, Tailwind CSS, Lucide icons, Sonner toast.
- React Flow for Discovery and resizable panels for primary work surfaces.
- Dark mode by default with light mode support.
- `src/lib/api-client.ts` rotates refresh tokens, retries one 401, clears invalid auth, and handles SSE.

### Local URLs

- Web: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8000`
- OpenAPI: `http://127.0.0.1:8000/api/v1/docs`
- Metrics: `http://127.0.0.1:8000/metrics`

Development seed accounts are in the root README. Seed data is forbidden in production.

## 4. Backend Startup Sequence

`backend/app/main.py` lifespan performs these operations in order:

1. Optionally create schema only when explicitly configured for local/test use.
2. Initialize the provider-neutral AI Manager.
3. Restore the database-selected active provider.
4. Reconcile legacy AI Session ownership from audited Server targets.
5. Synchronize every System Workspace from current database state.
6. Migrate old Workspace Memory layout and index missing Memory metadata.
7. Commit reconciliation and serve traffic.
8. Close providers and database engine during shutdown.

Production must run `alembic upgrade head` before API startup. Do not use automatic schema creation
as a production migration strategy.

## 5. Database Model

Models live in `backend/app/domain/models/entities.py`.

### Identity

- `User`: identity, password hash, active state, Role.
- `Role`, `Permission`, `RolePermission`: RBAC.
- `RefreshToken`: hashed, expiring, revocable login session.

### Infrastructure

- `System`: operational ownership and Workspace boundary.
- `Environment`: Development, Testing, UAT, Staging, or Production risk context.
- `Server`: System/Environment, hostname, IP, OS, type, role, tags, status, SSH metadata,
  and a Credential reference.
- `Credential`: encrypted Secret Manager payload. Plain values are write-only and never returned.

### Governance

- `ToolConfiguration`: editable public tool metadata; raw command mappings remain backend-only.
- `PolicyRule`: prioritized allow, deny, or approval-required rule.
- `ApprovalRequest`: plan, reason, impact, requester, status, and decision.
- `AuditLog`: immutable sequence and SHA-256 chain with prompt, normalized tool, mapped command,
  bounded output, decision, duration, result, user, session, and target.

### Knowledge and operations

- `KnowledgeDocument`: metadata and Workspace source URI. New upload text is not retained in DB.
- `DiscoveryScan`, `DiscoverySchedule`: normalized snapshots, topology, evidence, schedules.
- `Report`, `ReportTemplate`: persisted evidence and approved layouts.
- `Alert`: System/server operational alert.
- `Plugin`, `PlatformSetting`, `NotificationChannel`, `SshGatewayProfile`: platform extensions.

### AI persistence

- `AiSession`: Web conversation, user, System, status, activity, context size, provider thread ID.
- `AiMessage`: user/assistant message, tool timeline, confidence.
- `AiMemory`: searchable category/topic/summary, source references, file path, archive state.
- `AiProviderConfiguration`: adapter, model/transport, Secret reference, active/exclusive and health state.

Never place plaintext credentials or provider keys in JSON fields that can enter AI context.

## 6. System Workspace

Every safe System code maps to a persistent directory:

```text
backend/data/workspaces/ERP/
  docs/ uploads/ runbooks/ skills/
  generated/ discovery/ inventory/ reports/
  memory/{daily,incidents,operations,summaries,decisions,archive}/
  conversations/YYYY-MM/ summaries/ history/ context/
  servers.yaml policy.yaml tools.md system_prompt.md README.md
  inventory.md architecture.md topology.md dependencies.md services.md
  .workspace-manifest.json
```

`WorkspaceStorage` enforces root containment, rejects unsafe symlinks, and atomically replaces files.
`WorkspaceBuilder` validates System codes, serializes synchronization per System, and uses explicit
field allowlists. `servers.yaml` excludes credential IDs, SSH configuration, usernames, passwords,
tokens, keys, certificates, and encrypted payloads. `tools.md` excludes raw command templates.

Inventory, Knowledge, Runbook, Policy, Tool, Discovery, and Report mutations synchronize the affected
Workspace automatically. Startup reconciliation repairs interrupted DB/filesystem synchronization.
Original uploads are preserved through refresh, rebuild, and provider restart.

## 7. Knowledge and Memory Are Separate

Knowledge originates from uploads, authored Runbooks, Inventory, Discovery, and Reports. Originals
live under `uploads/`; PDF/DOCX/TXT/Markdown conversions live under `generated/`.

Memory originates from governed AI work:

- Every successful turn creates `summaries`.
- Tool use creates `operations`.
- Tool errors create `incidents`.
- Policy/approval outcomes create `decisions`.
- `daily` is reserved for scheduled consolidation.

Memory contains final summaries, confidence, source references, normalized tool names, decisions,
approval references, and redacted errors. Raw stdout, secrets, and mapped SSH commands stay in Audit.

| Maintenance action | Conversations | Memory | Knowledge/uploads | Derived files |
|---|---|---|---|---|
| Reset Conversation | delete | preserve and detach | preserve | preserve |
| Reset Memory | preserve | delete | preserve | clear learned Memory |
| Refresh Memory | preserve | rebuild from conversation | preserve | rewrite Memory |
| Archive Memory | preserve | move to archive | preserve | archive excluded |
| Refresh Knowledge | preserve | preserve | preserve originals | re-extract |
| Rebuild Workspace | preserve | preserve | preserve originals | regenerate |

Every maintenance call requires exact `confirm_system_code` to prevent cross-System mistakes.

## 8. Deterministic Context Builder

`backend/app/workspace/context.py` does not use embeddings. Before every provider request it selects:

1. `system_prompt.md`.
2. query-relevant Runbooks.
3. authored and generated Knowledge.
4. applicable Skills.
5. README, architecture, inventory, servers, policy, tool contract, dependencies, and services.
6. recent non-archived Memory.
7. current conversation summary.
8. recent reports.

The default hard budget is 80,000 characters and five recent Memory files. Selection and final size
are stored in `context/latest.json` and `AiSession.context_size`. If no System is selected, AI receives
only a minimal safety instruction and cannot execute a tool.

## 9. AI Adapter and Persistent Session

Adapters implement contracts in `backend/app/ai/models.py` and `app/ai/provider.py`. Application code
calls `AIGateway`; it never imports a concrete provider. Provider DB records are translated by
`services/ai_provider_runtime.py`.

### Codex CLI behavior

- Active local configuration: `codex-cli-local`, exclusive mode.
- Standalone Windows Codex is discovered under
  `%LOCALAPPDATA%\Programs\OpenAI\Codex\bin\codex.exe` before PATH fallback.
- Executable must match `CODEX_EXECUTABLE_ALLOWLIST`.
- Child environment is allowlisted and excludes application/database/JWT secrets.
- Codex runs read-only in the selected System Workspace.
- First turn runs `codex exec`; `thread.started` is stored on `AiSession`.
- Later turns run `codex exec resume <provider_session_id>`.
- A CLI subprocess exists only during one turn. Persistence comes from provider thread ID, DB Session,
  Workspace Memory, conversations, and rebuilt Context. This survives backend restart.
- Failed resume starts a replacement thread with rebuilt Context and saves the new ID.
- Health authentication probes are ephemeral and do not pollute operational sessions.

`AiSessionManager` locks by System/conversation, tracks `busy`, `idle`, or `error`, activity, Workspace,
and context size. Future providers may map the provider session ID or ignore it without service changes.

## 10. Controlled Tool Execution

AI never supplies shell. It may return a registered tool call with schema-valid arguments.

1. Gateway filters unknown tool names.
2. Operation Service validates selected Server and user permission.
3. Policy Engine evaluates Role, Environment, Server type, action, risk, time, and priority.
4. Deny stops; approval-required persists a request and stops.
5. Allowed action maps to an OS/plugin-specific reviewed command.
6. Secret Manager resolves credentials only inside backend execution.
7. SSH Gateway opens a short-lived session with connect/command/output limits and closes it.
8. Audit writes immutable evidence and integrity hash.
9. AI receives bounded/redacted evidence only.

Development simulation follows this same route and is available only in Development or explicit Test.
Configuration validation forbids simulation in UAT, Staging, and Production.

## 11. API Map

All paths are under `/api/v1`; OpenAPI is the exact schema authority.

### Auth

- `POST /auth/login`, `/auth/refresh`, `/auth/logout`
- `GET /auth/me`, `/auth/sessions`; `DELETE /auth/sessions/{id}`

### Inventory

- CRUD `/inventory/systems`, `/inventory/environments`, `/inventory/servers`
- `POST /inventory/servers/{id}/test-connection`
- CRUD `/inventory/credentials` with secret-free responses

### AI and Memory

- `POST /ai/chat`, `POST /ai/chat/stream`
- provider list/health/switch/reload/reconnect and cancellation under `/ai/...`
- System-scoped conversation create/list/detail/rename/delete under `/ai/sessions...`; list requires
  `system_id`, and a new conversation cannot be started before a System is selected
- `GET /ai/systems/{system_id}/session-status`
- `GET /ai/systems/{system_id}/memories`
- `POST /ai/systems/{system_id}/memories/compare`
- `GET /ai/systems/{system_id}/memories/export`
- `POST /ai/systems/{system_id}/{operation}` for reset, refresh, archive, rebuild

### Governance and evidence

- Tool list/update/delete and `POST /tools/execute`
- Policy rule CRUD/duplicate/status/bulk delete and approvals under `/policy/...`
- Audit list/detail/export/integrity under `/audit...`
- Knowledge CRUD/upload/reindex/download under `/knowledge...`
- Discovery scans/evidence and schedule CRUD/run under `/discovery...`
- Report CRUD/templates/download/compare under `/reports...`

### Administration

- Dashboard `/dashboard`, global search `/search`, health `/health`
- Users, Roles, Permissions, Providers, and settings under `/admin...`
- Development profiles/commands/server simulation under `/development...`; development only

Keep routes thin. Put behavior in services and Workspace classes. Preserve existing contracts unless
a coordinated migration and frontend update are necessary.

## 12. Frontend Screen Map

| URL | Main file | Responsibility |
|---|---|---|
| `/` | `features/dashboard/index.tsx` | health, alerts, audit, AI activity |
| `/inventory` | `features/aiops/inventory.tsx` | Systems, Environments, Servers, Credentials |
| `/inventory/servers/$serverId` | `features/aiops/server-detail.tsx` | Server detail |
| `/chats` | `features/aiops/ai-chat.tsx` | AI conversation and timeline |
| `/memory` | `features/aiops/memory.tsx` | Memory status, search, compare, lifecycle |
| `/terminal` | `features/aiops/terminal.tsx` | governed actions, never raw shell |
| `/discovery` | `features/aiops/discovery.tsx` | scans, schedules, React Flow topology |
| `/policy` | `features/aiops/policy.tsx` | Policy, Tools, approvals |
| `/knowledge` | `features/aiops/knowledge.tsx` | upload, reindex, preview, download |
| `/audit` | `features/aiops/audit.tsx` | immutable evidence timeline |
| `/reports` | `features/aiops/reports.tsx` | report generate/compare/download |
| `/users` | `features/aiops/user-admin.tsx` | Users and RBAC |
| `/settings/*` | `features/aiops/platform-settings.tsx` | provider/gateway/plugin/settings |
| `/development-test` | `features/aiops/development-test.tsx` | safe simulation admin |

Shared sticky Header and Main layout live under `components/layout`. Context Help is in
`components/contextual-help.tsx`; every major screen must add complete Help content.

Use `SearchableSelect` for API-backed choices and `EnterpriseDataTable` for records. Tables preserve
sticky header, internal scrolling, sticky right action column, visible Rows per page, full width,
text overflow handling, multi-select, and a `role="toolbar"` bulk action area.

The Chats screen follows a System-first contract. Selecting a System scopes the conversation list,
Workspace context, optional Environment/Server target, Memory, and new sessions. Its SSE timeline is
fed by real backend lifecycle events: request acceptance, session/context preparation, provider rounds,
tool request/result, audit write, and persistence completion. Do not replace these events with simulated
token delays. The answering indicator remains visible until the backend emits completion or error.

Audit list responses include bounded prompt/output previews. Audit detail stores the user prompt and the
exact secret-free provider input separately, plus provider, model, request ID, context source paths, tool
events, mapped command, output, and integrity hash. Codex records the exact CLI stdin for every provider
round. Adapter-neutral providers record their structured request snapshot when no wire serializer exists.
Never add credentials or Secret Manager payloads to these fields.

## 13. Security Invariants

1. AI never receives username, password, token, key, certificate, or encrypted Secret payload.
2. AI never sends shell, PowerShell, SQL, kubectl, or docker command strings.
3. Frontend never hardcodes API records or stores plaintext secrets.
4. Credentials are write-only to Secret Manager and never returned.
5. Workspace is path-contained and secret-free through explicit allowlists.
6. Production cannot enable local simulation or development test profiles.
7. High-risk writes follow Policy and Approval.
8. Audit is backend-owned and immutable through public APIs.
9. Provider failures map to controlled 503/504 responses, not generic 500 route crashes.
10. Do not silently break current API/UI contracts.

## 14. Safe Extension Recipes

### Add a Tool

Define normalized action and argument schema, add reviewed plugin/OS mapping, risk and targets, Policy
defaults, bounded/redacted output, tests for allow/deny/approval, and Audit assertions. Never expose
the command mapping in `tools.md`.

### Add an AI Provider

Implement provider protocol and provider-neutral request/response mapping. Keep credentials in Secret
Manager. Add health, timeout, cancellation, bounded output, public errors, optional session ID mapping,
Manager registration, Settings UI, adapter tests, fallback/exclusive tests, and restart verification.

### Add a Workspace Artifact

Identify whether it is Knowledge, Memory, or Audit; define a secret-free serializer; write only through
`WorkspaceStorage`; synchronize relevant mutations and startup; add to Context only when bounded and
relevant; test that credentials and raw command templates cannot leak.

### Codex Runtime, Compact Context, and SSH Proposals

Each `AiSession` persists an optional Codex model, `low|medium|high` reasoning effort, and the
full-memory preference. The first provider turn is a workspace bootstrap: Codex receives the System
identity, workspace revision, bootstrap filenames, at most one relevant runbook excerpt, bounded
Memory Summary, Recent Context, and the Current Task. A resumed provider thread receives only the
bounded recovery context and Current Task. Knowledge and the complete Workspace are never copied into
every prompt. `POST /api/v1/ai/systems/{system_id}/workspace/refresh` rebuilds derived artifacts and
marks the user's conversations to bootstrap the workspace on their next turn. The Chat workspace
dialog exposes secret-free file metadata and memory summaries.

Codex can propose `run_ssh_command({"command":"..."})`. It cannot open SSH. `SshCommandGuard`
tokenizes and canonicalizes one Linux read-only command, rejects shell operators and path traversal,
uses executable/subcommand allowlists, and blocks alternate-root/file options, Docker inspect/logs,
and Kubernetes secret-bearing resources. User command consent is distinct from organization policy:
Accept Once, Accept All This Session, and remembered exact-command consent never bypass Policy Deny,
RBAC, environment rules, output limits, Secret redaction, SSH Gateway, or independent high-risk
approval. Accept/Reject results are returned to the same persistent Codex thread.

Codex JSONL events are streamed as `codex_status`, `codex_activity`, and `codex_output`. Hidden
chain-of-thought is never exposed; only CLI-emitted status/activity and structured output are shown.
Audit stores exact provider input plus per-server SSH command, duration, exit code, approval use and
bounded output. The server detail Audit tab is the per-server command history.

### Add a Screen

Add a feature and authenticated file route, use shared Header/Main/Query/error/loading/table/select
patterns, add Context Help and permissions, regenerate `routeTree.gen.ts`, then run lint, browser tests,
production build, and a real browser smoke test.

## 15. Commands and Verification

From `backend/`:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

From `ShadcnTemplateFE/`:

```powershell
npm run lint
npm run test
npm run build
npm run dev -- --host 127.0.0.1 --port 5173
```

Latest verified baseline on 2026-07-22:

- Backend: 57 tests passed; Ruff passed; Alembic head `202607220004`.
- Frontend: 17 files / 108 tests passed; ESLint and production build passed.
- Real Codex CLI: `codex-cli-local`, exclusive, connected.
- Persistent session: first turn stored `PERSIST-7429`; the resumed turn returned `PERSIST-7429`.
- Browser `/chats`: System-scoped create/load flow, live answering indicator, provider/context Timeline,
  and a real Codex response `LIVE TIMELINE VERIFIED.` completed successfully.
- Browser `/audit`: prompt/output preview column, direct View action, full exact provider input, context
  sources and tool events loaded; integrity verification passed for 316 records.
- Browser `/chats`: High effort reached Codex CLI, first compact context was 1,150 characters and the
  resumed context was 985 characters. Live JSONL status/output rendered before completion.
- Browser command flow: Codex proposed `df -h`; Accept Once executed it through the simulated SSH
  transport, returned output to the same Codex thread, and produced a final evidence-based summary.
  Audit and Server detail displayed `df -h`, 89 ms, exit code 0 and bounded output.
- Backend and frontend dev services were left available at ports 8000 and 5173.

The >500 KB Vite chunk warning is currently non-blocking. Route code splitting is intentionally off
to avoid stale lazy chunks after long idle sessions. Revisit only with deployment-safe asset versioning.

## 16. Troubleshooting

### Chat/Terminal fails after idle

Check refresh-token rotation, provider health, API logs, and browser console. The API client retries one
401 after refresh. Provider errors should appear as 503/504.

### Codex installed but backend cannot execute it

Use standalone Codex outside WindowsApps under the same service account as FastAPI. Keep the executable
in `CODEX_EXECUTABLE_ALLOWLIST`, sign in under that account, and run Test Connection. Health probes use
a minimal ephemeral request.

### Workspace stale

Confirm the mutation route calls `WorkspaceBuilder`. Restart for reconciliation. Use Refresh Knowledge
for conversions or Rebuild Workspace for derived files. Never manually delete `uploads/`.

### Memory missing after upgrade

Startup moves old `memory/*.json` into `memory/summaries/` and creates missing `AiMemory` metadata with
source `workspace_migration`. Check startup logs and filesystem permissions.

### Database mismatch

Run `alembic current` and `alembic upgrade head`. Do not add columns manually. Stop stale API processes
before SQLite migration if a file lock exists.

## 17. Required Workflow for Future AI Agents

1. Read this guide and inspect current git status.
2. Read the relevant focused documents listed below.
3. Trace route -> service -> model -> Workspace/Audit before editing.
4. Preserve security invariants and API contracts.
5. Add Alembic migration for persistent schema changes.
6. Add focused tests proportional to risk.
7. Run full backend and frontend regressions.
8. Browser-test UI changes and inspect console errors.
9. Update this guide when architecture, routes, lifecycle, or baseline changes.

Companion documents:

- `docs/PROJECT_DOCUMENTATION.md`
- `docs/AI_WORKSPACE.md`
- `docs/AI_MEMORY.md`
- `docs/AI_CONTEXT_BUILDER.md`
- `docs/SESSION_MANAGER.md`
