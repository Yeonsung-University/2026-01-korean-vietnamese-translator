$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:KVT_BUILD_TYPE = "portable"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

. "$ProjectRoot\scripts\Resolve-Python.ps1"
$PythonInfo = Resolve-KvtPython
$PYTHON = $PythonInfo.Exe
$PythonArgs = @($PythonInfo.Args)

Write-Host "Installing/updating build dependencies..." -ForegroundColor Cyan
& $PYTHON @PythonArgs -m pip install -r requirements.txt
& $PYTHON @PythonArgs -m pip install pyinstaller

$AppEntry = Join-Path $ProjectRoot "app_launcher.py"
$IndexHtml = Join-Path $ProjectRoot "index.html"
$VersionFile = Join-Path $ProjectRoot "version_info.txt"
$iconArgs = @()
if (Test-Path (Join-Path $ProjectRoot "assets\app.ico")) {
  $iconArgs = @("--icon", (Join-Path $ProjectRoot "assets\app.ico"))
  Write-Host "Using icon: assets\app.ico" -ForegroundColor Cyan
} else {
  Write-Host "No assets\app.ico found. Building without a custom icon." -ForegroundColor Yellow
}

$BuildRoot = Join-Path $env:TEMP "KVT_PyInstaller_Build"
$TempDist = Join-Path $BuildRoot "dist"
$TempWork = Join-Path $BuildRoot "build"
$TempSpec = Join-Path $BuildRoot "spec"
$ResolvedBuildRoot = [System.IO.Path]::GetFullPath($BuildRoot)
$ResolvedTempRoot = [System.IO.Path]::GetFullPath($env:TEMP)
if (-not $ResolvedBuildRoot.StartsWith($ResolvedTempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
  Write-Error "Refusing to clean unexpected build path: $ResolvedBuildRoot"
}
Remove-Item -LiteralPath $BuildRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $TempDist, $TempWork, $TempSpec -Force | Out-Null

Write-Host "Using temporary build path: $BuildRoot" -ForegroundColor Cyan
Write-Host "Building portable Windows executable..." -ForegroundColor Cyan
& $PYTHON @PythonArgs -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --distpath "$TempDist" `
  --workpath "$TempWork" `
  --specpath "$TempSpec" `
  --name "KoreanVietnameseTranslator" `
  --version-file "$VersionFile" `
  --add-data "$IndexHtml;." `
  @iconArgs `
  "$AppEntry"

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$FinalDist = Join-Path $ProjectRoot "dist"
New-Item -ItemType Directory -Path $FinalDist -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $TempDist "KoreanVietnameseTranslator.exe") -Destination (Join-Path $FinalDist "KoreanVietnameseTranslator.exe") -Force
Write-Host "Build complete: dist\KoreanVietnameseTranslator.exe" -ForegroundColor Green
