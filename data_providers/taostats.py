#!/usr/bin/env python3
"""
Taostats API client — Bittensor on-chain analytics.

Base URL : https://api.taostats.io
Auth     : Authorization: <key>   (NO Bearer prefix — Bearer returns 401)
OpenAPI  : https://api.taostats.io/api/openapi.json
Version  : 1.8.52  (168 endpoints)
Docs     : https://docs.taostats.io/

Endpoint pattern: /api/{resource}/{scope}/v1
  (version number at END of path, not beginning)

Pagination: ?page=N&limit=N  →  {pagination: {current_page, per_page,
            total_items, total_pages, next_page}, data: [...]}
Time filters: timestamp_start / timestamp_end (ISO 8601 or epoch ms)
              block_start / block_end
"""

import os
import json
import httpx
from typing import Any, Optional
from pathlib import Path

BASE_URL = os.getenv("TAOSTATS_BASE_URL", "https://api.taostats.io")


# ── env / auth ────────────────────────────────────────────────────────────────

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
    key = os.getenv("TAOSTATS_API_KEY")
    if not key:
        raise EnvironmentError("TAOSTATS_API_KEY not set")
    return key


def _headers() -> dict:
    return {"Authorization": _get_api_key(), "accept": "application/json"}


def _get(path: str, params: Optional[dict] = None, *, _retries: int = 3) -> Any:
    import time
    p = {k: v for k, v in (params or {}).items() if v is not None}
    url = f"{BASE_URL}{path}"
    last_exc: Exception | None = None
    for attempt in range(_retries):
        try:
            r = httpx.get(url, params=p, headers=_headers(), timeout=30)
            if r.status_code == 403:
                raise httpx.HTTPStatusError(
                    f"403 Forbidden — endpoint may require a paid plan: {path}",
                    request=r.request, response=r,
                )
            r.raise_for_status()
            return r.json()
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
            last_exc = exc
            if attempt < _retries - 1:
                time.sleep(1.5 * (attempt + 1))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (429, 500, 502, 503, 504) and attempt < _retries - 1:
                last_exc = exc
                time.sleep(2.0 * (attempt + 1))
            else:
                raise
    raise last_exc  # type: ignore[misc]


# ── Subnets ───────────────────────────────────────────────────────────────────

def get_subnets(netuid=None, page=1, limit=50, order=None):
    """Full subnet state: emission, alpha, tempo, burn, validators, liquid_alpha, yuma3, fee_rate…"""
    return _get("/api/subnet/latest/v1", {"netuid": netuid, "page": page, "limit": limit, "order": order})

def get_subnet_pruning(netuid=None, is_immune=None, page=1, limit=50):
    """Subnet deregistration / pruning ranking."""
    return _get("/api/subnet/pruning/latest/v1", {"netuid": netuid, "is_immune": is_immune, "page": page, "limit": limit})

def get_subnet_history(netuid, frequency=None, block_start=None, block_end=None,
                       timestamp_start=None, timestamp_end=None, page=1, limit=50):
    """Historical subnet parameter snapshots."""
    return _get("/api/subnet/history/v1", {
        "netuid": netuid, "frequency": frequency,
        "block_start": block_start, "block_end": block_end,
        "timestamp_start": timestamp_start, "timestamp_end": timestamp_end,
        "page": page, "limit": limit,
    })

def get_subnet_registration_cost(as_history=False, page=1, limit=50):
    """Current or historical subnet registration cost (RAO)."""
    if as_history:
        return _get("/api/subnet/registration_cost/history/v1", {"page": page, "limit": limit})
    return _get("/api/subnet/registration_cost/latest/v1")

def get_subnet_emission(netuid=None, block_start=None, block_end=None,
                        timestamp_start=None, timestamp_end=None, page=1, limit=50):
    """Per-subnet emission data (dTAO era)."""
    return _get("/api/dtao/subnet_emission/v1", {
        "netuid": netuid, "block_start": block_start, "block_end": block_end,
        "timestamp_start": timestamp_start, "timestamp_end": timestamp_end,
        "page": page, "limit": limit,
    })

def get_neuron_registrations(netuid=None, uid=None, hotkey=None, coldkey=None,
                              block_start=None, block_end=None, timestamp_start=None,
                              timestamp_end=None, page=1, limit=50):
    """Neuron registration events."""
    return _get("/api/subnet/neuron/registration/v1", {
        "netuid": netuid, "uid": uid, "hotkey": hotkey, "coldkey": coldkey,
        "block_start": block_start, "block_end": block_end,
        "timestamp_start": timestamp_start, "timestamp_end": timestamp_end,
        "page": page, "limit": limit,
    })

def get_neuron_deregistrations(netuid=None, uid=None, hotkey=None,
                                block_start=None, block_end=None,
                                timestamp_start=None, timestamp_end=None, page=1, limit=50):
    """Neuron deregistration events."""
    return _get("/api/subnet/neuron/deregistration/v1", {
        "netuid": netuid, "uid": uid, "hotkey": hotkey,
        "block_start": block_start, "block_end": block_end,
        "timestamp_start": timestamp_start, "timestamp_end": timestamp_end,
        "page": page, "limit": limit,
    })

def get_subnet_distribution_coldkey(netuid: int):
    """Coldkey stake distribution for a subnet."""
    return _get("/api/subnet/distribution/coldkey/v1", {"netuid": netuid})

def get_subnet_distribution_incentive(netuid: int):
    """Miner incentive distribution for a subnet."""
    return _get("/api/subnet/distribution/incentive/v1", {"netuid": netuid})


# ── Neurons ───────────────────────────────────────────────────────────────────

def get_neurons(netuid=None, uid=None, hotkey=None, coldkey=None,
                is_immune=None, in_danger=None, has_dividends=None,
                has_incentive=None, page=1, limit=50):
    """Latest neuron state. Fields: uid, hotkey, coldkey, emission, incentive,
    dividends, trust, consensus, validator_permit, pruning_score, axon…"""
    return _get("/api/neuron/latest/v1", {
        "netuid": netuid, "uid": uid, "hotkey": hotkey, "coldkey": coldkey,
        "is_immune": is_immune, "in_danger": in_danger,
        "has_dividends": has_dividends, "has_incentive": has_incentive,
        "page": page, "limit": limit,
    })

def get_neuron_history(netuid=None, uid=None, hotkey=None, coldkey=None,
                       is_immune=None, in_danger=None, page=1, limit=50):
    """Historical neuron snapshots."""
    return _get("/api/neuron/history/v1", {
        "netuid": netuid, "uid": uid, "hotkey": hotkey, "coldkey": coldkey,
        "is_immune": is_immune, "in_danger": in_danger, "page": page, "limit": limit,
    })

