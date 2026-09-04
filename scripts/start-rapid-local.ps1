[CmdletBinding()]
param(
    [switch]$NoOpen,
    [switch]$ForceRebuild
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$WebRoot = Join-Path $ProjectRoot "apps\web"
$RuntimeRoot = Join-Path $ProjectRoot ".rapid-local"
$StatePath = Join-Path $RuntimeRoot "processes.json"
$BuildStampPath = Join-Path $RuntimeRoot "web-build.json"
$ApiUrl = "http://127.0.0.1:8900"
$WebUrl = "http://localhost:3900/rapid-design"

function Test-RapidApi {
    try {
        $openApi = Invoke-RestMethod -Uri "$ApiUrl/openapi.json" -TimeoutSec 2
        return $null -ne $openApi.paths.'/api/rapid-design/analyze'
    }
    catch {
        return $false
    }
}

function Test-RapidWeb {
    try {
        $response = Invoke-WebRequest -Uri $WebUrl -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

function Get-ProcessRecord {
    param([System.Diagnostics.Process]$Process)

    if ($null -eq $Process) {
        return $null
    }
    $startedAtUtc = $Process.StartTime.ToUniversalTime()
    return [ordered]@{
        pid = $Process.Id
        startedAtUtc = $startedAtUtc.ToString("o")
        startedAtUtcTicks = $startedAtUtc.Ticks.ToString([Globalization.CultureInfo]::InvariantCulture)
    }
}

function Get-ListenerProcessRecord {
    param([int]$Port)

    $pattern = "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$"
    foreach ($line in (& "$env:SystemRoot\System32\netstat.exe" -ano -p TCP)) {
        if ($line -match $pattern) {
            $listener = Get-Process -Id ([int]$Matches[1]) -ErrorAction SilentlyContinue
            return Get-ProcessRecord -Process $listener
        }
    }
    return $null
}

function Get-RecordStartTicks {
    param([object]$Record)

    if ($null -eq $Record) {
        return $null
    }
    if ($Record.PSObject.Properties.Name -contains "startedAtUtcTicks") {
        return [long]::Parse(
            [string]$Record.startedAtUtcTicks,
            [Globalization.CultureInfo]::InvariantCulture
        )
    }
    if ($Record.startedAtUtc -is [DateTime]) {
        return $Record.startedAtUtc.ToUniversalTime().Ticks
    }
    $parsed = [DateTimeOffset]::Parse(
        [string]$Record.startedAtUtc,
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::RoundtripKind
    )
    return $parsed.UtcDateTime.Ticks
}

function Test-RecordedProcess {
    param([object]$Record)

    if ($null -eq $Record -or $null -eq $Record.pid) {
        return $false
    }
    $process = Get-Process -Id ([int]$Record.pid) -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return $false
    }
    try {
        $recordedTicks = Get-RecordStartTicks -Record $Record
        $actualTicks = $process.StartTime.ToUniversalTime().Ticks
        return [Math]::Abs([double]($actualTicks - $recordedTicks)) -le (2 * [TimeSpan]::TicksPerSecond)
    }
    catch {
        return $false
    }
}

function Get-ManagedListenerRecord {
    param(
        [object]$Record,
        [int]$Port
    )

    if (-not (Test-RecordedProcess -Record $Record)) {
        return $null
    }
    $listener = Get-ListenerProcessRecord -Port $Port
    if ($null -eq $listener -or [int]$listener.pid -ne [int]$Record.pid) {
        return $null
    }
    return $listener
}

function Stop-ManagedProcess {
    param(
        [string]$Label,
        [object]$Record
    )

    if (-not (Test-RecordedProcess -Record $Record)) {
        return
    }
    $pidToStop = [int]$Record.pid
    Stop-Process -Id $pidToStop -Force
    Wait-Process -Id $pidToStop -Timeout 5 -ErrorAction SilentlyContinue
    Write-Host "Stopped stale $Label."
}

function Read-JsonFile {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    }
    catch {
        Write-Warning "Ignoring unreadable launcher state: $Path"
        return $null
    }
}

function Get-FileSetFingerprint {
    param(
        [System.IO.FileInfo[]]$Files,
        [string]$Salt
    )

    $builder = New-Object System.Text.StringBuilder
    [void]$builder.AppendLine($Salt)
    foreach ($file in @($Files) | Sort-Object FullName) {
        $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
        [void]$builder.AppendLine("$($file.FullName)|$hash")
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($builder.ToString())
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "")
    }
    finally {
        $sha.Dispose()
    }
}

