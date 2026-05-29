$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
. "$PSScriptRoot\scripts\Resolve-Python.ps1"
$PythonInfo = Resolve-KvtPython

Write-Host "Starting microphone/VAD CLI demo..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop." -ForegroundColor Yellow

& $PythonInfo.Exe @($PythonInfo.Args) -X utf8 mic_vad.py
