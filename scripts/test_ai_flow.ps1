param([ValidateSet('disk_full','cpu_high','memory_leak','redis_down','oracle_slow','kafka_lag','network_timeout','nginx_down')][string]$Profile = 'disk_full', [string]$BaseUrl = 'http://127.0.0.1:8000/api/v1')
$root = Split-Path -Parent $PSScriptRoot
& (Join-Path $root 'backend\.venv\Scripts\python.exe') (Join-Path $root 'scripts\test_ai_flow.py') $Profile --base-url $BaseUrl
