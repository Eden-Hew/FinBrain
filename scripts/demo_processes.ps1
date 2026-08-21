function Get-DemoPythonRuntime {
  param([Parameter(Mandatory)][string]$RepoRoot)

  $configuredPython = [Environment]::GetEnvironmentVariable("FINBRAIN_PYTHON")
  if (-not [string]::IsNullOrWhiteSpace($configuredPython)) {
    $candidate = if ([System.IO.Path]::IsPathRooted($configuredPython)) {
      $configuredPython
    } else {
      Join-Path $RepoRoot $configuredPython
    }
    $candidate = [System.IO.Path]::GetFullPath($candidate)
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
      throw "FINBRAIN_PYTHON does not point to an existing Python executable."
    }
    return [pscustomobject]@{
      executable = $candidate
      arguments = @()
      devArguments = @()
      description = "FINBRAIN_PYTHON (direct; dependency sync disabled)"
    }
  }

  $rootPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
  if (Test-Path -LiteralPath $rootPython -PathType Leaf) {
    return [pscustomobject]@{
      executable = $rootPython
      arguments = @()
      devArguments = @()
      description = "root .venv (direct; dependency sync disabled)"
    }
  }

  $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
  if (-not $uvCommand) {
    throw "Python is unavailable: create the root .venv, set FINBRAIN_PYTHON, or install uv on PATH."
  }
  return [pscustomobject]@{
    executable = $uvCommand.Source
    arguments = @("run", "python")
    devArguments = @("run", "--extra", "dev", "python")
    description = "uv-managed backend environment (automatic dependency sync enabled)"
  }
}

function Get-DemoValidatedProcess {
  param([Parameter(Mandatory)]$Entry)
  $process = Get-Process -Id ([int]$Entry.pid) -ErrorAction SilentlyContinue
  if (-not $process) { return $null }
  $expectedStart = if ($Entry.started -is [datetime]) {
    [datetime]$Entry.started
  } else {
    [datetime]::Parse(
      [string]$Entry.started,
      [System.Globalization.CultureInfo]::InvariantCulture,
      [System.Globalization.DateTimeStyles]::RoundtripKind
    )
  }
  if ([math]::Abs(($process.StartTime - $expectedStart).TotalSeconds) -gt 2) {
    Write-Warning "Skipped PID $($Entry.pid): its start time no longer matches."
    return $null
  }
  if ($Entry.executable) {
    try { $actualPath = [System.IO.Path]::GetFullPath($process.Path) } catch { return $null }
    $expectedPath = [System.IO.Path]::GetFullPath([string]$Entry.executable)
    if (-not $actualPath.Equals($expectedPath, [System.StringComparison]::OrdinalIgnoreCase)) {
      Write-Warning "Skipped PID $($Entry.pid): its executable no longer matches."
      return $null
    }
  }
  return $process
}

function Get-DemoDescendants {
  param([Parameter(Mandatory)][int]$RootPid)
  try {
    $all = @(Get-CimInstance Win32_Process -ErrorAction Stop)
  } catch {
    Write-Warning "Process ancestry is unavailable; stopping only the validated tracked process."
    return @()
  }
  $rootItem = $all | Where-Object { [int]$_.ProcessId -eq $RootPid } | Select-Object -First 1
  if (-not $rootItem) { return @() }
  $children = @{}
  foreach ($item in $all) {
    $parent = [int]$item.ParentProcessId
    if (-not $children.ContainsKey($parent)) { $children[$parent] = @() }
    $children[$parent] += $item
  }
  $result = @()
  $queue = @(@{
      pid = $RootPid
      depth = 0
      created = [datetime]$rootItem.CreationDate
    })
  $visited = @{}
  while ($queue.Count -gt 0) {
    $current = $queue[0]
    $queue = @($queue | Select-Object -Skip 1)
    $currentPid = [int]$current.pid
    if ($visited.ContainsKey($currentPid)) { continue }
    $visited[$currentPid] = $true
    if (-not $children.ContainsKey($currentPid)) { continue }
    foreach ($child in @($children[$currentPid])) {
      $childPid = [int]$child.ProcessId
      $childCreated = [datetime]$child.CreationDate
      # Windows keeps only a numeric parent PID. If that PID is later reused,
      # an older unrelated process can appear beneath a newly started demo
      # launcher. Only follow children created at or after their current parent.
      if ($childPid -eq $currentPid -or $childCreated -lt [datetime]$current.created) {
        continue
      }
      $entry = [pscustomobject]@{
        pid = $childPid
        depth = [int]$current.depth + 1
        created = $childCreated
      }
      $result += $entry
      $queue += @{ pid = $entry.pid; depth = $entry.depth; created = $entry.created }
    }
  }
  return @($result | Sort-Object depth -Descending)
}

function Stop-DemoEntry {
  param([Parameter(Mandatory)]$Entry)
  $root = Get-DemoValidatedProcess -Entry $Entry
  if (-not $root) { return }
  foreach ($child in @(Get-DemoDescendants -RootPid $root.Id)) {
    $process = Get-Process -Id $child.pid -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    try {
      Stop-Process -Id $process.Id -ErrorAction Stop
    } catch {
      if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) { throw }
      continue
    }
    $process.WaitForExit(5000) | Out-Null
    if (-not $process.HasExited) { throw "Child PID $($process.Id) did not stop." }
  }
  $root.Refresh()
  if (-not $root.HasExited) {
    Stop-Process -Id $root.Id -ErrorAction Stop
    $root.WaitForExit(5000) | Out-Null
    if (-not $root.HasExited) { throw "PID $($root.Id) did not stop." }
  }
}

function Test-DemoEnvFlag {
  param(
    [Parameter(Mandatory)][string]$EnvFile,
    [Parameter(Mandatory)][string]$Name
  )
  return [bool](Select-String -LiteralPath $EnvFile `
    -Pattern "^$([regex]::Escape($Name))\s*=\s*true\s*$" `
    -CaseSensitive:$false -Quiet)
}

function Test-DemoEnvValue {
  param(
    [Parameter(Mandatory)][string]$EnvFile,
    [Parameter(Mandatory)][string]$Name
  )
  return [bool](Select-String -LiteralPath $EnvFile `
    -Pattern "^$([regex]::Escape($Name))\s*=\s*\S+\s*$" -Quiet)
}
