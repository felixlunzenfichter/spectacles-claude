#!/usr/bin/env python3
"""
Simple WebSocket server for testing Spectacles connection.
Sends text messages to connected clients.
"""

import asyncio
import websockets
import datetime
import traceback

# Store connected clients
connected_clients = set()

def log(message):
    """Print a timestamped log message."""
    timestamp = datetime.datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}")

async def handle_client(websocket):
    """Handle a client connection."""
    # Add client to set
    connected_clients.add(websocket)
    client_addr = websocket.remote_address
    log(f"✅ CLIENT CONNECTED: {client_addr}")
    log(f"   Total clients: {len(connected_clients)}")

    try:
        # Send welcome message
        welcome_msg = "Hello from Mac server!"
        log(f"📤 SENDING to {client_addr}: '{welcome_msg}'")
        await websocket.send(welcome_msg)
        log(f"✅ SENT welcome message successfully")

        # Send periodic messages
        message_count = 1
        async def send_periodic_messages():
            nonlocal message_count
            while True:
                await asyncio.sleep(3)  # Send message every 3 seconds
                try:
                    message = f"Message #{message_count}\nTime: {datetime.datetime.now().strftime('%H:%M:%S')}"
                    log(f"📤 SENDING periodic message #{message_count} to {client_addr}")
                    await websocket.send(message)
                    log(f"✅ SENT: '{message.replace(chr(10), ' | ')}'")
                    message_count += 1
                except Exception as e:
                    log(f"❌ ERROR sending periodic message: {e}")
                    break

        # Start periodic message sender
        log(f"🔄 Starting periodic message sender for {client_addr}")
        periodic_task = asyncio.create_task(send_periodic_messages())

        # Listen for messages from client
        log(f"👂 Listening for messages from {client_addr}")
        async for message in websocket:
            log(f"📥 RECEIVED from {client_addr}: '{message}'")
            # Echo back
            response = f"Server received: {message}"
            log(f"📤 SENDING response: '{response}'")
            await websocket.send(response)
            log(f"✅ Response sent successfully")

    except websockets.exceptions.ConnectionClosed as e:
        log(f"🔌 CLIENT DISCONNECTED: {client_addr}")
        log(f"   Reason: {e}")
    except Exception as e:
        log(f"❌ ERROR with {client_addr}: {e}")
        log(f"   Traceback: {traceback.format_exc()}")
    finally:
        # Remove client from set
        connected_clients.discard(websocket)
        if 'periodic_task' in locals():
            periodic_task.cancel()
            log(f"🛑 Stopped periodic sender for {client_addr}")
        log(f"   Remaining clients: {len(connected_clients)}")

async def main():
    """Start the WebSocket server."""
    host = "0.0.0.0"  # Listen on all interfaces
    port = 8080

    log("=" * 60)
    log("🚀 STARTING WEBSOCKET SERVER")
    log("=" * 60)
    log(f"Host: {host}")
    log(f"Port: {port}")
    log(f"Local URL: ws://localhost:{port}")
    log(f"Network URL: ws://[YOUR_MAC_IP]:{port}")
    log("=" * 60)
    log("⏳ Waiting for connections...")
    log("")

    try:
        async with websockets.serve(handle_client, host, port):
            await asyncio.Future()  # Run forever
    except Exception as e:
        log(f"❌ FATAL ERROR: Server failed to start: {e}")
        log(f"   Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("")
        log("🛑 SERVER STOPPED by user (Ctrl+C)")
    except Exception as e:
        log(f"❌ UNEXPECTED ERROR: {e}")
        log(f"   Traceback: {traceback.format_exc()}")
