#!/bin/bash
cd "$(dirname "$0")"

echo "-------------------------------------------------------"
echo "Starting Lyridan macOS Build..."
echo "-------------------------------------------------------"

# 1. DEFINE YOUR VENV FOLDER NAME
# If your venv folder is named ".venv" or "env", change this line:
VENV_NAME="venv"

# 2. CHECK AND RUN
if [ -f "$VENV_NAME/bin/python" ]; then
    echo "✅ Found Virtual Environment: $VENV_NAME"
    # Execute the script using the VENV's python directly
    "$VENV_NAME/bin/python" maccompile.py
else
    echo "⚠️  Could not find a folder named '$VENV_NAME'"
    echo "Falling back to system Python (this might fail)..."
    python3 maccompile.py
fi

echo "Process Complete."
read -p "Press any key to close..." -n1 -s