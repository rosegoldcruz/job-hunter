#!/bin/bash
echo "Starting FastAPI backend on port 8000..."
uvicorn api:app --host 0.0.0.0 --port 8000 --reload &

echo "Building Next.js frontend..."
cd frontend && npm run build && npm start
