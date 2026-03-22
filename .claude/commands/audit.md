# /audit — Audit approfondi d'arbos.py

Effectue un audit technique complet de `arbos.py`. Lis d'abord le fichier `FINDINGS.md` (dans `.claude/`) pour connaître les bugs déjà identifiés et leur statut.

## Zones à auditer

1. **Routing DM vs Workspace** : Vérifie que TOUTES les fonctions qui acceptent `workspace_id` distinguent correctement les 3 cas (`== 0` legacy, `> 0` DM, `< 0` workspace group). Cherche les patterns `if workspace_id:` ou `else: _tg_goals_map()` qui oublient la distinction DM.

2. **Goal lifecycle** : Trace le cycle complet create → loop → deliver → cleanup pour les goals ephemeral ET regular. Vérifie les race conditions (locks), les zombie goals, les fuites de ressources (threads, fichiers).

3. **Crash recovery** : Vérifie que `_goal_loop` / `_goal_loop_inner` gèrent correctement tous les types d'exceptions. Vérifie que `_goal_manager_tick_map` redémarre les threads morts.

4. **Tools & prompts** : Vérifie que `load_prompt()` assemble correctement le contexte pour chaque type de workspace. Vérifie que les tools (btcli, agcli, taostats, taomarketcap) sont accessibles.

5. **Streaming & heartbeat** : Vérifie le seeding `.step_msg`, le reuse du message de progression, le `message_thread_id` pour les topic groups.

6. **Concurrence** : Vérifie `_goals_lock`, `_claude_semaphore`, `_token_usage` global, `_step_count` sans lock.

## Output attendu

- Liste des bugs trouvés avec sévérité (High/Medium/Low), numéros de ligne, et description
- Comparaison avec FINDINGS.md : quels bugs sont nouveaux ? lesquels sont fixés ?
- Met à jour FINDINGS.md avec les nouveaux findings et marque les bugs fixés comme `[FIXED]`
