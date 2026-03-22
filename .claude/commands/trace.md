# /trace — Tracer un flux de bout en bout

Trace le parcours complet d'une action dans le code pour vérifier sa cohérence.

## $ARGUMENTS

Flux disponibles :
- `arbos-member` — /arbos par un membre : message → ephemeral goal → loop → RESPONSE.md → delivery → cleanup
- `arbos-owner` — /arbos par l'owner : message → run_agent_streaming → reply
- `goal-create` — /goal : commande → goal dir → GoalState → _goal_manager → thread spawn
- `goal-crash` — crash dans run_step : exception → recovery → notification → restart
- `dm-goal` — goal dans un DM : routing → context/dm/<cid>/ → isolation
- `workspace-goal` — goal dans un workspace group : routing → context/workspace/<cid>/ → GOAL_TELEGRAM_BITTENSOR.md
- `voice` — message vocal : transcription → ephemeral goal

Sans argument : liste les flux disponibles.

## Output

Pour chaque flux :
1. Diagramme séquentiel (fonctions appelées dans l'ordre)
2. Fichiers lus/écrits à chaque étape
3. Points de défaillance identifiés
4. Verdict : OK / BUG / AMÉLIORATION POSSIBLE
