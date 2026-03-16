#!/usr/bin/env bash
set -euo pipefail

echo "=== Job Ace Setup ==="
echo ""

# Detect OS
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Detect distro
    if command -v apt-get &>/dev/null; then
        echo "[1/5] Installing system dependencies (apt)..."
        sudo apt-get update -qq
        sudo apt-get install -y -qq \
            python3 python3-venv python3-pip python3-dev \
            libpango-1.0-0 libpangocairo-1.0-0 libcairo2 \
            libgdk-pixbuf2.0-0 libffi-dev \
            2>/dev/null
    elif command -v dnf &>/dev/null; then
        echo "[1/5] Installing system dependencies (dnf)..."
        sudo dnf install -y -q \
            python3 python3-devel \
            pango cairo gdk-pixbuf2 libffi-devel \
            2>/dev/null
    elif command -v pacman &>/dev/null; then
        echo "[1/5] Installing system dependencies (pacman)..."
        sudo pacman -S --noconfirm --needed \
            python pango cairo gdk-pixbuf2 libffi \
            2>/dev/null
    else
        echo "[1/5] Unknown Linux distro. Please install manually:"
        echo "  python3, pango, cairo, gdk-pixbuf, libffi"
        echo "  (needed for WeasyPrint PDF export)"
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo "[1/5] Installing system dependencies (brew)..."
    if ! command -v brew &>/dev/null; then
        echo "  Homebrew not found. Install from https://brew.sh"
        exit 1
    fi
    brew install pango cairo libffi gdk-pixbuf 2>/dev/null || true
else
    echo "[1/5] Unsupported OS: $OSTYPE"
    echo "  Please install python3, pango, cairo, gdk-pixbuf, libffi manually."
fi

# Python venv
echo "[2/5] Creating Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

# Install Python packages
echo "[3/5] Installing Python dependencies..."
pip install -q -e .
pip install -q -e ".[dev]"

# Playwright
echo "[4/5] Installing Playwright browsers..."
playwright install chromium 2>/dev/null

# Database
echo "[5/5] Initializing database..."
job-ace init

echo ""
echo "=== Setup complete ==="
echo ""
echo "To start Job Ace:"
echo "  ./start.sh"
echo ""
echo "Or manually:"
echo "  source .venv/bin/activate"
echo "  python -m backend.main"
echo ""
echo "Web UI: http://localhost:3000"
echo "API docs: http://localhost:3000/docs"
