#!/usr/bin/env python3
"""
Build coldkeys that are non-validator (miner) neurons on >=3 distinct netuids,
with free TAO >= threshold (Taostats). Sort by free balance (proxy; not PnL —
Taostats portfolio/PnL requires upgraded API plan).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from typing import Any

# File: context/workspace/<id>/tools/ → repo root is four levels up.
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
AGCLI = os.path.expanduser(os.environ.get("AGCLI_BIN", "~/.cargo/bin/agcli"))
MIN_NETUID = 1
MAX_NETUID = 128
TAU_MIN = 50.0
RAO = 10**9
CACHE_PATH = os.path.join(os.path.dirname(__file__), ".miner_subnets_cache.json")


def agcli_metagraph(netuid: int) -> list[dict[str, Any]]:
    r = subprocess.run(
        [
            AGCLI,
            "--batch",
            "--yes",
            "--best",
            "--output",
            "json",
            "view",
            "metagraph",
            "--netuid",
            str(netuid),
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    # agcli may put JSON on stderr (warnings on stdout) or vice versa
    out, err = (r.stdout or "").strip(), (r.stderr or "").strip()
    raw = err if ("{" in err or "[" in err) else out
    if not raw or ("{" not in raw and "[" not in raw):
        raw = err + out
    # Skip leading log lines like {"level":"WARN",...} before the metagraph object.
    dec = json.decoder.JSONDecoder()
    idx = 0
    while idx < len(raw):
        b0, b1 = raw.find("{", idx), raw.find("[", idx)
        if b0 < 0 and b1 < 0:
            break
        if b0 >= 0 and (b1 < 0 or b0 < b1):
            try:
                val, end = dec.raw_decode(raw[b0:])
            except json.JSONDecodeError:
                idx = b0 + 1
                continue
            if isinstance(val, dict) and "neurons" in val:
                return val["neurons"]
            if isinstance(val, list):
                return val
            idx = b0 + 1
            continue
        try:
            val, _ = dec.raw_decode(raw[b1:])
        except json.JSONDecodeError:
            idx = b1 + 1
            continue
        if isinstance(val, list):
            return val
        idx = b1 + 1
    raise RuntimeError(f"netuid {netuid}: no metagraph neurons in agcli output")


def miner_coldkeys_by_subnet() -> dict[str, set[int]]:
    by_ck: dict[str, set[int]] = defaultdict(set)
    # Sequential agcli calls: parallel runs often return truncated JSON on this host.
    for netuid in range(MIN_NETUID, MAX_NETUID + 1):
        neurons = agcli_metagraph(netuid)
        for n in neurons:
            if n.get("validator_permit"):
                continue
            ck = n.get("coldkey")
            if not ck:
                continue
            by_ck[ck].add(netuid)
        if netuid % 16 == 0:
            print(f"  metagraph netuid {netuid}/128…", file=sys.stderr)
    return by_ck


def main() -> None:
    sys.path.insert(0, REPO)
    from data_providers.taostats import _get

    if os.environ.get("MINER_SUBNET_USE_CACHE") == "1" and os.path.isfile(CACHE_PATH):
        print(f"Loading miner subnet map from {CACHE_PATH}", file=sys.stderr)
        raw = json.load(open(CACHE_PATH))
        by_ck = {k: set(v) for k, v in raw.items()}
    else:
        print("Fetching metagraphs via agcli…", file=sys.stderr)
        by_ck = miner_coldkeys_by_subnet()
        try:
            json.dump({k: sorted(v) for k, v in by_ck.items()}, open(CACHE_PATH, "w"), indent=0)
        except OSError:
            pass
    cset = {ck for ck, nets in by_ck.items() if len(nets) >= 3}
    print(f"Coldkeys miner on ≥3 subnets: {len(cset)}", file=sys.stderr)

    rao_min_int = int(TAU_MIN * RAO)
    rows: list[dict[str, Any]] = []
    for i, ck in enumerate(sorted(cset)):
        if i and i % 50 == 0:
            print(f"  accounts {i}/{len(cset)}…", file=sys.stderr)
        time.sleep(0.35)
        try:
            acc = _get("/api/account/latest/v1", {"address": ck, "page": 1, "limit": 1})
        except Exception as e:
            if "429" in str(e):
                time.sleep(5.0)
                acc = _get("/api/account/latest/v1", {"address": ck, "page": 1, "limit": 1})
            else:
                print(f"skip {ck[:12]}… {e}", file=sys.stderr)
                continue
        data = acc.get("data") or []
        if not data:
            continue
        item = data[0]
        free = int(item.get("balance_free", "0"))
        if free < rao_min_int:
            continue
        rows.append(
            {
                "coldkey": ck,
                "miner_subnets": len(by_ck[ck]),
                "balance_free_rao": free,
                "balance_free_tau": free / RAO,
                "balance_total_rao": int(item.get("balance_total", "0")),
                "balance_total_tau": int(item.get("balance_total", "0")) / RAO,
            }
        )

    rows.sort(key=lambda r: r["balance_free_tau"], reverse=True)
    top = rows[:100]

    out = {
        "network": "finney",
        "criteria": {
            "miner": "validator_permit == false sur chaque subnet compté",
            "min_distinct_miner_subnets": 3,
            "min_free_tao_wallet": TAU_MIN,
        },
        "pnl_note": "Taostats /api/dtao/stake_balance/portfolio/v1 retourne 403 "
        "(plan requis) pour realised/unrealised PnL ; ce classement utilise "
        "balance_free comme proxy, pas le PnL trading/alpha.",
        "count_matching": len(rows),
        "top_100": top,
    }
    json.dump(out, sys.stdout, indent=2)
    print(file=sys.stderr)
    print(f"Matching coldkeys (avec filtre solde): {len(rows)}", file=sys.stderr)


if __name__ == "__main__":
    main()