def get_neuron_aggregated(netuid=None, page=1, limit=50):
    """Aggregated neuron stats per subnet."""
    return _get("/api/neuron/aggregated/latest/v1", {"netuid": netuid, "page": page, "limit": limit})


# ── Metagraph ─────────────────────────────────────────────────────────────────

def get_metagraph(netuid=None, uid=None, hotkey=None, coldkey=None,
                  active=None, validator_permit=None, is_immunity_period=None,
                  page=1, limit=256):
    """Full metagraph: hotkey, coldkey, uid, stake, trust, validator_trust,
    consensus, incentive, dividends, emission, axon…"""
    return _get("/api/metagraph/latest/v1", {
        "netuid": netuid, "uid": uid, "hotkey": hotkey, "coldkey": coldkey,
        "active": active, "validator_permit": validator_permit,
        "is_immunity_period": is_immunity_period, "page": page, "limit": limit,
    })

def get_metagraph_history(netuid=None, uid=None, hotkey=None, coldkey=None,
                          block_start=None, block_end=None, timestamp_start=None,
                          timestamp_end=None, page=1, limit=50):
    """Historical metagraph snapshots."""
    return _get("/api/metagraph/history/v1", {
        "netuid": netuid, "uid": uid, "hotkey": hotkey, "coldkey": coldkey,
        "block_start": block_start, "block_end": block_end,
        "timestamp_start": timestamp_start, "timestamp_end": timestamp_end,
        "page": page, "limit": limit,
    })

def get_root_metagraph(hotkey=None, page=1, limit=50):
    """Root subnet (netuid=0) metagraph."""
    return _get("/api/metagraph/root/latest/v1", {"hotkey": hotkey, "page": page, "limit": limit})


# ── Validators ────────────────────────────────────────────────────────────────

def get_validators(hotkey=None, stake_min=None, stake_max=None,
                   apr_min=None, apr_max=None, page=1, limit=50, order=None):
    """Validator state: hotkey, coldkey, name, rank, stake, nominators, apr,
    nominator_return_per_k, pending_emission, permits, subnet_dominance…"""
    return _get("/api/validator/latest/v1", {
        "hotkey": hotkey, "stake_min": stake_min, "stake_max": stake_max,
        "apr_min": apr_min, "apr_max": apr_max,
        "page": page, "limit": limit, "order": order,
    })

def get_validator_history(hotkey=None, block_start=None, block_end=None,
                          timestamp_start=None, timestamp_end=None, page=1, limit=50):
    """Historical validator snapshots."""
    return _get("/api/validator/history/v1", {
        "hotkey": hotkey, "block_start": block_start, "block_end": block_end,
        "timestamp_start": timestamp_start, "timestamp_end": timestamp_end,
        "page": page, "limit": limit,
    })

def get_validator_performance(hotkey=None, netuid=None, page=1, limit=50):
    """Validator performance metrics per subnet."""
    return _get("/api/validator/performance/v1", {
        "hotkey": hotkey, "netuid": netuid, "page": page, "limit": limit,
    })

def get_validator_metrics(hotkey=None, coldkey=None, netuid=None, page=1, limit=50):
    """Validator metrics (emission, dividends, take, stake)."""
    return _get("/api/validator/metrics/latest/v1", {
        "hotkey": hotkey, "coldkey": coldkey, "netuid": netuid,
        "page": page, "limit": limit,
    })

def get_validator_weights(hotkey=None, netuid=None, uid=None, page=1, limit=50, v2=False):
    """Current validator weights (use v2=True for dTAO era)."""
    path = "/api/validator/weights/latest/v2" if v2 else "/api/validator/weights/latest/v1"
    return _get(path, {"hotkey": hotkey, "netuid": netuid, "uid": uid, "page": page, "limit": limit})

def get_hotkey_family(hotkey=None, netuid=None, page=1, limit=50):
    """Parent/child hotkey relationships (childkey delegations)."""
    return _get("/api/hotkey/family/latest/v1", {
        "hotkey": hotkey, "netuid": netuid, "page": page, "limit": limit,
    })


# ── Miner ─────────────────────────────────────────────────────────────────────

def get_miner_weights(netuid=None, miner_uid=None, validator_uid=None,
                      miner_hotkey=None, validator_hotkey=None, page=1, limit=50):
    """Current miner weights set by validators."""
    return _get("/api/miner/weights/latest/v1", {
        "netuid": netuid, "miner_uid": miner_uid, "validator_uid": validator_uid,
        "miner_hotkey": miner_hotkey, "validator_hotkey": validator_hotkey,
        "page": page, "limit": limit,
    })

def get_miner_weights_history(netuid=None, miner_uid=None, validator_uid=None,
                               miner_hotkey=None, validator_hotkey=None,
                               block_start=None, block_end=None, page=1, limit=50):
    """Historical miner weights."""
    return _get("/api/miner/weights/history/v1", {
        "netuid": netuid, "miner_uid": miner_uid, "validator_uid": validator_uid,
        "miner_hotkey": miner_hotkey, "validator_hotkey": validator_hotkey,
        "block_start": block_start, "block_end": block_end, "page": page, "limit": limit,
    })

def get_miner_by_coldkey(coldkey: str, days: Optional[int] = None):
    """Miners associated with a coldkey."""
    return _get("/api/miner/coldkey/v1", {"coldkey": coldkey, "days": days})


# ── dTAO — Pools (AMM) ────────────────────────────────────────────────────────

def get_dtao_pools(netuid=None, page=1, limit=50, order=None):
    """Current dTAO subnet AMM pool state: price, reserves, volume, alpha supply…"""
    return _get("/api/dtao/pool/latest/v1", {
        "netuid": netuid, "page": page, "limit": limit, "order": order,
    })

def get_dtao_pool_history(netuid=None, frequency=None, block_start=None, block_end=None,
                          timestamp_start=None, timestamp_end=None, page=1, limit=50):
    """Historical dTAO pool snapshots."""
    return _get("/api/dtao/pool/history/v1", {
        "netuid": netuid, "frequency": frequency,
        "block_start": block_start, "block_end": block_end,
        "timestamp_start": timestamp_start, "timestamp_end": timestamp_end,
        "page": page, "limit": limit,
    })

def get_dtao_pool_total_price(frequency=None, page=1, limit=50):
    """Sum of all dTAO subnet prices (total alpha market cap in TAO)."""
    return _get("/api/dtao/pool/total_price/latest/v1")

def get_dtao_slippage(netuid: int, input_tokens: float, direction: str = "buy"):
    """Calculate slippage for a dTAO swap. direction: 'buy' or 'sell'."""
    return _get("/api/dtao/slippage/v1", {
        "netuid": netuid, "input_tokens": input_tokens, "direction": direction,
    })

