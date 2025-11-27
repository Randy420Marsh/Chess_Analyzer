#!/usr/bin/env bash

export PATH="$PATH:$PWD/stockfish"

# Resolve directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Activating ComfyUI virtual environment..."

# Point directly to the venv path inside the same folder as the script
if [ ! -f "$SCRIPT_DIR/.chess/bin/activate" ]; then
    echo "[INFO] No venv found. Creating one with uv..."
    uv venv "$SCRIPT_DIR/.chess" --python 3.12
else
    echo "[INFO] Venv found. Proceeding..."
fi

# Activate into current shell
source "$SCRIPT_DIR/.chess/bin/activate" && \
uv pip install -r requirements.txt


echo "Virtual environment activated."
echo "Python: $(python --version)"
echo "Pip:    $(pip --version)"
echo
echo "Use 'deactivate' to exit."

python -s Chess_Analyzer_GUI.py

