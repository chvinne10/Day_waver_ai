$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Host 'Created .env from .env.example. Change POSTGRES_PASSWORD, then run this script again.' -ForegroundColor Yellow
    exit 1
}
if ((Select-String -Path '.env' -Pattern '^POSTGRES_PASSWORD=change-this-local-development-password$' -Quiet)) {
    Write-Host 'Change POSTGRES_PASSWORD in .env before starting the database.' -ForegroundColor Yellow
    exit 1
}

function Test-ListeningPort([int]$Port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1)
}
function Find-FreePort([int]$Start) {
    for ($port = $Start; $port -lt ($Start + 100); $port++) {
        if (-not (Test-ListeningPort $port)) { return $port }
    }
    throw "No free port found in range $Start-$($Start + 99). Edit BACKEND_PORT or FRONTEND_PORT in .env."
}

$envValues = @{}
Get-Content '.env' | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$' -and $Matches[1] -in @('BACKEND_PORT','FRONTEND_PORT')) {
        $envValues[$Matches[1]] = [int]$Matches[2]
    }
}
$backendStart = if ($envValues.ContainsKey('BACKEND_PORT')) { $envValues['BACKEND_PORT'] } else { 8000 }
$frontendStart = if ($envValues.ContainsKey('FRONTEND_PORT')) { $envValues['FRONTEND_PORT'] } else { 8080 }
$backendPort = Find-FreePort $backendStart
if ($backendPort -eq $frontendStart) { $frontendStart++ }
$frontendPort = Find-FreePort $frontendStart
$env:BACKEND_PORT = "$backendPort"
$env:FRONTEND_PORT = "$frontendPort"

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw 'Docker Engine is unavailable. Start Docker Desktop, then rerun this script. No containers were changed.'
}

Write-Host "Starting only Compose project dayweave-ai. Frontend: http://localhost:$frontendPort  API: http://localhost:$backendPort"
docker compose --env-file .env -p dayweave-ai up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Compose start failed. Inspect with: docker compose -p dayweave-ai logs' }
docker compose --env-file .env -p dayweave-ai ps
