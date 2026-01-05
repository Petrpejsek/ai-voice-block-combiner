#!/bin/bash
set -e

echo "🔄 RESTART SCRIPT - Killing old processes and starting fresh..."
echo ""

# Kill frontend (port 4000)
echo "🔴 Killing frontend (port 4000)..."
lsof -ti tcp:4000 | xargs kill -9 2>/dev/null || echo "   No process on port 4000"
sleep 1

# Kill backend (port 50000)
echo "🔴 Killing backend (port 50000)..."
lsof -ti tcp:50000 | xargs kill -9 2>/dev/null || echo "   No process on port 50000"
sleep 2

# Verify ports are free
echo ""
echo "🔍 Verifying ports are free..."
if lsof -ti tcp:4000 >/dev/null 2>&1; then
    echo "❌ ERROR: Port 4000 still occupied!"
    lsof -nP -iTCP:4000 -sTCP:LISTEN
    exit 1
fi
if lsof -ti tcp:50000 >/dev/null 2>&1; then
    echo "❌ ERROR: Port 50000 still occupied!"
    lsof -nP -iTCP:50000 -sTCP:LISTEN
    exit 1
fi
echo "✅ Ports 4000 and 50000 are free"
echo ""

# Start backend
echo "🟢 Starting backend (port 50000)..."
cd /Users/petrliesner/podcasts/backend
nohup python3 app.py > /tmp/backend_restart.log 2>&1 &
BACKEND_PID=$!
echo "   Backend started with PID: $BACKEND_PID"
sleep 3

# Verify backend is responding
echo "🔍 Checking backend health..."
for i in {1..10}; do
    if curl -s http://localhost:50000/api/health >/dev/null 2>&1; then
        echo "✅ Backend is responding on port 50000"
        break
    fi
    if [ $i -eq 10 ]; then
        echo "❌ ERROR: Backend not responding after 10 attempts"
        echo "   Backend log:"
        tail -20 /tmp/backend_restart.log
        exit 1
    fi
    echo "   Waiting for backend... (attempt $i/10)"
    sleep 1
done
echo ""

# Start frontend
echo "🟢 Starting frontend (port 4000)..."
cd /Users/petrliesner/podcasts/frontend
nohup sh -c "PORT=4000 BROWSER=none npm start" > /tmp/frontend_restart.log 2>&1 &
FRONTEND_PID=$!
echo "   Frontend started with PID: $FRONTEND_PID"
sleep 5

# Verify frontend is responding
echo "🔍 Checking frontend..."
for i in {1..15}; do
    if curl -s -I http://localhost:4000 | grep -q "200 OK"; then
        echo "✅ Frontend is responding on port 4000"
        break
    fi
    if [ $i -eq 15 ]; then
        echo "❌ ERROR: Frontend not responding after 15 attempts"
        echo "   Frontend log:"
        tail -30 /tmp/frontend_restart.log
        exit 1
    fi
    echo "   Waiting for frontend... (attempt $i/15)"
    sleep 2
done

echo ""
echo "════════════════════════════════════════════════════"
echo "✅ RESTART COMPLETE"
echo "════════════════════════════════════════════════════"
echo "Backend:  http://localhost:50000 (PID: $BACKEND_PID)"
echo "Frontend: http://localhost:4000  (PID: $FRONTEND_PID)"
echo ""
echo "Logs:"
echo "  Backend:  tail -f /tmp/backend_restart.log"
echo "  Frontend: tail -f /tmp/frontend_restart.log"
echo "════════════════════════════════════════════════════"



