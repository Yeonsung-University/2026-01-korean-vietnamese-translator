$ErrorActionPreference = "Stop"

& "$PSScriptRoot\build_portable.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$candidates = @(
  "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
  "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)

$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
  Write-Error "Inno Setup 6 was not found. Install it from https://jrsoftware.org/isinfo.php, then rerun this script."
}

Write-Host "Building installer with Inno Setup..." -ForegroundColor Cyan
& $iscc "$PSScriptRoot\installer\KoreanVietnameseTranslator.iss"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Installer build complete: installer-output" -ForegroundColor Green
