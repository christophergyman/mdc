#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

VENV_DIR=".venv"

# --- Create virtual environment if missing ---
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

# --- Install / update dependencies ---
echo "Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# --- Build .app bundle ---
if [ "${1:-}" = "--build" ]; then
    echo "Building GazeTracker.app..."
    rm -rf build dist
    python setup.py py2app
    echo "Build complete: dist/GazeTracker.app"
    echo "Opening app..."
    open dist/GazeTracker.app
else
    # --- Run directly from source ---
    echo "Starting GazeTracker..."
    python main.py
fi
