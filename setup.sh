#!/usr/bin/env bash
#
# Quick setup script for Polymarket Whale Bot.
# Run: bash setup.sh
#
set -e

echo ""
echo "=== Polymarket Whale Bot - Setup ==="
echo ""

# ── Check Python version ────────────────────────────────────────────────────
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found. Install Python 3.10+ first."
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
    echo "ERROR: Python 3.10+ required, found $PY_VERSION"
    exit 1
fi
echo "[OK] Python $PY_VERSION"

# ── Create virtual environment ──────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "[..] Creating virtual environment..."
    python3 -m venv .venv
    echo "[OK] Virtual environment created"
else
    echo "[OK] Virtual environment exists"
fi

# ── Activate ────────────────────────────────────────────────────────────────
source .venv/bin/activate
echo "[OK] Virtual environment activated"

# ── Install dependencies ────────────────────────────────────────────────────
echo "[..] Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "[OK] Dependencies installed"

# ── Create .env if needed ───────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "=== IMPORTANT: .env file created ==="
    echo ""
    echo "You need to fill in these 4 values in .env:"
    echo ""
    echo "  1. TELEGRAM_API_ID     - Get from https://my.telegram.org/apps"
    echo "  2. TELEGRAM_API_HASH   - Get from https://my.telegram.org/apps"
    echo "  3. TELEGRAM_PHONE      - Your phone: +385601234567"
    echo "  4. POLYGON_PRIVATE_KEY - Your wallet private key (0x...)"
    echo ""
    echo "Edit with: nano .env"
    echo ""
else
    echo "[OK] .env file exists"
fi

# ── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env with your credentials (if not done yet)"
echo "  2. Run the bot:        source .venv/bin/activate && python main.py"
echo "  3. Or web dashboard:   source .venv/bin/activate && python web_app.py"
echo ""
echo "Bot starts in DRY_RUN=true mode (no real money spent)."
echo "First run will ask for Telegram verification code on your phone."
echo ""
