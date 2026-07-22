$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
& (Join-Path $root 'backend\.venv\Scripts\python.exe') (Join-Path $root 'scripts\run_discovery_schedules.py')
