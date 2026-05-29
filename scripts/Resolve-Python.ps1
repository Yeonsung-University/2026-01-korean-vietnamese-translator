function Resolve-KvtPython {
  param(
    [string]$RequestedPython = $env:PYTHON
  )

  if ($RequestedPython) {
    return [pscustomobject]@{
      Exe = $RequestedPython
      Args = @()
    }
  }

  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    return [pscustomobject]@{
      Exe = $python.Source
      Args = @()
    }
  }

  $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
  if ($pyLauncher) {
    return [pscustomobject]@{
      Exe = $pyLauncher.Source
      Args = @("-3")
    }
  }

  throw "Python was not found. Install Python 3.10+ or set `$env:PYTHON to the full python.exe path."
}
