param(
  [string]$ExePath = ".\dist\KoreanVietnameseTranslator.exe",
  [Parameter(Mandatory = $true)]
  [string]$CertificateThumbprint,
  [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ExePath)) {
  Write-Error "Executable not found: $ExePath"
}

$signtool = Get-Command signtool.exe -ErrorAction SilentlyContinue
if (-not $signtool) {
  Write-Error "signtool.exe not found. Install Windows SDK and ensure signtool is on PATH."
}

& $signtool.Source sign `
  /fd SHA256 `
  /tr $TimestampUrl `
  /td SHA256 `
  /sha1 $CertificateThumbprint `
  $ExePath

& $signtool.Source verify /pa /v $ExePath
