# Deploy Skill

Deploy components of the Spectacles Claude project.

## Usage

```
/deploy [component]
```

## Components

- `/deploy` - Mac server + Lens instructions (default)
- `/deploy mac` - Just restart Mac server
- `/deploy lens` - Just print Lens instructions
- `/deploy emergency` - Full reset: relay + Mac + Lens

## Instructions

### For `mac`:

1. Print deploy timestamp: `Deploy @ YYYY-MM-DD HH:MM:SS`
2. Run: `./start-server-in-window.sh` (script sends Ctrl+C to stop any existing server, then starts fresh)
3. Report: `Mac server started`

### For `lens`:

Print:
```
Push Lens to Spectacles:
  1. Open Lens Studio
  2. Open project: lens/
  3. Select Spectacles device
  4. Push to Device (Cmd+Shift+P)
```

### For default (`/deploy`):

1. Run `mac` steps
2. Run `lens` steps
3. Run connection verification with retry (see below)

### For `emergency`:

Full system reset. Run in order:
1. Deploy relay: `deployctl deploy --project=spectacles-relay relay_server_deno.ts`
2. Run `mac` steps
3. Run `lens` steps
4. Run connection verification with retry (see below)

## Connection Verification with Auto-Retry

After deploying mac server and printing lens instructions, AUTOMATICALLY verify the relay connection. Do NOT ask the user - just do it.

### Get RELAY_URL from .env:

```bash
# Source the .env file to get RELAY_URL
source .env
echo "Using relay: $RELAY_URL"
```

### Verification Loop (max 3 attempts):

```bash
MAX_RETRIES=3
ATTEMPT=1

while [ $ATTEMPT -le $MAX_RETRIES ]; do
    echo "[Attempt $ATTEMPT/$MAX_RETRIES] Waiting 5 seconds for connection..."
    sleep 5

    # Check relay status
    STATUS=$(curl -s "${RELAY_URL}/status")

    # Parse JSON response
    SERVER_CONNECTED=$(echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(str(d.get('server',{}).get('connected',False)).lower())")
    CLIENT_CONNECTED=$(echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(str(d.get('client',{}).get('connected',False)).lower())")
    PAIRED=$(echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(str(d.get('paired',False)).lower())")

    echo "Relay status: server=$SERVER_CONNECTED, client=$CLIENT_CONNECTED, paired=$PAIRED"

    if [ "$SERVER_CONNECTED" = "true" ] && [ "$CLIENT_CONNECTED" = "true" ] && [ "$PAIRED" = "true" ]; then
        echo "SUCCESS: Both server and client connected and paired!"
        break
    fi

    if [ $ATTEMPT -lt $MAX_RETRIES ]; then
        echo "Not connected, retrying..."
        ./start-server-in-window.sh
        sleep 1
    fi

    ATTEMPT=$((ATTEMPT + 1))
done

if [ "$SERVER_CONNECTED" != "true" ] || [ "$CLIENT_CONNECTED" != "true" ] || [ "$PAIRED" != "true" ]; then
    echo "FAILED: Could not establish connection after $MAX_RETRIES attempts"
    echo "Final status: server=$SERVER_CONNECTED, client=$CLIENT_CONNECTED, paired=$PAIRED"
fi
```

### Output Format:

Success:
```
Deploy @ 2026-01-14 04:10:23
Mac server started
Push Lens to Spectacles:
  1. Open Lens Studio
  2. Open project: lens/
  3. Select Spectacles device
  4. Push to Device (Cmd+Shift+P)

[Attempt 1/3] Waiting 5 seconds for connection...
Relay status: server=true, client=true, paired=true
SUCCESS: Both server and client connected and paired!
```

Retry scenario:
```
Deploy @ 2026-01-14 04:10:23
Mac server started
Push Lens to Spectacles...

[Attempt 1/3] Waiting 5 seconds for connection...
Relay status: server=true, client=false, paired=false
Not connected, retrying...
Mac server started

[Attempt 2/3] Waiting 5 seconds for connection...
Relay status: server=true, client=true, paired=true
SUCCESS: Both server and client connected and paired!
```

Failure after max retries:
```
[Attempt 3/3] Waiting 5 seconds for connection...
Relay status: server=true, client=false, paired=false
FAILED: Could not establish connection after 3 attempts
Final status: server=true, client=false, paired=false
```

## Additional Verification (after connection confirmed)

Once connected, also check server.log for data flow:

```bash
# Check for screenshot streaming
grep "Sending JPEG" server.log | tail -3

# Check for git diff
grep -E "(Git diff sent|SENDING GIT DIFF)" server.log | tail -1

# Check for conversation flow
grep "Text message sent" server.log | tail -1
```

## Error Handling

- `deployctl` not installed: `deno install -Arf jsr:@deno/deployctl`
- `pkill` fails (no process): OK, continue
- Script fails: report error, continue
- curl fails: report network error
- JSON parsing fails: report and retry

## Success Output

```
Deploy Summary:
- Relay: [SUCCESS/FAILED/SKIPPED]
- Mac Server: [SUCCESS/FAILED]
- Lens: [INSTRUCTIONS PROVIDED/SKIPPED]
- Connection: [VERIFIED after X attempts / FAILED after 3 attempts]
```
