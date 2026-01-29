#!/usr/bin/env python3
"""
WebSocket Streaming Test for Chat Application
Tests Phase 3: Real-time token-by-token streaming
"""

import asyncio
import json
import sys
from pathlib import Path

try:
    import websockets
    import requests
except ImportError:
    print("Installing required packages...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "requests"])
    import websockets
    import requests


BASE_URL = "http://localhost:8001"
WS_URL = "ws://localhost:8001"


async def test_websocket_streaming():
    """Test WebSocket connection and streaming"""

    print("=" * 60)
    print("Phase 3: WebSocket Streaming & LLM Integration Test")
    print("=" * 60)

    # Step 1: Login to get session cookie
    print("\n1. Logging in...")
    session = requests.Session()
    login_response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": "testuser", "password": "password123"}
    )

    if login_response.status_code != 200:
        print(f"❌ Login failed: {login_response.status_code}")
        return False

    print("✅ Login successful")
    session_cookie = session.cookies.get("session_token")
    print(f"   Session token: {session_cookie[:20]}...")

    # Step 2: Create a new conversation for testing
    print("\n2. Creating test conversation...")
    conv_response = session.post(
        f"{BASE_URL}/api/conversations",
        json={"title": "WebSocket Test", "llm_provider": "ollama"}
    )

    if conv_response.status_code != 200:
        print(f"❌ Conversation creation failed: {conv_response.status_code}")
        return False

    conversation = conv_response.json()
    conversation_id = conversation["id"]
    print(f"✅ Conversation created: {conversation_id}")

    # Step 3: Connect to WebSocket
    print("\n3. Connecting to WebSocket...")
    ws_uri = f"{WS_URL}/ws/{conversation_id}"

    try:
        # WebSocket connection with cookie authentication
        headers = {"Cookie": f"session_token={session_cookie}"}
        async with websockets.connect(
            ws_uri,
            additional_headers=headers
        ) as websocket:
            print("✅ WebSocket connected successfully")

            # Step 4: Send a test message
            print("\n4. Sending test message...")
            test_message = "What is 5 plus 3? Give me a very brief answer."

            await websocket.send(json.dumps({
                "type": "message",
                "content": test_message
            }))
            print(f"✅ Message sent: '{test_message}'")

            # Step 5: Receive streaming response
            print("\n5. Receiving streaming response:")
            print("   Assistant: ", end="", flush=True)

            token_count = 0
            full_response = ""
            message_id = None

            while True:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                    data = json.loads(response)

                    if data["type"] == "token":
                        token = data["token"]
                        print(token, end="", flush=True)
                        full_response += token
                        token_count += 1
                        if "message_id" in data:
                            message_id = data["message_id"]

                    elif data["type"] == "done":
                        print()  # New line after response
                        print(f"\n✅ Streaming complete")
                        print(f"   Tokens received: {token_count}")
                        print(f"   Message ID: {data.get('message_id', 'N/A')}")
                        print(f"   Total tokens: {data.get('tokens', 'N/A')}")
                        break

                    elif data["type"] == "error":
                        print(f"\n❌ Error: {data['error']}")
                        return False

                except asyncio.TimeoutError:
                    print("\n❌ Timeout waiting for response")
                    return False

            # Step 6: Verify messages in database
            print("\n6. Verifying messages in database...")
            conv_detail = session.get(f"{BASE_URL}/api/conversations/{conversation_id}")

            if conv_detail.status_code == 200:
                conv_data = conv_detail.json()
                messages = conv_data.get("messages", [])
                print(f"✅ Found {len(messages)} messages in database")

                if len(messages) >= 2:
                    user_msg = messages[-2]
                    assistant_msg = messages[-1]

                    print(f"   User message: '{user_msg['content'][:50]}...'")
                    print(f"   Assistant message: '{assistant_msg['content'][:50]}...'")

                    if user_msg["role"] == "user" and assistant_msg["role"] == "assistant":
                        print("✅ Messages saved correctly with proper roles")
                    else:
                        print("❌ Message roles incorrect")
                        return False
                else:
                    print("❌ Expected at least 2 messages")
                    return False

            # Step 7: Check if title was auto-generated
            print("\n7. Checking conversation title auto-generation...")
            conv_updated = session.get(f"{BASE_URL}/api/conversations/{conversation_id}")

            if conv_updated.status_code == 200:
                updated_conv = conv_updated.json()
                new_title = updated_conv.get("title", "")

                if new_title and new_title != "WebSocket Test":
                    print(f"✅ Title auto-generated: '{new_title}'")
                else:
                    print(f"   Title: '{new_title}' (may not have changed)")

            print("\n" + "=" * 60)
            print("✅ Phase 3 WebSocket Streaming Test PASSED")
            print("=" * 60)
            return True

    except websockets.exceptions.WebSocketException as e:
        print(f"\n❌ WebSocket error: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_websocket_streaming())
    sys.exit(0 if success else 1)
