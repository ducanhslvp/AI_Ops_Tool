# AIOps Platform

Enterprise AI Infrastructure Operations Platform. AI can orchestrate backend-registered tools but
cannot read credentials, connect over SSH, access the database, or submit arbitrary shell commands.

The canonical architecture, security, module, extension, development, and production guide is
[PROJECT_DOCUMENTATION.md](docs/PROJECT_DOCUMENTATION.md).

AI Agents and engineers joining the current implementation should start with
[AI_AGENT_SYSTEM_GUIDE.md](docs/AI_AGENT_SYSTEM_GUIDE.md). It is the single detailed map of the Web,
Backend, database, security gateways, persistent Workspace/Memory, APIs, and extension rules.

## Quick Start

Prerequisites: Python 3.12+, Node.js 20+ and npm 10+.

Windows:

```powershell
.\scripts\setup_windows.ps1
```

Linux:

```bash
sh scripts/setup_linux.sh
```

macOS:

```bash
sh scripts/setup_mac.sh
```

The setup scripts create strong local secrets, install locked frontend dependencies, install the backend, apply migrations and seed non-production data. They then expose the UI at `http://127.0.0.1:5173`, API at `http://127.0.0.1:8000`, OpenAPI at `http://127.0.0.1:8000/api/v1/docs` and metrics at `http://127.0.0.1:8000/metrics`.

Use `-NoStart` with the PowerShell setup script to install without starting services. For subsequent runs use `scripts/run_all.ps1`, `scripts/run_all.bat` or `sh scripts/run_all.sh`.

## Demo Accounts

Demo seed data is forbidden when `APP_ENV=production`.

| Role | Email | Password |
| --- | --- | --- |
| Admin | `admin@aiops.example.com` | `Admin@123456` |
| Operator | `operator@aiops.example.com` | `Operator@123456` |
| Viewer | `viewer@aiops.example.com` | `Viewer@123456` |

## Quality Gates

```bash
cd backend
python -m ruff check app tests scripts
python -m ruff format --check app tests scripts
python -m pytest -q

cd ../ShadcnTemplateFE
npm run lint
npm test -- --run
npm run build
```

## Safety Contract

`AI -> Tool Registry -> Policy -> Approval -> Backend-owned execution -> Audit`

Tool arguments are validated against strict schemas. The registry maps actions such as `check_disk`, `tail_log` and `restart_service` to fixed platform commands. High-risk operations fail closed and require a separate approver. Every decision and execution is added to a chained SHA-256 audit record.
