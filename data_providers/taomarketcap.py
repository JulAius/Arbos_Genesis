#!/usr/bin/env python3
"""
TaoMarketCap (TMC) API client for Bittensor market & network data.

Base URL : https://api.taomarketcap.com
Auth     : Authorization: <key>   (no Bearer prefix)
OpenAPI  : https://api.taomarketcap.com/api/public-oas3.json?format=json
Docs     : https://api.taomarketcap.com/developer/documentation/

Confirmed working endpoints (tested 2026-03-20):
  Market
    GET /public/v1/market/market-data/          price, supply, market cap (all-in-one)
    GET /public/v1/market/chart-data/           price chart series
    GET /public/v1/market/candle-data/          OHLCV candles

  Subnets
    GET /public/v1/subnets/                     subnet list
    GET /public/v1/subnets/{id}/                subnet detail
    GET /public/v1/subnets/info/                network-level stats (lock cost, burn)
    GET /public/v1/subnets/tokenomics/          recycled TAO amounts
    GET /public/v1/subnets/network-lock-cost/   lock cost history
    GET /public/v1/subnets/sum-of-sn-prices/    sum of all subnet prices history
    GET /public/v1/subnets/neurons/             all neurons across subnets
    GET /public/v1/subnets/neurons/{id}/        specific neuron (id = netuid:uid)
    GET /public/v1/subnets/table/               subnet summary table

  Validators
    GET /public/v1/validators/full/             full validator list (hotkey, apy, fee, stake)
    GET /public/v1/validators/full-compact/     compact validator list
    GET /public/v1/validators/{hotkey}/         specific validator detail
    GET /public/v1/validators/{hotkey}/stakers-table/  stakers for a validator

  Accounts
    GET /public/v1/accounts/coldkeys/           coldkey list
    GET /public/v1/accounts/coldkeys/{id}/      specific coldkey
    GET /public/v1/accounts/hotkeys/            hotkey list
    GET /public/v1/accounts/hotkeys/{address}/  specific hotkey
    GET /public/v1/accounts/info/               aggregate account stats

  Blocks & Extrinsics
    GET /public/v1/blocks/                      blocks
    GET /public/v1/extrinsics/                  extrinsics
    GET /public/v1/extrinsics/staking-activity/ staking activity
    GET /public/v1/events/                      events

  Transactions
    GET /public/v1/transactions/stakes/stake-added/    stake additions
    GET /public/v1/transactions/stakes/stake-removed/  stake removals
    GET /public/v1/transactions/stakes/stake-moved/    stake moves between subnets
    GET /public/v1/transactions/transfers/             TAO transfers

  Analytics
    GET /public/v1/analytics/chain/             chain-level analytics (volume, buys, etc.)
    GET /public/v1/analytics/subnet/{netuid}/   subnet-level analytics
    GET /public/v1/analytics/trending/          all trending data
    GET /public/v1/analytics/trending/subnets/  trending subnets
    GET /public/v1/analytics/trending/validators/ trending validators
    GET /public/v1/analytics/tax-report/        tax report for a coldkey

  General
    GET /public/v1/general/constants/           chain constants (balances, proxy, subtensor)
    GET /public/v1/general/staking-constants/   DefaultFeeRate, DefaultMinStake
    GET /public/v1/general/senate-members/      senate members + required stake
    GET /public/v1/general/global-search/       global search (q=...)
"""

import os
import json
import httpx
from typing import Any, Optional
from pathlib import Path

BASE_URL = os.getenv("TAOMARKETCAP_BASE_URL", "https://api.taomarketcap.com")


def _load_env() -> None:
    current = Path(__file__).resolve()
    for parent in [current.parent, current.parent.parent]:
        env_path = parent / ".env"
        if env_path.exists():
            try:
                from dotenv import load_dotenv
                load_dotenv(env_path, override=False)
            except ImportError:
                pass
            break


def _get_api_key() -> str:
    _load_env()
    key = os.getenv("TAOMARKETCAP_API_KEY")
    if not key:
        raise EnvironmentError("TAOMARKETCAP_API_KEY environment variable not set")
    return key


