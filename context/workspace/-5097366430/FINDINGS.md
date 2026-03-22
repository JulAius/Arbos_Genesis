# Connaissances techniques — Workspace Bittensor

> Fichier auto-incrémenté par le bot. Chaque agent (Cursor, Claude Code, Codex, OpenCode) le lit automatiquement via le prompt.
> Format : une ligne par finding, préfixée par `- `.
> Ne pas supprimer ce header.

- `agcli` mélange `WARN ...` et JSON sur stdout → parser avec `output[output.index('{'):]` ou `jq`, jamais `json.loads(output)` directement.
- Auth taostats/taomarketcap : `Authorization: <key>` sans préfixe Bearer (Bearer → 401).
- taomarketcap : le champ prix est `current_price` (pas `usd_quote.price_usd`). L'endpoint validateurs est `/validators/full/` (pas `/validators/` → 405).
- Pagination taostats : `--page` / `--limit` → réponse sous clé `data`. Pagination taomarketcap : `--limit` / `--offset` → réponse sous clé `results`.
- Taostats endpoints payants (plan Pro requis) : `accounting`, `tax-report`, `dtao-portfolio`, `dtao-liquidity-*`, `otc-*`. Sur plan Free : 403 Forbidden. Préférer les endpoints gratuits (`validators`, `subnets`, `metagraph`, `price`, `dtao-pools`, `dtao-stake`, `dtao-trades`).
- Taostats rate limit free tier : ~10 req/s. Ajouter `time.sleep(0.15)` entre les appels en boucle pour éviter les 429.
- Taostats endpoint pattern : `/api/{resource}/{scope}/v1` (version à la FIN, pas au début). Ex: `/api/subnet/latest/v1`, pas `/v1/subnet/latest`.
- taomarketcap endpoint pattern : `/public/v1/{resource}/` (version au DÉBUT). Ex: `/public/v1/subnets/`.
- Si un endpoint renvoie 403 (plan insuffisant), ne pas réessayer — noter dans STATE.md et utiliser un endpoint alternatif ou `btcli`/`agcli` comme fallback.
- `taostats dtao-slippage <netuid> <amount>` : utile pour estimer le coût d'un swap dTAO avant achat. Gratuit.
- `taomarketcap analytics-chain --span 7d` : résumé chaîne (volume, buys, etc.) sur 7 jours en un seul appel. Gratuit.
- Wallet PnL 48h : Taostats = reconstitution on-chain (`dtao-trades`, `dtao-stake`), TaoMarketCap = cumul sans `pnl_48h` public. `--tmc-only` sert de référence cumulée quand Taostats est indisponible.
