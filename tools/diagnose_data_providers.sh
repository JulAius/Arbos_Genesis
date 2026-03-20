#!/usr/bin/env bash
# Diagnose TaoStats and TaoMarketCap API connectivity
# Prints HTTP status codes for key endpoints with correct auth headers.
set -euo pipefail

_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Load .env if present
if [ -f "$_REPO/.env" ]; then
    set +u
    source "$_REPO/.env"
    set -u
fi

echo "=== TaoStats Diagnostics ==="
echo "Base URL : https://api.taostats.io"
echo "Auth     : Authorization: <key>  (no Bearer)"
echo "Pattern  : /api/{resource}/{scope}/v1"
echo ""
if [ -z "${TAOSTATS_API_KEY:-}" ]; then
    echo "  TAOSTATS_API_KEY not set — skipping live tests"
else
    for path in \
        "/api/subnet/latest/v1?limit=1" \
        "/api/neuron/latest/v1?netuid=1&limit=1" \
        "/api/validator/latest/v1?limit=1" \
        "/api/price/latest/v1?asset=tao" \
        "/api/block/v1?limit=1" \
        "/api/delegation/v1?limit=1" \
        "/api/account/latest/v1?limit=1" \
        "/api/metagraph/latest/v1?netuid=1&limit=1"
    do
        url="https://api.taostats.io${path}"
        code=$(curl -s -o /dev/null -w "%{http_code}" \
            -H "Authorization: $TAOSTATS_API_KEY" \
            -H "accept: application/json" \
            "$url" 2>/dev/null || echo "ERR")
        echo "  [$code] $path"
        sleep 0.5
    done
fi

echo ""
echo "=== TaoMarketCap Diagnostics ==="
echo "Base URL : https://api.taomarketcap.com"
echo "Auth     : Authorization: <key>  (no Bearer)"
echo "Pattern  : /public/v1/{category}/..."
echo ""
if [ -z "${TAOMARKETCAP_API_KEY:-}" ]; then
    echo "  TAOMARKETCAP_API_KEY not set — skipping live tests"
else
    for path in \
        "/public/v1/market/market-data/" \
        "/public/v1/market/candle-data/?limit=1" \
        "/public/v1/subnets/info/" \
        "/public/v1/validators/full/?limit=1" \
        "/public/v1/accounts/info/" \
        "/public/v1/analytics/chain/?span=1d" \
        "/public/v1/general/staking-constants/" \
        "/public/v1/transactions/stakes/stake-added/?limit=1"
    do
        url="https://api.taomarketcap.com${path}"
        code=$(curl -s -o /dev/null -w "%{http_code}" \
            -H "Authorization: $TAOMARKETCAP_API_KEY" \
            -H "accept: application/json" \
            "$url" 2>/dev/null || echo "ERR")
        echo "  [$code] $path"
        sleep 0.2
    done
fi

echo ""
echo "All [200] = OK. [429] = rate limited (retry later). [401] = bad key. [404] = wrong path."
