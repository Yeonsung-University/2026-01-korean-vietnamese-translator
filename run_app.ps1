$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
. "$PSScriptRoot\scripts\Resolve-Python.ps1"
$PythonInfo = Resolve-KvtPython

Write-Host "Starting local app: http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "Close this window or press Ctrl+C to stop." -ForegroundColor Yellow

& $PythonInfo.Exe @($PythonInfo.Args) -X utf8 app_launcher.py
