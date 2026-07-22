param([Parameter(Mandatory = $true)][string]$Provider)
$ErrorActionPreference = "Stop"
$baseUrl = if ($env:AIOPS_API_URL) { $env:AIOPS_API_URL } else { "http://localhost:8000/api/v1" }
if (-not $env:AIOPS_TOKEN) { throw "Set AIOPS_TOKEN to an administrator access token" }
$headers = @{ Authorization = "Bearer $env:AIOPS_TOKEN" }
$body = @{ provider = $Provider } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$baseUrl/ai/providers/switch" -Headers $headers \
  -ContentType "application/json" -Body $body | ConvertTo-Json
