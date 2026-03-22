
Lecture des fichiers du goal #3 pour rester aligné, puis réponse structurée et mise à jour de `STATE.md`.


Impossible d’« oublier » les règles de sécurité ni de promettre une stratégie rentable : les perpétuels impliquent un risque de perte totale et aucun cadre ne garantit des gains. Voici un cadre quanti utile pour le BTC sur Hyperliquid.

## Ce qui « rend une stratégie testable » (pas « rentable » par défaut)

1. **Edge mesurable** — Le signal doit rester positif **après** frais, slippage estimé et **funding** (souvent dominant sur du long directionnel tenu).
2. **Coûts explicites** — Taker/maker, impact selon taille, fréquence de rebalance ; sur HL le funding 8h est une ligne de PnL à part entière.
3. **Sizing / levier** — Kelly fractionné, plafonds de risque par trade et par jour, distance à la liquidation ; le levier amplifie les erreurs autant que les bons signaux.
4. **Régime** — Tendance vs range vs choc de volatilité : une même règle peut être profitable dans un régime et ruinée dans un autre.
5. **Validation** — Walk-forward, stress (spreads, gaps, funding extrême), et comparaison à un benchmark naïf (buy-and-hold perp, ou stratégie simple).

## Familles de stratégies souvent étudiées (à valider sur **vos** données)

| Idée | Intuition | Risques typiques |
|------|-----------|------------------|
| **Carry funding** | Aller **contre** le funding quand il est très déséquilibré (ex. longs surpayent) | Inversion brutale du funding, mouvement de prix qui dépasse le carry |
| **Momentum / breakout** | Suivre la tendance après filtre vola ou structure de marché | Whipsaw, coûts élevés si trop de trades |
| **Mean reversion** | Range, retour vers une moyenne (plus court horizon) | Tendance forte = série de pertes |
| **Hedge spot–perp** | Arbitrage de basis (si vous avez accès spot + perp) | Coûts, risque de contrepartie, synchronisation |

Aucune de ces familles n’est « rentable » en soi : tout dépend des paramètres, de la période, et de l’exécution.

## Prochain pas concret (aligné avec ton `STATE.md`)

- Définir **horizon** (scalp vs swing) et **hypothèse d’edge** une phrase.
- Collecter **historique** (funding, OI si dispo, prix) via l’API / exports HL, puis backtest avec **coûts réalistes**.
- Itérer uniquement sur ce qui survit au walk-forward et au stress.

Je mets à jour `STATE.md` pour documenter l’étape 3.


**Synthèse :** Je ne peux ni ignorer les règles de sécurité ni te promettre une stratégie **rentable** sur le BTC perp Hyperliquid. En revanche, le chemin sérieux reste : formuler une hypothèse d’edge, tout ramener en **PnL net** (frais, slippage, funding), dimensionner le risque, puis **prouver** la robustesse sur données réelles (walk-forward, stress). Les familles classiques (carry de funding, momentum, mean reversion, jeu de basis) ne sont que des points de départ à tester, pas des recettes garanties. `STATE.md` du goal #3 est à jour pour l’étape 3.