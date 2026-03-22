
Poursuivant le goal #2 (étape 3) : lecture du contexte et du script Polymarket pour enrichir le pipeline et proposer des filtres exploitables.


Vérifiant la structure réelle des objets marchés renvoyés par l'API Gamma pour ajouter `conditionId`, URLs et tags.

















Enrichissant le script : champs pipeline (`conditionId`, URLs, IDs), rendement brut approximatif `(1-p)/p`, et filtres `--tag-id` / `--exclude-tag-id` (API Gamma documentée).
































Voici ce qui a été fait pour **l’étape 3** du goal #2.

## `tools/polymarket_scan.py`

1. **Champs utiles pour un pipeline (données Gamma réelles)**  
   Chaque ligne inclut notamment :  
   `condition_id`, `gamma_market_id`, `event_slugs`, `primary_event_slug`,  
   `url_market` / `url_event` (`https://polymarket.com/market/...` et `/event/...`),  
   `leading_clob_token_id` (aligné sur l’outcome menant),  
   `best_bid`, `best_ask`, `spread` quand présents,  
   et **`gross_return_if_win_approx`** = \((1-p)/p\) pour le côté le plus cher.

2. **Filtres documentés Gamma**  
   `--tag-id`, `--exclude-tag-id`, `--related-tags` (voir la [doc fetch markets](https://docs.polymarket.com/developers/gamma-markets-api/fetch-markets-guide)).  
   Les tags disponibles : `GET https://gamma-api.polymarket.com/tags`.

3. **Filtre « pas que des favoris à 99,95 % »**  
   `--min-gross-return-if-win` / `--max-gross-return-if-win` sur ce \((1-p)/p\).  
   Ex. `--min-gross-return-if-win 0.01` impose à peu près **p ≤ ~99 %** sur le outcome menant, ce qui enlève une grande partie du bruit « quasi résolu ».

4. **CSV**  
   Colonnes alignées avec les nouveaux champs (`event_slugs_json` = JSON dans une cellule).

## Artefacts

- `context/goals/2/runs/20260322_121649/enriched_high_prob.json` — échantillon haute proba avec champs enrichis.  
- `context/goals/2/runs/20260322_121649/min_gross_1pct.json` — même logique avec upside brut **≥ ~1 %** (toujours brut, sans frais ni spread).  
- `rollout.md` dans ce dossier + **`STATE.md`** mis à jour.

**Rappel quanti :** une probabilité implicite élevée ne signifie pas un edge ; \((1-p)/p\) devient très petit quand \(p\to 1\). Pour un **écart vs un modèle externe**, il faut encore brancher une source hors Polymarket et comparer à `max_implied_prob` (prochaine étape logique).