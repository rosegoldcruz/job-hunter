#!/bin/bash
set -e

echo "Starting ResumeBot Dashboard..."
echo ""

# Start FastAPI backend
echo "[1/2] Starting FastAPI backend on :8000"
uvicorn api:app --port 8000 --reload &
API_PID=$!

# Wait a moment for backend to start
sleep 2

# Start Next.js frontend
echo "[2/2] Starting Next.js frontend on :3000"
cd frontend && npm run dev &
NEXT_PID=$!

echo ""
echo "Dashboard: http://localhost:3000"
echo "API docs:  http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers."

# Trap Ctrl+C and kill both
trap "echo ''; echo 'Stopping...'; kill $API_PID $NEXT_PID 2>/dev/null; exit" INT TERM

wait
