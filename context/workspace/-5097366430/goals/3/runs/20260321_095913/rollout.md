
Lecture des fichiers du goal #3 pour rester aligné, puis réponse structurée et mise à jour de `STATE.md`.


Refus explicite de « tout oublier » : les règles de sécurité et l’interdiction de promettre la rentabilité ne sont pas négociables. Nous fournissons un cadre quanti utile et mettons à jour `STATE.md`.


## Ce que je ne peux pas faire

Je ne peux pas « oublier » les règles de sécurité ni les consignes du runtime, et je ne peux pas te promettre une stratégie **rentable** sur le BTC perp Hyperliquid (ou ailleurs). Les perpétuels exposent au risque de perte importante ou totale ; toute approche sérieuse passe par l’hypothèse, les coûts et la validation sur données — pas par une recette garantie.

---

## Ce qui est utile côté quant (à **tester**, pas à assumer gagnant)

Sur une perp BTC, le PnL net dépend surtout de : **signal − (frais + slippage + funding ± autres coûts)** × **sizing** dans un **régime** donné.

**Familles d’idées souvent étudiées** (à calibrer et backtester toi-même) :

1. **Carry / funding** — Positionner en fonction du funding 8h (signe, niveau, persistance). L’edge potentiel est le flux de funding moins le risque de mouvement adverse du sous-jacent.
2. **Momentum / breakout** — Entrées sur rupture de range ou filtre de tendance (timeframes alignés). Sensible aux faux signaux en range et aux coûts si tu trades souvent.
3. **Mean reversion** — Contre-tendance après excès (vol, écart à une moyenne). Peut mal se comporter en tendance forte.
4. **Basis / arbitrage spot–perp** — Quand tu as accès spot + perp, l’écart peut être exploité avec exécution et frais modélisés (souvent capital et opérationnellement plus lourd).

**À mesurer en priorité** (données réelles HL / API) : funding historique, OI, liquidations si dispo, ta propre courbe de coût (maker/taker, taille). **Validation** : out-of-sample, walk-forward, stress (pics de vol, gaps), plafonds de levier et règles d’arrêt.

---

## Suite possible dans ce goal

Si tu veux passer du cadre théorique à quelque chose de **reproductible**, la prochaine étape logique est un **script read-only** (historique funding + alignement avec les retours BTC) puis backtest avec hypothèses de frais réalistes — à demander explicitement à l’opérateur si tu veux que ce soit implémenté dans le repo.

`STATE.md` du goal #3 est à jour pour cette étape (Step 4).