def get_dtao_tao_flow(netuid=None, block_start=None, block_end=None,
                      timestamp_start=None, timestamp_end=None):
    """TAO flow in/out of dTAO pools."""
    return _get("/api/dtao/tao_flow/v1", {
        "netuid": netuid, "block_start": block_start, "block_end": block_end,
        "timestamp_start": timestamp_start, "timestamp_end": timestamp_end,
    })

def get_dtao_trades(coldkey=None, extrinsic_id=None, from_name=None, to_name=None,
                    tao_value_min=None, tao_value_max=None,
                    block_number=None, block_start=None, block_end=None,
                    timestamp_start=None, timestamp_end=None, page=1, limit=50):
    """dTAO alpha buy/sell trade history.

    timestamp_start / timestamp_end: Unix seconds (per OpenAPI for /api/dtao/trade/v1).
    """
    return _get("/api/dtao/trade/v1", {
        "coldkey": coldkey, "extrinsic_id": extrinsic_id,
        "from_name": from_name, "to_name": to_name,
        "tao_value_min": tao_value_min, "tao_value_max": tao_value_max,
        "block_number": block_number,
        "block_start": block_start, "block_end": block_end,
        "timestamp_start": timestamp_start, "timestamp_end": timestamp_end,
        "page": page, "limit": limit,
    })


# ── dTAO — Stake & Alpha Shares ───────────────────────────────────────────────

def get_dtao_stake_balance(coldkey=None, hotkey=None, netuid=None,
                           balance_min=None, balance_as_tao_min=None, page=1, limit=50):
    """Current dTAO alpha stake balances per coldkey/hotkey/subnet."""
    return _get("/api/dtao/stake_balance/latest/v1", {
        "coldkey": coldkey, "hotkey": hotkey, "netuid": netuid,
        "balance_min": balance_min, "balance_as_tao_min": balance_as_tao_min,
        "page": page, "limit": limit,
    })

def get_dtao_stake_balance_history(coldkey=None, hotkey=None, netuid=None,
                                   block_start=None, block_end=None,
                                   timestamp_start=None, timestamp_end=None, page=1, limit=50):
    """Historical dTAO alpha stake balance snapshots."""
    return _get("/api/dtao/stake_balance/history/v1", {
        "coldkey": coldkey, "hotkey": hotkey, "netuid": netuid,
        "block_start": block_start, "block_end": block_end,
        "timestamp_start": timestamp_start, "timestamp_end": timestamp_end,
        "page": page, "limit": limit,
    })

def get_dtao_stake_portfolio(coldkey=None, hotkey=None, netuid=None, days=None,
                              balance_as_tao_min=None, page=1, limit=50):
    """dTAO stake portfolio overview (PnL, current value…)."""
    return _get("/api/dtao/stake_balance/portfolio/v1", {
        "coldkey": coldkey, "hotkey": hotkey, "netuid": netuid, "days": days,
        "balance_as_tao_min": balance_as_tao_min, "page": page, "limit": limit,
    })

def get_dtao_hotkey_alpha_shares(hotkey=None, netuid=None,
                                  alpha_min=None, page=1, limit=50):
    """Current hotkey alpha shares per subnet."""
    return _get("/api/dtao/hotkey_alpha_shares/latest/v1", {
        "hotkey": hotkey, "netuid": netuid, "alpha_min": alpha_min,
        "page": page, "limit": limit,
    })

def get_dtao_coldkey_alpha_shares(coldkey=None, hotkey=None, netuid=None,
                                   alpha_min=None, page=1, limit=50):
    """Current coldkey alpha shares (all validators staked to)."""
    return _get("/api/dtao/coldkey_alpha_shares/latest/v1", {
        "coldkey": coldkey, "hotkey": hotkey, "netuid": netuid,
        "alpha_min": alpha_min, "page": page, "limit": limit,
    })

def get_dtao_hotkey_emissions(hotkey=None, netuid=None, block_start=None,
                               block_end=None, timestamp_start=None, timestamp_end=None,
                               page=1, limit=50):
    """Hotkey emission events (alpha emitted per epoch)."""
    return _get("/api/dtao/hotkey_emission/v1", {
        "hotkey": hotkey, "netuid": netuid,
        "block_start": block_start, "block_end": block_end,
        "timestamp_start": timestamp_start, "timestamp_end": timestamp_end,
        "page": page, "limit": limit,
    })

def get_dtao_burned_alpha(netuid=None, hotkey=None, coldkey=None,
                           burn_type=None, block_start=None, block_end=None, page=1, limit=50):
    """Burned alpha events."""
    return _get("/api/dtao/burned_alpha/v1", {
        "netuid": netuid, "hotkey": hotkey, "coldkey": coldkey,
        "burn_type": burn_type, "block_start": block_start, "block_end": block_end,
        "page": page, "limit": limit,
    })


# ── dTAO — Validators (dTAO-specific) ────────────────────────────────────────

def get_dtao_validators(hotkey=None, page=1, limit=50, order=None):
    """dTAO validator state (post-dTAO launch metrics)."""
    return _get("/api/dtao/validator/latest/v1", {
        "hotkey": hotkey, "page": page, "limit": limit, "order": order,
    })

def get_dtao_validator_performance(hotkey=None, netuid=None, validator_type=None,
                                    page=1, limit=50):
    """dTAO validator performance per subnet: dividends, take, alpha earned…"""
    return _get("/api/dtao/validator/performance/latest/v1", {
        "hotkey": hotkey, "netuid": netuid, "validator_type": validator_type,
        "page": page, "limit": limit,
    })

def get_dtao_validator_yield(hotkey=None, netuid=None, min_stake=None, page=1, limit=50):
    """dTAO validator yield/APY per subnet."""
    return _get("/api/dtao/validator/yield/latest/v1", {
        "hotkey": hotkey, "netuid": netuid, "min_stake": min_stake,
        "page": page, "limit": limit,
    })

def get_dtao_validator_dividends(hotkey=None, netuid=None, page=1, limit=50):
    """Current dTAO validator dividend rates."""
    return _get("/api/dtao/validator/dividends/latest/v1", {
        "hotkey": hotkey, "netuid": netuid, "page": page, "limit": limit,
    })


# ── dTAO — Liquidity Positions ────────────────────────────────────────────────

def get_dtao_liquidity_positions(coldkey=None, netuid=None, status=None, page=1, limit=50):
    """Active/closed dTAO liquidity positions."""
    return _get("/api/dtao/liquidity/position/v1", {
        "coldkey": coldkey, "netuid": netuid, "status": status,
        "page": page, "limit": limit,
    })

