#!/usr/bin/env bash
# One-line install for Local-Agent
# Usage: ./install.sh  OR  curl -sSL <raw-url>/install.sh | bash

set -e
cd "$(dirname "$0")"

echo "🚀 Local-Agent: Installing..."
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "❌ Python 3 required. Install from https://python.org"
  exit 1
fi

# Create venv
if [ ! -d ".venv" ]; then
  echo "📦 Creating virtual environment..."
  python3 -m venv .venv
fi

# Activate and install
echo "📦 Installing dependencies..."
. .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Start Qdrant if Docker available
if command -v docker &>/dev/null && [ -f "docker-compose.yml" ]; then
  echo "🐳 Starting Qdrant..."
  docker compose up -d 2>/dev/null || docker-compose up -d 2>/dev/null || true
fi

echo ""
echo "✅ Done! Run:"
echo "   source .venv/bin/activate   # or: . .venv/bin/activate"
echo "   python3 local-agent/cli.py status"
echo "   python3 local-agent/cli.py bfs-index ~/Documents"
echo "   python3 local-agent/cli.py find \"your query\""
echo ""
echo "   # Web UI:"
echo "   uvicorn web.server:app --reload --port 8000"
echo ""
