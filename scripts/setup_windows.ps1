param([switch]$NoStart)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$frontendRoot = Join-Path $projectRoot 'ShadcnTemplateFE'
$python = Join-Path $backendRoot '.venv\Scripts\python.exe'

foreach ($command in @('python', 'node', 'npm')) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Required command '$command' is not installed or not on PATH."
    }
}

if (-not (Test-Path -LiteralPath $python)) {
    python -m venv (Join-Path $backendRoot '.venv')
}

& $python -m pip install --upgrade pip
Push-Location $backendRoot
try {
    & $python -m pip install -e '.[dev]'
    $envPath = Join-Path $backendRoot '.env'
    if (-not (Test-Path -LiteralPath $envPath)) {
        $content = Get-Content -Raw -LiteralPath (Join-Path $backendRoot '.env.example')
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try {
            $keys = 1..3 | ForEach-Object {
                $bytes = New-Object byte[] 48
                $rng.GetBytes($bytes)
                [Convert]::ToBase64String($bytes)
            }
        } finally {
            $rng.Dispose()
        }
        $content = $content.Replace('change-me-with-64-random-characters', $keys[0])
        $content = $content.Replace('change-me-refresh-secret', $keys[1])
        $content = $content.Replace('SECRET_ENCRYPTION_KEY=', "SECRET_ENCRYPTION_KEY=$($keys[2])")
        Set-Content -LiteralPath $envPath -Value $content -Encoding utf8
    }
    & $python -m alembic upgrade head
    & $python (Join-Path $projectRoot 'scripts\seed_backend.py')
} finally {
    Pop-Location
}

Push-Location $frontendRoot
try {
    npm ci
} finally {
    Pop-Location
}

Write-Host 'Setup complete. API: http://127.0.0.1:8000  UI: http://127.0.0.1:5173'
if (-not $NoStart) {
    & (Join-Path $PSScriptRoot 'run_all.ps1')
}
