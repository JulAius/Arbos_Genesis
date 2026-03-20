# Bot Memory — auto-injected, bot-maintained

> Ce fichier est lu automatiquement à chaque step et injecté dans ton prompt.
> Écris ici tes découvertes techniques. **Max 50 lignes utiles.**
> Si ça dépasse, self-curate : supprime les entrées obsolètes ou fusionne.

---

- `agcli` préfixe stdout avec `WARN ...` avant le JSON → `json.loads(output)` échoue. Fix : `output[output.index('{'):]` ou filtrer avec `jq`.

---
