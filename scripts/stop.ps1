[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = [System.IO.Path]::GetFullPath((Join-Path $projectRoot "backend\.venv\Scripts\python.exe"))
$pidFile = Join-Path $projectRoot ".runtime\validation-worker.pid"
$workerError = $null
Set-Location -LiteralPath $projectRoot

function Test-WorkerProcessOwnership {
    param(
        [Parameter(Mandatory = $true)]
        [int]$WorkerPid
    )

    $metadata = Get-CimInstance Win32_Process -Filter "ProcessId = $WorkerPid" -ErrorAction SilentlyContinue
    if (
        $null -eq $metadata -or
        [string]::IsNullOrWhiteSpace($metadata.CommandLine) -or
        [string]::IsNullOrWhiteSpace($metadata.ExecutablePath)
    ) {
        return $false
    }

    return (
        $metadata.CommandLine.Contains("runtime.validation_worker") -and
        [System.IO.Path]::GetFullPath($metadata.ExecutablePath) -eq $pythonPath
    )
}

try {
    if (Test-Path -LiteralPath $pidFile -PathType Leaf) {
        $pidFileCanBeRemoved = $false
        $pidText = (Get-Content -LiteralPath $pidFile -Raw).Trim()
        $workerPid = 0
        if (-not [int]::TryParse($pidText, [ref]$workerPid) -or $workerPid -le 0) {
            $workerError = "Invalid validation worker PID file; it was retained."
        } else {
            $process = Get-Process -Id $workerPid -ErrorAction SilentlyContinue
            if ($null -eq $process) {
                $pidFileCanBeRemoved = $true
            } else {
                $belongsToProject = $false
                $belongsToProject = Test-WorkerProcessOwnership -WorkerPid $workerPid
                if ($belongsToProject) {
                    Stop-Process -Id $workerPid
                    for ($attempt = 0; $attempt -lt 20; $attempt++) {
                        if (-not (Get-Process -Id $workerPid -ErrorAction SilentlyContinue)) {
                            break
                        }
                        Start-Sleep -Milliseconds 500
                    }

                    if (Get-Process -Id $workerPid -ErrorAction SilentlyContinue) {
                        if (Test-WorkerProcessOwnership -WorkerPid $workerPid) {
                            Stop-Process -Id $workerPid -Force
                            for ($attempt = 0; $attempt -lt 10; $attempt++) {
                                if (-not (Get-Process -Id $workerPid -ErrorAction SilentlyContinue)) {
                                    break
                                }
                                Start-Sleep -Milliseconds 500
                            }
                        } else {
                            $workerError = "Validation worker PID changed ownership during shutdown; it was not force-stopped."
                        }
                    }

                    if (Get-Process -Id $workerPid -ErrorAction SilentlyContinue) {
                        if ($null -eq $workerError) {
                            $workerError = "Validation worker did not stop; its PID file was retained."
                        }
                    } else {
                        $pidFileCanBeRemoved = $true
                    }
                } else {
                    $workerError = "Recorded PID does not belong to this project's validation worker; it was not stopped and its PID file was retained."
                }
            }
        }
        if ($pidFileCanBeRemoved) {
            Remove-Item -LiteralPath $pidFile -Force
        }
    }
} finally {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & docker compose down
        if ($LASTEXITCODE -ne 0) {
            throw "Docker Compose failed with exit code $LASTEXITCODE."
        }
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

if ($null -ne $workerError) {
    throw $workerError
}
