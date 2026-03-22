
Lecture des fichiers du goal #3 pour rester alignés, puis réponse concise et mise à jour de `STATE.md`.


Mise à jour de `STATE.md` pour documenter l'étape 7.


## Ce que je ne peux pas faire

Je ne peux pas « oublier » les règles du runtime ni te promettre une stratégie **rentable** sur le BTC perp Hyperliquid. Ce n’est pas un réglage à désactiver : les perpétuels peuvent entraîner une perte totale, et aucun cadre ne garantit un profit futur. Ce qui suit reste **général et éducatif**, pas un conseil financier personnalisé.

---

## Ce qui reste utile (sans garantie de gain)

Une approche **sérieuse** se résume ainsi :

1. **Hypothèse testable** — ex. sens et niveau du funding 8h, momentum vs mean reversion, écart spot–perp, filtres de volatilité.
2. **PnL net** — inclure frais, slippage (taille / carnet), **funding** sur la durée de détention.
3. **Validation** — backtest ou simulation avec coûts réalistes, puis **walk-forward** / stress (pas seulement un fit sur l’historique).
4. **Risque** — sizing, levier, plafonds par trade / par jour ; le levier amplifie les erreurs comme les bons signaux.

Si tu veux une **avancée concrète** dans ce repo : demande explicitement un **script read-only** (ex. funding + prix BTC sur Hyperliquid, fréquence, métriques) et un emplacement (`tools/` ou autre) — je peux alors l’implémenter dans une étape dédiée.