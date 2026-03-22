#!/usr/bin/env python3
"""Scan Polymarket (Gamma API) for active markets where one outcome is priced as highly likely.

Uses public HTTPS data only (no API key). Outcome prices are implied probabilities in [0, 1].

Note: a price near 1 means the market assigns high probability to that outcome; expected
return on buying that side is low (roughly (1-p)/p if the outcome resolves in your favor).
This tool surfaces consensus pricing, not a guarantee of profit — validate resolution rules,
liquidity, and fees before any decision.

Docs: https://docs.polymarket.com/developers/gamma-markets-api/fetch-markets-guide
(Tag filters: tag_id / exclude_tag_id on /markets; list tags via GET /tags or
`--list-tags-from-cache` + `--search-tags SUBSTR` for offline tag lookup.)
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

GAMMA_BASE = "https://gamma-api.polymarket.com"
POLY_FRONT = "https://polymarket.com"


def fetch_tags_page(*, limit: int, offset: int) -> list[dict]:
    """GET /tags — used to pick tag_id for --tag-id filters."""
    params = urllib.parse.urlencode({"limit": limit, "offset": offset})
    url = f"{GAMMA_BASE}/tags?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Arbos-polymarket_scan/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected /tags response type: {type(data)}")
    return data


def fetch_all_tags(*, limit: int, max_pages: int) -> list[dict]:
    out: list[dict] = []
    for page in range(max_pages):
        offset = page * limit
        batch = fetch_tags_page(limit=limit, offset=offset)
        if not batch:
            break
        out.extend(batch)
        if len(batch) < limit:
            break
    return out


def load_tags_from_json_file(path: str) -> list[dict]:
    """Load tag list from JSON (list of objects or {'tags': [...]})."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, list):
        return [t for t in raw if isinstance(t, dict)]
    if isinstance(raw, dict) and isinstance(raw.get("tags"), list):
        return [t for t in raw["tags"] if isinstance(t, dict)]
    raise RuntimeError(f"Expected JSON list of tags or {{'tags': [...]}} in {path!r}")


def filter_tags_by_substrings(tags: list[dict], substrs: list[str]) -> list[dict]:
    """Keep tags whose slug or label matches any substring (case-insensitive). Empty substrs = all."""
    if not substrs:
        return tags
    lowered = [s.lower() for s in substrs if s]
    if not lowered:
        return tags
    out: list[dict] = []
    for t in tags:
        slug = str(t.get("slug") or "").lower()
        label = str(t.get("label") or "").lower()
        hay = f"{slug} {label}"
        if any(s in hay for s in lowered):
            out.append(t)
    return out


def fetch_markets_page(
    *,
    offset: int,
    limit: int,
    active: bool,
    closed: bool,
    tag_id: int | None = None,
    exclude_tag_id: int | None = None,
    related_tags: bool | None = None,
) -> list[dict]:
    params: dict[str, str | int | bool] = {
        "active": str(active).lower(),
        "closed": str(closed).lower(),
        "limit": limit,
        "offset": offset,
        "order": "volume24hr",
        "ascending": "false",
    }
    if tag_id is not None:
        params["tag_id"] = tag_id
    if exclude_tag_id is not None:
        params["exclude_tag_id"] = exclude_tag_id
    if related_tags is not None:
        params["related_tags"] = str(related_tags).lower()
    q = urllib.parse.urlencode(params)
    url = f"{GAMMA_BASE}/markets?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "Arbos-polymarket_scan/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected response type: {type(data)}")
    return data


def parse_outcomes(m: dict) -> tuple[list[str], list[float]]:
    outs_raw = m.get("outcomes") or "[]"
    prices_raw = m.get("outcomePrices") or "[]"
    if isinstance(outs_raw, str):
        outcomes = json.loads(outs_raw)
    else:
        outcomes = list(outs_raw)
    if isinstance(prices_raw, str):
        prices = [float(x) for x in json.loads(prices_raw)]
    else:
        prices = [float(x) for x in prices_raw]
    if len(outcomes) != len(prices):
        raise ValueError("outcomes / outcomePrices length mismatch")
    return outcomes, prices


def parse_clob_token_ids(m: dict) -> list[str]:
    raw = m.get("clobTokenIds") or "[]"
    if isinstance(raw, str):
        return [str(x) for x in json.loads(raw)]
    return [str(x) for x in raw]


