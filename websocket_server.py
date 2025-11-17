#!/usr/bin/env python3
"""
WebSocket server for Spectacles that monitors Claude Code conversations.
Sends latest assistant messages to connected Spectacles in real-time.
"""

import asyncio
import websockets
import datetime
import traceback
import json
import os
import aiohttp
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import ImageGrab

# Store connected clients
connected_clients = set()

# Store last sent message to avoid duplicates
last_sent_message = None

# Store sun times for color calculation
sun_times_data = None
location_data = None

def log(message):
    """Print a timestamped log message."""
    timestamp = datetime.datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}")

def capture_screenshot_metadata():
    """Capture screenshot and return only metadata."""
    log("📸 Capturing screenshot metadata...")

    screenshot = ImageGrab.grab()
    width, height = screenshot.size
    total_pixels = width * height
    pixels_per_packet = 10000
    total_packets = (total_pixels + pixels_per_packet - 1) // pixels_per_packet

    log(f"   Screen resolution: {width}x{height}")
    log(f"   Total pixels: {total_pixels:,}")
    log(f"   Packets needed: {total_packets:,} ({pixels_per_packet} pixels each)")

    metadata = {
        'type': 'screenshot_start',
        'width': width,
        'height': height,
        'total_pixels': total_pixels,
        'total_packets': total_packets,
        'pixels_per_packet': pixels_per_packet
    }

    return metadata, screenshot

def generate_screenshot_packets(screenshot, pixels_per_packet=100000):
    """Generator that yields screenshot packets."""
    width, height = screenshot.size
    screenshot = screenshot.convert('RGB')
    pixels = screenshot.load()

    pixel_buffer = []

    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            pixel_buffer.append([x, height - 1 - y, r, g, b])

            if len(pixel_buffer) >= pixels_per_packet:
                packet = {
                    'type': 'screenshot_packet',
                    'pixels': pixel_buffer
                }
                yield packet
                pixel_buffer = []

    if pixel_buffer:
        packet = {
            'type': 'screenshot_packet',
            'pixels': pixel_buffer
        }
        yield packet

def generate_delta_packets(prev_screenshot, new_screenshot, pixels_per_packet=100000):
    """Generator that yields only changed pixels."""
    width, height = new_screenshot.size
    prev_screenshot = prev_screenshot.convert('RGB')
    new_screenshot = new_screenshot.convert('RGB')
    prev_pixels = prev_screenshot.load()
    new_pixels = new_screenshot.load()

    pixel_buffer = []

    for y in range(height):
        for x in range(width):
            prev_r, prev_g, prev_b = prev_pixels[x, y]
            new_r, new_g, new_b = new_pixels[x, y]

            if prev_r != new_r or prev_g != new_g or prev_b != new_b:
                pixel_buffer.append([x, height - 1 - y, new_r, new_g, new_b])

                if len(pixel_buffer) >= pixels_per_packet:
                    packet = {
                        'type': 'screenshot_packet',
                        'pixels': pixel_buffer
                    }
                    yield packet
                    pixel_buffer = []

    if pixel_buffer:
        packet = {
            'type': 'screenshot_packet',
            'pixels': pixel_buffer
        }
        yield packet

