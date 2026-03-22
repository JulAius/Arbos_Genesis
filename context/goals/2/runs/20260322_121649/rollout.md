# Goal #2 — Step 3

## Changes (`tools/polymarket_scan.py`)

- **Pipeline fields (JSON/CSV/table):** `condition_id`, `gamma_market_id`, `event_slugs`, `primary_event_slug`, `url_market`, `url_event`, `leading_clob_token_id`, optional `best_bid` / `best_ask` / `spread`, `gross_return_if_win_approx` ≈ `(1−p)/p` for the leading outcome.
- **Gamma filters:** `--tag-id`, `--exclude-tag-id`, `--related-tags` (passed to `/markets` per [fetch-markets guide](https://docs.polymarket.com/developers/gamma-markets-api/fetch-markets-guide)).
- **Rendement brut:** `--min-gross-return-if-win` / `--max-gross-return-if-win` to drop les favoris extrêmes (ex. `--min-gross-return-if-win 0.01` ⇒ *p* ≤ ~99 % pour le côté menant).

## Artefacts

- `enriched_high_prob.json` — même esprit que l’étape 2 (probabilité élevée), avec champs enrichis.
- `min_gross_1pct.json` — sous-ensemble avec upside brut ≥ ~1 % si résolution favorable (toujours sans frais/spread).

## Rappel

Haute probabilité implicite ≠ edge; valider règles de résolution sur Polymarket avant capital.
