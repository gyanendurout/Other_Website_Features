<#
    start.ps1 - bring the whole feature-catalog stack up locally.

        .\start.ps1              # start everything
        .\start.ps1 -Rebuild     # also wipe web/.next first
        .\start.ps1 -NoWeb       # containers only

    Safe to run twice. Everything here is idempotent.
#>
[CmdletBinding()]
param(
    [switch]$Rebuild,
    [switch]$NoWeb,
    [int]$WebPort = 3100,
    [int]$ApiPort = 3002
)

$ErrorActionPreference = "Continue"
$Root = $PSScriptRoot
$Compose = Join-Path $Root "firecrawl\docker-compose.yaml"
# Explicit -f disables compose's automatic override discovery, so the local
# override (a realistic RabbitMQ start_period) must be passed by hand.
$Override = Join-Path $Root "firecrawl\docker-compose.override.yaml"
$Files = @("-f", $Compose)
if (Test-Path $Override) { $Files += @("-f", $Override) }
$WebDir = Join-Path $Root "web"

# FoundationDB is deliberately excluded - the queue runs on NuQ Postgres.
$Services = @("nuq-postgres", "redis", "rabbitmq", "playwright-service", "api")

function Say([string]$msg, [string]$colour = "Gray") { Write-Host $msg -ForegroundColor $colour }
function Step([string]$msg) { Write-Host "`n[*] $msg" -ForegroundColor Cyan }
function Ok([string]$msg) { Write-Host "    OK  $msg" -ForegroundColor Green }
function Warn([string]$msg) { Write-Host "    !!  $msg" -ForegroundColor Yellow }
function Die([string]$msg) { Write-Host "`nFAILED: $msg" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------- docker up

function Test-Docker {
    # no stderr redirect: docker prints warnings there and 5.1 would treat
    # them as terminating errors.
    #
    # The exit code is NOT sufficient. `docker info --format ...` exits 0 even
    # when the daemon is unreachable - it prints the connection error to stderr
    # and returns an empty string. Trusting $LASTEXITCODE alone made this script
    # report "Docker is running" and then fail on the very next command.
    # Require an actual version string back.
    $v = docker info --format "{{.ServerVersion}}"
    return ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($v))
}

Step "Checking Docker"
if (-not (Test-Docker)) {
    Warn "Docker is not responding. Trying to start Docker Desktop..."
    $dd = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dd) {
        Start-Process $dd | Out-Null
        $waited = 0
        while ($waited -lt 180) {
            Start-Sleep -Seconds 5; $waited += 5
            if (Test-Docker) { break }
            Write-Host "    waiting for Docker Desktop... ${waited}s" -ForegroundColor DarkGray
        }
    }
    if (-not (Test-Docker)) { Die "Docker Desktop did not come up. Start it manually and re-run." }
}
Ok "Docker is running"

if (-not (Test-Path $Compose)) { Die "Compose file not found at $Compose" }

