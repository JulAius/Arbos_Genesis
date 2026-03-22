## Step 5 — `--search-tags` + `--list-tags-from-cache` + rescans niche

- **Script:** `tools/polymarket_scan.py`
  - **`--search-tags SUBSTR`** : répétable, filtre client-side sur `slug` **ou** `label` (insensible à la casse), après fetch HTTP **ou** après chargement cache.
  - **`--list-tags-from-cache PATH`** : avec `--list-tags`, charge la liste depuis un JSON (liste d’objets) au lieu de GET `/tags` — recherche de `tag_id` **sans** réseau.
- **Run:** `runs/20260322_121813/`
  - `tags_search_nba.json` — 3 tags (cache local + `--search-tags nba`).
  - `scan_tag_nba_draft_relaxed.json` — `tag_id=100283`, `--min-prob 0.85`, `--min-liquidity 150`, `--min-volume24h 0`, `--related-tags`, `--max-pages 15` : marchés réels (ex. draft 2026, outcome « No » très coté).
  - `scan_tag_election2024_relaxed.json` — `tag_id=400` : **[]** (filtres + volume / marchés actifs vides pour ce tag au moment du run).

## Rappel quanti

- *Forte probabilité* ≠ *edge* ; favoris extrêmes → `(1−p)/p` minuscule.
- Tag niche peut être vide si Gamma ne classe plus d’actifs sous ce `tag_id`.

## Exemples

```bash
# Tags NBA depuis cache, sans appel HTTP
python3 tools/polymarket_scan.py --list-tags --list-tags-from-cache context/goals/2/runs/20260322_111720/tags_cache_merged.json --search-tags nba --format json

# Scan tag choisi (id depuis la liste ci-dessus)
python3 tools/polymarket_scan.py --tag-id 100283 --related-tags --min-prob 0.85 --min-liquidity 150 --min-volume24h 0 --no-up-down --format json --top 20 --max-pages 15
```

## Suite possible

- Si un tag historique est vide : essayer `--related-tags`, assouplir `--min-prob` / volume, ou un autre `tag_id` (fetch HTTP + `--search-tags` sur le sujet).
- Optionnel : exporter un **résumé** (compte + 1ère ligne) en stderr quand `--search-tags` réduit à 0 résultat.
