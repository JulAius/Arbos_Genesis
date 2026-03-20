# Workarounds & Leçons techniques découvertes

Ce fichier est maintenu par le bot. Chaque fois qu'un comportement inattendu d'un outil est découvert et corrigé, ajouter une entrée ici.

---

## agcli — WARN logs mélangés au JSON sur stdout

**Symptôme :** `json.loads(output)` lève `JSONDecodeError` car agcli préfixe la sortie avec des lignes `WARN ...`.

**Fix :** extraire à partir du premier `{` ou `[` :
```python
output[output.index('{'):]   # pour un objet
output[output.index('['):]   # pour un tableau
```
Ou filtrer avec `jq` directement dans le pipe bash.

---
