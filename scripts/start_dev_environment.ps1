param([int]$BackendPort = 8000, [int]$FrontendPort = 5173, [switch]$ResetData)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'ShadcnTemplateFE'
$run = Join-Path $root '.run'
New-Item -ItemType Directory -Force $run | Out-Null
$env:APP_ENV = 'development'
$env:TEST_MODE = 'true'
$env:SSH_TRANSPORT = 'local_simulation'
Push-Location $backend
try { & (Join-Path $backend '.venv\Scripts\alembic.exe') upgrade head }
finally { Pop-Location }
if ($ResetData) { & (Join-Path $backend '.venv\Scripts\python.exe') (Join-Path $root 'scripts\reset_development_data.py') }
else { & (Join-Path $backend '.venv\Scripts\python.exe') (Join-Path $root 'scripts\seed_backend.py') }
$api = Start-Process -FilePath (Join-Path $backend '.venv\Scripts\python.exe') -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port',$BackendPort -WorkingDirectory $backend -WindowStyle Hidden -PassThru
$env:VITE_API_BASE_URL = "http://127.0.0.1:$BackendPort/api/v1"
$web = Start-Process -FilePath 'npm.cmd' -ArgumentList 'run','dev','--','--host','127.0.0.1','--port',$FrontendPort -WorkingDirectory $frontend -WindowStyle Hidden -PassThru
$api.Id | Set-Content (Join-Path $run 'backend.pid')
$web.Id | Set-Content (Join-Path $run 'frontend.pid')
Write-Host "Development environment started: http://127.0.0.1:$FrontendPort"
