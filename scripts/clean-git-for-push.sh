#!/bin/bash
# Run this in VS Code terminal or GitHub Desktop shell before pushing.
# Removes store/, *.db, .DS_Store, egg-info from Git tracking (keeps files locally).
# Use when: Cursor can't connect to GitHub, you push via VS Code or GitHub Desktop.

set -e
cd "$(dirname "$0")/.."

echo "Stopping Git tracking of local/store files (files stay on disk)..."
git rm -r --cached store/ 2>/dev/null || true
git rm --cached .DS_Store 2>/dev/null || true
git rm -r --cached local_agent.egg-info/ 2>/dev/null || true
git rm -r --cached "*.egg-info" 2>/dev/null || true
# Remove any tracked .db files
git ls-files '*.db' '*.db-*' 2>/dev/null | while read f; do git rm --cached "$f" 2>/dev/null; done || true

if git diff --cached --quiet; then
  echo "Nothing to change - files already untracked."
else
  git commit -m "Stop tracking store, db files, and build artifacts"
  echo "Done. Push from VS Code or GitHub Desktop."
fi
