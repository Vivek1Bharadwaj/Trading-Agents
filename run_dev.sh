#!/bin/bash
# TradingAgents Development Server
echo "Starting TradingAgents Development Servers..."
echo ""

# Start FastAPI backend in background
echo "[1/2] Starting FastAPI backend on http://localhost:8000"
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

sleep 2

# Start React frontend
echo "[2/2] Starting React frontend on http://localhost:3000"
cd frontend && npm run dev

# Cleanup
kill $BACKEND_PID 2>/dev/null

