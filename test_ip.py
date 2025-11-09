#!/usr/bin/env python3
import asyncio
import websockets

async def test():
    uri = "ws://172.20.10.3:8080"
    print(f"🔗 Testing connection to {uri}...")
    try:
        async with websockets.connect(uri) as ws:
            print("✅ Connected successfully!")
            msg = await websocket.recv()
            print(f"📥 Received: '{msg}'")
    except Exception as e:
        print(f"❌ Failed: {e}")

asyncio.run(test())
