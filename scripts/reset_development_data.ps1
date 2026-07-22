$root = Split-Path -Parent $PSScriptRoot
$env:APP_ENV = 'development'; $env:TEST_MODE = 'true'; $env:SSH_TRANSPORT = 'local_simulation'
& (Join-Path $root 'backend\.venv\Scripts\python.exe') (Join-Path $root 'scripts\reset_development_data.py')
