#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Zatrzymuję stare procesy..."
lsof -ti :8000 | xargs kill -9 2>/dev/null || true
lsof -ti :3000 | xargs kill -9 2>/dev/null || true
sleep 1

echo "==> Uruchamiam backend (port 8000)..."
source "$PROJECT_DIR/.venv/bin/activate"
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 \
  > /tmp/legitscore-backend.log 2>&1 &
echo "Backend PID: $!"

echo "==> Uruchamiam frontend (port 3000)..."
cd "$PROJECT_DIR/frontend"
nohup npm run dev > /tmp/legitscore-frontend.log 2>&1 &
echo "Frontend PID: $!"

echo ""
echo "Czekam na uruchomienie..."
sleep 6

if curl -s http://localhost:8000/api/auth/me > /dev/null 2>&1; then
  echo "✓ Backend działa:  http://localhost:8000"
else
  echo "✗ Backend nie odpowiada — sprawdź: cat /tmp/legitscore-backend.log"
fi

if curl -s http://localhost:3000 > /dev/null 2>&1; then
  echo "✓ Frontend działa: http://localhost:3000/analyze/form"
else
  echo "✗ Frontend nie odpowiada — sprawdź: cat /tmp/legitscore-frontend.log"
fi
