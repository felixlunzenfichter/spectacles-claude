#!/bin/bash

echo "Previewing lens..."

osascript <<'EOF'
tell application "Lens Studio" to activate
delay 1
tell application "System Events"
    tell process "Lens Studio"
        tell window 1
            click button "Preview Lens"
            return "Success: Clicked Preview Lens button"
        end tell
    end tell
end tell
EOF
