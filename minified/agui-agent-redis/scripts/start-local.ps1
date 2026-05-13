[CmdletBinding()]
param(
    [string]$HostAddress = "127.0.0.1",
    [int]$AgentServicePort = 18088,
    [int]$FrontendPort = 5173,
    [string]$RedisUrl = "redis://127.0.0.1:6379/0",
    [switch]$SkipNpmInstall,
    [switch]$DisableInMemoryFallback
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$FrontendRoot = Join-Path $Root "frontend"

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

if ($env:AGENT_SERVICE_HOST) {
    $HostAddress = $env:AGENT_SERVICE_HOST
}
if ($env:AGENT_SERVICE_PORT) {
    $AgentServicePort = [int]$env:AGENT_SERVICE_PORT
}
if (-not $env:REDIS_URL) {
    $env:REDIS_URL = $RedisUrl
}
if (-not $env:AGENT_SERVICE_STORE_TTL_SECONDS) {
    $env:AGENT_SERVICE_STORE_TTL_SECONDS = "86400"
}
if (-not $env:AGENT_SERVICE_METADATA_STORE) {
    $env:AGENT_SERVICE_METADATA_STORE = "auto"
}
if (-not $env:AGENT_SERVICE_ALLOW_IN_MEMORY_FALLBACK) {
    $env:AGENT_SERVICE_ALLOW_IN_MEMORY_FALLBACK = if ($DisableInMemoryFallback) { "false" } else { "true" }
}

Require-Command -Name "uv" -Hint "Install uv from https://docs.astral.sh/uv/ before starting FastAPI."
Require-Command -Name "npm" -Hint "Install Node.js LTS, which includes npm, before starting the React client."

$redisUri = [Uri]$env:REDIS_URL
$redisHost = if ($redisUri.Host) { $redisUri.Host } else { "127.0.0.1" }
$redisPort = if ($redisUri.Port -gt 0) { $redisUri.Port } else { 6379 }

$redisAvailable = Test-Redis -RedisHost $redisHost -RedisPort $redisPort
if (-not $redisAvailable) {
    $redisServer = Get-Command redis-server -ErrorAction SilentlyContinue
    if ($redisServer) {
        Write-Host "Starting redis-server on ${redisHost}:${redisPort}."
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
        $redisAvailable = Test-Redis -RedisHost $redisHost -RedisPort $redisPort
    }
}

if (-not $redisAvailable) {
    if ($DisableInMemoryFallback -or $env:AGENT_SERVICE_ALLOW_IN_MEMORY_FALLBACK -eq "false") {
        throw "Startup requires Redis at $env:REDIS_URL when in-memory fallback is disabled."
    }
    Write-Host "Redis is unavailable; using in-memory thread metadata."
    $env:AGENT_SERVICE_METADATA_STORE = "memory"
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

$rootLiteral = Quote-ForPowerShell -Value $Root.Path
$frontendLiteral = Quote-ForPowerShell -Value $FrontendRoot
$agentPathLiteral = Quote-ForPowerShell -Value (Join-Path $Root "services\agent_service")
$agentUrlLiteral = Quote-ForPowerShell -Value "http://${HostAddress}:${AgentServicePort}"

$agentCommand = "Set-Location $rootLiteral; `$env:PYTHONPATH = $agentPathLiteral; uv run uvicorn adk_agent_service.app:app --host $HostAddress --port $AgentServicePort"
$frontendCommand = "Set-Location $frontendLiteral; `$env:VITE_AGENT_SERVICE_URL = $agentUrlLiteral; npm run dev -- --host $HostAddress --port $FrontendPort"

Start-WindowsTerminalTab -Title "agent-service" -Command $agentCommand
Start-Sleep -Seconds 2
Start-WindowsTerminalTab -Title "frontend" -Command $frontendCommand

Write-Host "Started AG-UI Agent app."
Write-Host "Frontend:      http://${HostAddress}:${FrontendPort}"
Write-Host "Agent Service: http://${HostAddress}:${AgentServicePort}"
Write-Host "Metadata:      $env:AGENT_SERVICE_METADATA_STORE"
