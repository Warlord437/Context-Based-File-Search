#!/usr/bin/env bash
# Local-Agent: One-line install (like OpenClaw)
# Usage: curl -fsSL https://raw.githubusercontent.com/Warlord437/Context-Based-File-Search/main/install.sh | bash
#
# Or from repo: ./install.sh

set -e

INSTALL_DIR="${LOCAL_AGENT_HOME:-$HOME/.local-agent}"
REPO_URL="https://github.com/Warlord437/Context-Based-File-Search.git"
WEB_PORT="${LOCAL_AGENT_WEB_PORT:-8000}"

# If run from repo root (has requirements.txt and local-agent/cli.py), use current dir
if [ -f "requirements.txt" ] && [ -f "local-agent/cli.py" ] && [ -d ".git" ]; then
  INSTALL_DIR="$(pwd)"
  echo "🚀 Local-Agent: Installing from current directory..."
else
  echo "🚀 Local-Agent: Installing..."
fi
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "❌ Python 3 required. Install from https://python.org"
  exit 1
fi

# Clone or update (skip if already in repo)
if [ "$INSTALL_DIR" != "$(pwd)" ]; then
  if [ -d "$INSTALL_DIR/.git" ]; then
    echo "📂 Updating existing install at $INSTALL_DIR..."
    (cd "$INSTALL_DIR" && git pull --quiet 2>/dev/null || true)
  else
    echo "📂 Cloning to $INSTALL_DIR..."
    if ! git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"; then
      echo "❌ Clone failed. Ensure git is installed and URL is reachable."
      exit 1
    fi
  fi
  cd "$INSTALL_DIR"
fi

# Verify we're in the right place
if [ ! -f "requirements.txt" ]; then
  echo "❌ requirements.txt not found in $INSTALL_DIR. Clone may have failed."
  exit 1
fi

# Create venv
if [ ! -d ".venv" ]; then
  echo "📦 Creating virtual environment..."
  python3 -m venv .venv
fi

# Install deps
echo "📦 Installing dependencies..."
. .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Ensure config and store exist
if [ ! -f "config.yaml" ] && [ -f "config.yaml.example" ]; then
  echo "📋 Creating config.yaml from example..."
  cp config.yaml.example config.yaml
fi
mkdir -p store

# Start Qdrant (required for localhost)
if command -v docker &>/dev/null && [ -f "docker-compose.yml" ]; then
  echo "🐳 Starting Qdrant (vector DB)..."
  (docker compose up -d 2>/dev/null || docker-compose up -d 2>/dev/null) || true
  # Wait for Qdrant to be ready
  echo "⏳ Waiting for Qdrant to be ready..."
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if curl -s http://localhost:6333/health >/dev/null 2>&1; then
      echo "✅ Qdrant is ready"
      break
    fi
    sleep 2
  done
  if ! curl -s http://localhost:6333/health >/dev/null 2>&1; then
    echo "⚠️  Qdrant may still be starting. Run 'local-agent status' to verify."
  fi
else
  echo ""
  echo "⚠️  Docker not found. Qdrant (vector DB) is required."
  echo "   Install Docker, then run:"
  echo "     cd $INSTALL_DIR && docker compose up -d"
  echo ""
  echo "   macOS: brew install --cask docker"
  echo "   Linux: https://docs.docker.com/engine/install/"
  echo ""
fi

# Create launcher wrapper
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
LAUNCHER="$BIN_DIR/local-agent"
cat > "$LAUNCHER" << LAUNCHER_EOF
#!/usr/bin/env bash
INSTALL_DIR="$INSTALL_DIR"
cd "\$INSTALL_DIR"
. "\$INSTALL_DIR/.venv/bin/activate"
exec python3 "\$INSTALL_DIR/local-agent/cli.py" "\$@"
LAUNCHER_EOF
chmod +x "$LAUNCHER"

# Ensure ~/.local/bin in PATH
export PATH="$HOME/.local/bin:$PATH"
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
  echo ""
  echo "  Add to your shell config (~/.bashrc or ~/.zshrc):"
  echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
  echo ""
fi

# Verify setup (initializes DB schema, checks Qdrant)
echo "🔍 Verifying setup..."
if "$LAUNCHER" status 2>/dev/null; then
  echo ""
else
  echo "⚠️  Run 'local-agent status' manually to verify."
  echo ""
fi

echo "✅ Done! Run:"
echo "   local-agent status"
echo "   local-agent bfs-index ~/Documents"
echo "   local-agent find \"your query\""
echo ""
echo "   # Web UI (start first): cd $INSTALL_DIR && uvicorn web.server:app --reload --port $WEB_PORT"
echo ""
echo "   # Localhost links (set LOCAL_AGENT_WEB_PORT to change web port):"
echo "   • Qdrant dashboard:  http://localhost:6333/dashboard"
echo "   • Web UI:            http://localhost:$WEB_PORT"
echo "   • GraphQL (metrics): http://localhost:$WEB_PORT/graphql"
echo ""
