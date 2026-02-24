# EduBot NAAC System - Start Both Services
Write-Host "Starting EduBot NAAC System..." -ForegroundColor Cyan

# Kill any old processes on ports 8000 and 3000
Get-Process -Name python* -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process -Name node* -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -eq "" } | Stop-Process -Force -ErrorAction SilentlyContinue

Start-Sleep -Seconds 1

# Start Backend
Write-Host "Starting Backend on http://localhost:8000 ..." -ForegroundColor Yellow
$backendDir = "$PSScriptRoot"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$backendDir'; .\naac_env\Scripts\Activate.ps1; python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000" -WindowStyle Normal

# Wait for backend to be ready
Write-Host "Waiting for backend to start..." -ForegroundColor Yellow
$maxWait = 40
$waited = 0
do {
    Start-Sleep -Seconds 2
    $waited += 2
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8000/api/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        Write-Host "Backend ready!" -ForegroundColor Green
        break
    } catch {}
    Write-Host "  Still waiting... ($waited s)" -ForegroundColor Gray
} while ($waited -lt $maxWait)

# Start Frontend
Write-Host "Starting Frontend on http://localhost:3000 ..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\frontend'; npm start" -WindowStyle Normal

Write-Host ""
Write-Host "Both services started!" -ForegroundColor Green
Write-Host "  Frontend: http://localhost:3000" -ForegroundColor Cyan
Write-Host "  Backend:  http://localhost:8000" -ForegroundColor Cyan
Write-Host ""
Write-Host "NOTE: First chatbot response takes ~60 seconds (CPU-based LLM)." -ForegroundColor White
