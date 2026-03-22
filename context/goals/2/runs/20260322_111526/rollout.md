# Goal #2 — Step 2

## Done

- Extended `tools/polymarket_scan.py`: `--format json|csv|table`, `--no-up-down`, `--exclude-slug-substr` (repeatable), `--min-competitive` / `--max-competitive`, refactored `collect_rows()` for reuse.
- Live run (15 pages, prob ≥ 88 %, liq ≥ 1000, vol24h ≥ 200, excluding `up-or-down`): **1051** matches; top rows still dominated by sports/live and **~99.95 %** implied on the lead — **expected gross return ≈ (1−p)** is tiny; not an edge by itself.
- Sample export: `high_prob_sample.json` (50 rows).

## Caveat

High *p* from the order book is consensus, not alpha. Check resolution rules on polymarket.com before sizing.
