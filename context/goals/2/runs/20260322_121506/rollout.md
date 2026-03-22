
Poursuivant le goal #2 : lecture du contexte et du script Polymarket, puis amélioration et exécution pour produire des résultats exploitables.


Étendant le script avec export JSON/CSV et filtres (excl. slugs `up-or-down`, option `competitive`), puis exécution sur l’API réelle et mise à jour de `STATE.md`.




















Voici ce qui a été fait pour le **goal #2** (étape 2).

## Outil `tools/polymarket_scan.py`

- **`--format table|json|csv`** — sortie exploitable pour backtests / tableurs (`json` / `csv` = en-têtes fixes).
- **`--no-up-down`** — exclut les slugs contenant `up-or-down` (bruit crypto intraday).
- **`--exclude-slug-substr STR`** — répétable pour d’autres motifs de slug.
- **`--min-competitive` / `--max-competitive`** — filtre optionnel sur le champ Gamma `competitive`.
- Refactor : collecte dans **`collect_rows()`**, puis formatage.

## Run réel (API Gamma)

Commande du type : prob ≥ 88 %, liquidité ≥ 1000, vol 24h ≥ 200, `--no-up-down`, 15 pages.

- **1051** marchés correspondent encore ; en tête : beaucoup de **sports live**, aussi politique, NHL, tweets Elon, etc.
- Beaucoup de lignes à **~99.95 %** sur l’outcome menant → gain brut espéré très faible si tu achètes ce côté (ordre de grandeur **~0.05 %** avant frais / spread / risque de résolution). Ce n’est pas un filtre d’« edge », seulement de **consensus à prix serré**.

## Fichiers goal #2

- `context/goals/2/runs/20260322_111526/high_prob_sample.json` — **50** lignes en JSON.
- `context/goals/2/runs/20260322_111526/rollout.md` — résumé de l’étape.
- `context/goals/2/STATE.md` — mis à jour pour la prochaine itération.

**À retenir :** « forte probabilité » sur Polymarket = marché déjà très convaincu ; pour des **opportunités** au sens quanti, il faut en général comparer au **modèle** (ou aux fondamentaux) et vérifier les **règles de résolution** sur le site pour chaque marché avant toute décision.