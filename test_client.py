#!/usr/bin/env python3
"""
Simple WebSocket test client to verify server is working.
Connects, sends a message, receives acknowledgment.
"""

import asyncio
import websockets

async def test_connection():
    uri = "ws://localhost:8080"

    print("🔗 Connecting to server...")
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected successfully!")

            # Receive welcome message
            welcome = await websocket.recv()
            print(f"📥 Received welcome: '{welcome}'")

            # Send a test message
            test_message = "Hello from test client!"
            print(f"📤 Sending: '{test_message}'")
            await websocket.send(test_message)

            # Receive acknowledgment
            response = await websocket.recv()
            print(f"📥 Received acknowledgment: '{response}'")

            # Wait for periodic messages
            print("\n⏳ Waiting for periodic messages (15 seconds)...")
            for i in range(5):
                message = await websocket.recv()
                print(f"📥 Received periodic message: '{message}'")

            print("\n✅ TEST SUCCESSFUL! Server is working correctly.")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_connection())
