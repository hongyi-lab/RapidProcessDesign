[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeRoot = Join-Path $ProjectRoot ".rapid-local"
$StatePath = Join-Path $RuntimeRoot "processes.json"

function Stop-RecordedProcess {
    param(
        [string]$Label,
        [object]$Record
    )

    if ($null -eq $Record -or $null -eq $Record.pid) {
        return
    }

    $process = Get-Process -Id ([int]$Record.pid) -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return
    }

    if ($Record.PSObject.Properties.Name -contains "startedAtUtcTicks") {
        $recordedTicks = [long]::Parse(
            [string]$Record.startedAtUtcTicks,
            [Globalization.CultureInfo]::InvariantCulture
        )
    }
    elseif ($Record.startedAtUtc -is [DateTime]) {
        $recordedTicks = $Record.startedAtUtc.ToUniversalTime().Ticks
    }
    else {
        $parsed = [DateTimeOffset]::Parse(
            [string]$Record.startedAtUtc,
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::RoundtripKind
        )
        $recordedTicks = $parsed.UtcDateTime.Ticks
    }
    $actualTicks = $process.StartTime.ToUniversalTime().Ticks
    if ([Math]::Abs([double]($actualTicks - $recordedTicks)) -gt (2 * [TimeSpan]::TicksPerSecond)) {
        Write-Warning "$Label PID was reused by another process, so it was not stopped."
        return
    }

    Stop-Process -Id $process.Id -Force
    Write-Host "Stopped $Label."
}

if (-not (Test-Path -LiteralPath $StatePath)) {
    Write-Host "No Rapid Design processes created by the launcher were found."
    exit 0
}

$state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
Stop-RecordedProcess -Label "web service" -Record $state.web
Stop-RecordedProcess -Label "analysis service" -Record $state.api
Remove-Item -LiteralPath $StatePath -Force
Write-Host "Rapid Design local services are stopped." -ForegroundColor Green
