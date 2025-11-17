#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_PATH="$SCRIPT_DIR/lens/lens.esproj"

echo "Opening project and previewing lens..."

open "$PROJECT_PATH"

osascript <<'EOF'
tell application "Lens Studio" to activate
delay 5
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
