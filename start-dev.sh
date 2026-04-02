#!/bin/bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload &
cd frontend && npm run dev
