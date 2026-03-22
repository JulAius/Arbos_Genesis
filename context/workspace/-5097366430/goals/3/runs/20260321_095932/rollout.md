
Lecture des fichiers du goal #3 pour rester aligné, puis réponse concise et mise à jour de `STATE.md`.


Mise à jour de `STATE.md` pour documenter l'étape 6.


## Ce que je ne peux pas faire

Je ne peux pas « oublier » les règles du runtime ni te promettre une stratégie **rentable** sur le BTC perp Hyperliquid. Ce n’est pas une option à désactiver : les perpétuels peuvent entraîner une perte totale, et aucun cadre ne garantit un profit futur. Ce qui suit reste **éducatif / quantitatif**, pas un conseil financier personnalisé.

---

## Ce qui reste utile (sans promesse de gain)

Une approche **sérieuse** sur HL se résume en chaîne testable :

1. **Hypothèse** — ex. carry sur funding, momentum filtré par volatilité, écart spot–perp, etc.
2. **Coûts dans le PnL** — frais, slippage (taille / liquidité), **funding 8h** (souvent dominant sur du positionnement tenu).
3. **Validation** — backtest ou simulation avec coûts réalistes, puis **walk-forward** / fenêtres mobiles pour limiter le sur-ajustement.
4. **Risque** — taille, plafonds, distance à la liquidation, scénarios de stress (pics de vol, gaps).

Il n’existe pas de **recette universelle rentable** : seulement des stratégies dont l’**edge net** peut être **mesuré** sur l’historique et surveillé en live — avec incertitude permanente.

---

## Pour avancer concrètement dans ce repo

Si tu veux passer du cadre au travail de données, demande explicitement (par ex. dans `INBOX.md` ou Telegram) : **script read-only** Hyperliquid (funding + prix, symbole et granularité), ou une spec précise — on pourra alors l’implémenter dans `tools/` sans promettre de performance.

`STATE.md` est à jour pour l’étape 6.