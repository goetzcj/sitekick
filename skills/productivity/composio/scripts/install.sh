#!/usr/bin/env bash
# Install composio into the Hermes Agent Python environment.
#
# Usage (from the sitekick profile root):
#   bash skills/productivity/composio/scripts/install.sh
#
# Detects whether Hermes is running inside a uv-managed virtualenv or a
# standard pip virtualenv and uses the appropriate installer.

set -euo pipefail

PACKAGE="composio"

echo "→ Installing ${PACKAGE}..."

if command -v uv &>/dev/null && [ -f pyproject.toml ]; then
  echo "  Using uv add (pyproject.toml found)"
  uv add "${PACKAGE}"
elif python -m pip --version &>/dev/null; then
  echo "  Using python -m pip install"
  python -m pip install "${PACKAGE}"
elif command -v pip &>/dev/null; then
  echo "  Using pip install"
  pip install "${PACKAGE}"
else
  echo "  No pip found for default python; trying Hermes venv python"
  /usr/local/lib/hermes-agent/venv/bin/python3 -m pip install "${PACKAGE}"
fi

echo "→ Verifying install..."
if command -v python &>/dev/null; then
  python -c "import composio; print('  composio version:', getattr(composio, '__version__', 'unknown'))" || \
    /usr/local/lib/hermes-agent/venv/bin/python3 -c "import composio; print('  composio version:', getattr(composio, '__version__', 'unknown'))"
else
  /usr/local/lib/hermes-agent/venv/bin/python3 -c "import composio; print('  composio version:', getattr(composio, '__version__', 'unknown'))"
fi

echo ""
echo "✓ ${PACKAGE} installed successfully."
echo ""
echo "Next steps:"
echo "  1. Ensure COMPOSIO_API_KEY is set in your profile .env"
echo "  2. Run 'composio add <toolkit>' once per service you want to connect"
echo "  3. Run 'composio connections' to confirm linked accounts"
