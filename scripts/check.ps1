# 一次跑完所有檢查（CLAUDE.md §5.4）。完成任何工作前都必須全過。
# 用法：powershell -ExecutionPolicy Bypass -File scripts\check.ps1
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

$venv = Join-Path (Get-Location) '.venv\Scripts'
if (Test-Path $venv) { $env:PATH = "$venv;$env:PATH" }
$env:PYTHONUTF8 = '1'

$steps = @(
    @{ Name = 'ruff format'; Cmd = { ruff format --check . } },
    @{ Name = 'ruff check';  Cmd = { ruff check . } },
    @{ Name = 'pyright';     Cmd = { pyright } },
    @{ Name = 'lint-imports'; Cmd = { lint-imports } },
    @{ Name = 'pytest';      Cmd = { pytest --cov=usage_monitor --cov-fail-under=90 } }
)

$failed = @()
foreach ($step in $steps) {
    Write-Host "`n=== $($step.Name) ===" -ForegroundColor Cyan
    & $step.Cmd
    if ($LASTEXITCODE -ne 0) {
        $failed += $step.Name
        Write-Host "✗ $($step.Name) 失敗" -ForegroundColor Red
    } else {
        Write-Host "✓ $($step.Name)" -ForegroundColor Green
    }
}

Write-Host ''
if ($failed.Count -gt 0) {
    Write-Host "檢查失敗：$($failed -join '、')" -ForegroundColor Red
    exit 1
}
Write-Host '全部檢查通過' -ForegroundColor Green