def get_dtao_liquidity_distribution(netuid: int, min_price=None, max_price=None,
                                     num_points=None, log_scale=None):
    """Price distribution of liquidity in a dTAO pool."""
    return _get("/api/dtao/liquidity/distribution/v1", {
        "netuid": netuid, "min_price": min_price, "max_price": max_price,
        "num_points": num_points, "log_scale": log_scale,
    })


# ── Price ─────────────────────────────────────────────────────────────────────

def get_price(asset: str = "tao"):
    """Current TAO price. Returns unwrapped single object.
    Fields: price, volume_24h, market_cap, percent_change_1h/24h/7d/30d/60d/90d,
    circulating_supply, max_supply, fully_diluted_market_cap…"""
    data = _get("/api/price/latest/v1", {"asset": asset})
    if isinstance(data, dict) and "data" in data and data["data"]:
        return data["data"][0]
    return data

def get_price_history(asset="tao", timestamp_start=None, timestamp_end=None,
                      page=1, limit=50, order=None):
    """Historical TAO price snapshots."""
    return _get("/api/price/history/v1", {
        "asset": asset, "timestamp_start": timestamp_start,
        "timestamp_end": timestamp_end, "page": page, "limit": limit, "order": order,
    })

def get_price_ohlc(asset="tao", period="1d", timestamp_start=None,
                   timestamp_end=None, page=1, limit=50):
    """OHLC candlestick price data. period: 1m, 5m, 15m, 1h, 4h, 1d, 1w."""
    return _get("/api/price/ohlc/v1", {
        "asset": asset, "period": period,
        "timestamp_start": timestamp_start, "timestamp_end": timestamp_end,
        "page": page, "limit": limit,
    })


# ── Accounts / Balances ───────────────────────────────────────────────────────

def get_accounts(address=None, balance_free_min=None, balance_staked_min=None,
                 page=1, limit=50):
    """Account balances and stake totals."""
    return _get("/api/account/latest/v1", {
        "address": address, "balance_free_min": balance_free_min,
        "balance_staked_min": balance_staked_min, "page": page, "limit": limit,
    })

def get_account_history(address=None, block_start=None, block_end=None,
                        timestamp_start=None, timestamp_end=None, page=1, limit=50):
    """Historical account balance snapshots."""
    return _get("/api/account/history/v1", {
        "address": address, "block_start": block_start, "block_end": block_end,
        "timestamp_start": timestamp_start, "timestamp_end": timestamp_end,
        "page": page, "limit": limit,
    })

def get_stake_balance_history(coldkey=None, hotkey=None, block_start=None,
                               block_end=None, timestamp_start=None, timestamp_end=None,
                               page=1, limit=50):
    """Historical stake balance (legacy pre-dTAO)."""
    return _get("/api/stake_balance/history/v1", {
        "coldkey": coldkey, "hotkey": hotkey,
        "block_start": block_start, "block_end": block_end,
        "timestamp_start": timestamp_start, "timestamp_end": timestamp_end,
        "page": page, "limit": limit,
    })

def get_identity(address=None, validator_hotkey=None, page=1, limit=50):
    """On-chain identity (name, description, url…) for addresses."""
    return _get("/api/identity/latest/v1", {
        "address": address, "validator_hotkey": validator_hotkey,
        "page": page, "limit": limit,
    })


# ── Transfers & Staking Events ────────────────────────────────────────────────

def get_transfers(address=None, from_addr=None, to_addr=None,
                  amount_min=None, amount_max=None,
                  block_start=None, block_end=None,
                  timestamp_start=None, timestamp_end=None,
                  transaction_hash=None, page=1, limit=50):
    """TAO transfer history."""
    return _get("/api/transfer/v1", {
        "address": address, "from": from_addr, "to": to_addr,
        "amount_min": amount_min, "amount_max": amount_max,
        "block_start": block_start, "block_end": block_end,
        "timestamp_start": timestamp_start, "timestamp_end": timestamp_end,
        "transaction_hash": transaction_hash, "page": page, "limit": limit,
    })

def get_delegations(nominator=None, delegate=None, action=None,
                    amount_min=None, amount_max=None, page=1, limit=50):
    """Delegation / staking events (add/remove stake, legacy)."""
    return _get("/api/delegation/v1", {
        "nominator": nominator, "delegate": delegate, "action": action,
        "amount_min": amount_min, "amount_max": amount_max,
        "page": page, "limit": limit,
    })

def get_stake_events(coldkey=None, hotkey=None, block_start=None, block_end=None,
                     timestamp_start=None, timestamp_end=None, page=1, limit=50):
    """Raw stake add/remove extrinsic events."""
    return _get("/api/stake/v1", {
        "coldkey": coldkey, "hotkey": hotkey,
        "block_start": block_start, "block_end": block_end,
        "timestamp_start": timestamp_start, "timestamp_end": timestamp_end,
        "page": page, "limit": limit,
    })


# ── Blocks & Chain ────────────────────────────────────────────────────────────

def get_blocks(block_number=None, block_start=None, block_end=None,
               timestamp_start=None, timestamp_end=None,
               hash=None, spec_version=None, page=1, limit=10):
    """Blocks: block_number, hash, timestamp, validator, events_count, spec_version…"""
    return _get("/api/block/v1", {
        "block_number": block_number, "block_start": block_start,
        "block_end": block_end, "timestamp_start": timestamp_start,
        "timestamp_end": timestamp_end, "hash": hash,
        "spec_version": spec_version, "page": page, "limit": limit,
    })

def get_block_emission(block_number=None, block_start=None, block_end=None,
                       timestamp_start=None, timestamp_end=None, page=1, limit=50):
    """Block emission records."""
    return _get("/api/block/emission/v1", {
        "block_number": block_number, "block_start": block_start,
        "block_end": block_end, "timestamp_start": timestamp_start,
        "timestamp_end": timestamp_end, "page": page, "limit": limit,
    })

def get_extrinsics(block_number=None, block_start=None, block_end=None,
                   timestamp_start=None, timestamp_end=None,
                   hash=None, full_name=None, page=1, limit=50):
    """Chain extrinsics."""
    return _get("/api/extrinsic/v1", {
        "block_number": block_number, "block_start": block_start,
        "block_end": block_end, "timestamp_start": timestamp_start,
        "timestamp_end": timestamp_end, "hash": hash,
        "full_name": full_name, "page": page, "limit": limit,
    })

def get_events(block_number=None, block_start=None, block_end=None,
               timestamp_start=None, timestamp_end=None,
               pallet=None, name=None, page=1, limit=50):
    """Chain events."""
    return _get("/api/event/v1", {
        "block_number": block_number, "block_start": block_start,
        "block_end": block_end, "timestamp_start": timestamp_start,
        "timestamp_end": timestamp_end, "pallet": pallet,
        "name": name, "page": page, "limit": limit,
    })

