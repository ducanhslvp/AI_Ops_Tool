$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$frontendRoot = Join-Path $projectRoot 'ShadcnTemplateFE'
$python = Join-Path $backendRoot '.venv\Scripts\python.exe'

Push-Location $backendRoot
try {
    & $python -m ruff check app tests alembic
    & $python -m pytest -q
} finally {
    Pop-Location
}

Push-Location $frontendRoot
try {
    npm run lint
    npm run test
    npm run build
} finally {
    Pop-Location
}

Write-Host 'All backend and frontend checks passed.'
