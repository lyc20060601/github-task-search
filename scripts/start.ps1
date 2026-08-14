[CmdletBinding()]
param(
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot "backend"
$pythonPath = Join-Path $backendRoot ".venv\Scripts\python.exe"
$runtimeRoot = Join-Path $projectRoot ".runtime"
$pidFile = Join-Path $runtimeRoot "validation-worker.pid"
$sandboxImage = "github-task-search-sandbox:latest"
$sandboxDockerfile = "backend/runtime/Dockerfile.sandbox"
$sandboxContext = "backend/runtime"
$workerProcess = $null
$composeStarted = $false
$workerToken = $null
Set-Location -LiteralPath $projectRoot

function Invoke-DockerCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [switch]$Quiet
    )

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        if ($Quiet) {
            & docker @Arguments *> $null
        } else {
            & docker @Arguments
        }
        if ($LASTEXITCODE -ne 0) {
            throw "Docker command failed with exit code $LASTEXITCODE."
        }
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Assert-Prerequisites {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker command was not found. Install Docker Desktop or Docker Engine first."
    }
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw "Backend virtual environment was not found. Create backend/.venv and install backend requirements first."
    }
    Invoke-DockerCommand -Arguments @("compose", "version") -Quiet
}

function Wait-ForBackend {
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        $previousPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & $pythonPath -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=2).read()" *> $null
            $healthExitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $previousPreference
        }
        if ($healthExitCode -eq 0) {
            return
        }
        Start-Sleep -Seconds 1
    }
    throw "Backend did not become healthy within 60 seconds."
}

function Wait-ForWorker {
    param(
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process]$Process
    )

    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        $Process.Refresh()
        if ($Process.HasExited) {
            throw "Validation worker exited before becoming ready."
        }
        try {
            $status = Invoke-RestMethod -Uri "http://127.0.0.1:8000/validation-status" -TimeoutSec 2
            if ($status.mode -eq "worker" -and $status.worker_ready -eq $true) {
                return
            }
        } catch {
            # The backend or worker heartbeat may still be starting.
        }
        Start-Sleep -Seconds 1
    }
    throw "Validation worker did not become ready within 30 seconds."
}

Assert-Prerequisites
if ($ValidateOnly) {
    Write-Host "Lifecycle prerequisites are valid."
    exit 0
}

try {
    Invoke-DockerCommand -Arguments @("info", "--format", "{{.ServerVersion}}") -Quiet

    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot ".env"))) {
        Write-Warning "No .env file was found. Copy .env.example to .env and add your own API keys before using search."
    }

    if (Test-Path -LiteralPath $pidFile -PathType Leaf) {
        $existingText = (Get-Content -LiteralPath $pidFile -Raw).Trim()
        $existingPid = 0
        if ([int]::TryParse($existingText, [ref]$existingPid) -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
            throw "A validation worker recorded for this project is already running."
        }
        Remove-Item -LiteralPath $pidFile -Force
    }

    Invoke-DockerCommand -Arguments @(
        "build",
        "--file", $sandboxDockerfile,
        "--tag", $sandboxImage,
        $sandboxContext
    )

    $tokenBytes = New-Object byte[] 32
    $randomNumberGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $randomNumberGenerator.GetBytes($tokenBytes)
    } finally {
        $randomNumberGenerator.Dispose()
    }
    $workerToken = [Convert]::ToBase64String($tokenBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    $env:VALIDATION_MODE = "worker"
    $env:VALIDATION_WORKER_TOKEN = $workerToken
    $env:VALIDATION_BACKEND_URL = "http://127.0.0.1:8000"

    $composeStarted = $true
    Invoke-DockerCommand -Arguments @("compose", "up", "--build", "--detach")
    Wait-ForBackend

    $workerProcess = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList "-m runtime.validation_worker" `
        -WorkingDirectory $backendRoot `
        -WindowStyle Hidden `
        -PassThru

    New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
    Set-Content -LiteralPath $pidFile -Value $workerProcess.Id -Encoding ascii
    Wait-ForWorker -Process $workerProcess
    Write-Host "Application and validation worker started."
} catch {
    if ($null -ne $workerProcess -and -not $workerProcess.HasExited) {
        Stop-Process -Id $workerProcess.Id -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $pidFile) {
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    }
    if ($composeStarted) {
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & docker compose down *> $null
        $ErrorActionPreference = $previousPreference
    }
    throw
} finally {
    $workerToken = $null
    Remove-Item Env:VALIDATION_WORKER_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:VALIDATION_BACKEND_URL -ErrorAction SilentlyContinue
    Remove-Item Env:VALIDATION_MODE -ErrorAction SilentlyContinue
}