def _opt_float(v: object) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_row(
    m: dict,
    *,
    max_p: float,
    leading_outcome: str,
    outcome_index: int,
) -> dict:
    slug = str(m.get("slug") or "")
    qtext = str(m.get("question") or "")
    liq = float(m.get("liquidityNum") or m.get("liquidity") or 0)
    v24 = float(m.get("volume24hr") or 0)
    comp = float(m.get("competitive") or 0)
    end = str(m.get("endDateIso") or m.get("endDate") or "")
    events = m.get("events") or []
    event_slugs: list[str] = []
    if isinstance(events, list):
        for ev in events:
            if isinstance(ev, dict) and ev.get("slug"):
                event_slugs.append(str(ev["slug"]))
    primary_event_slug = event_slugs[0] if event_slugs else ""
    market_url = f"{POLY_FRONT}/market/{slug}" if slug else ""
    event_url = f"{POLY_FRONT}/event/{primary_event_slug}" if primary_event_slug else ""

    token_ids = parse_clob_token_ids(m)
    lead_token = ""
    if 0 <= outcome_index < len(token_ids):
        lead_token = token_ids[outcome_index]

    gross_ret = (1.0 - max_p) / max_p if max_p > 0 else float("inf")

    return {
        "max_implied_prob": max_p,
        "leading_outcome": leading_outcome,
        "question": qtext,
        "slug": slug,
        "liquidity": liq,
        "volume24hr": v24,
        "competitive": comp,
        "end": end,
        "condition_id": str(m.get("conditionId") or ""),
        "gamma_market_id": str(m.get("id") or ""),
        "event_slugs": event_slugs,
        "primary_event_slug": primary_event_slug,
        "url_market": market_url,
        "url_event": event_url,
        "leading_clob_token_id": lead_token,
        "best_bid": _opt_float(m.get("bestBid")),
        "best_ask": _opt_float(m.get("bestAsk")),
        "spread": _opt_float(m.get("spread")),
        "gross_return_if_win_approx": gross_ret,
    }