function Write-LauncherState {
    param(
        [object]$ApiRecord,
        [object]$WebRecord,
        [string]$ApiFingerprint
    )

    $state = [ordered]@{
        projectRoot = $ProjectRoot
        apiFingerprint = $ApiFingerprint
        api = $ApiRecord
        web = $WebRecord
    }
    $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $StatePath -Encoding UTF8
}

function Show-LogTail {
    param([string]$Path)

    if (Test-Path -LiteralPath $Path) {
        Get-Content -LiteralPath $Path -Tail 20
    }
}

New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$NextCli = Join-Path $WebRoot "node_modules\next\dist\bin\next"
$BuildId = Join-Path $WebRoot ".next\BUILD_ID"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment is missing: $Python. Complete the README setup once first."
}
if (-not (Test-Path -LiteralPath $NextCli)) {
    throw "Frontend dependencies are missing. Run npm install in apps/web first."
}

$Node = (Get-Command node.exe -ErrorAction Stop).Source
$Npm = (Get-Command npm.cmd -ErrorAction Stop).Source
$NodeVersion = [string](& $Node --version)

$webInputFiles = @(Get-ChildItem -Path (Join-Path $WebRoot "src") -File -Recurse)
$publicRoot = Join-Path $WebRoot "public"
if (Test-Path -LiteralPath $publicRoot) {
    $webInputFiles += @(Get-ChildItem -Path $publicRoot -File -Recurse)
}
foreach ($name in @("package.json", "package-lock.json", "next.config.mjs", "next.config.js", "tsconfig.json", "next-env.d.ts")) {
    $path = Join-Path $WebRoot $name
    if (Test-Path -LiteralPath $path) {
        $webInputFiles += Get-Item -LiteralPath $path
    }
}
$webFingerprint = Get-FileSetFingerprint `
    -Files $webInputFiles `
    -Salt "NEXT_PUBLIC_API_BASE_URL=$ApiUrl|node=$NodeVersion"

$apiInputFiles = @(
    Get-ChildItem -Path (Join-Path $ProjectRoot "services"), (Join-Path $ProjectRoot "packages"), (Join-Path $ProjectRoot "configs") -File -Recurse |
        Where-Object { $_.Extension -in @(".py", ".json", ".toml", ".yaml", ".yml") }
)
foreach ($name in @("pyproject.toml", ".env")) {
    $path = Join-Path $ProjectRoot $name
    if (Test-Path -LiteralPath $path) {
        $apiInputFiles += Get-Item -LiteralPath $path
    }
}
$apiFingerprint = Get-FileSetFingerprint `
    -Files $apiInputFiles `
    -Salt "CAD_BACKEND=fake|python=$Python"

$buildStamp = Read-JsonFile -Path $BuildStampPath
$NeedsBuild = $ForceRebuild -or -not (Test-Path -LiteralPath $BuildId)
if (-not $NeedsBuild) {
    $NeedsBuild = $null -eq $buildStamp -or [string]$buildStamp.fingerprint -ne $webFingerprint
}

$previousState = Read-JsonFile -Path $StatePath
$managedApi = if ($null -ne $previousState) {
    Get-ManagedListenerRecord -Record $previousState.api -Port 8900
} else { $null }
$managedWeb = if ($null -ne $previousState) {
    Get-ManagedListenerRecord -Record $previousState.web -Port 3900
} else { $null }

