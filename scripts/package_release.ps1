param(
  [string]$Version = "1.2.0",
  [switch]$SkipBuild,
  [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path "$PSScriptRoot\.."
Push-Location $root
try {
  if (-not $SkipBuild) {
    & "$root\build_portable.ps1"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }

  if (-not $SkipSmokeTest) {
    & "$root\scripts\smoke_test.ps1" -ExePath "$root\dist\KoreanVietnameseTranslator.exe"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }

  $releaseRoot = Join-Path $root "release"
  $packageName = "KoreanVietnameseTranslator-$Version-portable"
  $packageDir = Join-Path $releaseRoot $packageName
  $zipPath = Join-Path $releaseRoot "$packageName.zip"

  Remove-Item -LiteralPath $packageDir, $zipPath -Recurse -Force -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Path $packageDir -Force | Out-Null

  Copy-Item -LiteralPath "$root\dist\KoreanVietnameseTranslator.exe" -Destination "$packageDir\KoreanVietnameseTranslator.exe" -Force
  Copy-Item -LiteralPath "$root\docs\local_first_deployment.md" -Destination "$packageDir\README_RUN.md" -Force

  $checklist = @"
Korean-Vietnamese Live Translator $Version

Quick run:
1. Double-click KoreanVietnameseTranslator.exe.
2. Host PC opens http://127.0.0.1:8000 automatically.
3. Choose Host, enter Groq API key if needed, then copy/scan the guest URL.
4. Guest phone must be on the same Wi-Fi and open the LAN URL shown in the app.

Field checklist:
- Windows Firewall allows this exe on Private networks.
- Host PC and guest phone use the same Wi-Fi.
- Guest phone does not open 127.0.0.1.
- If port 8000 is busy, the app automatically uses the next free port.
- Always share the guest URL shown inside the app because the port may change.
- Keep the host PC awake during the session.
"@
  Set-Content -Path "$packageDir\CHECKLIST.txt" -Value $checklist -Encoding UTF8

  Compress-Archive -Path "$packageDir\*" -DestinationPath $zipPath -Force
  Get-FileHash $zipPath -Algorithm SHA256 | Format-List
  Write-Host "Release package created: $zipPath" -ForegroundColor Green
} finally {
  Pop-Location
}