def _headers() -> dict:
    # NOTE: plain key, no "Bearer" prefix — Bearer returns 401
    return {"Authorization": _get_api_key(), "accept": "application/json"}


def _get(path: str, params: Optional[dict] = None) -> Any:
    url = f"{BASE_URL}{path}"
    response = httpx.get(url, params={k: v for k, v in (params or {}).items() if v is not None},
                         headers=_headers(), timeout=30)
    response.raise_for_status()
    return response.json()


# ── Market ────────────────────────────────────────────────────────────────────

def get_market_data() -> dict[str, Any]:
    """
    Current TAO market snapshot (all-in-one).
    Fields: current_price, usd_quote (price_usd, volume_24h, market_cap,
            percent_change_*), circulating_supply, max_supply,
            network_lock_cost, block_number, ai_market_dominance.
    """
    return _get("/public/v1/market/market-data/")


def get_chart_data(limit: int = 100, offset: int = 0) -> Any:
    """Price chart series data. Returns {series, min, max}."""
    return _get("/public/v1/market/chart-data/", {"limit": limit, "offset": offset})


def get_candle_data(limit: int = 100, offset: int = 0) -> Any:
    """
    OHLCV candlestick data.
    Returns list of {timestamp, open, high, low, close}.
    """
    return _get("/public/v1/market/candle-data/", {"limit": limit, "offset": offset})


# ── Subnets ───────────────────────────────────────────────────────────────────

def get_subnets(netuid: Optional[int] = None, limit: int = 50, offset: int = 0) -> Any:
    """Subnet list. Returns paginated {count, next, previous, results}."""
    return _get("/public/v1/subnets/", {"netuid": netuid, "limit": limit, "offset": offset})


def get_subnet_detail(subnet_id: int) -> dict[str, Any]:
    """
    Specific subnet detail.
    Fields: id, netuid, created_at_block, registered_at, is_active,
            is_subsidized, mechanism_count, latest_snapshot_id.
    """
    return _get(f"/public/v1/subnets/{subnet_id}/")


def get_subnets_info() -> dict[str, Any]:
    """
    Network-level subnet stats.
    Fields: total_networks, network_rate_limit, network_lock_cost,
            sum_of_sn_burns, sum_of_sn_prices, network_lock_cost_preview.
    """
    return _get("/public/v1/subnets/info/")


def get_subnets_tokenomics() -> dict[str, Any]:
    """Recycled TAO amounts per subnet."""
    return _get("/public/v1/subnets/tokenomics/")


def get_network_lock_cost_history(limit: int = 100, offset: int = 0) -> Any:
    """Network lock cost history. Returns list of {block_number, timestamp, value, tao_price_usd}."""
    return _get("/public/v1/subnets/network-lock-cost/", {"limit": limit, "offset": offset})


def get_sn_prices_history(limit: int = 100, offset: int = 0) -> Any:
    """Sum of all subnet prices over time. Returns list of {block_number, timestamp, value, tao_price_usd}."""
    return _get("/public/v1/subnets/sum-of-sn-prices/", {"limit": limit, "offset": offset})


