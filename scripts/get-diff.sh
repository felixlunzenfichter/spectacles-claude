#!/bin/bash
# Read target repo from config file (one line: path to repo)
CONFIG_FILE="$HOME/.spectacles-repo"

if [ -f "$CONFIG_FILE" ]; then
    REPO_PATH=$(cat "$CONFIG_FILE")
else
    # Default to current directory
    REPO_PATH="$(pwd)"
fi

cd "$REPO_PATH" || exit 1

# Branch status with ahead/behind count
echo "=== Branch Status ==="
# Get repo name and combine with branch status
repo_name=$(basename -s .git "$(git config --get remote.origin.url)" 2>/dev/null || basename "$(pwd)")
git status -sb | sed "s/^## /$repo_name\//"
echo ""

# Unstaged changes
echo "=== Unstaged Changes ==="
git diff --function-context
echo ""

# Staged changes
echo "=== Staged Changes ==="
git diff --staged --function-context
echo ""

# Untracked files with their content
echo "=== Untracked files ==="
git ls-files --others --exclude-standard | while read -r f; do
    if [ -f "$f" ]; then
        echo ""
        echo "new file: $f"
        echo "---"
        cat "$f"
        echo ""
    fi
done
echo ""

# Unified commit list showing local and remote positions
echo "=== Commits ==="
git fetch -q 2>/dev/null

# Get local and remote HEAD commit hashes
local_head=$(git rev-parse HEAD 2>/dev/null)
remote_head=$(git rev-parse origin/development 2>/dev/null || echo "")

# Get all commits and process them
git log --all -10 --format="%H|%ad %s %h" --date=format:'%b %d %H:%M' | while IFS='|' read -r commit_hash commit_line; do
    # Check if this commit is the remote HEAD
    if [ "$commit_hash" = "$remote_head" ]; then
        echo "=== REMOTE HEAD ==="
    fi

    # Check if this commit is the local HEAD
    if [ "$commit_hash" = "$local_head" ]; then
        echo "=== LOCAL HEAD ==="
    fi

    # Print the commit line
    echo "$commit_line"
done

# Latest 3 commits (message only, no diff)
echo "=== Recent Commits ==="
git log -3 --format="%h %ad %s" --date=format:'%b %d %H:%M'
