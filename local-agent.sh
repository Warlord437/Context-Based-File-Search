#!/bin/bash
# Local-Agent CLI Wrapper
# Automatically uses the virtual environment

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"

# Check if virtual environment exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ Virtual environment not found at $VENV_PYTHON"
    echo "💡 Please run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Check if Qdrant server is running
if ! curl -s http://localhost:6333/health > /dev/null 2>&1; then
    echo "⚠️  Qdrant server not running. Starting it..."
    cd "$PROJECT_DIR"
    docker-compose up -d
    sleep 3
fi

# Run the CLI with the virtual environment's Python
exec "$VENV_PYTHON" "$SCRIPT_DIR/local-agent/cli.py" "$@"
