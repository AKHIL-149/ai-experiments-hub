#!/bin/bash

# Voice Assistant - Quick Test Setup Script
# This script helps you quickly set up and test the voice assistant

set -e

echo "🎤 Voice Assistant - Test Setup"
echo "================================"
echo ""

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    echo "❌ Error: Run this script from the 08-voice-assistant directory"
    exit 1
fi

# Check Node.js
echo "1️⃣ Checking Node.js installation..."
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed"
    echo "   Install from: https://nodejs.org/"
    exit 1
fi

NODE_VERSION=$(node --version)
echo "   ✓ Node.js $NODE_VERSION installed"

# Check npm
if ! command -v npm &> /dev/null; then
    echo "❌ npm is not installed"
    exit 1
fi

NPM_VERSION=$(npm --version)
echo "   ✓ npm $NPM_VERSION installed"
echo ""

# Check if dependencies are installed
echo "2️⃣ Checking dependencies..."
if [ ! -d "node_modules" ]; then
    echo "   📦 Installing dependencies..."
    npm install
    echo "   ✓ Dependencies installed"
else
    echo "   ✓ Dependencies already installed"
fi
echo ""

# Check .env file
echo "3️⃣ Checking configuration..."
if [ ! -f ".env" ]; then
    echo "   ⚠️  .env file not found, creating from template..."
    cp .env.example .env
    echo "   ✓ Created .env file"
    echo ""
    echo "   ⚠️  IMPORTANT: Edit .env and add your OpenAI API key:"
    echo "      OPENAI_API_KEY=sk-your-actual-key-here"
    echo ""
    echo "   Get your API key from: https://platform.openai.com/api-keys"
    echo ""
    read -p "   Press Enter after you've added your API key..."
else
    # Check if API key is set
    if grep -q "your_openai_api_key_here" .env; then
        echo "   ⚠️  OpenAI API key not configured"
        echo ""
        echo "   Edit .env and replace:"
        echo "      OPENAI_API_KEY=your_openai_api_key_here"
        echo "   with:"
        echo "      OPENAI_API_KEY=sk-your-actual-key-here"
        echo ""
        read -p "   Press Enter after you've added your API key..."
    else
        echo "   ✓ Configuration file exists"
    fi
fi
echo ""

# Check data directories
echo "4️⃣ Checking data directories..."
mkdir -p data/audio-cache
mkdir -p data/conversations
echo "   ✓ Data directories ready"
echo ""

# Start server check
echo "5️⃣ Testing server startup..."
echo "   Starting server (this may take a moment)..."
echo ""

# Try to start the server in background
node server.js &
SERVER_PID=$!

# Wait for server to start
sleep 3

# Check if server is running
if kill -0 $SERVER_PID 2>/dev/null; then
    echo "   ✓ Server started successfully!"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✅ Setup Complete!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "🌐 Open in browser:"
    echo "   http://localhost:3000"
    echo ""
    echo "📚 Testing guide:"
    echo "   See TESTING.md for comprehensive test scenarios"
    echo ""
    echo "🎤 Quick Test:"
    echo "   1. Click 'Push to Talk' button"
    echo "   2. Say: 'What time is it?'"
    echo "   3. Release button"
    echo "   4. Verify response!"
    echo ""
    echo "⚙️  Advanced Features:"
    echo "   • Hands-free mode: Enable in settings"
    echo "   • Voice commands: Say 'help' for list"
    echo "   • Conversations: Press Ctrl+H"
    echo ""
    echo "Press Ctrl+C to stop the server"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Wait for Ctrl+C
    wait $SERVER_PID
else
    echo "   ❌ Server failed to start"
    echo ""
    echo "   Check for errors above and verify:"
    echo "   • OpenAI API key is valid"
    echo "   • Port 3000 is not in use"
    echo "   • All dependencies are installed"
    echo ""
    echo "   Run manually to see errors:"
    echo "   npm start"
    exit 1
fi
