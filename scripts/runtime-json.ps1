function Write-AtomicJson {
  param(
    [Parameter(Mandatory = $true)]
    [string]$LiteralPath,
    [Parameter(Mandatory = $true)]
    $Value,
    [int]$Depth = 16,
    [int]$MaxRetries = 5,
    [int]$RetryDelayMs = 120
  )

  $directory = Split-Path -Parent $LiteralPath
  if (-not [string]::IsNullOrWhiteSpace($directory)) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
  }

  $json = ($Value | ConvertTo-Json -Compress -Depth $Depth) + "`n"
  $tempPath = Join-Path $directory (".{0}.{1}.{2}.tmp" -f (Split-Path -Leaf $LiteralPath), $PID, [guid]::NewGuid().ToString("N"))
  $encoding = [System.Text.Encoding]::ASCII
  $bytes = $encoding.GetBytes($json)

  for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
    try {
      $stream = [System.IO.File]::Open($tempPath, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
      try {
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
      } finally {
        $stream.Dispose()
      }

      if (Test-Path -LiteralPath $LiteralPath) {
        $backupPath = "{0}.{1}.{2}.bak" -f $LiteralPath, $PID, [guid]::NewGuid().ToString("N")
        [System.IO.File]::Replace($tempPath, $LiteralPath, $backupPath, $true)
        Remove-Item -LiteralPath $backupPath -Force -ErrorAction SilentlyContinue
      } else {
        [System.IO.File]::Move($tempPath, $LiteralPath)
      }
      return
    } catch {
      if ($attempt -ge $MaxRetries) {
        throw
      }
      Start-Sleep -Milliseconds $RetryDelayMs
    } finally {
      if (Test-Path -LiteralPath $tempPath) {
        Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
      }
    }
  }
}
