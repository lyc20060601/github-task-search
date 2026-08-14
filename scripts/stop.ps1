[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = [System.IO.Path]::GetFullPath((Join-Path $projectRoot "backend\.venv\Scripts\python.exe"))
$pidFile = Join-Path $projectRoot ".runtime\validation-worker.pid"
$workerError = $null
Set-Location -LiteralPath $projectRoot

try {
    if (Test-Path -LiteralPath $pidFile -PathType Leaf) {
        $pidText = (Get-Content -LiteralPath $pidFile -Raw).Trim()
        $workerPid = 0
        if (-not [int]::TryParse($pidText, [ref]$workerPid) -or $workerPid -le 0) {
            $workerError = "Ignoring invalid validation worker PID file."
        } else {
            $process = Get-Process -Id $workerPid -ErrorAction SilentlyContinue
            if ($null -ne $process) {
                $metadata = Get-CimInstance Win32_Process -Filter "ProcessId = $workerPid" -ErrorAction SilentlyContinue
                $belongsToProject = $true
                if ($null -ne $metadata -and -not [string]::IsNullOrWhiteSpace($metadata.CommandLine)) {
                    $belongsToProject = $metadata.CommandLine.Contains("runtime.validation_worker")
                    if (-not [string]::IsNullOrWhiteSpace($metadata.ExecutablePath)) {
                        $belongsToProject = $belongsToProject -and (
                            [System.IO.Path]::GetFullPath($metadata.ExecutablePath) -eq $pythonPath
                        )
                    }
                }
                if ($belongsToProject) {
                    Stop-Process -Id $workerPid
                    for ($attempt = 0; $attempt -lt 20; $attempt++) {
                        if (-not (Get-Process -Id $workerPid -ErrorAction SilentlyContinue)) {
                            break
                        }
                        Start-Sleep -Milliseconds 500
                    }
                } else {
                    $workerError = "Recorded PID does not belong to this project's validation worker; it was not stopped."
                }
            }
        }
        Remove-Item -LiteralPath $pidFile -Force
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
