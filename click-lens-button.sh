#!/bin/bash

echo "Previewing lens..."

osascript <<'EOF'
tell application "Lens Studio" to activate
delay 1
tell application "System Events"
    tell process "Lens Studio"
        repeat with w from 1 to count of windows
            if name of window w contains "lens" then
                tell window w
                    click button "Preview Lens"
                    return "Success: Clicked Preview Lens button"
                end tell
                exit repeat
            end if
        end repeat
    end tell
end tell
EOF