Step "Starting Firecrawl containers"
# The first launch of a freshly-created rabbitmq container exits 1 and takes the
# api container down with it (api depends_on rabbitmq being healthy). Re-running
# the identical command immediately afterwards succeeds every time - observed on
# every cold start, never on a restart. See firecrawl/docker-compose.override.yaml.
docker compose @Files up -d @Services
if ($LASTEXITCODE -ne 0) {
    Warn "First bring-up failed (the known cold-start RabbitMQ exit). Retrying in 15s..."
    Start-Sleep -Seconds 15
    docker compose @Files up -d @Services
    if ($LASTEXITCODE -ne 0) { Die "Containers would not start. Check: docker compose -f `"$Compose`" logs --tail 50" }
}
Ok "Containers requested"

# ---------------------------------------------------------------- health

Step "Waiting for Firecrawl API on :$ApiPort"
$deadline = (Get-Date).AddSeconds(180)
$healthy = $false
$tick = 0
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:$ApiPort/" -TimeoutSec 4 -UseBasicParsing
        if ($r.StatusCode -lt 500) { $healthy = $true; break }
    } catch {
        # Invoke-WebRequest throws on any non-2xx as well as on a refused
        # connection. A status in the response means something is listening.
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -and $code -lt 500) { $healthy = $true; break }
    }
    Start-Sleep -Seconds 4
    $tick += 4
    if ($tick % 20 -eq 0) { Write-Host "    still booting... ${tick}s" -ForegroundColor DarkGray }
}
if (-not $healthy) {
    # The api container runs its own harness that waits 60s for port 3002 to
    # bind, then exits 1 with "Port 3002 did not become available". On a cold
    # Docker start the six workers take longer than that, so the container dies
    # while every other service is fine. Restarting it once - with the rest of
    # the stack already warm - succeeds.
    $state = docker inspect -f "{{.State.Status}}" firecrawl-api-1
    if ($state -ne "running") {
        Warn "api container is '$state' (known cold-start harness timeout). Restarting it..."
        docker compose @Files up -d api
        $deadline = (Get-Date).AddSeconds(180)
        $tick = 0
        while ((Get-Date) -lt $deadline) {
            try {
                $r = Invoke-WebRequest -Uri "http://localhost:$ApiPort/" -TimeoutSec 4 -UseBasicParsing
                if ($r.StatusCode -lt 500) { $healthy = $true; break }
            } catch {
                $code = $_.Exception.Response.StatusCode.value__
                if ($code -and $code -lt 500) { $healthy = $true; break }
            }
            Start-Sleep -Seconds 4
            $tick += 4
            if ($tick % 20 -eq 0) { Write-Host "    restarting... ${tick}s" -ForegroundColor DarkGray }
        }
    }
}
if ($healthy) { Ok "Firecrawl answering on http://localhost:$ApiPort" }
else { Warn "Firecrawl did not answer. Scrapes will fail until it does. Logs: docker compose -f `"$Compose`" logs api --tail 50" }

# ---------------------------------------------------------------- web

if ($NoWeb) {
    Step "Skipping web UI (-NoWeb)"
} else {
    Step "Starting Next.js on :$WebPort"

    # Never let `next dev` and `next build` share .next - both write it, and the
    # result is a runtime "Cannot find module './###.js'".
    $stale = Get-NetTCPConnection -LocalPort $WebPort -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $stale) {
        try {
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction Stop
            Warn "Killed stale listener on :$WebPort (pid $($c.OwningProcess))"
        } catch { }
    }
    if ($stale) { Start-Sleep -Seconds 2 }

    if ($Rebuild) {
        $next = Join-Path $WebDir ".next"
        if (Test-Path $next) { Remove-Item -Recurse -Force $next; Ok "Cleared web/.next" }
    }

    if (-not (Test-Path (Join-Path $WebDir "node_modules"))) {
        Warn "node_modules missing - running npm install (one time)"
        Push-Location $WebDir; npm install; Pop-Location
    }

    $log = Join-Path $Root "data\web-dev.log"
    New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
    Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev" `
        -WorkingDirectory $WebDir -WindowStyle Hidden `
        -RedirectStandardOutput $log -RedirectStandardError "$log.err" | Out-Null

    # A cold .next can take well over a minute to compile the first route.
    $deadline = (Get-Date).AddSeconds(240)
    $up = $false
    $tick = 0
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:$WebPort/" -TimeoutSec 6 -UseBasicParsing
            if ($r.StatusCode -lt 500) { $up = $true; break }
        } catch {
            $code = $_.Exception.Response.StatusCode.value__
            if ($code -and $code -lt 500) { $up = $true; break }
        }
        Start-Sleep -Seconds 3
        $tick += 3
        if ($tick % 15 -eq 0) { Write-Host "    compiling... ${tick}s" -ForegroundColor DarkGray }
    }
    if ($up) { Ok "Web UI live at http://localhost:$WebPort" }
    else { Warn "Web UI did not answer in 240s. Log: $log" }
}

# ---------------------------------------------------------------- summary

Step "Stack status"
docker compose @Files ps --format "    {{.Service}}`t{{.State}}"

$py = Join-Path $Root ".venv\Scripts\python.exe"
$stats = Join-Path $Root "scripts\stats.py"
if ((Test-Path $py) -and (Test-Path $stats)) {
    Write-Host ""
    & $py $stats
}

Write-Host ""
Say "  Web UI      http://localhost:$WebPort" "White"
Say "  Firecrawl   http://localhost:$ApiPort" "White"
Say "  Capture     http://localhost:$WebPort/capture" "White"
Say "  Gaps        http://localhost:$WebPort/gaps" "White"
Write-Host ""
Say "  Stop with:  .\stop.ps1" "DarkGray"
Write-Host ""
