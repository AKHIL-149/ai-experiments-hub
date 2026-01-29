#!/bin/bash
# Stable Diffusion WebUI Installation Script
# This installs Stable Diffusion for local image generation

set -e

echo "======================================"
echo "Stable Diffusion WebUI Installer"
echo "======================================"
echo ""

# Check if already installed
if [ -d "$HOME/stable-diffusion-webui" ]; then
    echo "⚠️  Stable Diffusion WebUI already exists at $HOME/stable-diffusion-webui"
    read -p "Do you want to reinstall? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Skipping installation. Starting existing installation..."
        cd "$HOME/stable-diffusion-webui"
        ./webui.sh --api --listen
        exit 0
    fi
    rm -rf "$HOME/stable-diffusion-webui"
fi

# Installation directory
INSTALL_DIR="$HOME/stable-diffusion-webui"
echo "📁 Installing to: $INSTALL_DIR"
echo ""

# Step 1: Clone repository
echo "Step 1/3: Cloning Stable Diffusion WebUI repository..."
cd "$HOME"
git clone https://github.com/AUTOMATIC1111/stable-diffusion-webui.git
echo "✅ Repository cloned"
echo ""

# Step 2: Download recommended model
echo "Step 2/3: Model Information"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Recommended models:"
echo ""
echo "1. Stable Diffusion 1.5 (default, ~4GB)"
echo "   https://huggingface.co/runwayml/stable-diffusion-v1-5"
echo ""
echo "2. Stable Diffusion XL (~6.9GB, higher quality)"
echo "   https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0"
echo ""
echo "3. Realistic Vision (~2GB, photorealistic)"
echo "   https://civitai.com/models/4201/realistic-vision"
echo ""
echo "The WebUI will download Stable Diffusion 1.5 automatically"
echo "on first run if no model is present."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Step 3: Start WebUI
echo "Step 3/3: Starting Stable Diffusion WebUI..."
echo ""
echo "⏳ First run will take 10-20 minutes (downloads dependencies + model)"
echo "   Subsequent runs take ~30 seconds"
echo ""
echo "Server will be available at: http://127.0.0.1:7860"
echo "API will be available at: http://127.0.0.1:7860/docs"
echo ""
echo "Press Ctrl+C to stop the server when needed."
echo ""
echo "Starting in 3 seconds..."
sleep 3

cd "$INSTALL_DIR"
./webui.sh --api --listen

# Note: --api enables the API for our chat app
# Note: --listen allows connections from other devices (optional)
