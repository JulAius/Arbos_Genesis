# /status — État du projet

Donne un rapport rapide sur l'état du projet :

1. **Git** : branche, dernier commit, fichiers modifiés non commités
2. **Syntaxe** : `python3 -c "import py_compile; py_compile.compile('arbos.py', doraise=True)"`
3. **Taille** : `wc -l arbos.py`
4. **Bugs connus** : Lis `.claude/FINDINGS.md` et résume les bugs `[OPEN]` par sévérité
5. **Architecture** : Compte les fonctions (`def `), les handlers (`@bot.message_handler`), les goals maps (`_tg_workspace_goals`, `_tg_dm_goals`, `_goals`)

Format de sortie : tableau concis, pas de prose inutile.
