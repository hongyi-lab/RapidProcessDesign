$ErrorActionPreference = 'Stop'
$demoRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$recordPath = Join-Path $demoRoot '.run\processes.json'
if (-not (Test-Path -LiteralPath $recordPath)) { Write-Output 'No recorded demo processes.'; exit 0 }
$records = @(Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json)
function Stop-DemoTree([int]$processId) {
    $process=Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction Stop
    if (-not $process) { return }
    # Reject reused/stale PIDs: only stop commands explicitly in this directory.
    if ($process.CommandLine -notlike ('*'+$demoRoot+'*')) { Write-Warning ('Skipped unrelated PID '+$processId); return }
    $children=@(Get-CimInstance Win32_Process -Filter "ParentProcessId=$processId" -ErrorAction Stop)
    foreach ($child in $children) { Stop-DemoTree ([int]$child.ProcessId) }
    $outcome=Invoke-CimMethod -InputObject $process -MethodName Terminate -Arguments @{Reason=[uint32]0} -ErrorAction Stop
    if ($outcome.ReturnValue -ne 0) { throw ('Could not stop demo PID '+$processId+', code '+$outcome.ReturnValue) }
}
foreach ($record in $records) { Stop-DemoTree ([int]$record.id) }
Write-Output 'Stopped recorded BWB demo processes.'
