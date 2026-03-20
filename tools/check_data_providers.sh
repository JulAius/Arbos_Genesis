#!/usr/bin/env bash
# Verify data provider tools, API keys, and live connectivity.
set -euo pipefail

_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Check Python dependency
python3 -c "import httpx" 2>/dev/null || {
    echo "httpx not installed. Run: pip install httpx" >&2
    exit 1
}

# Check tools on PATH (or fall back to repo tools/)
_TAOSTATS="$_REPO/tools/taostats"
_TAOMARKETCAP="$_REPO/tools/taomarketcap"

[ -x "$_TAOSTATS" ]    || { echo "tools/taostats not found or not executable" >&2; exit 1; }
[ -x "$_TAOMARKETCAP" ] || { echo "tools/taomarketcap not found or not executable" >&2; exit 1; }

# Load API keys from .env (or accept from environment)
if [ -f "$_REPO/.env" ]; then
    set +u
    source "$_REPO/.env"
    set -u
fi

missing=()
[ -z "${TAOSTATS_API_KEY:-}"    ] && missing+=("TAOSTATS_API_KEY")
[ -z "${TAOMARKETCAP_API_KEY:-}" ] && missing+=("TAOMARKETCAP_API_KEY")

if [ ${#missing[@]} -gt 0 ]; then
    echo "Missing API keys: ${missing[*]}" >&2
    exit 1
fi

export TAOSTATS_API_KEY TAOMARKETCAP_API_KEY

# Live connectivity check
echo "Checking TaoStats API..."
ts_result=$("$_TAOSTATS" price 2>&1) || {
    echo "  FAIL: taostats price returned non-zero" >&2
    echo "  $ts_result" >&2
    exit 1
}
ts_price=$(echo "$ts_result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('price','?'))" 2>/dev/null || echo "?")
echo "  OK  TAO price = \$${ts_price}"

echo "Checking TaoMarketCap API..."
tmc_result=$("$_TAOMARKETCAP" market 2>&1) || {
    echo "  FAIL: taomarketcap market returned non-zero" >&2
    echo "  $tmc_result" >&2
    exit 1
}
tmc_price=$(echo "$tmc_result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('current_price','?'))" 2>/dev/null || echo "?")
echo "  OK  TAO price = \$${tmc_price}"

echo ""
echo "taostats and taomarketcap are operational."
exit 0
