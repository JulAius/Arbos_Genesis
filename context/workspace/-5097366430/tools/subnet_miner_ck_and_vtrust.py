#!/usr/bin/env python3
"""Per netuid: distinct coldkeys (miners remunerated) + validators with vtrust > 0.98."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
AGCLI = os.path.expanduser(os.environ.get("AGCLI_BIN", "~/.cargo/bin/agcli"))
MIN_NETUID = 0
MAX_NETUID = 128


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
    out, err = (r.stdout or "").strip(), (r.stderr or "").strip()
    raw = err if ("{" in err or "[" in err) else out
    if not raw or ("{" not in raw and "[" not in raw):
        raw = err + out
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


def parse_emission(n: dict[str, Any]) -> float:
    e = n.get("emission")
    if e is None:
        return 0.0
    if isinstance(e, (int, float)):
        return float(e)
    s = str(e).strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_vtrust(n: dict[str, Any]) -> float:
    v = n.get("validator_trust")
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except ValueError:
        return 0.0


def main() -> None:
    rows: list[dict[str, Any]] = []
    for netuid in range(MIN_NETUID, MAX_NETUID + 1):
        try:
            neurons = agcli_metagraph(netuid)
        except Exception as e:
            print(f"netuid {netuid} ERROR: {e}", file=sys.stderr)
            continue
        miner_cks: set[str] = set()
        miner_slots = 0
        val_high = 0
        for n in neurons:
            vp = bool(n.get("validator_permit"))
            em = parse_emission(n)
            if not vp and em > 0.0:
                miner_slots += 1
                ck = n.get("coldkey")
                if ck:
                    miner_cks.add(str(ck))
            if vp and parse_vtrust(n) > 0.98:
                val_high += 1
        rows.append(
            {
                "netuid": netuid,
                "distinct_miner_coldkeys_emission": len(miner_cks),
                "miner_slots_emission_gt0": miner_slots,
                "validators_vtrust_gt_0_98": val_high,
            }
        )
        if netuid % 16 == 0:
            print(f"  … netuid {netuid}/{MAX_NETUID}", file=sys.stderr)

    rows.sort(key=lambda r: r["distinct_miner_coldkeys_emission"], reverse=True)
    out = {
        "network": "finney",
        "criteria": {
            "miner": "validator_permit == false",
            "remunerated": "emission > 0",
            "metric_distinct_coldkeys": "unique coldkey among remunerated miners",
            "validators_vtrust": "validator_permit == true AND validator_trust > 0.98",
        },
        "sorted_by_distinct_coldkeys_desc": rows,
    }
    json.dump(out, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
