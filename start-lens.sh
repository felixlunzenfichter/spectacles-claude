#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_PATH="$SCRIPT_DIR/lens/lens.esproj"

echo "Starting Lens Studio..."
echo "================================"

# Quit Lens Studio first if it's running
echo "Quitting any existing Lens Studio instance..."
osascript -e 'tell application "Lens Studio" to quit' 2>/dev/null || true

# Wait a moment for Lens Studio to fully quit
sleep 1

echo "Opening project: $PROJECT_PATH"
echo ""

# Open the project
open "$PROJECT_PATH"

# Wait for Lens Studio to fully open
echo "Waiting 5 seconds for Lens Studio to open..."
sleep 5

echo ""
echo "Dismissing dialogs..."
echo "================================"

osascript <<'EOF'
tell application "Lens Studio" to activate
delay 2

tell application "System Events"
    tell process "Lens Studio"
        -- First dismiss all dialogs
        log "Checking for dialogs to dismiss..."

        set continueLoop to true

        repeat while continueLoop
            set continueLoop to false  -- Will be set to true if we find any dialog
            set windowCount to count of windows

            repeat with w from 1 to windowCount
                    try
                        set wName to name of window w
                    on error
                        set wName to ""
                    end try

                    -- Process dialogs (empty name or specific dialog windows)
                    if wName is "" or wName contains "Report an Issue" then
                        -- Handle Report an Issue dialog directly
                        if wName contains "Report an Issue" then
                            log "Found 'Report an Issue' dialog at window " & w

                            -- Bring window to foreground
                            tell window w
                                perform action "AXRaise"
                            end tell
                            delay 0.5

                            log "  Looking for Cancel button..."
                            -- Find and click Cancel using entire contents
                            set allElements to entire contents of window w
                            repeat with elem in allElements
                                if class of elem is button then
                                    try
                                        if name of elem is "Cancel" then
                                            click elem
                                            log "  Clicked Cancel"
                                            delay 1  -- Wait 1 second after clicking
                                            set continueLoop to true
                                            exit repeat
                                        end if
                                    end try
                                end if
                            end repeat
                        else
                        -- Check the text content to identify dialog type
                        try
                            set staticTexts to static texts of window w
                            repeat with txt in staticTexts
                                try
                                    set textContent to value of txt

                                    if textContent contains "Project is modified" then
                                        log "Found 'Project is modified' dialog at window " & w

                                        -- Bring window to foreground
                                        tell window w
                                            perform action "AXRaise"
                                        end tell
                                        delay 0.5

                                        log "  Looking for Don't Save button..."
                                        -- Find and click Don't Save using entire contents
                                        set allElements to entire contents of window w
                                        repeat with elem in allElements
                                            if class of elem is button then
                                                try
                                                    if name of elem is "Don't Save" then
                                                        click elem
                                                        log "  Clicked Don't Save"
                                                        delay 1  -- Wait 1 second after clicking
                                                        set continueLoop to true
                                                        exit repeat
                                                    end if
                                                end try
                                            end if
                                        end repeat
                                        if continueLoop then exit repeat

                                    else if textContent contains "Connection Failed" then
                                        log "Found 'Connection Failed' dialog at window " & w

                                        -- Bring window to foreground
                                        tell window w
                                            perform action "AXRaise"
                                        end tell
                                        delay 0.5

                                        log "  Looking for OK button..."
                                        -- Find and click OK using entire contents
                                        set allElements to entire contents of window w
                                        repeat with elem in allElements
                                            if class of elem is button then
                                                try
                                                    if name of elem is "OK" then
                                                        click elem
                                                        log "  Clicked OK"
                                                        delay 1  -- Wait 1 second after clicking
                                                        set continueLoop to true
                                                        exit repeat
                                                    end if
                                                end try
                                            end if
                                        end repeat
                                        if continueLoop then exit repeat

                                    else if textContent contains "Reload Project" then
                                        log "Found 'Reload Project' dialog at window " & w

                                        -- Bring window to foreground
                                        tell window w
                                            perform action "AXRaise"
                                        end tell
                                        delay 0.5

                                        log "  Looking for Yes button..."
                                        -- Find and click Yes using entire contents
                                        set allElements to entire contents of window w
                                        repeat with elem in allElements
                                            if class of elem is button then
                                                try
                                                    if name of elem is "Yes" then
                                                        click elem
                                                        log "  Clicked Yes to reload project"
                                                        delay 1  -- Wait 1 second after clicking
                                                        set continueLoop to true
                                                        exit repeat
                                                    end if
                                                end try
                                            end if
                                        end repeat
                                        if continueLoop then exit repeat

                                    else if textContent contains "There are unfinished tasks" then
                                        log "Found 'Unfinished Tasks' dialog at window " & w

                                        -- Bring window to foreground
                                        tell window w
                                            perform action "AXRaise"
                                        end tell
                                        delay 0.5

                                        log "  Looking for Yes button to cancel tasks..."
                                        -- Find and click Yes using entire contents
                                        set allElements to entire contents of window w
                                        repeat with elem in allElements
                                            if class of elem is button then
                                                try
                                                    if name of elem is "Yes" then
                                                        click elem
                                                        log "  Clicked Yes to cancel unfinished tasks"
                                                        delay 1  -- Wait 1 second after clicking
                                                        set continueLoop to true
                                                        exit repeat
                                                    end if
                                                end try
                                            end if
                                        end repeat
                                        if continueLoop then exit repeat

                                    else if textContent contains "A new version of Lens Studio is available" then
                                        log "Found 'Lens Studio Update' dialog at window " & w

                                        -- Bring window to foreground
                                        tell window w
                                            perform action "AXRaise"
                                        end tell
                                        delay 0.5

                                        log "  Looking for Skip button..."
                                        -- Find and click Skip using entire contents
                                        set allElements to entire contents of window w
                                        repeat with elem in allElements
                                            if class of elem is button then
                                                try
                                                    if name of elem is "Skip" then
                                                        click elem
                                                        log "  Clicked Skip to dismiss update dialog"
                                                        delay 1  -- Wait 1 second after clicking
                                                        set continueLoop to true
                                                        exit repeat
                                                    end if
                                                end try
                                            end if
                                        end repeat
                                        if continueLoop then exit repeat
                                    end if
                                end try
                            end repeat
                        end try
                        end if  -- Close the else for Report an Issue
                    end if
            end repeat
        end repeat

        -- After loop completes (no more dialogs found)
        log "No more dialogs found"

        log ""
        log "Now listing all remaining windows:"
        log "=================================="

        set windowCount to count of windows
        log ""
        log "=============================="
        log "Total windows: " & windowCount
        log "=============================="

        -- List each window with details
        repeat with w from 1 to windowCount
            log ""
            log "WINDOW " & w & ":"
            log "----------"

            -- Get window name
            try
                set wName to name of window w
                log "  Name: '" & wName & "'"
            on error
                log "  Name: <empty or unavailable>"
            end try

            -- Get static text content to identify dialog type
            try
                set staticTexts to static texts of window w
                set textCount to count of staticTexts
                if textCount > 0 then
                    log "  Text content:"
                    repeat with t in staticTexts
                        try
                            set textContent to value of t
                            if length of textContent > 0 then
                                -- Truncate long text for readability
                                if length of textContent > 100 then
                                    set textContent to (text 1 thru 100 of textContent) & "..."
                                end if
                                log "    - " & textContent
                            end if
                        on error
                            -- Skip if can't read text
                        end try
                    end repeat
                end if
            on error
                -- Skip if can't access static texts
            end try

            -- List all buttons using entire contents for better accuracy
            log "  Buttons:"
            try
                set allElements to entire contents of window w
                set buttonIndex to 0
                repeat with elem in allElements
                    if class of elem is button then
                        set buttonIndex to buttonIndex + 1
                        try
                            set btnName to name of elem
                            if btnName is not missing value then
                                log "    [" & buttonIndex & "] '" & btnName & "'"
                            else
                                log "    [" & buttonIndex & "] <no name>"
                            end if
                        on error
                            log "    [" & buttonIndex & "] <error accessing>"
                        end try
                    end if
                end repeat
                if buttonIndex is 0 then
                    log "    No buttons found"
                else
                    log "    Total: " & buttonIndex & " buttons"
                end if
            on error errMsg
                log "    <could not access buttons: " & errMsg & ">"
            end try
        end repeat

        log ""
        log "=============================="
        log "End of window listing"
        log "=============================="

        -- First close the Home window
        log ""
        log "Looking for Home window to close it..."

        set windowCount to count of windows
        repeat with w from 1 to windowCount
            try
                set wName to name of window w
                if wName is "Home" then
                    log "Found Home window, clicking button 2 to close it..."

                    -- Click button 2 directly (the close button)
                    try
                        click button 2 of window w
                        log "Clicked button 2 on Home window"
                        delay 1
                    on error
                        log "Could not click button 2"
                    end try

                    exit repeat
                end if
            on error
                -- Continue checking other windows
            end try
        end repeat

        -- Now try to click Preview Lens in the main window
        log ""
        log "Looking for main Lens Studio window to click Preview Lens..."

        set windowCount to count of windows
        repeat with w from 1 to windowCount
            try
                set wName to name of window w
                if wName contains "Lens Studio" and wName contains ".1" then
                    log "Found main Lens Studio window: '" & wName & "'"

                    -- Bring to foreground
                    tell window w
                        perform action "AXRaise"
                    end tell
                    delay 1

                    log "Looking for Preview Lens button..."
                    -- Find and click Preview Lens using entire contents
                    set allElements to entire contents of window w
                    repeat with elem in allElements
                        if class of elem is button then
                            try
                                if name of elem is "Preview Lens" then
                                    click elem
                                    log "SUCCESS: Clicked Preview Lens!"
                                    exit repeat
                                end if
                            on error
                                -- Continue searching
                            end try
                        end if
                    end repeat

                    exit repeat
                end if
            on error
                -- Continue checking other windows
            end try
        end repeat
    end tell
end tell
EOF

echo ""
echo "Done!"