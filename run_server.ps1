$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
. "$PSScriptRoot\scripts\Resolve-Python.ps1"
$PythonInfo = Resolve-KvtPython

Write-Host "Starting FastAPI server: http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "Open the URL in a browser. Press Ctrl+C to stop." -ForegroundColor Yellow

& $PythonInfo.Exe @($PythonInfo.Args) -X utf8 server.py
