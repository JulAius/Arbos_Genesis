# /push — Commit et push les changements

1. Vérifie la syntaxe Python : `python3 -c "import py_compile; py_compile.compile('arbos.py', doraise=True)"`
2. `git status` pour voir les fichiers modifiés
3. `git diff --stat` pour le résumé
4. `git log --oneline -3` pour le style des commits récents
5. Stage uniquement `arbos.py` et les fichiers `.claude/` modifiés (pas les logs, chatlogs, STATE.md, etc.)
6. Commit avec un message descriptif en anglais, format conventionnel (feat/fix/refactor/chore)
7. Push sur la branche courante

Ne push JAMAIS les fichiers de contexte runtime (context/chat/, context/workspace/*/goals/*/STATE.md, etc.)
