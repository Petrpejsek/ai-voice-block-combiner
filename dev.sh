#!/bin/bash

# 🚀 Development script pro podcast aplikaci
# Použití: ./dev.sh [start|stop|restart|status]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Funkce pro zastavení procesů
stop_processes() {
    echo "🛑 Zastavuji existující procesy..."
    # Kill backend robustly (macOS can show process name as "Python", not "python3")
    pkill -f "python3 app.py" 2>/dev/null
    pkill -f "python app.py" 2>/dev/null
    pkill -f "Python app.py" 2>/dev/null
    # Also kill by port in case command-line match fails
    if command -v lsof >/dev/null 2>&1; then
        lsof -ti tcp:50000 | xargs -r kill -9 2>/dev/null
        lsof -ti tcp:4000 | xargs -r kill -9 2>/dev/null
    fi
    pkill -f "node.*react-scripts" 2>/dev/null
    pkill -f "PORT=4000 npm start" 2>/dev/null
    sleep 2
    echo "✅ Procesy zastaveny"
}

# Funkce pro spuštění aplikace
start_app() {
    echo "🚀 Spouštím podcast aplikaci..."
    
    # Zkontrolovat, zda existují potřebné složky
    echo "📁 Kontroluji složky..."
    mkdir -p uploads
    mkdir -p output
    mkdir -p images
    mkdir -p projects
    
    # Spustit backend
    echo "🔥 Spouštím backend na portu 50000..."
    cd backend
    PORT=50000 python3 app.py > ../backend_server.log 2>&1 &
    BACKEND_PID=$!
    cd ..
    
    # Počkat na backend s retry logikou
    echo "⏳ Čekám na backend..."
    BACKEND_READY=false
    for i in {1..10}; do
        sleep 2
        if curl -s http://localhost:50000/api/health > /dev/null 2>&1; then
            BACKEND_READY=true
            break
        fi
        echo "   Pokus $i/10..."
    done
    
    if [ "$BACKEND_READY" = true ]; then
        echo "✅ Backend běží správně (PID: $BACKEND_PID)"
    else
        echo "⚠️  Backend se nespustil - zkontroluj logy: tail -f backend_server.log"
        echo "   Pokračuji se spuštěním frontendu..."
    fi
    
    # Spustit frontend (i když backend selhal)
    echo "🎨 Spouštím frontend na portu 4000..."
    cd frontend
    PORT=4000 npm start > ../frontend_server.log 2>&1 &
    FRONTEND_PID=$!
    cd ..
    
    # Počkat na frontend s retry logikou
    echo "⏳ Čekám na frontend..."
    FRONTEND_READY=false
    for i in {1..15}; do
        sleep 2
        if curl -s http://localhost:4000 > /dev/null 2>&1; then
            FRONTEND_READY=true
            break
        fi
        echo "   Pokus $i/15..."
    done
    
    if [ "$FRONTEND_READY" = true ]; then
        echo "✅ Frontend běží správně (PID: $FRONTEND_PID)"
    else
        echo "❌ Frontend se nespustil - zkontroluj logy: tail -f frontend_server.log"
        # Pokud ani frontend neběží, exit s chybou
        if [ "$BACKEND_READY" != true ]; then
            echo "❌ Ani backend ani frontend se nespustily"
            exit 1
        fi
    fi
    
    echo ""
    echo "🎉 Aplikace je spuštěna!"
    echo "🌐 Frontend: http://localhost:4000"
    echo "🔧 Backend: http://localhost:50000"
    echo ""
    echo "📝 Logy:"
    echo "   Backend:  tail -f backend_server.log"
    echo "   Frontend: tail -f frontend_server.log"
    echo ""
    echo "🔄 Backend PID: $BACKEND_PID"
    echo "🔄 Frontend PID: $FRONTEND_PID"
}

# Funkce pro status
check_status() {
    echo "📊 Kontroluji status aplikace..."
    
    # Backend check
    if curl -s http://localhost:50000/api/health > /dev/null; then
        BACKEND_PID=$(pgrep -f "python3 app.py" | head -1)
        echo "✅ Backend běží (PID: $BACKEND_PID)"
    else
        echo "❌ Backend neběží"
    fi
    
    # Frontend check
    if curl -s http://localhost:4000 > /dev/null; then
        FRONTEND_PID=$(pgrep -f "node.*react-scripts" | head -1)
        echo "✅ Frontend běží (PID: $FRONTEND_PID)"
    else
        echo "❌ Frontend neběží"
    fi
}

# Hlavní logika
case "$1" in
    start)
        start_app
        ;;
    stop)
        stop_processes
        ;;
    restart)
        echo "🔄 Volám robustní restart skript..."
        exec /Users/petrliesner/podcasts/restart.sh
        ;;
    status)
        check_status
        ;;
    *)
        echo "Použití: $0 {start|stop|restart|status}"
        echo ""
        echo "Příkazy:"
        echo "  start   - Spustí aplikaci"
        echo "  stop    - Zastaví aplikaci"
        echo "  restart - Restartuje aplikaci"
        echo "  status  - Zobrazí status aplikace"
        exit 1
        ;;
esac

