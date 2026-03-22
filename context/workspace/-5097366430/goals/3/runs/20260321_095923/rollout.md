
Lecture des fichiers du goal #3 pour rester aligné, puis réponse concise et mise à jour de `STATE.md`.


Mise à jour de `STATE.md` pour documenter l'étape 5.


## Ce que je ne peux pas faire

Je ne peux pas « oublier » les règles du runtime ni te promettre une stratégie **rentable** sur le BTC perp Hyperliquid. Ce n’est pas du caprice : les marchés ne permettent pas de garantir un profit, et les perpétuels peuvent entraîner des pertes importantes ou totales.

---

## Ce qui reste utile (cadre quanti, à valider sur données)

| Levier | Idée | À mesurer |
|--------|------|-----------|
| **Coûts** | Edge = signal **net** de frais, slippage, **funding 8h** | Historique funding + hypothèses d’exécution |
| **Régimes** | Tendance / range / pics de vol | Filtrer ou adapter les règles (sinon sur-ajustement) |
| **Familles** | Carry funding, momentum, mean reversion, basis spot–perp | Chacune se teste ; aucune n’est « rentable » par défaut |
| **Risque** | Taille, levier, distance à la liquidation, plafonds journaliers | Stress + walk-forward hors échantillon |

Pipeline réaliste : **hypothèse → données réelles (API/UI HL) → backtest avec coûts réalistes → validation temporelle** — sans promesse de résultat futur.

---

`STATE.md` est à jour pour l’**étape 5** (même refus + rappel du pipeline + proposition : script read-only funding/prix si tu le demandes explicitement). Si tu veux qu’on code ce collecteur dans le dépôt, indique le format souhaité (Python, fréquence, paires).