#!/usr/bin/env bash
# Install composio-core into the Hermes Agent Python environment.
#
# Usage (from the sitekick profile root):
#   bash skills/productivity/composio/scripts/install.sh
#
# Detects whether Hermes is running inside a uv-managed virtualenv or a
# standard pip virtualenv and uses the appropriate installer.

set -euo pipefail

PACKAGE="composio"

echo "→ Installing ${PACKAGE}..."

if command -v uv &>/dev/null; then
  echo "  Using uv add"
  uv add "${PACKAGE}"
else
  echo "  Using pip install"
  pip install "${PACKAGE}"
fi

echo "→ Verifying install..."
python -c "import composio; print('  composio version:', composio.__version__)"

echo ""
echo "✓ ${PACKAGE} installed successfully."
echo ""
echo "Next steps:"
echo "  1. Ensure COMPOSIO_API_KEY is set in your profile .env"
echo "  2. Run 'composio add <toolkit>' once per service you want to connect"
echo "  3. Run 'composio connections' to confirm linked accounts"
