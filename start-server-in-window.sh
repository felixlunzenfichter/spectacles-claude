#!/bin/bash

# Switch to spectacles window and execute server start

osascript <<'EOF'
    tell application "Terminal"
        activate
        repeat with w from 1 to count of windows
            if name of window w contains "spectacles" then
                set index of window w to 1
            end if
        end repeat
    end tell

    delay 0.3

    tell application "System Events"
        tell process "Terminal"
            keystroke "c" using control down
            delay 0.5
            keystroke "./start-server-and-preview.sh"
            delay 0.2
            key code 36
        end tell
    end tell
EOF