def get_subnet_neurons(
    subnet: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """All neurons across subnets. Returns paginated results."""
    return _get("/public/v1/subnets/neurons/", {"subnet": subnet, "limit": limit, "offset": offset})


def get_subnet_table() -> Any:
    """Subnet summary table with key metrics."""
    return _get("/public/v1/subnets/table/")


# ── Validators ────────────────────────────────────────────────────────────────

def get_validators_full(
    hotkey: Optional[str] = None,
    subnet: Optional[int] = None,
    apy_gte: Optional[float] = None,
    apy_lte: Optional[float] = None,
    tao_stake_gte: Optional[float] = None,
    tao_stake_lte: Optional[float] = None,
) -> Any:
    """
    Full validator list.
    Fields: subnet, hotkey, coldkey, apy, validator_fee, tao_alpha_staked, etc.
    Returns a list (not paginated).
    """
    params = {
        "hotkey": hotkey,
        "subnet": subnet,
        "apy_gte": apy_gte,
        "apy_lte": apy_lte,
        "tao_stake_gte": tao_stake_gte,
        "tao_stake_lte": tao_stake_lte,
    }
    return _get("/public/v1/validators/full/", params)


def get_validator_detail(hotkey: str) -> dict[str, Any]:
    """Specific validator detail by hotkey."""
    return _get(f"/public/v1/validators/{hotkey}/")


def get_validator_stakers(
    hotkey: str,
    limit: int = 50,
    offset: int = 0,
    ordering: Optional[str] = None,
) -> Any:
    """Stakers table for a specific validator."""
    return _get(f"/public/v1/validators/{hotkey}/stakers-table/",
                {"limit": limit, "offset": offset, "hotkey": hotkey, "ordering": ordering})


# ── Accounts ──────────────────────────────────────────────────────────────────

def get_coldkeys(
    search: Optional[str] = None,
    subnet: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    ordering: Optional[str] = None,
) -> Any:
    """Coldkey accounts with balances and stake. Returns paginated {count, results}."""
    return _get("/public/v1/accounts/coldkeys/",
                {"search": search, "subnet": subnet, "limit": limit, "offset": offset, "ordering": ordering})


def get_coldkey_detail(coldkey_id: str) -> dict[str, Any]:
    """Specific coldkey detail."""
    return _get(f"/public/v1/accounts/coldkeys/{coldkey_id}/")


def get_hotkeys(
    address: Optional[str] = None,
    coldkey: Optional[str] = None,
    subnet: Optional[int] = None,
    is_neuron: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """Hotkey list. Returns paginated results."""
    return _get("/public/v1/accounts/hotkeys/",
                {"address": address, "coldkey": coldkey, "subnet": subnet,
                 "is_neuron": is_neuron, "limit": limit, "offset": offset})


def get_hotkey_detail(address: str) -> dict[str, Any]:
    """Specific hotkey detail by SS58 address."""
    return _get(f"/public/v1/accounts/hotkeys/{address}/")


def get_accounts_info() -> dict[str, Any]:
    """
    Aggregate account statistics.
    Fields: total_accounts, new_accounts_24h, existential_deposit.
    """
    return _get("/public/v1/accounts/info/")


# ── Blocks & Extrinsics ───────────────────────────────────────────────────────

def get_blocks(
    height: Optional[int] = None,
    limit: int = 10,
    offset: int = 0,
) -> Any:
    """Blocks. Returns paginated {count, results}."""
    return _get("/public/v1/blocks/", {"height": height, "limit": limit, "offset": offset})


def get_extrinsics(
    hotkey: Optional[str] = None,
    coldkey: Optional[str] = None,
    subnet: Optional[int] = None,
    call_module: Optional[str] = None,
    call_function: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """Extrinsics. Returns paginated results."""
    return _get("/public/v1/extrinsics/",
                {"hotkey": hotkey, "coldkey": coldkey, "subnet": subnet,
                 "call_module": call_module, "call_function": call_function,
                 "limit": limit, "offset": offset})


def get_staking_activity(
    hotkey: Optional[str] = None,
    coldkey: Optional[str] = None,
    subnet: Optional[int] = None,
    function: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """Staking activity (add/remove/move stake extrinsics). Returns paginated results."""
    return _get("/public/v1/extrinsics/staking-activity/",
                {"hotkey": hotkey, "coldkey": coldkey, "subnet": subnet,
                 "function": function, "limit": limit, "offset": offset})


def get_events(
    hotkey: Optional[str] = None,
    coldkey: Optional[str] = None,
    subnet: Optional[int] = None,
    method: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """On-chain events. Returns paginated results."""
    return _get("/public/v1/events/",
                {"hotkey": hotkey, "coldkey": coldkey, "subnet": subnet,
                 "method": method, "limit": limit, "offset": offset})


# ── Transactions ──────────────────────────────────────────────────────────────

def get_stakes_added(
    hotkey: Optional[str] = None,
    subnet: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """Stake-add transactions. Returns paginated {count, results}."""
    return _get("/public/v1/transactions/stakes/stake-added/",
                {"hotkey": hotkey, "subnet": subnet, "limit": limit, "offset": offset})


def get_stakes_removed(
    hotkey: Optional[str] = None,
    subnet: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """Stake-remove transactions. Returns paginated {count, results}."""
    return _get("/public/v1/transactions/stakes/stake-removed/",
                {"hotkey": hotkey, "subnet": subnet, "limit": limit, "offset": offset})


def get_stakes_moved(
    origin_hotkey: Optional[str] = None,
    destination_hotkey: Optional[str] = None,
    subnet_from: Optional[int] = None,
    subnet_to: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """Stake-move transactions between subnets. Returns paginated results."""
    return _get("/public/v1/transactions/stakes/stake-moved/",
                {"origin_hotkey": origin_hotkey, "destination_hotkey": destination_hotkey,
                 "subnet_from": subnet_from, "subnet_to": subnet_to,
                 "limit": limit, "offset": offset})


def get_transfers(
    coldkey: Optional[str] = None,
    from_coldkey: Optional[str] = None,
    to_coldkey: Optional[str] = None,
    subnet: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """TAO transfer transactions. Returns paginated {count, results}."""
    return _get("/public/v1/transactions/transfers/",
                {"coldkey": coldkey, "from_coldkey": from_coldkey, "to_coldkey": to_coldkey,
                 "subnet": subnet, "limit": limit, "offset": offset})


# ── Analytics ─────────────────────────────────────────────────────────────────

def get_analytics_chain(
    span: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    fields: Optional[str] = None,
) -> Any:
    """
    Chain-level analytics time series.
    span: 1h, 1d, 7d, 30d, 1y, all
    Fields in each item: ts, block_number, trading_volume_1h,
    trading_volume_cumulative, total_chain_buys, etc.
    """
    return _get("/public/v1/analytics/chain/",
                {"span": span, "from": from_date, "to": to_date, "fields": fields})


def get_analytics_subnet(
    netuid: int,
    span: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Any:
    """Subnet-level analytics time series."""
    return _get(f"/public/v1/analytics/subnet/{netuid}/",
                {"span": span, "from": from_date, "to": to_date})


def get_trending(limit: Optional[int] = None) -> dict[str, Any]:
    """All trending data (subnets, validators, coldkeys)."""
    return _get("/public/v1/analytics/trending/", {"limit": limit})


def get_trending_subnets(limit: Optional[int] = None) -> dict[str, Any]:
    """Trending subnets."""
    return _get("/public/v1/analytics/trending/subnets/", {"limit": limit})


def get_trending_validators(limit: Optional[int] = None) -> dict[str, Any]:
    """Trending validators."""
    return _get("/public/v1/analytics/trending/validators/", {"limit": limit})


def get_tax_report(
    coldkey: str,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
) -> Any:
    """Tax report for a coldkey (date format: YYYY-MM-DD)."""
    return _get("/public/v1/analytics/tax-report/",
                {"coldkey": coldkey, "date_start": date_start, "date_end": date_end})


# ── General ───────────────────────────────────────────────────────────────────

def get_constants(constant_type: Optional[str] = None) -> dict[str, Any]:
    """
    Chain constants.
    Fields: balances, proxy, subtensor_module, swap, spec_version, etc.
    """
    return _get("/public/v1/general/constants/", {"type": constant_type})


def get_staking_constants() -> dict[str, Any]:
    """
    Staking constants.
    Fields: DefaultFeeRate, DefaultMinStake.
    """
    return _get("/public/v1/general/staking-constants/")


def get_senate_members() -> dict[str, Any]:
    """Senate members and required stake/percentage."""
    return _get("/public/v1/general/senate-members/")


def global_search(query: str) -> Any:
    """Global search across subnets, validators, accounts."""
    return _get("/public/v1/general/global-search/", {"q": query})


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="TaoMarketCap API CLI — TAO market & network data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="All output is JSON. Docs: https://api.taomarketcap.com/developer/documentation/",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # market
    sub.add_parser("market", help="Current TAO price, supply, market cap (all-in-one)")

    # candles
    p = sub.add_parser("candles", help="OHLCV candlestick data")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--offset", type=int, default=0)

    # chart
    p = sub.add_parser("chart", help="Price chart series data")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--offset", type=int, default=0)

    # subnets
    p = sub.add_parser("subnets", help="Subnet list")
    p.add_argument("--netuid", type=int)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--offset", type=int, default=0)

    # subnet-detail
    p = sub.add_parser("subnet-detail", help="Specific subnet detail")
    p.add_argument("id", type=int, help="Subnet ID")

    # subnets-info
    sub.add_parser("subnets-info", help="Network-level subnet stats (lock cost, burn sums)")

    # subnet-tokenomics
    sub.add_parser("subnet-tokenomics", help="Recycled TAO amounts per subnet")

    # validators
    p = sub.add_parser("validators", help="Full validator list with APY/stake/fee")
    p.add_argument("--hotkey", type=str)
    p.add_argument("--subnet", type=int)
    p.add_argument("--apy-gte", type=float)
    p.add_argument("--apy-lte", type=float)

    # validator-detail
    p = sub.add_parser("validator-detail", help="Specific validator by hotkey")
    p.add_argument("hotkey", type=str)

    # validator-stakers
    p = sub.add_parser("validator-stakers", help="Stakers for a validator")
    p.add_argument("hotkey", type=str)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--offset", type=int, default=0)

    # coldkeys
    p = sub.add_parser("coldkeys", help="Coldkey accounts with balance/stake")
    p.add_argument("--search", type=str)
    p.add_argument("--subnet", type=int)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--offset", type=int, default=0)

    # coldkey-detail
    p = sub.add_parser("coldkey-detail", help="Specific coldkey detail")
    p.add_argument("id", type=str)

    # hotkeys
    p = sub.add_parser("hotkeys", help="Hotkey list")
    p.add_argument("--address", type=str)
    p.add_argument("--coldkey", type=str)
    p.add_argument("--subnet", type=int)
    p.add_argument("--limit", type=int, default=50)

    # accounts-info
    sub.add_parser("accounts-info", help="Aggregate account stats")

    # blocks
    p = sub.add_parser("blocks", help="Recent blocks")
    p.add_argument("--height", type=int)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--offset", type=int, default=0)

    # staking-activity
    p = sub.add_parser("staking-activity", help="Staking activity (add/remove/move)")
    p.add_argument("--hotkey", type=str)
    p.add_argument("--coldkey", type=str)
    p.add_argument("--subnet", type=int)
    p.add_argument("--function", type=str)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--offset", type=int, default=0)

    # stakes-added
    p = sub.add_parser("stakes-added", help="Stake-add transactions")
    p.add_argument("--hotkey", type=str)
    p.add_argument("--subnet", type=int)
    p.add_argument("--limit", type=int, default=50)

    # stakes-removed
    p = sub.add_parser("stakes-removed", help="Stake-remove transactions")
    p.add_argument("--hotkey", type=str)
    p.add_argument("--subnet", type=int)
    p.add_argument("--limit", type=int, default=50)

    # stakes-moved
    p = sub.add_parser("stakes-moved", help="Stake-move transactions between subnets")
    p.add_argument("--origin-hotkey", type=str)
    p.add_argument("--dest-hotkey", type=str)
    p.add_argument("--subnet-from", type=int)
    p.add_argument("--subnet-to", type=int)
    p.add_argument("--limit", type=int, default=50)

    # transfers
    p = sub.add_parser("transfers", help="TAO transfer transactions")
    p.add_argument("--coldkey", type=str)
    p.add_argument("--from-coldkey", type=str)
    p.add_argument("--to-coldkey", type=str)
    p.add_argument("--subnet", type=int)
    p.add_argument("--limit", type=int, default=50)

    # analytics-chain
    p = sub.add_parser("analytics-chain", help="Chain-level analytics time series")
    p.add_argument("--span", type=str, choices=["1h", "1d", "7d", "30d", "1y", "all"])
    p.add_argument("--from", dest="from_date", type=str)
    p.add_argument("--to", dest="to_date", type=str)

    # analytics-subnet
    p = sub.add_parser("analytics-subnet", help="Subnet-level analytics time series")
    p.add_argument("netuid", type=int)
    p.add_argument("--span", type=str, choices=["1h", "1d", "7d", "30d", "1y", "all"])

    # trending
    sub.add_parser("trending", help="All trending data")

    # trending-subnets
    sub.add_parser("trending-subnets", help="Trending subnets")

    # trending-validators
    sub.add_parser("trending-validators", help="Trending validators")

    # tax-report
    p = sub.add_parser("tax-report", help="Tax report for a coldkey")
    p.add_argument("coldkey", type=str)
    p.add_argument("--from", dest="from_date", type=str, help="Start date YYYY-MM-DD")
    p.add_argument("--to", dest="to_date", type=str, help="End date YYYY-MM-DD")

    # constants
    sub.add_parser("constants", help="Chain constants")

    # staking-constants
    sub.add_parser("staking-constants", help="DefaultFeeRate and DefaultMinStake")

    # senate
    sub.add_parser("senate", help="Senate members and required stake")

    # search
    p = sub.add_parser("search", help="Global search")
    p.add_argument("query", type=str)

    args = parser.parse_args()

    try:
        if args.cmd == "market":
            result = get_market_data()
        elif args.cmd == "candles":
            result = get_candle_data(args.limit, args.offset)
        elif args.cmd == "chart":
            result = get_chart_data(args.limit, args.offset)
        elif args.cmd == "subnets":
            result = get_subnets(args.netuid, args.limit, args.offset)
        elif args.cmd == "subnet-detail":
            result = get_subnet_detail(args.id)
        elif args.cmd == "subnets-info":
            result = get_subnets_info()
        elif args.cmd == "subnet-tokenomics":
            result = get_subnets_tokenomics()
        elif args.cmd == "validators":
            result = get_validators_full(args.hotkey, args.subnet, args.apy_gte, args.apy_lte)
        elif args.cmd == "validator-detail":
            result = get_validator_detail(args.hotkey)
        elif args.cmd == "validator-stakers":
            result = get_validator_stakers(args.hotkey, args.limit, args.offset)
        elif args.cmd == "coldkeys":
            result = get_coldkeys(args.search, args.subnet, args.limit, args.offset)
        elif args.cmd == "coldkey-detail":
            result = get_coldkey_detail(args.id)
        elif args.cmd == "hotkeys":
            result = get_hotkeys(args.address, args.coldkey, args.subnet, limit=args.limit)
        elif args.cmd == "accounts-info":
            result = get_accounts_info()
        elif args.cmd == "blocks":
            result = get_blocks(args.height, args.limit, args.offset)
        elif args.cmd == "staking-activity":
            result = get_staking_activity(args.hotkey, args.coldkey, args.subnet, args.function, args.limit, args.offset)
        elif args.cmd == "stakes-added":
            result = get_stakes_added(args.hotkey, args.subnet, args.limit)
        elif args.cmd == "stakes-removed":
            result = get_stakes_removed(args.hotkey, args.subnet, args.limit)
        elif args.cmd == "stakes-moved":
            result = get_stakes_moved(args.origin_hotkey, args.dest_hotkey, args.subnet_from, args.subnet_to, args.limit)
        elif args.cmd == "transfers":
            result = get_transfers(args.coldkey, args.from_coldkey, args.to_coldkey, args.subnet, args.limit)
        elif args.cmd == "analytics-chain":
            result = get_analytics_chain(args.span, args.from_date, args.to_date)
        elif args.cmd == "analytics-subnet":
            result = get_analytics_subnet(args.netuid, args.span)
        elif args.cmd == "trending":
            result = get_trending()
        elif args.cmd == "trending-subnets":
            result = get_trending_subnets()
        elif args.cmd == "trending-validators":
            result = get_trending_validators()
        elif args.cmd == "tax-report":
            result = get_tax_report(args.coldkey, args.from_date, args.to_date)
        elif args.cmd == "constants":
            result = get_constants()
        elif args.cmd == "staking-constants":
            result = get_staking_constants()
        elif args.cmd == "senate":
            result = get_senate_members()
        elif args.cmd == "search":
            result = global_search(args.query)
        else:
            parser.error(f"Unknown command: {args.cmd}")

        print(json.dumps(result, indent=2))
    except httpx.HTTPStatusError as e:
        print(json.dumps({"error": str(e), "status_code": e.response.status_code}))
        raise SystemExit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        raise SystemExit(1)
