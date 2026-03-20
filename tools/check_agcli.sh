#!/usr/bin/env bash
# Verify agcli is on PATH (see README.md and PROMPT.md).
set -euo pipefail
if command -v agcli >/dev/null 2>&1; then
	exec agcli --version
fi
echo "agcli not found. Install Rust 1.75+, then:" >&2
echo "  cargo install --git https://github.com/unconst/agcli" >&2
exit 1