async def fetch_location():
    """Fetch current location based on IP address."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('http://ip-api.com/json/') as response:
                data = await response.json()
                if data.get('status') == 'success':
                    return {
                        'city': data.get('city', 'Unknown'),
                        'country': data.get('country', 'Unknown'),
                        'lat': data.get('lat'),
                        'lon': data.get('lon'),
                        'timezone': data.get('timezone', 'Unknown')
                    }
    except Exception as e:
        log(f"❌ Error fetching location: {e}")
    return None

async def fetch_sun_times(lat, lon):
    """Fetch sunrise/sunset times from API."""
    try:
        url = f"https://api.sunrise-sunset.org/json?lat={lat}&lng={lon}&formatted=0"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                if data.get('status') == 'OK':
                    results = data.get('results', {})

                    # Convert UTC times to local datetime objects
                    def parse_time(utc_time_str):
                        try:
                            dt = datetime.datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
                            return dt.astimezone()
                        except:
                            return None

                    return {
                        'astronomical_dawn': parse_time(results.get('astronomical_twilight_begin', '')),
                        'nautical_dawn': parse_time(results.get('nautical_twilight_begin', '')),
                        'civil_dawn': parse_time(results.get('civil_twilight_begin', '')),
                        'sunrise': parse_time(results.get('sunrise', '')),
                        'solar_noon': parse_time(results.get('solar_noon', '')),
                        'sunset': parse_time(results.get('sunset', '')),
                        'civil_dusk': parse_time(results.get('civil_twilight_end', '')),
                        'nautical_dusk': parse_time(results.get('nautical_twilight_end', '')),
                        'astronomical_dusk': parse_time(results.get('astronomical_twilight_end', ''))
                    }
    except Exception as e:
        log(f"❌ Error fetching sun times: {e}")
    return None

def get_sun_phase_color(sun_times):
    """Determine current sun phase and return (color, phase_name)."""
    if not sun_times:
        return ((1.0, 0.0, 0.0, 1.0), "night")  # Default to night (red)

    now = datetime.datetime.now().astimezone()

    civil_dawn = sun_times['civil_dawn']
    sunrise = sun_times['sunrise']
    solar_noon = sun_times['solar_noon']
    sunset = sun_times['sunset']
    civil_dusk = sun_times['civil_dusk']

    if civil_dawn <= now < sunrise:
        # Dawn: yellow (100% red + 100% green)
        return ((1.0, 1.0, 0.0, 1.0), "dawn")
    elif sunrise <= now < solar_noon:
        # Morning: blue (100% blue)
        return ((0.0, 0.0, 1.0, 1.0), "morning")
    elif solar_noon <= now < sunset:
        # Afternoon: white (100% everything)
        return ((1.0, 1.0, 1.0, 1.0), "afternoon")
    elif sunset <= now < civil_dusk:
        # Dusk: orange (100% red + 50% green)
        return ((1.0, 0.5, 0.0, 1.0), "dusk")
    else:
        # Night: red (100% red)
        return ((1.0, 0.0, 0.0, 1.0), "night")

def extract_latest_event(file_path):
    """Extract the latest event from a Claude Code .jsonl file."""
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()

        # Get the last non-empty line
        for line in reversed(lines):
            line = line.strip()
            if line:
                # Parse the event
                event = json.loads(line)

                # Extract timestamp (just the time part)
                timestamp = event.get('timestamp', '')
                if timestamp:
                    # Extract HH:MM:SS from ISO timestamp
                    time_part = timestamp.split('T')[1].split('.')[0] if 'T' in timestamp else timestamp
                else:
                    time_part = '??:??:??'

                # Extract role from message
                if 'message' in event:
                    msg = event['message']
                    role = msg.get('role', 'unknown')

                    # Extract content
                    content_parts = []
                    if 'content' in msg:
                        content = msg['content']
                        if isinstance(content, str):
                            content_parts.append(content)
                        elif isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict):
                                    if item.get('type') == 'text':
                                        content_parts.append(item.get('text', ''))
                                    elif item.get('type') == 'tool_use':
                                        tool_name = item.get('name', 'unknown')
                                        tool_input = item.get('input', {})
                                        input_str = json.dumps(tool_input, indent=None)
                                        content_parts.append(f"[Tool: {tool_name}] {input_str}")
                                    elif item.get('type') == 'tool_result':
                                        result_content = item.get('content', '')
                                        content_parts.append(f"[Tool Result] {result_content}")

                    content_text = ' '.join(content_parts)

                    # Format: [timestamp] role: content
                    return f"[{time_part}] {role}: {content_text}"

                # If no message, just show event type
                return f"[{time_part}] {event.get('type', 'unknown')}"

        return None
    except Exception as e:
        log(f"❌ Error reading conversation file: {e}")
        return None

class ClaudeConversationHandler(FileSystemEventHandler):
    """Handles file system events for Claude Code conversation files."""

    def __init__(self, loop):
        self.loop = loop
        super().__init__()

    def on_modified(self, event):
        """Called when a file is modified."""
        if event.is_directory:
            return

        # Only process .jsonl files
        if not event.src_path.endswith('.jsonl'):
            return

        log(f"📝 Conversation file changed: {Path(event.src_path).name}")

        # Extract latest event
        message = extract_latest_event(event.src_path)

        if message:
            # Schedule sending the message to all clients
            asyncio.run_coroutine_threadsafe(
                broadcast_message(message),
                self.loop
            )

async def broadcast_message(message):
    """Send a message to all connected clients."""
    global last_sent_message

    # Avoid sending duplicate messages
    if message == last_sent_message:
        log("⏭️  Skipping duplicate message")
        return

    last_sent_message = message

    # Print FULL message being sent
    log("=" * 60)
    log("📤 FULL MESSAGE BEING SENT:")
    log("=" * 60)
    log(message)
    log("=" * 60)
    log(f"   Message length: {len(message)} characters")
    log(f"   Sending to {len(connected_clients)} client(s)")

    # Send to all connected clients
    if connected_clients:
        disconnected_clients = set()
        for client in connected_clients:
            try:
                await client.send(message)
                log(f"   ✅ Sent to {client.remote_address}")
            except Exception as e:
                log(f"   ❌ Failed to send to {client.remote_address}: {e}")
                disconnected_clients.add(client)

        # Remove disconnected clients
        for client in disconnected_clients:
            connected_clients.discard(client)

async def handle_client(websocket):
    """Handle a client connection."""
    global sun_times_data, location_data

    # Add client to set
    connected_clients.add(websocket)
    client_addr = websocket.remote_address
    log(f"✅ CLIENT CONNECTED: {client_addr}")
    log(f"   Total clients: {len(connected_clients)}")

    try:
        # Send welcome message
        welcome_msg = "Connected! Watching Claude Code conversations..."
        log(f"📤 SENDING to {client_addr}: '{welcome_msg}'")
        await websocket.send(welcome_msg)
        log(f"✅ SENT welcome message successfully")

        # Get screenshot and resize to Full HD (1920x1240)
        screenshot = ImageGrab.grab()
        original_size = screenshot.size
        screenshot = screenshot.resize((1920, 1240))
        width, height = screenshot.size
        log(f"📸 Screenshot: {original_size[0]}x{original_size[1]} → {width}x{height}")

        # Send color and phase based on sun position
        if sun_times_data and location_data:
            color, phase = get_sun_phase_color(sun_times_data)
            color_msg = f"COLOR:{color[0]},{color[1]},{color[2]},{color[3]}|PHASE:{phase}|WIDTH:{width}|HEIGHT:{height}"

            log(f"📤 Sending to {client_addr}: {phase} - {color} - {width}x{height}")
            await websocket.send(color_msg)
            log(f"✅ Color and dimensions sent successfully")

        # If we have a previous message, send it
        if last_sent_message:
            preview = last_sent_message[:80].replace('\n', ' ')
            log(f"📤 Sending last message to new client: {preview}...")
            await websocket.send(last_sent_message)

        # Send initial full screenshot
        log(f"📤 Sending initial screenshot...")
        log(f"   Screen resolution: {width}x{height}")

        packet_count = 0
        for packet in generate_screenshot_packets(screenshot):
            packet_json = json.dumps(packet)
            await websocket.send(packet_json)
            packet_count += 1

        log(f"✅ Initial screenshot sent ({packet_count} packets)")

        # Store as previous screenshot
        prev_screenshot = screenshot

        # Continuous delta updates loop
        log(f"🔄 Starting continuous delta updates (every 1 second)")
        while True:
            await asyncio.sleep(1.0)

            # Capture new screenshot
            new_screenshot = ImageGrab.grab()
            new_screenshot = new_screenshot.resize((1920, 1240))

            # Generate and send delta packets
            delta_count = 0
            total_changed_pixels = 0
            for packet in generate_delta_packets(prev_screenshot, new_screenshot):
                total_changed_pixels += len(packet['pixels'])
                packet_json = json.dumps(packet)
                await websocket.send(packet_json)
                delta_count += 1

            if total_changed_pixels > 0:
                log(f"📊 Delta update: {total_changed_pixels} pixels changed ({delta_count} packets)")

            # Update previous screenshot
            prev_screenshot = new_screenshot

    except websockets.exceptions.ConnectionClosed as e:
        log(f"🔌 CLIENT DISCONNECTED: {client_addr}")
        log(f"   Reason: {e}")
    except Exception as e:
        log(f"❌ ERROR with {client_addr}: {e}")
        log(f"   Traceback: {traceback.format_exc()}")
    finally:
        # Remove client from set
        connected_clients.discard(websocket)
        log(f"   Remaining clients: {len(connected_clients)}")

async def main():
    """Start the WebSocket server and file watcher."""
    global sun_times_data, location_data

    host = "0.0.0.0"  # Listen on all interfaces
    port = 8080

    log("=" * 60)
    log("🚀 STARTING WEBSOCKET SERVER FOR SPECTACLES")
    log("=" * 60)
    log(f"Host: {host}")
    log(f"Port: {port}")
    log(f"Local URL: ws://localhost:{port}")
    log(f"Network URL: ws://[YOUR_MAC_IP]:{port}")
    log("=" * 60)

    # Fetch and log location and sun times
    log("")
    log("☀️  Fetching location and sun times...")
    # Hardcoded to Vienna, 1st District (Innere Stadt)
    location = {
        'city': 'Vienna',
        'country': 'Austria',
        'lat': 48.2082,
        'lon': 16.3738,
        'timezone': 'Europe/Vienna'
    }
    if location:
        location_data = location  # Store globally
        log(f"📍 Location: {location['city']}, {location['country']}")
        log(f"   Coordinates: {location['lat']:.4f}, {location['lon']:.4f}")
        log(f"   Timezone: {location['timezone']}")

        sun_times = await fetch_sun_times(location['lat'], location['lon'])
        if sun_times:
            sun_times_data = sun_times  # Store globally
            log("")
            log("🌅 Sun Times for Today (local time):")
            log(f"   Astronomical Dawn: {sun_times['astronomical_dawn']}")
            log(f"   Nautical Dawn:     {sun_times['nautical_dawn']}")
            log(f"   Civil Dawn:        {sun_times['civil_dawn']}")
            log(f"   Sunrise:           {sun_times['sunrise']}")
            log(f"   Solar Noon:        {sun_times['solar_noon']}")
            log(f"   Sunset:            {sun_times['sunset']}")
            log(f"   Civil Dusk:        {sun_times['civil_dusk']}")
            log(f"   Nautical Dusk:     {sun_times['nautical_dusk']}")
            log(f"   Astronomical Dusk: {sun_times['astronomical_dusk']}")
        else:
            log("❌ Failed to fetch sun times")
    else:
        log("❌ Failed to fetch location")
    log("")
    log("=" * 60)

    # Set up file watcher for Claude Code conversations
    claude_projects_path = Path.home() / '.claude' / 'projects'

    if not claude_projects_path.exists():
        log(f"⚠️  WARNING: Claude Code projects directory not found: {claude_projects_path}")
        log(f"   Conversation monitoring will not work!")
    else:
        log(f"📁 Monitoring Claude Code conversations in:")
        log(f"   {claude_projects_path}")

        # Get the event loop
        loop = asyncio.get_event_loop()

        # Create and start the observer
        event_handler = ClaudeConversationHandler(loop)
        observer = Observer()
        observer.schedule(event_handler, str(claude_projects_path), recursive=True)
        observer.start()
        log(f"👁️  File watcher started successfully")

    log("=" * 60)
    log("⏳ Waiting for connections...")
    log("")

    try:
        async with websockets.serve(handle_client, host, port):
            await asyncio.Future()  # Run forever
    except Exception as e:
        log(f"❌ FATAL ERROR: Server failed to start: {e}")
        log(f"   Traceback: {traceback.format_exc()}")
    finally:
        if 'observer' in locals():
            observer.stop()
            observer.join()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("")
        log("🛑 SERVER STOPPED by user (Ctrl+C)")
    except Exception as e:
        log(f"❌ UNEXPECTED ERROR: {e}")
        log(f"   Traceback: {traceback.format_exc()}")
