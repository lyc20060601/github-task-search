[CmdletBinding()]
param(
    [switch]$FailAfterWorkerReady
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot "backend"
$pythonPath = Join-Path $backendRoot ".venv\Scripts\python.exe"
$workerFixture = Join-Path $backendRoot "tests\controlled_validation_worker.py"
$exampleEnvironment = Join-Path $projectRoot ".env.example"
$composeProject = "github-task-search-worker-smoke-$PID".ToLowerInvariant()
$composeAttempted = $false
$workerProcess = $null
$savedEnvironment = @{}
$isolatedEnvironmentNames = @(
    "GITHUB_TOKEN",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "FRONTEND_ORIGIN",
    "NEXT_PUBLIC_API_BASE_URL",
    "VALIDATION_MODE",
    "VALIDATION_WORKER_TOKEN",
    "VALIDATION_BACKEND_URL",
    "VALIDATION_CONTROLLED_DELAY_SECONDS"
)
Set-Location -LiteralPath $projectRoot

function Invoke-Compose {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & docker compose --project-name $composeProject --env-file $exampleEnvironment @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Docker Compose failed with exit code $LASTEXITCODE."
        }
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Wait-ForWorkerReady {
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        if ($null -ne $workerProcess) {
            $workerProcess.Refresh()
            if ($workerProcess.HasExited) {
                throw "Controlled validation Worker exited before becoming ready."
            }
        }
        try {
            $status = Invoke-RestMethod -Uri "http://127.0.0.1:8000/validation-status" -TimeoutSec 2
            if ($status.mode -eq "worker" -and $status.worker_ready -eq $true) {
                return
            }
        } catch {
            # Backend or Worker may still be starting.
        }
        Start-Sleep -Seconds 1
    }
    throw "Controlled validation Worker did not become ready."
}

function Stop-ControlledWorker {
    if ($null -eq $script:workerProcess) {
        return
    }

    $workerId = $script:workerProcess.Id
    $script:workerProcess.Refresh()
    if (-not $script:workerProcess.HasExited) {
        Stop-Process -Id $workerId -ErrorAction Stop
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            if (-not (Get-Process -Id $workerId -ErrorAction SilentlyContinue)) {
                break
            }
            Start-Sleep -Milliseconds 250
        }
    }
    if (Get-Process -Id $workerId -ErrorAction SilentlyContinue) {
        throw "Controlled validation Worker did not stop."
    }
    $script:workerProcess = $null
}

function Assert-HttpFailure {
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Request,
        [Parameter(Mandatory = $true)][int]$ExpectedStatus
    )

    try {
        & $Request | Out-Null
        throw "HTTP request unexpectedly succeeded; expected $ExpectedStatus."
    } catch {
        if ($null -eq $_.Exception.Response -or $_.Exception.Response.StatusCode.value__ -ne $ExpectedStatus) {
            throw
        }
    }
}

foreach ($name in $isolatedEnvironmentNames) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

try {
    foreach ($name in $isolatedEnvironmentNames) {
        [Environment]::SetEnvironmentVariable($name, $null, "Process")
    }
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw "Backend virtual environment was not found."
    }
    if (-not (Test-Path -LiteralPath $workerFixture -PathType Leaf)) {
        throw "Controlled Worker fixture was not found."
    }

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
    $env:VALIDATION_CONTROLLED_DELAY_SECONDS = "2"

    try {
        $composeAttempted = $true
        Invoke-Compose -Arguments @("up", "--build", "--detach", "backend")

        $workerProcess = Start-Process `
            -FilePath $pythonPath `
            -ArgumentList $workerFixture `
            -WorkingDirectory $backendRoot `
            -WindowStyle Hidden `
            -PassThru
        Wait-ForWorkerReady
        if ($FailAfterWorkerReady) {
            throw "Intentional Worker smoke-test failure."
        }

        Assert-HttpFailure -ExpectedStatus 401 -Request {
            Invoke-WebRequest `
                -UseBasicParsing `
                -Method Post `
                -Uri "http://127.0.0.1:8000/internal/validation/jobs/next" `
                -Headers @{ Authorization = "Bearer incorrect-token" } `
                -TimeoutSec 5
        }

        Add-Type -AssemblyName System.Net.Http
        $httpClient = New-Object System.Net.Http.HttpClient
        try {
            $firstBody = New-Object System.Net.Http.StringContent(
                '{"full_name":"owner/repository"}',
                [System.Text.Encoding]::UTF8,
                "application/json"
            )
            $firstRequest = $httpClient.PostAsync(
                "http://127.0.0.1:8000/validate-repository",
                $firstBody
            )
            Start-Sleep -Milliseconds 750

            Assert-HttpFailure -ExpectedStatus 429 -Request {
                Invoke-WebRequest `
                    -UseBasicParsing `
                    -Method Post `
                    -Uri "http://127.0.0.1:8000/validate-repository" `
                    -ContentType "application/json" `
                    -Body '{"full_name":"owner/second"}' `
                    -TimeoutSec 5
            }

            $firstResponse = $firstRequest.GetAwaiter().GetResult()
            if ([int]$firstResponse.StatusCode -ne 200) {
                throw "Controlled validation returned HTTP $([int]$firstResponse.StatusCode)."
            }
            $report = ($firstResponse.Content.ReadAsStringAsync().GetAwaiter().GetResult() | ConvertFrom-Json)
            if ($report.full_name -ne "owner/repository" -or $report.runtime_score -ne 100) {
                throw "Controlled validation returned an unexpected report."
            }
        } finally {
            if ($null -ne $firstBody) {
                $firstBody.Dispose()
            }
            $httpClient.Dispose()
        }

        Stop-ControlledWorker

        Start-Sleep -Seconds 16
        Assert-HttpFailure -ExpectedStatus 503 -Request {
            Invoke-WebRequest `
                -UseBasicParsing `
                -Method Post `
                -Uri "http://127.0.0.1:8000/validate-repository" `
                -ContentType "application/json" `
                -Body '{"full_name":"owner/repository"}' `
                -TimeoutSec 5
        }
    } finally {
        $cleanupFailure = $null
        try {
            Stop-ControlledWorker
        } catch {
            $cleanupFailure = $_.Exception
        }
        try {
            if ($composeAttempted) {
                Invoke-Compose -Arguments @("down", "--remove-orphans")
                $remainingContainers = @(& docker compose --project-name $composeProject --env-file $exampleEnvironment ps --all --quiet)
                if ($LASTEXITCODE -ne 0 -or $remainingContainers.Count -ne 0) {
                    throw "Worker smoke-test cleanup left containers behind."
                }
            }
        } catch {
            if ($null -eq $cleanupFailure) {
                $cleanupFailure = $_.Exception
            } else {
                $cleanupFailure = [System.Exception]::new(
                    "Worker and Compose cleanup both failed.",
                    $cleanupFailure
                )
            }
        }
        if ($null -ne $cleanupFailure) {
            throw $cleanupFailure
        }
    }

    Write-Host "Validation Worker smoke test passed."
} finally {
    foreach ($name in $isolatedEnvironmentNames) {
        [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], "Process")
    }
}
