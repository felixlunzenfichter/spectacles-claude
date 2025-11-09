#!/bin/bash

echo "Previewing lens..."

osascript <<'EOF'
tell application "Lens Studio" to activate
delay 1
tell application "System Events"
    tell process "Lens Studio"
        tell window "lens* - Lens Studio v5.15.1.25102815"
            click button "Preview Lens"
            return "Success: Clicked Preview Lens button"
        end tell
    end tell
end tell
EOF
