#!/bin/bash

cat <<'EOF'
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   MULTI-AGENT TASK ORCHESTRATOR - QUICK START              ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

Starting demo mode with minimal dependencies...

EOF

echo ""
echo "📍 Current directory: $(pwd)"
echo ""

# Step 1: Check if .env exists
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "✓ .env created"
    echo ""
    echo "⚠️  IMPORTANT: You need to add your API keys to .env"
    echo "   Edit .env and add:"
    echo "   - OPENAI_API_KEY=sk-your-key-here"
    echo "   OR"
    echo "   - ANTHROPIC_API_KEY=sk-ant-your-key-here"
    echo ""
    read -p "Press Enter after you've added your API key..."
else
    echo "✓ .env file exists"
fi

echo ""
echo "🔑 Checking API keys..."
if grep -q "sk-" .env; then
    echo "✓ API key found in .env"
else
    echo "⚠️  No API key found. The server will start but agent execution will fail."
    echo "   Add OPENAI_API_KEY or ANTHROPIC_API_KEY to .env"
fi

echo ""
echo "🐍 Checking Python dependencies..."
python3 -c "import fastapi" 2>/dev/null && echo "✓ FastAPI installed" || {
    echo "⚠️  FastAPI not found. Installing required packages..."
    pip install fastapi uvicorn --quiet
}

echo ""
echo "🚀 Starting minimal server on http://localhost:8001..."
echo ""
echo "   Once server starts, you can:"
echo "   • Open http://localhost:8001 in your browser"
echo "   • View API docs at http://localhost:8001/docs"
echo "   • View dashboard at http://localhost:8001/dashboard"
echo ""
echo "   Press Ctrl+C to stop the server"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Start the server
python3 server_minimal.py
