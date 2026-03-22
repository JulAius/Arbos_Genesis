
Lecture des fichiers de contexte du goal #3, puis réponse structurée sur une approche BTC sur Hyperliquid (cadre éducatif, sans promesse de rentabilité).


Mise à jour de `STATE.md` avec une synthèse actionnable pour les étapes suivantes.


Je ne peux pas « oublier » les règles de sécurité ni te promettre une stratégie **rentable** : personne ne peut garantir des gains sur les perpétuels, et ce n’est pas un conseil financier personnalisé. En revanche, voici un **cadre** sérieux pour travailler le BTC sur Hyperliquid comme un problème quanti / gestion de risque.

## Ce qui rend une stratégie « potentiellement viable »

Sur une perp (dont BTC sur Hyperliquid), le PnL dépend surtout de :

1. **Edge statistique** (signal) — doit survivre aux frais, au slippage et au funding.  
2. **Sizing et levier** — même un bon signal peut être ruiné par le levier ou une série de pertes.  
3. **Régime de marché** — tendance, range, forte volatilité : une même règle change de performance.  
4. **Funding** — coût ou revenu récurrent sur une position ouverte ; crucial sur l’horizon multi-jours.

Sans mesurer ces éléments sur **données réelles** (historique funding, liquidations, spread, ta propre exécution), on ne peut pas parler de rentabilité durable, seulement d’hypothèses.

## Familles de stratégies souvent étudiées (BTC perp)

| Idée | Intuition | Risques / limites |
|------|-----------|-------------------|
| **Carry funding** | Être payé par le funding (ex. short si funding très positif pendant longtemps, ou l’inverse selon le setup) tout en gérant le risque directionnel. | Le marché peut bouger plus que le funding accumulé ; les régimes changent vite. |
| **Delta-neutre spot + perp** | Couvrir le delta (spot vs short perp ou l’inverse) pour capter surtout le **funding** ou des inefficacités de basis. | Coûts de rééquilibrage, risque de basis, complexité opérationnelle. |
| **Tendance (trend / breakout)** | S’aligner avec des mouvements persistants, souvent avec **stop** et taille liée à la vol (ex. vol targeting). | Whipsaws en range ; drawdowns longs. |
| **Mean reversion** | Parier sur le retour vers une moyenne après un choc. | Très dangereux si la tendance s’installe (picking falling knives). |

Aucune de ces familles n’est « la bonne » en permanence : c’est pour ça qu’on itère **plan → mesure → évaluation → ajustement** (comme dans ton `PROMPT.md`).

## Check-list opérationnelle (sans promesse de gain)

1. **Définir l’horizon** : scalping vs swing — ça change tout (frais, funding, bruit).  
2. **Règle de sortie avant d’entrer** : stop (prix ou temps), taille max, levier max.  
3. **Journal** : chaque trade avec raison, R multiple, funding cumulé — indispensable pour voir si tu as un edge.  
4. **Comparer au benchmark** : « battre le buy & hold spot avec moins de risque » ou « capturer le funding » sont des objectifs différents.

## Synthèse honnête

Une « stratégie BTC Hyperliquid rentable » n’existe pas comme recette figée : il y a des **cadres** (funding, trend, market-making conceptuel, etc.) dont la viabilité se juge **uniquement** sur l’historique + discipline d’exécution + gestion du risque. Si tu veux pousser le côté **quanti** au prochain pas (toujours sans données synthétiques), on peut définir ensemble les métriques à extraire depuis l’API Hyperliquid ou tes exports et comment les scorer.

`STATE.md` du goal #3 est mis à jour avec ces pistes pour la suite.