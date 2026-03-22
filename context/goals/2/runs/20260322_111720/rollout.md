# Goal #2 — Step 4 (Polymarket tags + cache)

## Changements code

- `tools/polymarket_scan.py` : mode **`--list-tags`** (GET `/tags`, pagination `--tags-limit` / `--tags-max-pages`), sorties **table** (défaut), **`--format json|csv`**, et **`--tags-cache PATH`** (merge par `id`, réécriture JSON triée par label).

## Commandes exécutées (API réelle)

```bash
python3 tools/polymarket_scan.py --list-tags --tags-max-pages 2 --format json
python3 tools/polymarket_scan.py --list-tags --tags-max-pages 3 --tags-cache context/goals/2/runs/20260322_111720/tags_cache_merged.json
python3 tools/polymarket_scan.py --tag-id 101528 --min-prob 0.88 --min-liquidity 1000 --no-up-down --min-volume24h 200 --min-gross-return-if-win 0.005 --format json --top 30 --max-pages 12
# → [] pour ce tag + filtres (peu ou pas de marchés passant les seuils)
python3 tools/polymarket_scan.py --min-prob 0.88 --min-liquidity 1000 --no-up-down --min-volume24h 200 --format json --top 25 --max-pages 12
# → 25 lignes (ex. slug `will-liverpool-win-the-202526-english-premier-league`)
```

## Fichiers

| Fichier | Rôle |
|--------|------|
| `tags_sample.json` | Échantillon `--list-tags` |
| `tags_cache_merged.json` | Cache merge (300 entrées après 3 pages) |
| `scan_global_highprob.json` | Scan global haute probabilité |
| `scan_tag_altcoin_highprob.json` | Scan tag altcoin (vide avec filtres serrés) |

## Remarque

Un **`--tag-id`** étroit + seuils élevés peut donner **0 résultat** : assouplir `--min-prob` / `--min-gross-return-if-win` ou retirer le tag pour explorer, puis resserrer.
