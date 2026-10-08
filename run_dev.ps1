# TradingAgents Development Server
Write-Host "Starting TradingAgents Development Servers..." -ForegroundColor Green
Write-Host ""

# Start FastAPI backend
Write-Host "[1/2] Starting FastAPI backend on http://localhost:8000" -ForegroundColor Cyan
Start-Process -NoNewWindow powershell -ArgumentList "-Command", "cd '$PSScriptRoot'; python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000"

Start-Sleep -Seconds 2

# Start React frontend
Write-Host "[2/2] Starting React frontend on http://localhost:3000" -ForegroundColor Cyan  
Set-Location "$PSScriptRoot\frontend"
npm run dev

