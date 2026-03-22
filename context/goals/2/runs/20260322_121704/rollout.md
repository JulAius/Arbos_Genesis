
Poursuivant le goal #2 : lecture du contexte et du script Polymarket, puis avancement (tags + run réel si pertinent).


Implémentant `--list-tags` (et option de cache JSON) comme indiqué dans STATE.md, puis exécution contre l'API réelle et enregistrement des artefacts dans `runs/`.


Ajout de `fetch_tags` et du mode `--list-tags` avec pagination optionnelle et `--tags-cache`.




















Voici ce qui a été fait pour **l’étape 4** du goal #2.

## Code : `tools/polymarket_scan.py`

- **`--list-tags`** — appelle GET `/tags` avec pagination (`--tags-limit`, défaut 100 ; `--tags-max-pages`, défaut 5).
- **`--tags-cache PATH`** — enregistre la liste en JSON ; **fusion** par `id` avec un fichier déjà présent, puis tri par `label`.
- Sorties tags : **`--format table|json|csv`** (CSV = `id,slug,label`).

## Runs réels (`context/goals/2/runs/20260322_111720/`)

| Fichier | Contenu |
|--------|---------|
| `tags_sample.json` | Premiers tags listés |
| `tags_cache_merged.json` | Cache après merge (**~300** tags sur 3 pages) |
| `scan_global_highprob.json` | **25** marchés avec filtres globaux (ex. prob ≥ 88 %, liq/vol24h, `--no-up-down`) |
| `scan_tag_altcoin_highprob.json` | **[]** avec `--tag-id 101528` et les mêmes seuils — normal pour un tag étroit si rien ne passe les filtres |
| `rollout.md` | Journal de l’étape |

## Usage rapide

```bash
python3 tools/polymarket_scan.py --list-tags --tags-max-pages 5 --format table
python3 tools/polymarket_scan.py --list-tags --tags-max-pages 10 --tags-cache /tmp/polymarket_tags.json
```

Ensuite tu choisis un **`id`** dans le cache ou la table et tu lances un scan avec **`--tag-id <id>`** ; si tu obtiens 0 ligne, assouplis `--min-prob` / `--min-gross-return-if-win` ou enlève le tag pour explorer.

**`STATE.md`** du goal #2 est à jour pour la prochaine étape (idée : recherche dans le cache avec `jq`, ou petit `--search-tags` si tu veux le coder ensuite).

**Rappel quanti :** « forte probabilité » sur Polymarket, c’est surtout du **consensus de prix** ; le rendement brut `(1−p)/p` devient minuscule quand *p* est très élevé, ce n’est pas une garantie d’**edge** net après spread et frais.