$apiHealthy = Test-RapidApi
$webHealthy = Test-RapidWeb
$apiListener = Get-ListenerProcessRecord -Port 8900
$webListener = Get-ListenerProcessRecord -Port 3900

if (-not $apiHealthy -and $null -ne $apiListener) {
    if ($null -ne $managedApi) {
        Stop-ManagedProcess -Label "analysis service" -Record $managedApi
        $managedApi = $null
        $apiListener = $null
    }
    else {
        throw "Port 8900 is occupied by another process. Close that process, then run Start-RapidDesign.cmd again."
    }
}
if (-not $webHealthy -and $null -ne $webListener) {
    if ($null -ne $managedWeb) {
        Stop-ManagedProcess -Label "web service" -Record $managedWeb
        $managedWeb = $null
        $webListener = $null
    }
    else {
        throw "Port 3900 is occupied by another process. Close that process, then run Start-RapidDesign.cmd again."
    }
}

if ($NeedsBuild -and $webHealthy) {
    if ($null -eq $managedWeb) {
        throw "The UI on port 3900 was not started by this launcher, so it cannot be updated safely. Close it, then run Start-RapidDesign.cmd again."
    }
    Stop-ManagedProcess -Label "web service" -Record $managedWeb
    $managedWeb = $null
    $webHealthy = $false
}

$apiOutdated = $apiHealthy -and $null -ne $managedApi -and (
    $null -eq $previousState -or
    -not ($previousState.PSObject.Properties.Name -contains "apiFingerprint") -or
    [string]$previousState.apiFingerprint -ne $apiFingerprint
)

$apiProcess = $null
$webProcess = $null
$startedApi = $null
$startedWeb = $null
$apiStdout = Join-Path $RuntimeRoot "api.out.log"
$apiStderr = Join-Path $RuntimeRoot "api.err.log"
$webStdout = Join-Path $RuntimeRoot "web.out.log"
$webStderr = Join-Path $RuntimeRoot "web.err.log"

