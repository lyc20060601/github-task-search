[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$exampleEnvironment = Join-Path $projectRoot ".env.example"
$composeProject = "github-task-search-smoke-$PID".ToLowerInvariant()
$composeAttempted = $false
$savedEnvironment = @{}
$isolatedEnvironmentNames = @(
    "GITHUB_TOKEN",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "FRONTEND_ORIGIN",
    "NEXT_PUBLIC_API_BASE_URL",
    "VALIDATION_MODE",
    "VALIDATION_WORKER_TOKEN"
)
Set-Location -LiteralPath $projectRoot

function Invoke-Compose {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [switch]$Quiet
    )

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        if ($Quiet) {
            & docker compose --project-name $composeProject --env-file $exampleEnvironment @Arguments *> $null
        } else {
            & docker compose --project-name $composeProject --env-file $exampleEnvironment @Arguments
        }
        if ($LASTEXITCODE -ne 0) {
            throw "Docker Compose failed with exit code $LASTEXITCODE."
        }
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Wait-ForHttp {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedText
    )

    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 3
            if ($response.StatusCode -eq 200 -and $response.Content.Contains($ExpectedText)) {
                return
            }
        } catch {
            # The service may still be starting.
        }
        Start-Sleep -Seconds 1
    }
    throw "Timed out waiting for $Uri."
}

function Assert-ImageBoundary {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Image
    )

    $inspectionResult = & docker image inspect $Image | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect image $Image."
    }
    $inspection = $inspectionResult[0]
    $sensitiveNames = @("GITHUB_TOKEN", "LLM_API_KEY", "VALIDATION_WORKER_TOKEN")
    foreach ($entry in @($inspection.Config.Env)) {
        $name = ($entry -split "=", 2)[0]
        if ($sensitiveNames -contains $name) {
            throw "Image $Image contains a sensitive runtime variable."
        }
    }

    & docker run --rm --network none --entrypoint sh $Image -c "test ! -e /app/.env -a ! -e /app/backend/.env"
    if ($LASTEXITCODE -ne 0) {
        throw "Image $Image contains an unexpected .env file."
    }
}

foreach ($name in $isolatedEnvironmentNames) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

try {
    foreach ($name in $isolatedEnvironmentNames) {
        [Environment]::SetEnvironmentVariable($name, $null, "Process")
    }

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker command was not found."
    }
    if (-not (Test-Path -LiteralPath $exampleEnvironment -PathType Leaf)) {
        throw ".env.example was not found."
    }
    & docker info --format "{{.ServerVersion}}" *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Engine is not running."
    }

    $existingContainers = @(& docker compose --project-name $composeProject --env-file $exampleEnvironment ps --all --quiet)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect existing Compose services."
    }
    if ($existingContainers.Count -gt 0) {
        throw "The isolated smoke-test Compose project is not clean."
    }

    try {
        Invoke-Compose -Arguments @("config", "--quiet")
        Invoke-Compose -Arguments @("build")
        Assert-ImageBoundary -Image "github-task-search-backend:local"
        Assert-ImageBoundary -Image "github-task-search-frontend:local"

        $composeAttempted = $true
        Invoke-Compose -Arguments @("up", "--detach")
        Wait-ForHttp -Uri "http://127.0.0.1:8000/" -ExpectedText "GitHub Task Search API"
        Wait-ForHttp -Uri "http://127.0.0.1:3000/" -ExpectedText "GitHub Task Search"

        $schema = Invoke-RestMethod -Uri "http://127.0.0.1:8000/openapi.json" -TimeoutSec 5
        foreach ($route in @("/search", "/smart-search", "/recommend-search", "/validate-repository")) {
            if ($null -eq $schema.paths.PSObject.Properties[$route]) {
                throw "Expected API route is missing: $route"
            }
        }

        try {
            Invoke-RestMethod `
                -Method Post `
                -Uri "http://127.0.0.1:8000/validate-repository" `
                -ContentType "application/json" `
                -Body '{"full_name":"owner/repository"}' `
                -TimeoutSec 5 | Out-Null
            throw "Disabled validation unexpectedly accepted a repository."
        } catch {
            if ($null -eq $_.Exception.Response -or $_.Exception.Response.StatusCode.value__ -ne 503) {
                throw
            }
        }

        $containerIds = @(& docker compose --project-name $composeProject --env-file $exampleEnvironment ps --quiet)
        if ($LASTEXITCODE -ne 0 -or $containerIds.Count -ne 2) {
            throw "Expected exactly two running application containers."
        }
        foreach ($containerId in $containerIds) {
            $containerResult = & docker inspect $containerId | ConvertFrom-Json
            if ($LASTEXITCODE -ne 0) {
                throw "Unable to inspect a Compose container."
            }
            $container = $containerResult[0]
            if ($container.HostConfig.Privileged) {
                throw "A Compose container is running in privileged mode."
            }
            if ($container.Config.User -ne "10001:10001") {
                throw "A Compose container is not using the expected non-root identity."
            }
            if (@($container.Mounts).Count -ne 0) {
                throw "A Compose container has an unexpected host mount."
            }
        }

    } finally {
        if ($composeAttempted) {
            Invoke-Compose -Arguments @("down", "--remove-orphans")
            $remainingContainers = @(& docker compose --project-name $composeProject --env-file $exampleEnvironment ps --all --quiet)
            if ($LASTEXITCODE -ne 0 -or $remainingContainers.Count -ne 0) {
                throw "Smoke-test Compose cleanup left containers behind."
            }
        }
    }

    Write-Host "Self-hosted smoke test passed."
} finally {
    foreach ($name in $isolatedEnvironmentNames) {
        [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], "Process")
    }
}
