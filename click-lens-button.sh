#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_PATH="$SCRIPT_DIR/lens/lens.esproj"

echo "Opening project and previewing lens..."

open "$PROJECT_PATH"

osascript <<'EOF'
tell application "Lens Studio" to activate
delay 3

tell application "System Events"
    tell process "Lens Studio"
        -- Loop while we have more than 1 window
        repeat 30 times
            delay 1

            set windowCount to count of windows
            log "Window count: " & windowCount

            -- If only 1 window, we're done!
            if windowCount ≤ 1 then
                log "SUCCESS: Only 1 window remains"
                exit repeat
            end if

            -- Process windows (skip the main project window)
            repeat with w from 1 to windowCount
                try
                    set wName to name of window w
                    log "  Checking window " & w & ": " & wName

                    -- Skip the main project window (be VERY specific)
                    if wName contains "Lens Studio v" and wName contains "Project" then
                        log "    -> Skipping main project window"
                    else
                        -- This is NOT the main window, process it
                        log "    -> Processing (not main window)"

                        -- Bring this window to foreground
                        activate
                        tell window w
                            perform action "AXRaise"
                        end tell
                        delay 0.5

                        -- Handle specific cases
                        if wName is "Home" then
                            -- Home window: button 2 is the close button
                            log "    -> Closing Home window (button 2)"
                            click button 2 of window w
                            delay 1
                            exit repeat

                        else if wName is "Report an Issue" then
                            -- Report an Issue: click Cancel button
                            log "    -> Looking for Cancel in Report an Issue"
                            set allElements to entire contents of window w
                            repeat with elem in allElements
                                if class of elem is button then
                                    if name of elem is "Cancel" then
                                        log "    -> Clicking Cancel"
                                        click elem
                                        delay 1
                                        exit repeat
                                    end if
                                end if
                            end repeat
                            exit repeat

                        else
                            -- Any other dialog: try Don't Save, Yes, OK, Cancel
                            log "    -> Looking for dialog buttons"
                            set buttonClicked to false
                            set allElements to entire contents of window w
                            repeat with elem in allElements
                                if class of elem is button then
                                    try
                                        set btnName to name of elem

                                        if btnName is "Don't Save" then
                                            log "    -> Clicking Don't Save"
                                            click elem
                                            set buttonClicked to true
                                            exit repeat
                                        else if btnName is "Yes" then
                                            log "    -> Clicking Yes"
                                            click elem
                                            set buttonClicked to true
                                            exit repeat
                                        else if btnName is "OK" then
                                            log "    -> Clicking OK"
                                            click elem
                                            set buttonClicked to true
                                            exit repeat
                                        else if btnName is "Cancel" then
                                            log "    -> Clicking Cancel"
                                            click elem
                                            set buttonClicked to true
                                            exit repeat
                                        end if
                                    end try
                                end if
                            end repeat

                            if buttonClicked then
                                delay 1
                                exit repeat
                            end if
                        end if
                    end if
                end try
            end repeat
        end repeat

        -- After cleanup, try to click Preview Lens
        set finalWindowCount to count of windows
        log "Final window count: " & finalWindowCount

        if finalWindowCount = 1 then
            log "Looking for Preview Lens button..."
            delay 1

            -- Focus the remaining window
            tell window 1
                perform action "AXRaise"
            end tell

            -- Look for Preview Lens button
            try
                click button "Preview Lens" of window 1
                log "SUCCESS: Clicked Preview Lens!"
                return "Success"
            on error
                -- Search through all buttons
                set allElements to entire contents of window 1
                repeat with elem in allElements
                    if class of elem is button then
                        try
                            if name of elem contains "Preview" then
                                click elem
                                log "SUCCESS: Clicked Preview button!"
                                return "Success"
                            end if
                        end try
                    end if
                end repeat
                log "Could not find Preview Lens button"
            end try
        else
            log "Still have " & finalWindowCount & " windows"
        end if
    end tell
end tell
EOF