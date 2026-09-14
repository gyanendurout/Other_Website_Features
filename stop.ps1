<#
    stop.ps1 - shut the local stack down.

        .\stop.ps1            # stop containers + web UI (data kept)
        .\stop.ps1 -Volumes   # also drop container volumes

    The catalog lives in db/features.db on the host, so nothing here touches
    your data. -Volumes only clears Firecrawl's own queue/cache volumes.
#>
[CmdletBinding()]
param(
    [switch]$Volumes,
    [int]$WebPort = 3100
)

$ErrorActionPreference = "Continue"
$Root = $PSScriptRoot
$Compose = Join-Path $Root "firecrawl\docker-compose.yaml"
# Explicit -f disables compose's automatic override discovery, so the local
# override (a realistic RabbitMQ start_period) must be passed by hand.
$Override = Join-Path $Root "firecrawl\docker-compose.override.yaml"
$Files = @("-f", $Compose)
if (Test-Path $Override) { $Files += @("-f", $Override) }

Write-Host "`n[*] Stopping web UI on :$WebPort" -ForegroundColor Cyan
$conns = Get-NetTCPConnection -LocalPort $WebPort -State Listen -ErrorAction SilentlyContinue
if ($conns) {
    foreach ($c in $conns) {
        try {
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction Stop
            Write-Host "    OK  stopped pid $($c.OwningProcess)" -ForegroundColor Green
        } catch {
            Write-Host "    !!  could not stop pid $($c.OwningProcess)" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "    nothing listening on :$WebPort" -ForegroundColor DarkGray
}

Write-Host "`n[*] Stopping Firecrawl containers" -ForegroundColor Cyan
if ($Volumes) {
    docker compose @Files down -v
    Write-Host "    OK  containers and volumes removed" -ForegroundColor Green
} else {
    docker compose @Files down
    Write-Host "    OK  containers stopped (volumes kept)" -ForegroundColor Green
}

Write-Host "`n  db/features.db is on the host and was not touched.`n" -ForegroundColor DarkGray
