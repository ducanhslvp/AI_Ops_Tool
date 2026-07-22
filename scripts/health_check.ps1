$ErrorActionPreference = "Stop"
$baseUrl = if ($env:AIOPS_API_URL) { $env:AIOPS_API_URL } else { "http://localhost:8000/api/v1" }
if (-not $env:AIOPS_TOKEN) { throw "Set AIOPS_TOKEN to an access token" }
$headers = @{ Authorization = "Bearer $env:AIOPS_TOKEN" }
Invoke-RestMethod -Uri "$baseUrl/ai/providers/health" -Headers $headers | ConvertTo-Json -Depth 8
