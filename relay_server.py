"""
IP Discovery Relay Server for Spectacles-Claude

A lightweight FastAPI server that enables Spectacles devices to discover
Mac servers on the local network without hardcoding IP addresses.

RUNNING LOCALLY:
    pip install fastapi uvicorn
    uvicorn relay_server:app --host 0.0.0.0 --port 8000

DEPLOYING TO RAILWAY:
    1. Create a new project on railway.app
    2. Connect your GitHub repo
    3. Railway auto-detects Python, add these files:

       requirements.txt:
           fastapi
           uvicorn

       Procfile:
           web: uvicorn relay_server:app --host 0.0.0.0 --port $PORT

    4. Deploy! Railway provides a public URL like: your-app.up.railway.app

DEPLOYING TO FLY.IO:
    1. Install flyctl: brew install flyctl
    2. Run: fly launch
    3. Create fly.toml with:

       [build]
         builder = "paketobuildpacks/builder:base"

       [env]
         PORT = "8080"

       [http_service]
         internal_port = 8080
         force_https = true

    4. Run: fly deploy
    5. Your URL: your-app.fly.dev

USAGE:
    Mac server registers itself:
        POST /register
        {"device_secret": "felix-macbook", "ip": "192.168.1.100", "port": 8080}

    Spectacles discovers the server:
        GET /discover?device_secret=felix-macbook
        Returns: {"device_secret": "felix-macbook", "ip": "192.168.1.100", "port": 8080, "ws_url": "ws://192.168.1.100:8080"}

    Or get any available server:
        GET /discover
        Returns the most recently registered server
"""

import time
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Configuration
REGISTRATION_TTL_SECONDS = 60  # Registrations expire after 60 seconds

# In-memory storage: device_secret -> {ip, port, timestamp}
registrations: dict[str, dict] = {}

app = FastAPI(
    title="Spectacles IP Discovery Relay",
    description="Enables Spectacles devices to discover Mac servers dynamically",
    version="1.0.0"
)

# CORS - allow all origins for Spectacles/browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RegistrationRequest(BaseModel):
    device_secret: str
    ip: str
    port: int = 8080


class RegistrationResponse(BaseModel):
    device_secret: str
    ip: str
    port: int
    ws_url: str
    expires_in: int


@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers and monitoring."""
    return {"status": "healthy", "timestamp": int(time.time())}


@app.post("/register", response_model=RegistrationResponse)
async def register_server(request: RegistrationRequest):
    """
    Register a Mac server's IP address for discovery.

    The registration expires after 60 seconds, so the Mac server
    should send a heartbeat (re-register) every 30-45 seconds.
    """
    now = int(time.time())

    registrations[request.device_secret] = {
        "ip": request.ip,
        "port": request.port,
        "timestamp": now
    }

    return RegistrationResponse(
        device_secret=request.device_secret,
        ip=request.ip,
        port=request.port,
        ws_url=f"ws://{request.ip}:{request.port}",
        expires_in=REGISTRATION_TTL_SECONDS
    )


@app.get("/discover", response_model=RegistrationResponse)
async def discover_server(device_secret: Optional[str] = None):
    """
    Discover a registered Mac server.

    If device_secret is provided, returns that specific server.
    Otherwise, returns the most recently registered server.

    Returns 404 if no valid (non-expired) registration exists.
    """
    now = int(time.time())

    # Clean up expired registrations
    expired = [
        ds for ds, data in registrations.items()
        if now - data["timestamp"] > REGISTRATION_TTL_SECONDS
    ]
    for ds in expired:
        del registrations[ds]

    if not registrations:
        raise HTTPException(
            status_code=404,
            detail="No servers registered. Start the Mac server first."
        )

    # Find the requested or most recent registration
    if device_secret:
        if device_secret not in registrations:
            raise HTTPException(
                status_code=404,
                detail=f"Server '{device_secret}' not found or registration expired."
            )
        data = registrations[device_secret]
        selected_device_secret = device_secret
    else:
        # Return most recently registered
        selected_device_secret = max(
            registrations.keys(),
            key=lambda ds: registrations[ds]["timestamp"]
        )
        data = registrations[selected_device_secret]

    expires_in = REGISTRATION_TTL_SECONDS - (now - data["timestamp"])

    return RegistrationResponse(
        device_secret=selected_device_secret,
        ip=data["ip"],
        port=data["port"],
        ws_url=f"ws://{data['ip']}:{data['port']}",
        expires_in=expires_in
    )


@app.get("/servers")
async def list_servers():
    """List all currently registered servers (for debugging)."""
    now = int(time.time())

    active = {}
    for device_secret, data in registrations.items():
        age = now - data["timestamp"]
        if age <= REGISTRATION_TTL_SECONDS:
            active[device_secret] = {
                "ip": data["ip"],
                "port": data["port"],
                "ws_url": f"ws://{data['ip']}:{data['port']}",
                "expires_in": REGISTRATION_TTL_SECONDS - age
            }

    return {"servers": active, "count": len(active)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