try {
    Write-LauncherState -ApiRecord $managedApi -WebRecord $managedWeb -ApiFingerprint $apiFingerprint

    if ($NeedsBuild) {
        Write-Host "Preparing the local UI (unchanged builds are reused)..." -ForegroundColor Cyan
        Push-Location $WebRoot
        try {
            $env:NEXT_PUBLIC_API_BASE_URL = $ApiUrl
            & $Npm run build
            if ($LASTEXITCODE -ne 0) {
                throw "Frontend build failed."
            }
        }
        finally {
            Pop-Location
        }
        [ordered]@{
            fingerprint = $webFingerprint
            apiBaseUrl = $ApiUrl
            builtAtUtc = (Get-Date).ToUniversalTime().ToString("o")
        } | ConvertTo-Json | Set-Content -LiteralPath $BuildStampPath -Encoding UTF8
    }

    if ($apiOutdated) {
        Stop-ManagedProcess -Label "analysis service" -Record $managedApi
        $managedApi = $null
        $apiHealthy = $false
        Write-LauncherState -ApiRecord $managedApi -WebRecord $managedWeb -ApiFingerprint $apiFingerprint
    }

    $apiHealthy = Test-RapidApi
    $webHealthy = Test-RapidWeb

    if ($apiHealthy -and $webHealthy) {
        Write-LauncherState -ApiRecord $managedApi -WebRecord $managedWeb -ApiFingerprint $apiFingerprint
        Write-Host "Rapid Design is already running: $WebUrl" -ForegroundColor Green
        if (-not $NoOpen) {
            Start-Process $WebUrl
        }
        exit 0
    }

    if (-not $apiHealthy -and $null -ne (Get-ListenerProcessRecord -Port 8900)) {
        throw "Port 8900 became occupied before startup. Close that process and try again."
    }
    if (-not $webHealthy -and $null -ne (Get-ListenerProcessRecord -Port 3900)) {
        throw "Port 3900 became occupied before startup. Close that process and try again."
    }

    if (-not $apiHealthy) {
        Write-Host "Starting the analysis service..."
        $env:CAD_BACKEND = "fake"
        $env:WEB_PORT = "3900"
        $apiArguments = @(
            "-X", "utf8", "-m", "uvicorn", "services.api.app.main:app",
            "--host", "127.0.0.1", "--port", "8900"
        )
        $apiProcess = Start-Process `
            -FilePath $Python `
            -ArgumentList $apiArguments `
            -WorkingDirectory $ProjectRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $apiStdout `
            -RedirectStandardError $apiStderr `
            -PassThru
    }

    if (-not $webHealthy) {
        Write-Host "Starting the UI..."
        $webArguments = @($NextCli, "start", "-H", "127.0.0.1", "-p", "3900")
        $webProcess = Start-Process `
            -FilePath $Node `
            -ArgumentList $webArguments `
            -WorkingDirectory $WebRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $webStdout `
            -RedirectStandardError $webStderr `
            -PassThru
    }

    $deadline = (Get-Date).AddSeconds(45)
    do {
        if ($null -ne $apiProcess -and $null -eq $startedApi) {
            $startedApi = Get-ListenerProcessRecord -Port 8900
            if ($null -ne $startedApi) {
                Write-LauncherState -ApiRecord $startedApi -WebRecord $managedWeb -ApiFingerprint $apiFingerprint
            }
        }
        if ($null -ne $webProcess -and $null -eq $startedWeb) {
            $startedWeb = Get-ListenerProcessRecord -Port 3900
            if ($null -ne $startedWeb) {
                $apiRecord = if ($null -ne $startedApi) { $startedApi } else { $managedApi }
                Write-LauncherState -ApiRecord $apiRecord -WebRecord $startedWeb -ApiFingerprint $apiFingerprint
            }
        }

        if ((Test-RapidApi) -and (Test-RapidWeb)) {
            if ($null -ne $apiProcess -and $null -eq $startedApi) {
                $startedApi = Get-ListenerProcessRecord -Port 8900
            }
            if ($null -ne $webProcess -and $null -eq $startedWeb) {
                $startedWeb = Get-ListenerProcessRecord -Port 3900
            }
            $finalApi = if ($null -ne $startedApi) { $startedApi } else { $managedApi }
            $finalWeb = if ($null -ne $startedWeb) { $startedWeb } else { $managedWeb }
            Write-LauncherState -ApiRecord $finalApi -WebRecord $finalWeb -ApiFingerprint $apiFingerprint
            Write-Host "Rapid Design is ready: $WebUrl" -ForegroundColor Green
            if (-not $NoOpen) {
                Start-Process $WebUrl
            }
            exit 0
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)

    throw "Local services were not ready in 45 seconds."
}
catch {
    if ($null -eq $startedApi -and $null -ne $apiProcess) {
        $startedApi = Get-ListenerProcessRecord -Port 8900
    }
    if ($null -eq $startedWeb -and $null -ne $webProcess) {
        $startedWeb = Get-ListenerProcessRecord -Port 3900
    }
    if ($null -ne $startedWeb) {
        Stop-ManagedProcess -Label "new web service" -Record $startedWeb
    }
    elseif ($null -ne $webProcess -and -not $webProcess.HasExited) {
        Stop-Process -Id $webProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($null -ne $startedApi) {
        Stop-ManagedProcess -Label "new analysis service" -Record $startedApi
    }
    elseif ($null -ne $apiProcess -and -not $apiProcess.HasExited) {
        Stop-Process -Id $apiProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Write-LauncherState -ApiRecord $managedApi -WebRecord $managedWeb -ApiFingerprint $apiFingerprint
    Write-Host "API log:" -ForegroundColor Yellow
    Show-LogTail -Path $apiStderr
    Write-Host "Web log:" -ForegroundColor Yellow
    Show-LogTail -Path $webStderr
    throw
}
