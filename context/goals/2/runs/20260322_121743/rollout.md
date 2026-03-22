
Poursuivant le goal #2 (étape 5) : lecture du contexte et du script Polymarket pour implémenter la suite (recherche de tags, rescans).


Implémentant `--search-tags` et `--list-tags-from-cache` (recherche hors ligne sur le cache), puis exécution d'un scan réel avec des filtres assouplis sur un tag pertinent.


























Implémentant le filtrage `--search-tags` et `--list-tags-from-cache`, puis exécution de scans réels.








Les scans sur le tag « election 2024 » (400) renvoient [] — marchés probablement inactifs ou hors filtres. Le flux NBA Draft + recherche locale fonctionne. Mise à jour de `STATE.md`.





Voici ce qui a été fait pour **l’étape 5** du goal #2.

## Code : `tools/polymarket_scan.py`

- **`--search-tags SUBSTR`** (répétable) : après chargement des tags (HTTP ou fichier), ne garde que les entrées dont le **`slug` ou le `label`** contient une des sous-chaînes (insensible à la casse).
- **`--list-tags-from-cache PATH`** : avec **`--list-tags`**, charge la liste depuis un JSON (liste d’objets) **sans** appeler GET `/tags`.

## Runs réels — `context/goals/2/runs/20260322_121813/`

| Fichier | Contenu |
|--------|---------|
| `tags_search_nba.json` | 3 tags issus du cache + filtre `nba` (ex. NBA Draft `id` **100283**) |
| `scan_tag_nba_draft_relaxed.json` | Scan **`--tag-id 100283`** + `--related-tags`, prob ≥ 85 %, liquidité ≥ 150 — **données Gamma** (marchés draft 2026, côté « No » très probable, `gross_return_if_win_approx` ~0,25–0,4 %) |
| `scan_tag_election2024_relaxed.json` | **`tag_id=400`** (election 2024) — **`[]`** avec les mêmes idées de filtres (pas de lignes dans ce flux au moment du run) |

## Lecture quanti

Une **probabilité implicite élevée** décrit surtout un **consensus** ; le rendement brut approximatif **(1−p)/p** sur le côté gagnant tend vers **0** quand *p* → 1. Pour un « edge », il faut une **vue externe** (modèle, info, résolution) par rapport à ce prix.

## Commandes utiles

```bash
python3 tools/polymarket_scan.py --list-tags --list-tags-from-cache context/goals/2/runs/20260322_111720/tags_cache_merged.json --search-tags nba --format json

python3 tools/polymarket_scan.py --tag-id 100283 --related-tags --min-prob 0.85 --min-liquidity 150 --min-volume24h 0 --no-up-down --format json --top 20 --max-pages 15
```

`STATE.md` du goal #2 est à jour ; `rollout.md` est dans le dossier de run ci-dessus.