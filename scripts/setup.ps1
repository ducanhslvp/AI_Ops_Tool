param([switch]$NoStart)

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'setup_windows.ps1') -NoStart
& (Join-Path $PSScriptRoot 'test_all.ps1')

if (-not $NoStart) {
    & (Join-Path $PSScriptRoot 'run_all.ps1')
}
