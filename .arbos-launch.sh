#!/usr/bin/env bash
_repo="$(cd "$(dirname "$0")" && pwd)"
export PATH="$_repo/tools:$_repo/tools/shims:$HOME/.local/bin:$HOME/.cargo/bin:$HOME/.npm-global/bin:/usr/local/bin:$PATH"
cd "$_repo"
set -a; [ -f .env ] && source .env; set +a
source .venv/bin/activate
# Shims must precede .venv/bin so agcli/btcli wallet subcommands stay blocked.
export PATH="$_repo/tools/shims:$PATH"
exec python3 arbos.py 2>&1
