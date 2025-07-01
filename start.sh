#!/bin/bash

# 🎵 AI Voice Block Combiner - Start Script

echo "🎵 AI Voice Block Combiner"
echo "========================="
echo ""

# Zkontroluje, zda existují potřebné složky
if [ ! -d "backend" ] || [ ! -d "frontend" ]; then
    echo "❌ Chyba: Složky 'backend' nebo 'frontend' neexistují!"
    echo "   Ujistěte se, že jste ve správném adresáři."
    exit 1
fi

# Funkce pro spuštění backendu
start_backend() {
    echo "🐍 Spouštím backend server..."
    cd backend
    
    # Zkontroluje Python dependencies
    if [ ! -f "requirements.txt" ]; then
        echo "❌ Soubor requirements.txt nebyl nalezen!"
        exit 1
    fi
    
    # Spustí backend
    python app.py &
    BACKEND_PID=$!
    echo "✅ Backend server spuštěn (PID: $BACKEND_PID)"
    cd ..
}

# Funkce pro spuštění frontendu
start_frontend() {
    echo "⚛️  Spouštím frontend server..."
    cd frontend
    
    # Zkontroluje Node.js dependencies
    if [ ! -d "node_modules" ]; then
        echo "📦 Instaluji Node.js dependencies..."
        npm install
    fi
    
    # Spustí frontend
    npm start &
    FRONTEND_PID=$!
    echo "✅ Frontend server spuštěn (PID: $FRONTEND_PID)"
    cd ..
}

# Spustí oba servery
start_backend
sleep 2
start_frontend

echo ""
echo "🌐 Aplikace je spuštěna!"
echo "   Frontend: http://localhost:3000"
echo "   Backend:  http://localhost:5000"
echo ""
echo "⚡ Pro zastavení aplikace stiskněte Ctrl+C"

# Čeká na ukončení
wait 