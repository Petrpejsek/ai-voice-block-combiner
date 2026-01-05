#!/bin/bash

# 🚀 Spolehlivý start skript pro podcast aplikaci
# Deleguje na robustní restart.sh skript

echo "🚀 Spouštím podcast aplikaci (pomocí restart.sh)..."
echo ""

# Ensure necessary folders exist
mkdir -p uploads output images projects

# Call the robust restart script
exec /Users/petrliesner/podcasts/restart.sh 