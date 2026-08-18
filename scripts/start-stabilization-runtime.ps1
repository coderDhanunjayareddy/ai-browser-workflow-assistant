param(
    [string]$BackendUrl = "http://localhost:8000",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendRoot = Join-Path $repoRoot "backend"
$extensionRoot = Join-Path $repoRoot "extension"
$pythonPath = Join-Path $backendRoot ".venv-codex\Scripts\python.exe"
$runtimeDir = Join-Path $repoRoot "docs\production_validation\day1\runtime"
$runtimeUri = [Uri]$BackendUrl

function Get-CanonicalHealth {
    param([string]$Url)

    # Invoke-RestMethod can wait on Windows proxy/name-resolution state even after
    # Uvicorn is accepting loopback connections. curl gives us a hard per-attempt
    # deadline so runtime startup cannot become an unbounded launcher bottleneck.
    $body = & curl.exe --silent --show-error --max-time 3 "$($Url.TrimEnd('/'))/health" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $body) { return $null }
    try { return ($body | ConvertFrom-Json) }
    catch { return $null }
}

if ($runtimeUri.Scheme -ne "http" -or $runtimeUri.Host -notin @("localhost", "127.0.0.1") -or $runtimeUri.Port -ne $Port) {
    throw "The stabilization runtime must use one explicit local HTTP URL whose port matches -Port. Received $BackendUrl and $Port."
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Backend Python runtime not found: $pythonPath"
}

$alternatePorts = @(8000, 8001, 8002, 8003) | Where-Object { $_ -ne $Port }
$alternateListeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in $alternatePorts }
if ($alternateListeners) {
    $details = ($alternateListeners | Select-Object LocalAddress, LocalPort, OwningProcess | ConvertTo-Json -Compress)
    throw "Refusing to start with alternate validation backend listeners present: $details"
}

# A direct application handshake is authoritative when Windows restricts TCP
# owner enumeration. This prevents accidentally launching a second backend.
$existingHealth = Get-CanonicalHealth -Url $BackendUrl
if (
    $existingHealth -and
    $existingHealth.status -eq "ok" -and
    $existingHealth.runtime.canonical_backend_url.TrimEnd("/") -eq $BackendUrl.TrimEnd("/")
) {
    $serverPid = [int]$existingHealth.runtime.process_id
    $serverProcess = Get-Process -Id $serverPid -ErrorAction SilentlyContinue
    if (-not $serverProcess -or $serverProcess.ProcessName -notmatch "python") {
        throw "Health endpoint reported an invalid canonical server process: $serverPid"
    }
    New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
    [ordered]@{
        recorded_at = (Get-Date).ToUniversalTime().ToString("o")
        backend_url = $BackendUrl
        process_id = $serverPid
        app_version = $existingHealth.runtime.app_version
        build_commit = $existingHealth.runtime.build_commit
        build_id = $existingHealth.runtime.build_id
        extension_dist = (Join-Path $extensionRoot "dist")
        state = "reused_verified_runtime"
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDir "runtime-latest.json") -Encoding utf8
    Write-Output "Canonical runtime already active: $BackendUrl pid=$serverPid build=$($existingHealth.runtime.build_id)"
    exit 0
}

$canonicalListeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
$canonicalPids = @($canonicalListeners | Select-Object -ExpandProperty OwningProcess -Unique)
if ($canonicalPids.Count -gt 1) {
    throw "Refusing to continue: more than one process owns canonical port $Port."
}
if ($canonicalPids.Count -eq 1) {
    $health = Get-CanonicalHealth -Url $BackendUrl
    $listenerPid = [int]$canonicalPids[0]
    if (
        $health.status -eq "ok" -and
        $health.runtime.canonical_backend_url.TrimEnd("/") -eq $BackendUrl.TrimEnd("/") -and
        [int]$health.runtime.process_id -eq $listenerPid
    ) {
        New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
        [ordered]@{
            recorded_at = (Get-Date).ToUniversalTime().ToString("o")
            backend_url = $BackendUrl
            process_id = $listenerPid
            app_version = $health.runtime.app_version
            build_commit = $health.runtime.build_commit
            build_id = $health.runtime.build_id
            extension_dist = (Join-Path $extensionRoot "dist")
            state = "reused_verified_runtime"
        } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDir "runtime-latest.json") -Encoding utf8
        Write-Output "Canonical runtime already active: $BackendUrl pid=$listenerPid build=$($health.runtime.build_id)"
        exit 0
    }
    throw "Port $Port is occupied by a process that does not match the canonical runtime handshake."
}

New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$commit = (& git -C $repoRoot rev-parse --short HEAD 2>$null).Trim()
if (-not $commit) { $commit = "dev" }
$buildId = "stabilization-" + (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$appVersion = "0.4.0"

$env:VITE_BACKEND_URL = $BackendUrl
$env:VITE_APP_VERSION = $appVersion
$env:VITE_BUILD_COMMIT = $commit
$env:VITE_BUILD_ID = $buildId

Push-Location $extensionRoot
try {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "Extension build failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}

$env:APP_VERSION = $appVersion
$env:BUILD_COMMIT = $commit
$env:BUILD_ID = $buildId
$env:CANONICAL_BACKEND_URL = $BackendUrl

$stdoutPath = Join-Path $runtimeDir "$buildId.stdout.log"
$stderrPath = Join-Path $runtimeDir "$buildId.stderr.log"
$backendProcess = Start-Process -FilePath $pythonPath `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port") `
    -WorkingDirectory $backendRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -PassThru

$health = $null
for ($attempt = 1; $attempt -le 120; $attempt += 1) {
    Start-Sleep -Milliseconds 500
    $health = Get-CanonicalHealth -Url $BackendUrl
    if ($health -and $health.status -eq "ok") { break }
    if ($backendProcess.HasExited) { break }
}

if (-not $health -or $health.status -ne "ok") {
    throw "Canonical backend did not become healthy. Inspect $stderrPath"
}
if (
    $health.db -ne "connected" -or
    $health.runtime.app_version -ne $appVersion -or
    $health.runtime.build_commit -ne $commit -or
    $health.runtime.build_id -ne $buildId -or
    $health.runtime.canonical_backend_url.TrimEnd("/") -ne $BackendUrl.TrimEnd("/") -or
    -not (Get-Process -Id ([int]$health.runtime.process_id) -ErrorAction SilentlyContinue)
) {
    throw "Canonical runtime handshake failed after startup: $($health | ConvertTo-Json -Depth 5 -Compress)"
}

$runtimeRecord = [ordered]@{
    recorded_at = (Get-Date).ToUniversalTime().ToString("o")
    backend_url = $BackendUrl
    process_id = [int]$health.runtime.process_id
    app_version = $appVersion
    build_commit = $commit
    build_id = $buildId
    extension_dist = (Join-Path $extensionRoot "dist")
    backend_stdout = $stdoutPath
    backend_stderr = $stderrPath
}
$runtimeRecord | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDir "runtime-latest.json") -Encoding utf8
Write-Output ($runtimeRecord | ConvertTo-Json -Compress)