def get_stats():
    """Current network-wide statistics."""
    return _get("/api/stats/latest/v1")

def get_network_parameters():
    """All current network/pallet parameters."""
    return _get("/api/network_parameter/latest/v1")

def get_status():
    """API service status."""
    return _get("/api/status/v1")

def get_live_block_head():
    """Latest block from live node (real-time)."""
    return _get("/api/v1/live/blocks/head")

def get_live_block(height: int):
    """Specific block from live node."""
    return _get(f"/api/v1/live/blocks/{height}")


# ── Accounting / Tax ──────────────────────────────────────────────────────────

def get_accounting(coldkey: str, hotkey=None, date_start=None, date_end=None):
    """Transaction accounting for a coldkey (income, cost basis…)."""
    return _get("/api/accounting/v1", {
        "coldkey": coldkey, "hotkey": hotkey,
        "date_start": date_start, "date_end": date_end,
    })

def get_tax_report(coldkey: str, token="tao", date_start=None, date_end=None):
    """Tax report for a coldkey (gain/loss events)."""
    return _get("/api/accounting/tax/v1", {
        "coldkey": coldkey, "token": token,
        "date_start": date_start, "date_end": date_end,
    })


# ── OTC Market ────────────────────────────────────────────────────────────────

def get_otc_listings(netuid=None, seller=None, hotkey=None, status=None, page=1, limit=50):
    """OTC alpha listings for sale (v2)."""
    return _get("/api/otc/listing/v2", {
        "netuid": netuid, "seller": seller, "hotkey": hotkey,
        "status": status, "page": page, "limit": limit,
    })

def get_otc_trades(netuid=None, seller=None, buyer=None, page=1, limit=50):
    """Completed OTC trades."""
    return _get("/api/otc/trade/v2", {
        "netuid": netuid, "seller": seller, "buyer": buyer,
        "page": page, "limit": limit,
    })

