[CmdletBinding()]
param(
    [string]$HostAddress = "127.0.0.1",
    [int]$GatewayPort = 18088,
    [int]$AgentServicePort = 18090,
    [int]$FrontendPort = 5173,
    [string]$RedisUrl = "redis://127.0.0.1:6379/0",
    [switch]$SkipNpmInstall
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$FrontendRoot = Join-Path $Root "frontend"
$LogRoot = Join-Path $Root ".local\logs"

function Require-Command {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Hint
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required. $Hint"
    }
}

function Import-DotEnv {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path $Path)) {
        return
    }

    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if ($line.Length -eq 0 -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }

        $name, $value = $line.Split("=", 2)
        $name = $name.Trim()
        $value = $value.Trim().Trim('"').Trim("'")
        if ($name -and -not [Environment]::GetEnvironmentVariable($name, "Process")) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

function Test-TcpPort {
    param(
        [Parameter(Mandatory = $true)][string]$TargetHost,
        [Parameter(Mandatory = $true)][int]$Port
    )

    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $connection = $client.BeginConnect($TargetHost, $Port, $null, $null)
        $connected = $connection.AsyncWaitHandle.WaitOne(1000, $false)
        if ($connected) {
            $client.EndConnect($connection)
        }
        $client.Close()
        return $connected
    }
    catch {
        return $false
    }
}

function Test-Redis {
    param(
        [Parameter(Mandatory = $true)][string]$RedisHost,
        [Parameter(Mandatory = $true)][int]$RedisPort
    )

    $redisCli = Get-Command redis-cli -ErrorAction SilentlyContinue
    if ($redisCli) {
        $response = & $redisCli.Source -h $RedisHost -p $RedisPort ping 2>$null
        return $LASTEXITCODE -eq 0 -and $response -eq "PONG"
    }

    return Test-TcpPort -TargetHost $RedisHost -Port $RedisPort
}

function Quote-ForPowerShell {
    param([Parameter(Mandatory = $true)][string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

function Start-WindowsTerminalTab {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][string]$Command
    )

    $wt = Get-Command wt.exe -ErrorAction SilentlyContinue
    if (-not $wt) {
        throw "Windows Terminal is required. Install it from Microsoft Store or winget, then rerun this script."
    }

    $shell = Get-Command pwsh -ErrorAction SilentlyContinue
    if (-not $shell) {
        $shell = Get-Command powershell.exe -ErrorAction SilentlyContinue
    }
    if (-not $shell) {
        throw "PowerShell is required to launch service tabs."
    }

    Start-Process -FilePath $wt.Source -ArgumentList @(
        "new-tab",
        "--title",
        $Title,
        $shell.Source,
        "-NoExit",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        $Command
    )
}

Import-DotEnv -Path (Join-Path $Root ".env")

if (-not $env:REDIS_URL) {
    $env:REDIS_URL = $RedisUrl
}
if (-not $env:AGENT_SERVICE_STORE_TTL_SECONDS) {
    $env:AGENT_SERVICE_STORE_TTL_SECONDS = "86400"
}

Require-Command -Name "uv" -Hint "Install uv from https://docs.astral.sh/uv/ before starting the Python services."
Require-Command -Name "npm" -Hint "Install Node.js LTS, which includes npm, before starting the React client."

$redisUri = [Uri]$env:REDIS_URL
$redisHost = if ($redisUri.Host) { $redisUri.Host } else { "127.0.0.1" }
$redisPort = if ($redisUri.Port -gt 0) { $redisUri.Port } else { 6379 }

if (-not (Test-Redis -RedisHost $redisHost -RedisPort $redisPort)) {
    $redisServer = Get-Command redis-server -ErrorAction SilentlyContinue
    if ($redisServer) {
        Write-Host "Starting local redis-server on ${redisHost}:${redisPort}."
        Start-Process -FilePath $redisServer.Source -ArgumentList @(
            "--bind",
            $redisHost,
            "--port",
            $redisPort,
            "--save",
            '""',
            "--appendonly",
            "no"
        ) | Out-Null
        Start-Sleep -Seconds 2
    }
}

if (-not (Test-Redis -RedisHost $redisHost -RedisPort $redisPort)) {
    throw "Docker-free startup requires Redis at $env:REDIS_URL or redis-server on PATH. Start Redis first, then rerun this script."
}

if (-not $SkipNpmInstall -and -not (Test-Path (Join-Path $FrontendRoot "node_modules"))) {
    Push-Location $FrontendRoot
    try {
        npm install
    }
    finally {
        Pop-Location
    }
}

New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null

$rootLiteral = Quote-ForPowerShell -Value $Root.Path
$frontendLiteral = Quote-ForPowerShell -Value $FrontendRoot
$agentPathLiteral = Quote-ForPowerShell -Value (Join-Path $Root "services\agent_service")
$gatewayPathLiteral = Quote-ForPowerShell -Value (Join-Path $Root "services\ag_ui_gateway")
$agentUrlLiteral = Quote-ForPowerShell -Value "http://${HostAddress}:${AgentServicePort}"
$gatewayUrlLiteral = Quote-ForPowerShell -Value "http://${HostAddress}:${GatewayPort}"

$agentCommand = "Set-Location $rootLiteral; `$env:PYTHONPATH = $agentPathLiteral; uv run uvicorn adk_agent_service.app:app --host $HostAddress --port $AgentServicePort"
$gatewayCommand = "Set-Location $rootLiteral; `$env:PYTHONPATH = $gatewayPathLiteral; `$env:AGENT_SERVICE_URL = $agentUrlLiteral; uv run uvicorn gateway_app.app:app --host $HostAddress --port $GatewayPort"
$frontendCommand = "Set-Location $frontendLiteral; `$env:VITE_AG_UI_GATEWAY_URL = $gatewayUrlLiteral; npm run dev -- --host $HostAddress --port $FrontendPort"

Start-WindowsTerminalTab -Title "agent-service" -Command $agentCommand
Start-Sleep -Seconds 2
Start-WindowsTerminalTab -Title "ag-ui-gateway" -Command $gatewayCommand
Start-Sleep -Seconds 1
Start-WindowsTerminalTab -Title "frontend" -Command $frontendCommand

Write-Host "Started AG-UI Agent stack without Docker."
Write-Host "Frontend: http://${HostAddress}:${FrontendPort}"
Write-Host "Gateway:  http://${HostAddress}:${GatewayPort}"
Write-Host "Agent:    http://${HostAddress}:${AgentServicePort}"
Write-Host "Redis:    $env:REDIS_URL"
