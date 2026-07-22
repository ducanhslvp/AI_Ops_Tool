$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "backend/.venv/Scripts/python.exe"
if (-not (Test-Path $python)) { $python = "python" }
Push-Location (Join-Path $root "backend")
try {
  & $python -m pytest -q -p no:cacheprovider tests/test_ai_adapter.py
  if ($LASTEXITCODE -ne 0) { throw "AI provider tests failed" }
} finally { Pop-Location }
