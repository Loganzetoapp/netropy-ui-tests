#!/usr/bin/env bash
# One-time setup for running the test suite / dashboard on a new machine.
# Safe to re-run — every step skips or no-ops if already done.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Netropy Test Dashboard — setup"
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.9+ first: https://www.python.org/downloads/"
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Creating virtual environment (.venv)..."
  python3 -m venv .venv
else
  echo "Virtual environment (.venv) already exists — reusing it."
fi

# shellcheck source=/dev/null
source .venv/bin/activate

echo "Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "Installing the Chromium browser Playwright drives (one-time download, ~150MB)..."
if [ "$(uname -s)" = "Linux" ]; then
  # Headless Chromium needs OS-level shared libraries (libnss3,
  # libatk-bridge2.0-0, etc.) that macOS already has and Linux doesn't —
  # --with-deps installs them via apt on Debian/Ubuntu, which needs root.
  # Without this, the browser fixture crashes on its first launch on a
  # fresh Linux box with an error that doesn't obviously point at missing
  # system libs.
  echo "Linux detected — also installing Chromium's OS-level dependencies via apt (may prompt for your sudo password)..."
  python -m playwright install --with-deps chromium
else
  python -m playwright install chromium
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo "Created .env from .env.example. Open it now and fill in:"
  echo "  NETROPY_URL, NETROPY_USER, NETROPY_PASS"
  echo "(ask a teammate for these values if you don't have them)"
else
  echo
  echo ".env already exists — leaving it as-is."
fi

echo
echo "Setup complete. Next steps:"
echo "  1. Make sure .env has real NETROPY_URL / NETROPY_USER / NETROPY_PASS."
echo "  2. Run: make run-dashboard"
echo "  3. Open the URL it prints in your browser."
