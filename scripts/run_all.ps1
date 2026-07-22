$ErrorActionPreference = 'Stop'
$powershell = (Get-Command powershell.exe).Source
Start-Process -FilePath $powershell -ArgumentList @(
    '-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
    (Join-Path $PSScriptRoot 'run_backend.ps1')
)
Start-Process -FilePath $powershell -ArgumentList @(
    '-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
    (Join-Path $PSScriptRoot 'run_frontend.ps1')
)
Start-Sleep -Seconds 3
Start-Process 'http://127.0.0.1:5173'
Write-Host 'AIOps Platform is starting. API: http://127.0.0.1:8000  UI: http://127.0.0.1:5173'
