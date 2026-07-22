param([Parameter(Mandatory=$true)][string]$Profile, [string]$Hostname = 'erp-linux-01', [string]$BaseUrl = 'http://127.0.0.1:8000/api/v1')
$root = Split-Path -Parent $PSScriptRoot
& (Join-Path $root 'backend\.venv\Scripts\python.exe') (Join-Path $root 'scripts\local_test_client.py') $Profile --hostname $Hostname --base-url $BaseUrl
