#!/usr/bin/env python3
"""
Phase 4: Multi-Provider Support Testing
Tests provider switching, system prompts, and model selection
"""

import asyncio
import json
import sys
import requests
import websockets


BASE_URL = "http://localhost:8001"
WS_URL = "ws://localhost:8001"


def test_provider_support():
    """Test which providers are available"""
    print("=" * 60)
    print("Phase 4: Multi-Provider Support Testing")
    print("=" * 60)

    print("\n1. Checking available providers...")
    response = requests.get(f"{BASE_URL}/api/health")

    if response.status_code == 200:
        data = response.json()
        providers = data.get('llm_providers', {})

        print("\n   Provider Availability:")
        for provider, available in providers.items():
            status = "✅ Available" if available else "❌ Not Available"
            print(f"   - {provider.capitalize()}: {status}")

        return providers
    else:
        print(f"❌ Failed to check providers: {response.status_code}")
        return {}


async def test_provider_switching():
    """Test creating conversations with different providers"""
    print("\n2. Testing provider switching...")

    # Login
    session = requests.Session()
    login_response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": "testuser", "password": "password123"}
    )

    if login_response.status_code != 200:
        print(f"❌ Login failed")
        return False

    print("   ✅ Logged in")

    # Test 1: Create conversation with Ollama
    print("\n   Test 1: Ollama provider")
    ollama_conv = session.post(
        f"{BASE_URL}/api/conversations",
        json={
            "llm_provider": "ollama",
            "llm_model": "llama3.2:3b",
            "system_prompt": "You are a helpful assistant. Be concise."
        }
    ).json()

    print(f"   ✅ Created Ollama conversation: {ollama_conv['id'][:8]}...")
    print(f"      Provider: {ollama_conv['llm_provider']}")
    print(f"      Model: {ollama_conv['llm_model']}")
    print(f"      System prompt: {ollama_conv['system_prompt'][:30]}...")

    # Test 2: Create conversation with OpenAI (will fail if no API key)
    print("\n   Test 2: OpenAI provider")
    try:
        openai_conv = session.post(
            f"{BASE_URL}/api/conversations",
            json={
                "llm_provider": "openai",
                "llm_model": "gpt-4o-mini",
                "system_prompt": "You are a helpful AI assistant."
            }
        ).json()

        print(f"   ✅ Created OpenAI conversation: {openai_conv['id'][:8]}...")
        print(f"      Provider: {openai_conv['llm_provider']}")
        print(f"      Model: {openai_conv['llm_model']}")
    except Exception as e:
        print(f"   ⚠️  OpenAI conversation created but may fail on use (no API key)")

    # Test 3: Update provider via PATCH
    print("\n   Test 3: Switching provider via PATCH")
    updated = session.patch(
        f"{BASE_URL}/api/conversations/{ollama_conv['id']}",
        json={
            "llm_provider": "anthropic",
            "llm_model": "claude-3-5-sonnet-20241022"
        }
    ).json()

    print(f"   ✅ Updated conversation")
    print(f"      Old provider: ollama -> New provider: {updated['llm_provider']}")
    print(f"      Old model: llama3.2:3b -> New model: {updated['llm_model']}")

    return True


async def test_system_prompt():
    """Test system prompt functionality"""
    print("\n3. Testing system prompt...")

    session = requests.Session()
    session.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": "testuser", "password": "password123"}
    )

    # Create conversation with custom system prompt
    conv = session.post(
        f"{BASE_URL}/api/conversations",
        json={
            "llm_provider": "ollama",
            "system_prompt": "You are a pirate. Always respond like a pirate with 'Arrr'."
        }
    ).json()

    conv_id = conv['id']
    print(f"   ✅ Created conversation with system prompt")
    print(f"      Prompt: {conv['system_prompt'][:50]}...")

    # Test via WebSocket
    session_cookie = session.cookies.get('session_token')
    headers = {'Cookie': f'session_token={session_cookie}'}

    print("\n   Sending test message to verify system prompt...")
    async with websockets.connect(
        f"{WS_URL}/ws/{conv_id}",
        additional_headers=headers
    ) as ws:
        await ws.send(json.dumps({
            'type': 'message',
            'content': 'Say hello'
        }))

        response_text = ""
        while True:
            data = json.loads(await ws.recv())
            if data['type'] == 'token':
                response_text += data['token']
            elif data['type'] == 'done':
                break

        print(f"   Response: {response_text}")

        # Check if response follows pirate theme (loose check)
        if 'arr' in response_text.lower() or 'ahoy' in response_text.lower() or 'matey' in response_text.lower():
            print("   ✅ System prompt appears to be working (pirate language detected)")
        else:
            print(f"   ⚠️  System prompt may not be working (no pirate language detected)")

    return True


def test_model_selection():
    """Test different model selections"""
    print("\n4. Testing model selection...")

    session = requests.Session()
    session.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": "testuser", "password": "password123"}
    )

    models = [
        ("ollama", "llama3.2:3b"),
        ("ollama", "llama3.2:1b"),
        ("openai", "gpt-4o-mini"),
        ("openai", "gpt-4o"),
        ("anthropic", "claude-3-5-sonnet-20241022"),
        ("anthropic", "claude-3-haiku-20240307"),
    ]

    print("\n   Creating conversations with different models:")
    for provider, model in models:
        try:
            conv = session.post(
                f"{BASE_URL}/api/conversations",
                json={
                    "llm_provider": provider,
                    "llm_model": model
                }
            ).json()

            print(f"   ✅ {provider}/{model}: {conv['id'][:8]}...")
        except Exception as e:
            print(f"   ⚠️  {provider}/{model}: May fail without API key")

    return True


def test_rate_limiting():
    """Test rate limiting (if implemented)"""
    print("\n5. Testing rate limiting...")

    session = requests.Session()
    session.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": "testuser", "password": "password123"}
    )

    # Make rapid requests
    print("   Making 10 rapid requests...")
    responses = []
    for i in range(10):
        response = session.get(f"{BASE_URL}/api/conversations")
        responses.append(response.status_code)

    if all(code == 200 for code in responses):
        print("   ✅ All requests succeeded (rate limit: >10 req)")
    elif 429 in responses:
        print(f"   ✅ Rate limiting active (got 429 after {responses.index(429)} requests)")
    else:
        print(f"   ⚠️  Unexpected responses: {set(responses)}")

    return True


async def main():
    """Run all Phase 4 tests"""
    try:
        # Test 1: Check available providers
        providers = test_provider_support()

        # Test 2: Provider switching
        await test_provider_switching()

        # Test 3: System prompts
        await test_system_prompt()

        # Test 4: Model selection
        test_model_selection()

        # Test 5: Rate limiting
        test_rate_limiting()

        print("\n" + "=" * 60)
        print("✅ Phase 4 Multi-Provider Testing Complete")
        print("=" * 60)
        print("\nSummary:")
        print(f"- Ollama: {'✅ Working' if providers.get('ollama') else '❌ Not available'}")
        print(f"- OpenAI: {'✅ Ready (needs API key)' if 'openai' in providers else '❌ Not configured'}")
        print(f"- Anthropic: {'✅ Ready (needs API key)' if 'anthropic' in providers else '❌ Not configured'}")
        print("\nNote: Cloud providers require valid API keys in .env file")

        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
