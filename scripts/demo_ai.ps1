param([string]$Message = "Check disk health and explain the evidence")
$ErrorActionPreference = "Stop"
$baseUrl = if ($env:AIOPS_API_URL) { $env:AIOPS_API_URL } else { "http://localhost:8000/api/v1" }
if (-not $env:AIOPS_TOKEN) { throw "Set AIOPS_TOKEN to an access token" }
$headers = @{ Authorization = "Bearer $env:AIOPS_TOKEN"; Accept = "text/event-stream" }
$payload = @{ message = $Message }
if ($env:AIOPS_SERVER_ID) { $payload.server_id = $env:AIOPS_SERVER_ID }
$body = $payload | ConvertTo-Json
Invoke-WebRequest -Method Post -Uri "$baseUrl/ai/chat/stream" -Headers $headers \
  -ContentType "application/json" -Body $body | Select-Object -ExpandProperty Content
