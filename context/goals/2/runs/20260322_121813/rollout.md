# Goal #2 — Step 5

## Changes

- `tools/polymarket_scan.py`: `--search-tags` (filter tags by substring on slug/label), `--list-tags-from-cache` (offline tag list from JSON).

## Live API

- Tag search on cached JSON + scan `tag_id=100283` (NBA Draft): JSON rows with real Gamma fields.
- Scan `tag_id=400` (election 2024): empty array with relaxed filters (no active matches in this slice).

## Quant note

High implied probability lists **consensus** prices, not trade edge; gross return `(1-p)/p` vanishes as p→1.
