$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $projectRoot 'ShadcnTemplateFE'
if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'node_modules'))) {
    throw 'Frontend dependencies are missing. Run scripts\setup_windows.ps1 first.'
}
Push-Location $frontendRoot
try {
    npm run dev -- --host 127.0.0.1 --port 5173
} finally {
    Pop-Location
}
