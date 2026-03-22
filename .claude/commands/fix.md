# /fix — Corriger les bugs connus

Lis `.claude/FINDINGS.md` pour voir les bugs connus et leur statut. Corrige les bugs marqués `[OPEN]` par ordre de sévérité (High → Medium → Low).

## Règles

1. **Lis le code avant de modifier** — comprends le contexte complet
2. **Un fix à la fois** — ne mélange pas plusieurs corrections
3. **Vérifie la syntaxe** après chaque modification : `python3 -c "import py_compile; py_compile.compile('arbos.py', doraise=True)"`
4. **Teste la cohérence** — le fix ne doit pas casser d'autres chemins
5. **Respecte le pattern 3-way dispatch** : `if workspace_id == 0: ... elif workspace_id > 0: ... else: ...` pour toute fonction qui route par workspace_id
6. **Met à jour FINDINGS.md** : marque le bug comme `[FIXED]` avec la date et une description du fix

## Après chaque fix

- Vérifie syntaxe Python
- Vérifie que les fonctions modifiées sont cohérentes avec leurs appelants
- Log le fix dans FINDINGS.md

## $ARGUMENTS

Si un argument est fourni (ex: `/fix race-condition`), ne corrige que le bug correspondant. Sinon, corrige le bug High le plus prioritaire.
