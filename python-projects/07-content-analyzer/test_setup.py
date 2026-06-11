#!/usr/bin/env python3
"""Quick test script to verify the setup."""
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.image_processor import ImageProcessor
from src.core.vision_client import VisionClient

print("✅ Imports successful")

# Test image processor
print("\n🔧 Testing ImageProcessor...")
processor = ImageProcessor()
print("   ✅ ImageProcessor initialized")

# Test downloading a sample image
try:
    print("   📥 Downloading sample image from URL...")
    image = processor.download_from_url("https://picsum.photos/200/200")
    print(f"   ✅ Image downloaded: {image.format} | {image.size}")

    # Get metadata
    metadata = processor.extract_metadata(image)
    print(f"   📊 Metadata: {metadata['dimensions']} | {metadata['size_mb']} MB")
except Exception as e:
    print(f"   ❌ Error downloading image: {e}")

# Test vision client initialization
print("\n🤖 Testing VisionClient...")
try:
    client = VisionClient(backend="ollama")
    print(f"   ✅ VisionClient initialized (backend: ollama, model: {client.model})")
except Exception as e:
    print(f"   ❌ Error initializing VisionClient: {e}")

# Test Ollama API connectivity
print("\n🌐 Testing Ollama API connectivity...")
try:
    import requests
    response = requests.get("http://localhost:11434/api/tags", timeout=5)
    if response.status_code == 200:
        data = response.json()
        models = [m['name'] for m in data.get('models', [])]
        print(f"   ✅ Ollama API accessible")
        print(f"   📦 Available models: {', '.join(models)}")

        # Check for LLaVA
        llava_models = [m for m in models if 'llava' in m.lower()]
        if llava_models:
            print(f"   ✅ LLaVA model found: {', '.join(llava_models)}")
        else:
            print(f"   ⚠️  LLaVA model not found")
            print(f"   💡 Install with: ollama pull llava")
    else:
        print(f"   ❌ Ollama API returned status {response.status_code}")
except Exception as e:
    print(f"   ❌ Cannot connect to Ollama API: {e}")
    print(f"   💡 Make sure Ollama is running: ollama serve")

print("\n" + "="*60)
print("Setup test complete!")
print("="*60)