def get_otc_offers(netuid=None, buyer=None, status=None, page=1, limit=50):
    """OTC buy offers (v2)."""
    return _get("/api/otc/offer/v2", {
        "netuid": netuid, "buyer": buyer, "status": status,
        "page": page, "limit": limit,
    })


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    P = argparse.ArgumentParser(
        description="Taostats API CLI — 168-endpoint Bittensor analytics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="All output is JSON. OpenAPI: https://api.taostats.io/api/openapi.json",
    )
    S = P.add_subparsers(dest="cmd", required=True)

    def _add(name, help_, **kw):
        p = S.add_parser(name, help=help_)
        for flag, cfg in kw.items():
            p.add_argument(f"--{flag}", **cfg)
        return p

    def _paged(p):
        p.add_argument("--page", type=int, default=1)
        p.add_argument("--limit", type=int, default=50)
        return p

    def _timerange(p):
        p.add_argument("--block-start", type=int)
        p.add_argument("--block-end", type=int)
        p.add_argument("--ts-start", type=str, help="ISO 8601 timestamp_start")
        p.add_argument("--ts-end", type=str, help="ISO 8601 timestamp_end")
        return p

    def _trade_ts(v):
        """dtao/trade/v1 attend des timestamps Unix en secondes (entier)."""
        if v is None:
            return None
        s = str(v).strip()
        return int(s) if s.isdigit() else v

    # ── Status
    S.add_parser("status", help="API service status")
    S.add_parser("stats", help="Network-wide statistics")
    S.add_parser("network-params", help="All network/pallet parameters")

    # ── Price
    p = S.add_parser("price", help="Current TAO price")
    p.add_argument("--asset", default="tao")

    p = _paged(S.add_parser("price-history", help="Historical TAO price"))
    p.add_argument("--asset", default="tao")
    _timerange(p)

    p = _paged(S.add_parser("price-ohlc", help="OHLC candlestick data"))
    p.add_argument("--asset", default="tao")
    p.add_argument("--period", default="1d",
                   choices=["1m","5m","15m","1h","4h","1d","1w"])
    _timerange(p)

    # ── Subnets
    p = _paged(S.add_parser("subnets", help="Full subnet state"))
    p.add_argument("--netuid", type=int)
    p.add_argument("--order", type=str)

    p = _paged(S.add_parser("subnet-pruning", help="Deregistration ranking"))
    p.add_argument("--netuid", type=int)

    p = _paged(_timerange(S.add_parser("subnet-history", help="Historical subnet snapshots")))
    p.add_argument("--netuid", type=int, required=True)
    p.add_argument("--frequency", type=str)

    S.add_parser("subnet-registration-cost", help="Current subnet registration cost")

    p = _paged(_timerange(S.add_parser("subnet-emission", help="Per-subnet emission")))
    p.add_argument("--netuid", type=int)

    p = S.add_parser("subnet-distribution", help="Coldkey or incentive distribution")
    p.add_argument("netuid", type=int)
    p.add_argument("--type", dest="dtype", default="coldkey",
                   choices=["coldkey", "incentive", "ip"])

    p = _paged(_timerange(S.add_parser("neuron-registrations", help="Neuron registration events")))
    p.add_argument("--netuid", type=int); p.add_argument("--hotkey"); p.add_argument("--coldkey")

    p = _paged(_timerange(S.add_parser("neuron-deregistrations", help="Neuron deregistration events")))
    p.add_argument("--netuid", type=int); p.add_argument("--hotkey")

    # ── Neurons
    p = _paged(S.add_parser("neurons", help="Neuron state"))
    p.add_argument("--netuid", type=int); p.add_argument("--uid", type=int)
    p.add_argument("--hotkey"); p.add_argument("--coldkey")
    p.add_argument("--is-immune", type=bool); p.add_argument("--in-danger", type=bool)

    p = _paged(S.add_parser("neuron-history", help="Historical neuron snapshots"))
    p.add_argument("--netuid", type=int); p.add_argument("--uid", type=int)
    p.add_argument("--hotkey"); p.add_argument("--coldkey")

    p = _paged(S.add_parser("neuron-aggregated", help="Aggregated neuron stats"))
    p.add_argument("--netuid", type=int)

    # ── Metagraph
    p = _paged(S.add_parser("metagraph", help="Full metagraph for a subnet"))
    p.add_argument("--netuid", type=int, required=True); p.add_argument("--hotkey")
    p.add_argument("--uid", type=int); p.add_argument("--active", type=bool)

    p = _paged(_timerange(S.add_parser("metagraph-history", help="Historical metagraph")))
    p.add_argument("--netuid", type=int); p.add_argument("--hotkey"); p.add_argument("--uid", type=int)

    p = _paged(S.add_parser("root-metagraph", help="Root subnet metagraph"))
    p.add_argument("--hotkey")

    # ── Validators
    p = _paged(S.add_parser("validators", help="Validator state (APR, stake, nominators)"))
    p.add_argument("--hotkey"); p.add_argument("--stake-min", type=float)
    p.add_argument("--apr-min", type=float); p.add_argument("--apr-max", type=float)
    p.add_argument("--order")

    p = _paged(_timerange(S.add_parser("validator-history", help="Historical validator snapshots")))
    p.add_argument("--hotkey")

    p = _paged(S.add_parser("validator-performance", help="Validator performance per subnet"))
    p.add_argument("--hotkey"); p.add_argument("--netuid", type=int)

    p = _paged(S.add_parser("validator-metrics", help="Validator metrics"))
    p.add_argument("--hotkey"); p.add_argument("--coldkey"); p.add_argument("--netuid", type=int)

    p = _paged(S.add_parser("validator-weights", help="Current validator weights"))
    p.add_argument("--hotkey"); p.add_argument("--netuid", type=int); p.add_argument("--uid", type=int)
    p.add_argument("--v2", action="store_true", help="Use v2 (dTAO era)")

    p = _paged(S.add_parser("hotkey-family", help="Parent/child hotkey relationships"))
    p.add_argument("--hotkey"); p.add_argument("--netuid", type=int)

    # ── Miner
    p = _paged(S.add_parser("miner-weights", help="Current miner weights"))
    p.add_argument("--netuid", type=int); p.add_argument("--miner-hotkey")
    p.add_argument("--validator-hotkey"); p.add_argument("--miner-uid", type=int)

    p = S.add_parser("miner-coldkey", help="Miners for a coldkey")
    p.add_argument("coldkey"); p.add_argument("--days", type=int)

    # ── dTAO Pools
    p = _paged(S.add_parser("dtao-pools", help="dTAO AMM pool state"))
    p.add_argument("--netuid", type=int); p.add_argument("--order")

    p = _paged(_timerange(S.add_parser("dtao-pool-history", help="dTAO pool history")))
    p.add_argument("--netuid", type=int); p.add_argument("--frequency")

    S.add_parser("dtao-pool-total-price", help="Sum of all subnet prices")

    p = S.add_parser("dtao-slippage", help="Calculate swap slippage")
    p.add_argument("netuid", type=int)
    p.add_argument("amount", type=float, help="Input tokens")
    p.add_argument("--direction", default="buy", choices=["buy","sell"])

    p = _timerange(S.add_parser("dtao-tao-flow", help="TAO flow in/out of pools"))
    p.add_argument("--netuid", type=int)

    p = _paged(_timerange(S.add_parser("dtao-trades", help="dTAO alpha buy/sell trades")))
    p.add_argument("--coldkey"); p.add_argument("--from-name"); p.add_argument("--to-name")
    p.add_argument("--tao-min", type=float); p.add_argument("--tao-max", type=float)
    p.add_argument("--block-number", type=int)

    # ── dTAO Stake
    p = _paged(S.add_parser("dtao-stake", help="Current dTAO alpha stake balances"))
    p.add_argument("--coldkey"); p.add_argument("--hotkey"); p.add_argument("--netuid", type=int)
    p.add_argument("--balance-as-tao-min", type=float)

    p = _paged(_timerange(S.add_parser("dtao-stake-history", help="Historical dTAO stake")))
    p.add_argument("--coldkey"); p.add_argument("--hotkey"); p.add_argument("--netuid", type=int)

    p = _paged(S.add_parser("dtao-portfolio", help="dTAO stake portfolio (PnL)"))
    p.add_argument("--coldkey"); p.add_argument("--hotkey"); p.add_argument("--netuid", type=int)
    p.add_argument("--days", type=int)

    p = _paged(S.add_parser("dtao-hotkey-alpha", help="Hotkey alpha shares per subnet"))
    p.add_argument("--hotkey"); p.add_argument("--netuid", type=int)

    p = _paged(S.add_parser("dtao-coldkey-alpha", help="Coldkey alpha shares"))
    p.add_argument("--coldkey"); p.add_argument("--hotkey"); p.add_argument("--netuid", type=int)

    p = _paged(_timerange(S.add_parser("dtao-emissions", help="Hotkey emission events")))
    p.add_argument("--hotkey"); p.add_argument("--netuid", type=int)

    p = _paged(S.add_parser("dtao-burned-alpha", help="Burned alpha events"))
    p.add_argument("--netuid", type=int); p.add_argument("--hotkey"); p.add_argument("--coldkey")
    p.add_argument("--burn-type")

    # ── dTAO Validators
    p = _paged(S.add_parser("dtao-validators", help="dTAO validator state"))
    p.add_argument("--hotkey"); p.add_argument("--order")

    p = _paged(S.add_parser("dtao-validator-performance", help="dTAO validator performance per subnet"))
    p.add_argument("--hotkey"); p.add_argument("--netuid", type=int)

    p = _paged(S.add_parser("dtao-validator-yield", help="dTAO validator APY per subnet"))
    p.add_argument("--hotkey"); p.add_argument("--netuid", type=int)
    p.add_argument("--min-stake", type=float)

    p = _paged(S.add_parser("dtao-validator-dividends", help="dTAO validator dividend rates"))
    p.add_argument("--hotkey"); p.add_argument("--netuid", type=int)

    # ── dTAO Liquidity
    p = _paged(S.add_parser("dtao-liquidity-positions", help="dTAO liquidity positions"))
    p.add_argument("--coldkey"); p.add_argument("--netuid", type=int); p.add_argument("--status")

    p = S.add_parser("dtao-liquidity-distribution", help="Price distribution of liquidity in a pool")
    p.add_argument("netuid", type=int)
    p.add_argument("--min-price", type=float); p.add_argument("--max-price", type=float)
    p.add_argument("--num-points", type=int)

    # ── Accounts
    p = _paged(S.add_parser("accounts", help="Account balances and stake"))
    p.add_argument("--address"); p.add_argument("--balance-free-min", type=float)
    p.add_argument("--balance-staked-min", type=float)

    p = _paged(_timerange(S.add_parser("account-history", help="Historical account snapshots")))
    p.add_argument("--address")

    p = S.add_parser("identity", help="On-chain identity for an address")
    p.add_argument("--address"); p.add_argument("--validator-hotkey")

    # ── Transfers & Staking
    p = _paged(_timerange(S.add_parser("transfers", help="TAO transfers")))
    p.add_argument("--address"); p.add_argument("--from", dest="from_addr")
    p.add_argument("--to", dest="to_addr"); p.add_argument("--amount-min", type=float)

    p = _paged(S.add_parser("delegations", help="Delegation/staking events"))
    p.add_argument("--nominator"); p.add_argument("--delegate"); p.add_argument("--action")

    p = _paged(_timerange(S.add_parser("stake-events", help="Raw stake add/remove events")))
    p.add_argument("--coldkey"); p.add_argument("--hotkey")

    # ── Blocks & Chain
    p = _paged(_timerange(S.add_parser("blocks", help="Blocks")))
    p.add_argument("--block-number", type=int); p.add_argument("--hash")

    p = _paged(_timerange(S.add_parser("block-emission", help="Block emission records")))
    p.add_argument("--block-number", type=int)

    p = _paged(_timerange(S.add_parser("extrinsics", help="Chain extrinsics")))
    p.add_argument("--hash"); p.add_argument("--full-name")

    p = _paged(_timerange(S.add_parser("events", help="Chain events")))
    p.add_argument("--pallet"); p.add_argument("--name")

    S.add_parser("live-block-head", help="Latest live block from node")
    p = S.add_parser("live-block", help="Specific block from live node")
    p.add_argument("height", type=int)

    # ── Accounting
    p = S.add_parser("accounting", help="Transaction accounting for a coldkey")
    p.add_argument("coldkey"); p.add_argument("--hotkey")
    p.add_argument("--from", dest="date_start"); p.add_argument("--to", dest="date_end")

    p = S.add_parser("tax-report", help="Tax report for a coldkey")
    p.add_argument("coldkey"); p.add_argument("--token", default="tao")
    p.add_argument("--from", dest="date_start"); p.add_argument("--to", dest="date_end")

    # ── OTC
    p = _paged(S.add_parser("otc-listings", help="OTC alpha listings for sale"))
    p.add_argument("--netuid", type=int); p.add_argument("--seller"); p.add_argument("--status")

    p = _paged(S.add_parser("otc-trades", help="Completed OTC trades"))
    p.add_argument("--netuid", type=int); p.add_argument("--seller"); p.add_argument("--buyer")

    p = _paged(S.add_parser("otc-offers", help="OTC buy offers"))
    p.add_argument("--netuid", type=int); p.add_argument("--buyer"); p.add_argument("--status")

    args = P.parse_args()
    a = vars(args)

    try:
        cmd = a.pop("cmd")
        dispatch = {
            "status":                   lambda: get_status(),
            "stats":                    lambda: get_stats(),
            "network-params":           lambda: get_network_parameters(),
            "price":                    lambda: get_price(a["asset"]),
            "price-history":            lambda: get_price_history(a["asset"], a.get("ts_start"), a.get("ts_end"), a["page"], a["limit"]),
            "price-ohlc":               lambda: get_price_ohlc(a["asset"], a["period"], a.get("ts_start"), a.get("ts_end"), a["page"], a["limit"]),
            "subnets":                  lambda: get_subnets(a.get("netuid"), a["page"], a["limit"], a.get("order")),
            "subnet-pruning":           lambda: get_subnet_pruning(a.get("netuid"), page=a["page"], limit=a["limit"]),
            "subnet-history":           lambda: get_subnet_history(a["netuid"], a.get("frequency"), a.get("block_start"), a.get("block_end"), a.get("ts_start"), a.get("ts_end"), a["page"], a["limit"]),
            "subnet-registration-cost": lambda: get_subnet_registration_cost(),
            "subnet-emission":          lambda: get_subnet_emission(a.get("netuid"), a.get("block_start"), a.get("block_end"), a.get("ts_start"), a.get("ts_end"), a["page"], a["limit"]),
            "subnet-distribution":      lambda: (get_subnet_distribution_coldkey(a["netuid"]) if a["dtype"]=="coldkey" else get_subnet_distribution_incentive(a["netuid"])),
            "neuron-registrations":     lambda: get_neuron_registrations(a.get("netuid"), hotkey=a.get("hotkey"), coldkey=a.get("coldkey"), block_start=a.get("block_start"), block_end=a.get("block_end"), page=a["page"], limit=a["limit"]),
            "neuron-deregistrations":   lambda: get_neuron_deregistrations(a.get("netuid"), hotkey=a.get("hotkey"), block_start=a.get("block_start"), block_end=a.get("block_end"), page=a["page"], limit=a["limit"]),
            "neurons":                  lambda: get_neurons(a.get("netuid"), a.get("uid"), a.get("hotkey"), a.get("coldkey"), a.get("is_immune"), a.get("in_danger"), page=a["page"], limit=a["limit"]),
            "neuron-history":           lambda: get_neuron_history(a.get("netuid"), a.get("uid"), a.get("hotkey"), a.get("coldkey"), page=a["page"], limit=a["limit"]),
            "neuron-aggregated":        lambda: get_neuron_aggregated(a.get("netuid"), a["page"], a["limit"]),
            "metagraph":                lambda: get_metagraph(a.get("netuid"), a.get("uid"), a.get("hotkey"), active=a.get("active"), page=a["page"], limit=a["limit"]),
            "metagraph-history":        lambda: get_metagraph_history(a.get("netuid"), hotkey=a.get("hotkey"), uid=a.get("uid"), block_start=a.get("block_start"), block_end=a.get("block_end"), page=a["page"], limit=a["limit"]),
            "root-metagraph":           lambda: get_root_metagraph(a.get("hotkey"), a["page"], a["limit"]),
            "validators":               lambda: get_validators(a.get("hotkey"), a.get("stake_min"), None, a.get("apr_min"), a.get("apr_max"), a["page"], a["limit"], a.get("order")),
            "validator-history":        lambda: get_validator_history(a.get("hotkey"), a.get("block_start"), a.get("block_end"), a.get("ts_start"), a.get("ts_end"), a["page"], a["limit"]),
            "validator-performance":    lambda: get_validator_performance(a.get("hotkey"), a.get("netuid"), a["page"], a["limit"]),
            "validator-metrics":        lambda: get_validator_metrics(a.get("hotkey"), a.get("coldkey"), a.get("netuid"), a["page"], a["limit"]),
            "validator-weights":        lambda: get_validator_weights(a.get("hotkey"), a.get("netuid"), a.get("uid"), a["page"], a["limit"], a.get("v2", False)),
            "hotkey-family":            lambda: get_hotkey_family(a.get("hotkey"), a.get("netuid"), a["page"], a["limit"]),
            "miner-weights":            lambda: get_miner_weights(a.get("netuid"), a.get("miner_uid"), None, a.get("miner_hotkey"), a.get("validator_hotkey"), a["page"], a["limit"]),
            "miner-coldkey":            lambda: get_miner_by_coldkey(a["coldkey"], a.get("days")),
            "dtao-pools":               lambda: get_dtao_pools(a.get("netuid"), a["page"], a["limit"], a.get("order")),
            "dtao-pool-history":        lambda: get_dtao_pool_history(a.get("netuid"), a.get("frequency"), a.get("block_start"), a.get("block_end"), a.get("ts_start"), a.get("ts_end"), a["page"], a["limit"]),
            "dtao-pool-total-price":    lambda: get_dtao_pool_total_price(),
            "dtao-slippage":            lambda: get_dtao_slippage(a["netuid"], a["amount"], a["direction"]),
            "dtao-tao-flow":            lambda: get_dtao_tao_flow(a.get("netuid"), a.get("block_start"), a.get("block_end"), a.get("ts_start"), a.get("ts_end")),
            "dtao-trades":              lambda: get_dtao_trades(a.get("coldkey"), from_name=a.get("from_name"), to_name=a.get("to_name"), tao_value_min=a.get("tao_min"), tao_value_max=a.get("tao_max"), block_number=a.get("block_number"), block_start=a.get("block_start"), block_end=a.get("block_end"), timestamp_start=_trade_ts(a.get("ts_start")), timestamp_end=_trade_ts(a.get("ts_end")), page=a["page"], limit=a["limit"]),
            "dtao-stake":               lambda: get_dtao_stake_balance(a.get("coldkey"), a.get("hotkey"), a.get("netuid"), balance_as_tao_min=a.get("balance_as_tao_min"), page=a["page"], limit=a["limit"]),
            "dtao-stake-history":       lambda: get_dtao_stake_balance_history(a.get("coldkey"), a.get("hotkey"), a.get("netuid"), a.get("block_start"), a.get("block_end"), a.get("ts_start"), a.get("ts_end"), a["page"], a["limit"]),
            "dtao-portfolio":           lambda: get_dtao_stake_portfolio(a.get("coldkey"), a.get("hotkey"), a.get("netuid"), a.get("days"), page=a["page"], limit=a["limit"]),
            "dtao-hotkey-alpha":        lambda: get_dtao_hotkey_alpha_shares(a.get("hotkey"), a.get("netuid"), page=a["page"], limit=a["limit"]),
            "dtao-coldkey-alpha":       lambda: get_dtao_coldkey_alpha_shares(a.get("coldkey"), a.get("hotkey"), a.get("netuid"), page=a["page"], limit=a["limit"]),
            "dtao-emissions":           lambda: get_dtao_hotkey_emissions(a.get("hotkey"), a.get("netuid"), a.get("block_start"), a.get("block_end"), a.get("ts_start"), a.get("ts_end"), a["page"], a["limit"]),
            "dtao-burned-alpha":        lambda: get_dtao_burned_alpha(a.get("netuid"), a.get("hotkey"), a.get("coldkey"), a.get("burn_type"), a.get("block_start"), a.get("block_end"), a["page"], a["limit"]),
            "dtao-validators":          lambda: get_dtao_validators(a.get("hotkey"), a["page"], a["limit"], a.get("order")),
            "dtao-validator-performance": lambda: get_dtao_validator_performance(a.get("hotkey"), a.get("netuid"), page=a["page"], limit=a["limit"]),
            "dtao-validator-yield":     lambda: get_dtao_validator_yield(a.get("hotkey"), a.get("netuid"), a.get("min_stake"), a["page"], a["limit"]),
            "dtao-validator-dividends": lambda: get_dtao_validator_dividends(a.get("hotkey"), a.get("netuid"), a["page"], a["limit"]),
            "dtao-liquidity-positions": lambda: get_dtao_liquidity_positions(a.get("coldkey"), a.get("netuid"), a.get("status"), a["page"], a["limit"]),
            "dtao-liquidity-distribution": lambda: get_dtao_liquidity_distribution(a["netuid"], a.get("min_price"), a.get("max_price"), a.get("num_points")),
            "accounts":                 lambda: get_accounts(a.get("address"), a.get("balance_free_min"), a.get("balance_staked_min"), a["page"], a["limit"]),
            "account-history":          lambda: get_account_history(a.get("address"), a.get("block_start"), a.get("block_end"), a.get("ts_start"), a.get("ts_end"), a["page"], a["limit"]),
            "identity":                 lambda: get_identity(a.get("address"), a.get("validator_hotkey")),
            "transfers":                lambda: get_transfers(a.get("address"), a.get("from_addr"), a.get("to_addr"), a.get("amount_min"), None, a.get("block_start"), a.get("block_end"), a.get("ts_start"), a.get("ts_end"), page=a["page"], limit=a["limit"]),
            "delegations":              lambda: get_delegations(a.get("nominator"), a.get("delegate"), a.get("action"), page=a["page"], limit=a["limit"]),
            "stake-events":             lambda: get_stake_events(a.get("coldkey"), a.get("hotkey"), a.get("block_start"), a.get("block_end"), a.get("ts_start"), a.get("ts_end"), a["page"], a["limit"]),
            "blocks":                   lambda: get_blocks(a.get("block_number"), a.get("block_start"), a.get("block_end"), a.get("ts_start"), a.get("ts_end"), a.get("hash"), page=a["page"], limit=a["limit"]),
            "block-emission":           lambda: get_block_emission(a.get("block_number"), a.get("block_start"), a.get("block_end"), a.get("ts_start"), a.get("ts_end"), a["page"], a["limit"]),
            "extrinsics":               lambda: get_extrinsics(None, a.get("block_start"), a.get("block_end"), a.get("ts_start"), a.get("ts_end"), a.get("hash"), a.get("full_name"), a["page"], a["limit"]),
            "events":                   lambda: get_events(None, a.get("block_start"), a.get("block_end"), a.get("ts_start"), a.get("ts_end"), a.get("pallet"), a.get("name"), a["page"], a["limit"]),
            "live-block-head":          lambda: get_live_block_head(),
            "live-block":               lambda: get_live_block(a["height"]),
            "accounting":               lambda: get_accounting(a["coldkey"], a.get("hotkey"), a.get("date_start"), a.get("date_end")),
            "tax-report":               lambda: get_tax_report(a["coldkey"], a.get("token","tao"), a.get("date_start"), a.get("date_end")),
            "otc-listings":             lambda: get_otc_listings(a.get("netuid"), a.get("seller"), None, a.get("status"), a["page"], a["limit"]),
            "otc-trades":               lambda: get_otc_trades(a.get("netuid"), a.get("seller"), a.get("buyer"), a["page"], a["limit"]),
            "otc-offers":               lambda: get_otc_offers(a.get("netuid"), a.get("buyer"), a.get("status"), a["page"], a["limit"]),
        }
        fn = dispatch.get(cmd)
        if not fn:
            P.error(f"Unknown command: {cmd}")
        print(json.dumps(fn(), indent=2))
    except httpx.HTTPStatusError as e:
        print(json.dumps({"error": str(e), "status_code": e.response.status_code}))
        raise SystemExit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        raise SystemExit(1)
