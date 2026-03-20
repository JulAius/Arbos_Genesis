#!/usr/bin/env bash
# Verify btcli is on PATH (install inside project .venv — see README.md / PROMPT.md).
set -euo pipefail
if command -v btcli >/dev/null 2>&1; then
	exec btcli --version
fi
echo "btcli not found. With .venv activated:" >&2
echo "  pip install -U bittensor-cli" >&2
echo "  or from repo root: pip install -e \".[bittensor]\"" >&2
exit 1
