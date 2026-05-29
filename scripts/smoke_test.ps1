param(
  [string]$ExePath = "$PSScriptRoot\..\dist\KoreanVietnameseTranslator.exe",
  [int]$Port = 8017,
  [int]$StartupTimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"

$resolvedExe = Resolve-Path $ExePath
$resolvedExePath = [System.IO.Path]::GetFullPath($resolvedExe.Path)
$workDir = Split-Path -Parent $resolvedExe
$stdout = Join-Path $env:TEMP "kvt-smoke-$Port.out"
$stderr = Join-Path $env:TEMP "kvt-smoke-$Port.err"
Remove-Item -LiteralPath $stdout, $stderr -ErrorAction SilentlyContinue

$oldPort = $env:KVT_PORT
$oldNoBrowser = $env:KVT_NO_BROWSER
$env:KVT_PORT = [string]$Port
$env:KVT_NO_BROWSER = "1"

$process = $null
$existingPids = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
  $_.Path -and ([System.IO.Path]::GetFullPath($_.Path) -ieq $resolvedExePath)
} | Select-Object -ExpandProperty Id)
try {
  Write-Host "Starting exe smoke test on port $Port..." -ForegroundColor Cyan
  $process = Start-Process `
    -FilePath $resolvedExe `
    -WorkingDirectory $workDir `
    -PassThru `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr

  $health = $null
  $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if ($process.HasExited) {
      throw "App exited before health endpoint was ready. ExitCode=$($process.ExitCode)"
    }
    try {
      $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
      break
    } catch {
      Start-Sleep -Milliseconds 750
    }
  }
  if (-not $health) {
    throw "Health endpoint did not become ready within $StartupTimeoutSeconds seconds."
  }

  $page = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -TimeoutSec 10
  $network = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/network" -TimeoutSec 10
  $diagnostics = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/diagnostics" -TimeoutSec 10
  $qr = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/qr" -TimeoutSec 10

  . "$PSScriptRoot\Resolve-Python.ps1"
  $PythonInfo = Resolve-KvtPython
  $wsScript = @"
import asyncio, json, urllib.request
import websockets

async def main():
    async with websockets.connect("ws://127.0.0.1:$Port/ws/guest"):
        await asyncio.sleep(0.5)
        with urllib.request.urlopen("http://127.0.0.1:$Port/api/diagnostics", timeout=5) as response:
            diag = json.loads(response.read().decode("utf-8"))
        if diag["websocket"]["guest_count"] < 1:
            raise SystemExit("guest websocket did not register")
        print(json.dumps({"guest_count": diag["websocket"]["guest_count"]}))

asyncio.run(main())
"@
  $wsResult = $wsScript | & $PythonInfo.Exe @($PythonInfo.Args) -
  if ($LASTEXITCODE -ne 0) {
    throw "Guest WebSocket verification failed with exit code $LASTEXITCODE."
  }
  $wsJson = $wsResult | ConvertFrom-Json
  if ($wsJson.guest_count -lt 1) {
    throw "Guest WebSocket verification did not report an active guest."
  }

  $summary = [pscustomobject]@{
    ok = $true
    app = $health.app
    version = $health.version
    local_url = $network.local_url
    guest_url = $network.guest_url
    html_bytes = $page.RawContentLength
    qr_bytes = $qr.RawContentLength
    microphone = $diagnostics.audio.state.current_input_device_name
    websocket_guest_count = $wsJson.guest_count
  }
  $summary | ConvertTo-Json -Depth 6
  Write-Host "Smoke test passed." -ForegroundColor Green
} catch {
  Write-Host "Smoke test failed: $($_.Exception.Message)" -ForegroundColor Red
  if (Test-Path $stdout) {
    Write-Host "--- stdout ---" -ForegroundColor Yellow
    Get-Content $stdout -Raw -ErrorAction SilentlyContinue
  }
  if (Test-Path $stderr) {
    Write-Host "--- stderr ---" -ForegroundColor Yellow
    Get-Content $stderr -Raw -ErrorAction SilentlyContinue
  }
  exit 1
} finally {
  if ($process -and -not $process.HasExited) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
  }
  Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -and
    ([System.IO.Path]::GetFullPath($_.Path) -ieq $resolvedExePath) -and
    ($existingPids -notcontains $_.Id)
  } | Stop-Process -Force -ErrorAction SilentlyContinue
  if ($null -eq $oldPort) { Remove-Item Env:KVT_PORT -ErrorAction SilentlyContinue } else { $env:KVT_PORT = $oldPort }
  if ($null -eq $oldNoBrowser) { Remove-Item Env:KVT_NO_BROWSER -ErrorAction SilentlyContinue } else { $env:KVT_NO_BROWSER = $oldNoBrowser }
  Remove-Item -LiteralPath $stdout, $stderr -ErrorAction SilentlyContinue
}
