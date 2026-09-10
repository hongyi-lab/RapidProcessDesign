param([switch]$NoBrowser, [string]$PythonExecutable)
$ErrorActionPreference = 'Stop'
$demoRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $demoRoot '..\..'))
$runDir = Join-Path $demoRoot '.run'
New-Item -ItemType Directory -Path $runDir -Force | Out-Null
$pythonOptions = if ($PythonExecutable) { @($PythonExecutable) } else { @(
    (Join-Path $repoRoot '.venv\Scripts\python.exe'),
    (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
) + @(Get-Command python.exe,python3.exe -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike '*\WindowsApps\*' } | ForEach-Object { $_.Source }) }
$pythonPath = $pythonOptions | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $pythonPath) { throw 'Python runtime not found. Install Python 3.11+ or pass -PythonExecutable with its full path.' }
$nodePath = (Get-Command node.exe -ErrorAction Stop).Source
$cliPath = Join-Path $demoRoot 'ui\node_modules\vinext\dist\cli.js'
if (-not (Test-Path -LiteralPath $cliPath)) { throw 'Run npm ci inside ui first.' }
$processes = @()
$apiReady = $false
$apiHealth = $null
try { $apiHealth=Invoke-RestMethod -Uri 'http://127.0.0.1:8842/health' -TimeoutSec 2 } catch {}
if ($null -ne $apiHealth) {
    if ($apiHealth.service -ne 'bwb-flow-demo' -or $apiHealth.version -ne 'review-v2') {
        throw 'Port 8842 is serving a different BWB version or another application. Close the old demo with its own Stop-Demo.cmd, then start this review-v2 copy. No existing process was stopped.'
    }
    $apiReady = $true
} else {
    $portListener = Get-NetTCPConnection -State Listen -LocalPort 8842 -ErrorAction SilentlyContinue
    if ($portListener) {
        throw 'Port 8842 is occupied but its review-v2 health check did not succeed. Close the old demo with its own Stop-Demo.cmd or inspect that service, then retry. No existing process was stopped.'
    }
}
if (-not $apiReady) {
    $api = Start-Process -FilePath $pythonPath -ArgumentList @('-X','utf8',('"'+(Join-Path $demoRoot 'server.py')+'"')) -WorkingDirectory $demoRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runDir 'api.out.log') -RedirectStandardError (Join-Path $runDir 'api.err.log')
    $processes += @{id=$api.Id;role='api'}
}
$uiReady = $false
try { $response=Invoke-WebRequest -Uri 'http://127.0.0.1:3981/' -UseBasicParsing -TimeoutSec 2; $uiReady=($response.StatusCode -eq 200 -and $response.Content -match 'BWB') } catch {}
if (-not $uiReady) {
    $ui = Start-Process -FilePath $nodePath -ArgumentList @(('"'+$cliPath+'"'),'dev','--hostname','127.0.0.1','--port','3981') -WorkingDirectory (Join-Path $demoRoot 'ui') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runDir 'ui.out.log') -RedirectStandardError (Join-Path $runDir 'ui.err.log')
    $processes += @{id=$ui.Id;role='ui'}
}
$recordPath = Join-Path $runDir 'processes.json'
if (Test-Path -LiteralPath $recordPath) { $previous=Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json; $processes=@($previous)+$processes }
ConvertTo-Json -InputObject @($processes) | Set-Content -LiteralPath $recordPath -Encoding UTF8
$ready=$false
for ($attempt=0; $attempt -lt 25; $attempt++) {
    try {
        $health=Invoke-RestMethod -Uri 'http://127.0.0.1:8842/health' -TimeoutSec 2
        $response=Invoke-WebRequest -Uri 'http://127.0.0.1:3981/' -UseBasicParsing -TimeoutSec 3
        if ($health.service -eq 'bwb-flow-demo' -and $health.version -eq 'review-v2' -and $response.StatusCode -eq 200 -and $response.Content -match 'BWB') { $ready=$true; break }
    } catch {}
    Start-Sleep -Seconds 1
}
if (-not $ready) { throw ('Inspect logs in '+$runDir) }
Write-Output 'BWB demo ready: http://127.0.0.1:3981/'
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:3981/' }
