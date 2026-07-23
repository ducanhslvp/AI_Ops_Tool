$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Backend virtual environment is missing. Run scripts\setup_windows.ps1 first.'
}
& $python (Join-Path $PSScriptRoot 'init_sqlite.py')
