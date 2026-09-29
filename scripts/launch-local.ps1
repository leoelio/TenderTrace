$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$serviceUrl = "http://127.0.0.1:8000/"
$healthUrl = "${serviceUrl}api/health"
$logDirectory = Join-Path $projectRoot "logs"
$standardLog = Join-Path $logDirectory "local-service.log"
$errorLog = Join-Path $logDirectory "local-service-error.log"

function Test-TenderTraceService {
    try {
        $response = Invoke-WebRequest -UseBasicParsing $healthUrl -TimeoutSec 2
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Host "[TenderTrace] Local Python environment was not found." -ForegroundColor Red
    Write-Host "Complete the README Quick Start steps first."
    Read-Host "Press Enter to close"
    exit 1
}

if (-not (Test-TenderTraceService)) {
    Write-Host "[TenderTrace] Starting the local service..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $env:TENDERTRACE_HOST = "127.0.0.1"
    $env:TENDERTRACE_SCHEDULER_ENABLED = "true"
    $env:TENDERTRACE_DELIVERY_CHANNELS = "web,outbox,feishu_bitable"
    $env:PYTHONUTF8 = "1"
    Start-Process `
        -FilePath $pythonPath `
        -ArgumentList @("-m", "tendertrace", "serve") `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $standardLog `
        -RedirectStandardError $errorLog

    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt += 1) {
        Start-Sleep -Seconds 1
        if (Test-TenderTraceService) {
            $ready = $true
            break
        }
    }
    if (-not $ready) {
        Write-Host "[TenderTrace] Startup failed. See logs\local-service-error.log." -ForegroundColor Red
        Read-Host "Press Enter to close"
        exit 1
    }
}

Write-Host "[TenderTrace] Ready: $serviceUrl" -ForegroundColor Green
Start-Process $serviceUrl
exit 0