def collect_rows(
    *,
    min_prob: float,
    min_liquidity: float,
    min_volume24h: float,
    min_competitive: float | None,
    max_competitive: float | None,
    exclude_slug_substr: list[str],
    limit: int,
    max_pages: int,
    tag_id: int | None,
    exclude_tag_id: int | None,
    related_tags: bool | None,
    min_gross_return_if_win: float | None,
    max_gross_return_if_win: float | None,
) -> list[dict]:
    rows: list[dict] = []

    for page in range(max_pages):
        offset = page * limit
        try:
            markets = fetch_markets_page(
                offset=offset,
                limit=limit,
                active=True,
                closed=False,
                tag_id=tag_id,
                exclude_tag_id=exclude_tag_id,
                related_tags=related_tags,
            )
        except urllib.error.URLError as e:
            print(f"HTTP error: {e}", file=sys.stderr)
            sys.exit(2)
        if not markets:
            break
        for m in markets:
            try:
                outcomes, prices = parse_outcomes(m)
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
            if not prices:
                continue
            i = max(range(len(prices)), key=lambda j: prices[j])
            max_p = prices[i]
            if max_p < min_prob:
                continue
            gross_ret = (1.0 - max_p) / max_p if max_p > 0 else float("inf")
            if min_gross_return_if_win is not None and gross_ret < min_gross_return_if_win:
                continue
            if max_gross_return_if_win is not None and gross_ret > max_gross_return_if_win:
                continue
            liq = float(m.get("liquidityNum") or m.get("liquidity") or 0)
            v24 = float(m.get("volume24hr") or 0)
            if liq < min_liquidity or v24 < min_volume24h:
                continue
            comp = float(m.get("competitive") or 0)
            if min_competitive is not None and comp < min_competitive:
                continue
            if max_competitive is not None and comp > max_competitive:
                continue
            slug = str(m.get("slug") or "")
            if exclude_slug_substr and any(s in slug for s in exclude_slug_substr):
                continue
            rows.append(build_row(m, max_p=max_p, leading_outcome=outcomes[i], outcome_index=i))
        if len(markets) < limit:
            break

    rows.sort(key=lambda r: (-r["max_implied_prob"], -r["liquidity"], -r["volume24hr"]))
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description="Polymarket: list high-implied-probability outcomes")
    p.add_argument(
        "--list-tags",
        action="store_true",
        help="List Gamma tags (GET /tags) and exit; use ids with --tag-id for market scans",
    )
    p.add_argument(
        "--tags-limit",
        type=int,
        default=100,
        help="Page size for --list-tags (default 100)",
    )
    p.add_argument(
        "--tags-max-pages",
        type=int,
        default=5,
        help="Max pages when listing tags (default 5)",
    )
    p.add_argument(
        "--tags-cache",
        metavar="PATH",
        default=None,
        help="With --list-tags: write full tag list JSON to this path (append-only merge if file exists)",
    )
    p.add_argument(
        "--list-tags-from-cache",
        metavar="PATH",
        default=None,
        help="With --list-tags: load tags from this JSON file instead of HTTP (use with --search-tags offline)",
    )
    p.add_argument(
        "--search-tags",
        action="append",
        default=[],
        metavar="SUBSTR",
        help="With --list-tags: keep only tags whose slug or label contains this substring (repeatable, case-insensitive)",
    )
    p.add_argument(
        "--min-prob",
        type=float,
        default=0.85,
        help="Minimum implied probability for the leading outcome (0–1)",
    )
    p.add_argument("--min-liquidity", type=float, default=500.0, help="Minimum liquidityNum")
    p.add_argument("--min-volume24h", type=float, default=0.0, help="Minimum volume24hr")
    p.add_argument(
        "--min-competitive",
        type=float,
        default=None,
        help="Optional minimum competitive score (Gamma field)",
    )
    p.add_argument(
        "--max-competitive",
        type=float,
        default=None,
        help="Optional maximum competitive score (Gamma field)",
    )
    p.add_argument(
        "--exclude-slug-substr",
        action="append",
        default=[],
        metavar="STR",
        help="Exclude markets whose slug contains this substring (repeatable)",
    )
    p.add_argument(
        "--no-up-down",
        action="store_true",
        help="Shorthand: exclude slugs containing 'up-or-down' (crypto intraday noise)",
    )
    p.add_argument(
        "--tag-id",
        type=int,
        default=None,
        help="Gamma tag_id filter (see GET /tags). Narrows markets to a category/topic.",
    )
    p.add_argument(
        "--exclude-tag-id",
        type=int,
        default=None,
        help="Exclude markets with this Gamma tag id",
    )
    p.add_argument(
        "--related-tags",
        action="store_true",
        help="Pass related_tags=true to Gamma (include related tag markets when using tag-id)",
    )
    p.add_argument(
        "--min-gross-return-if-win",
        type=float,
        default=None,
        help="Minimum (1-p)/p for the leading outcome (excludes ultra-favorites with tiny upside)",
    )
    p.add_argument(
        "--max-gross-return-if-win",
        type=float,
        default=None,
        help="Maximum (1-p)/p for the leading outcome (optional upper cap)",
    )
    p.add_argument("--limit", type=int, default=100, help="Page size (API request)")
    p.add_argument("--max-pages", type=int, default=40, help="Max pages to fetch (pagination)")
    p.add_argument("--top", type=int, default=30, help="How many rows to print or export")
    p.add_argument(
        "--format",
        choices=("table", "json", "csv"),
        default="table",
        help="Output format (json/csv suitable for backtests)",
    )
    args = p.parse_args()

    if args.list_tags:
        if args.list_tags_from_cache:
            try:
                tags = load_tags_from_json_file(args.list_tags_from_cache)
            except (OSError, json.JSONDecodeError, RuntimeError) as e:
                print(f"Cache read error: {e}", file=sys.stderr)
                sys.exit(2)
        else:
            try:
                tags = fetch_all_tags(limit=args.tags_limit, max_pages=args.tags_max_pages)
            except urllib.error.URLError as e:
                print(f"HTTP error: {e}", file=sys.stderr)
                sys.exit(2)
        tags = filter_tags_by_substrings(tags, list(args.search_tags))
        if args.tags_cache:
            merged: dict[str, dict] = {}
            path = args.tags_cache
            try:
                with open(path, encoding="utf-8") as f:
                    prev = json.load(f)
                if isinstance(prev, list):
                    for t in prev:
                        if isinstance(t, dict) and t.get("id") is not None:
                            merged[str(t["id"])] = t
            except (OSError, json.JSONDecodeError):
                pass
            for t in tags:
                if isinstance(t, dict) and t.get("id") is not None:
                    merged[str(t["id"])] = t
            out_list = sorted(merged.values(), key=lambda x: str(x.get("label") or ""))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(out_list, f, indent=2)
                f.write("\n")
            print(f"# Wrote {len(out_list)} tags to {path}", file=sys.stderr)
        if args.format == "json":
            print(json.dumps(tags, indent=2))
        elif args.format == "csv":
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["id", "slug", "label"])
            for t in tags:
                w.writerow(
                    [
                        str(t.get("id", "")),
                        str(t.get("slug", "")),
                        str(t.get("label", "")),
                    ]
                )
            sys.stdout.write(buf.getvalue())
        else:
            print(f"# Gamma tags (pages <= {args.tags_max_pages}, limit {args.tags_limit})\n")
            print(f"{'id':>12}  {'slug':<36}  label")
            for t in tags:
                tid = str(t.get("id", ""))
                slug = str(t.get("slug", ""))[:36]
                lab = str(t.get("label", ""))
                short = (lab[:48] + "…") if len(lab) > 49 else lab
                print(f"{tid:>12}  {slug:<36}  {short}")
            print(f"\n# Total: {len(tags)}", file=sys.stderr)
        return

    exclude = list(args.exclude_slug_substr)
    if args.no_up_down:
        exclude.append("up-or-down")

    rows = collect_rows(
        min_prob=args.min_prob,
        min_liquidity=args.min_liquidity,
        min_volume24h=args.min_volume24h,
        min_competitive=args.min_competitive,
        max_competitive=args.max_competitive,
        exclude_slug_substr=exclude,
        limit=args.limit,
        max_pages=args.max_pages,
        tag_id=args.tag_id,
        exclude_tag_id=args.exclude_tag_id,
        related_tags=True if args.related_tags else None,
        min_gross_return_if_win=args.min_gross_return_if_win,
        max_gross_return_if_win=args.max_gross_return_if_win,
    )

    head = rows[: args.top]

    if args.format == "json":
        print(json.dumps(head, indent=2))
        return

    if args.format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        csv_cols = [
            "max_implied_prob",
            "leading_outcome",
            "question",
            "slug",
            "liquidity",
            "volume24hr",
            "competitive",
            "end",
            "condition_id",
            "gamma_market_id",
            "primary_event_slug",
            "event_slugs_json",
            "url_market",
            "url_event",
            "leading_clob_token_id",
            "best_bid",
            "best_ask",
            "spread",
            "gross_return_if_win_approx",
        ]
        w.writerow(csv_cols)
        for r in head:
            w.writerow(
                [
                    r["max_implied_prob"],
                    r["leading_outcome"],
                    r["question"],
                    r["slug"],
                    r["liquidity"],
                    r["volume24hr"],
                    r["competitive"],
                    r["end"],
                    r["condition_id"],
                    r["gamma_market_id"],
                    r["primary_event_slug"],
                    json.dumps(r["event_slugs"]),
                    r["url_market"],
                    r["url_event"],
                    r["leading_clob_token_id"],
                    r["best_bid"],
                    r["best_ask"],
                    r["spread"],
                    r["gross_return_if_win_approx"],
                ]
            )
        sys.stdout.write(buf.getvalue())
        return

    print(
        f"# Polymarket — active markets with max implied prob >= {args.min_prob:.0%}, "
        f"liquidity >= {args.min_liquidity:g}, pages scanned <= {args.max_pages}\n"
    )
    if exclude:
        print(f"# Excluded slug substrings: {exclude!r}\n")
    if args.tag_id is not None:
        print(f"# tag_id filter: {args.tag_id}\n")
    if args.exclude_tag_id is not None:
        print(f"# exclude_tag_id: {args.exclude_tag_id}\n")
    print(
        f"{'prob':>6}  {'gross≈':>8}  {'outcome':<12}  {'liq':>10}  {'vol24h':>10}  question / urls"
    )
    for r in head:
        max_p = r["max_implied_prob"]
        gret = r["gross_return_if_win_approx"]
        oc = r["leading_outcome"]
        qtext = r["question"]
        slug = r["slug"]
        liq = r["liquidity"]
        v24 = r["volume24hr"]
        short_q = (qtext[:56] + "…") if len(qtext) > 57 else qtext
        print(
            f"{max_p:6.2%}  {gret:8.4%}  {oc[:12]:<12}  {liq:10.0f}  {v24:10.0f}  {short_q}"
        )
        if r.get("url_market"):
            print(f"         {r['url_market']}")
        if r.get("condition_id"):
            print(f"         condition_id={r['condition_id'][:18]}…")
    print(f"\n# Total matching: {len(rows)} (showing up to {args.top})")


if __name__ == "__main__":
    main()
