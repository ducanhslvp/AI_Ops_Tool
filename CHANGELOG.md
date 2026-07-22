# Changelog

## 2026-07-20 - Production hardening

- Enforced refresh rotation, RBAC, approval integrity, strict tool DSL and SSH host verification.
- Added AES-256-GCM secret storage, chained immutable audit verification and observability endpoints.
- Replaced frontend mock authentication and operational data with protected API-backed workflows.
- Added deterministic migrations, cross-platform setup scripts, hardened containers, tests and operations documentation.

## 0.2.0 - 2026-07-20

- Replaced mock frontend login with API-backed authentication and protected routes.
- Added refresh-token rotation, revocation, session management, and logout.
- Hardened Tool Registry validation, policy approvals, SSH host verification, and audit chaining.
- Added deterministic Alembic schema migration and cross-platform setup/run scripts.
- Hardened Docker images, reverse proxy, health checks, networking, and runtime users.

## 0.1.0 - 2026-07-20

- Initial modular AIOps platform implementation.
