# 打包成兩個 exe（CLAUDE.md 階段 8a）：
#   dist\ClaudeUsageTracker.exe  主程式（--noconsole --onefile）
#   dist\diagnose.exe            診斷工具（有主控台，不含 Qt）
#   dist\THIRD_PARTY_LICENSES.txt  打包進 exe 的第三方元件授權（含 PySide6／Qt 的 LGPL）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\build.ps1 [-SkipCheck]
param([switch]$SkipCheck)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$venv = Join-Path $root '.venv\Scripts'
if (Test-Path $venv) { $env:PATH = "$venv;$env:PATH" }
$env:PYTHONUTF8 = '1'

function Invoke-Step([string]$name, [scriptblock]$cmd) {
    Write-Host "`n=== $name ===" -ForegroundColor Cyan
    & $cmd
    if ($LASTEXITCODE -ne 0) { throw "$name 失敗（結束代碼 $LASTEXITCODE）" }
}

if (-not $SkipCheck) {
    Invoke-Step 'check.ps1' { powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'check.ps1') }
}

$version = (python scripts\version_info.py --print-version).Trim()
Write-Host "版本 $version" -ForegroundColor Green

$build = Join-Path $root 'build'
$dist = Join-Path $root 'dist'
$icon = Join-Path $root 'assets\app.ico'
$src = Join-Path $root 'src'

Invoke-Step '版本資訊' {
    python scripts\version_info.py "$build\version_app.txt" ClaudeUsageTracker "Claude / Codex usage monitor" ClaudeUsageTracker.exe
    python scripts\version_info.py "$build\version_diagnose.txt" diagnose "Claude Usage Tracker diagnostics" diagnose.exe
}

# 用不到的 Qt 模組全部排除，exe 才不會塞進 WebEngine、QML 等大型元件
$qtExcludes = @(
    'QtNetwork', 'QtQml', 'QtQuick', 'QtQuickWidgets', 'QtQuickControls2', 'QtWebEngineCore',
    'QtWebEngineWidgets', 'QtWebEngineQuick', 'QtWebChannel', 'QtWebSockets', 'QtHttpServer',
    'Qt3DCore', 'Qt3DRender', 'Qt3DInput', 'Qt3DLogic', 'Qt3DAnimation', 'Qt3DExtras',
    'QtMultimedia', 'QtMultimediaWidgets', 'QtSpatialAudio', 'QtTextToSpeech', 'QtPdf',
    'QtPdfWidgets', 'QtSvg', 'QtSvgWidgets', 'QtSql', 'QtTest', 'QtXml', 'QtOpenGL',
    'QtOpenGLWidgets', 'QtCharts', 'QtDataVisualization', 'QtGraphs', 'QtBluetooth', 'QtNfc',
    'QtPositioning', 'QtLocation', 'QtSensors', 'QtSerialPort', 'QtSerialBus', 'QtDesigner',
    'QtHelp', 'QtPrintSupport', 'QtUiTools', 'QtConcurrent', 'QtDBus', 'QtRemoteObjects',
    'QtScxml', 'QtStateMachine', 'QtVirtualKeyboard'
) | ForEach-Object { '--exclude-module'; "PySide6.$_" }
$devExcludes = @('tkinter', 'pytest', 'pytestqt', '_pytest', 'pyright', 'importlinter', 'IPython') |
    ForEach-Object { '--exclude-module'; $_ }

$common = @('--noconfirm', '--clean', '--onefile', '--paths', $src,
            '--specpath', $build, '--workpath', "$build\work", '--distpath', $dist)

# --icon：exe 在檔案總管的圖示；--add-data：執行時 QApplication.setWindowIcon() 讀的 assets\app.ico
Invoke-Step 'PyInstaller：ClaudeUsageTracker.exe' {
    pyinstaller @common --noconsole --name ClaudeUsageTracker --icon $icon `
        --add-data "$icon;assets" `
        --version-file "$build\version_app.txt" @qtExcludes @devExcludes `
        "$src\usage_monitor\__main__.py"
}

Invoke-Step 'PyInstaller：diagnose.exe' {
    pyinstaller @common --console --name diagnose --icon $icon `
        --version-file "$build\version_diagnose.txt" `
        --exclude-module PySide6 --exclude-module shiboken6 @devExcludes `
        "$src\usage_monitor\diagnose.py"
}

Invoke-Step '第三方授權' {
    python scripts\third_party_licenses.py "$dist\THIRD_PARTY_LICENSES.txt"
}

Write-Host "`n=== 完成 ===" -ForegroundColor Green
Get-ChildItem $dist -File | ForEach-Object {
    '{0,-28} {1,8:N1} MB' -f $_.Name, ($_.Length / 1MB)
}
