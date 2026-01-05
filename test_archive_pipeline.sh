#!/bin/bash
# Archive Pipeline Integration Test Runner
# Spustí kompletní test FDA → AAR → CB

set -e

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Archive Downloader + Compiler - Integration Test           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Kontrola API key
if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ ERROR: OPENAI_API_KEY not set"
    echo ""
    echo "Please export your OpenAI API key:"
    echo "  export OPENAI_API_KEY=sk-..."
    echo ""
    exit 1
fi

echo "✅ OPENAI_API_KEY found"
echo ""

# Kontrola FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  WARNING: FFmpeg not found"
    echo "   CB (Compilation Builder) will fail without FFmpeg"
    echo "   Install: brew install ffmpeg (macOS) or apt install ffmpeg (Linux)"
    echo ""
fi

# Kontrola working directory
if [ ! -f "backend/test_archive_pipeline.py" ]; then
    echo "❌ ERROR: Must run from project root (podcasts/)"
    echo "   Current dir: $(pwd)"
    exit 1
fi

echo "📁 Working directory: $(pwd)"
echo ""

# Spustit test
cd backend
echo "🚀 Running integration test..."
echo ""

python3 test_archive_pipeline.py

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  ✅ TEST PASSED                                             ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
else
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  ❌ TEST FAILED                                             ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
fi

exit $EXIT_CODE



