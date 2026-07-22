$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$run = Join-Path $root '.run'
foreach ($name in @('backend', 'frontend')) {
    $file = Join-Path $run "$name.pid"
    if (Test-Path $file) {
        $processId = [int](Get-Content $file)
        Stop-Process -Id $processId -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $file -Force
        Write-Host "Stopped $name process $processId"
    }
}
