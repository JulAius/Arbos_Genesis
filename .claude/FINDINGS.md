# Technical Findings — Arbos Bittensor Bot

Ce fichier est la mémoire technique du projet. Chaque session d'audit (`/audit`) le met à jour.
Les skills `/fix`, `/improve`, `/status` le lisent pour prioriser le travail.

---

## Bugs

### [FIXED] HIGH — Legacy /clear nuke tout sans clear mémoire (l.4646-4670)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** `/clear` en mode legacy fait `shutil.rmtree(CONTEXT_DIR)` qui supprime TOUT (workspace, DM, goals) mais ne clear que `_goals` en mémoire. `_tg_workspace_goals` et `_tg_dm_goals` restent peuplés → threads zombies. Ne recrée pas `GOALS_DIR` ni `DM_GOALS_DIR` après.
- **Fix:** Clear les 3 maps (legacy + workspace + DM) avec stop_event, save_goals(0), recréer GOALS_DIR + DM_GOALS_DIR + WORKSPACES_DIR.

### [FIXED] MEDIUM — Race condition dans _create_ephemeral_arbos_goal (l.3450-3460)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** L'index uniqueness check (`while idx in gmap: idx += 1`) est fait SANS `_goals_lock`.
- **Fix:** Déplacé le check d'unicité dans un bloc `with _goals_lock`.

### [FIXED] MEDIUM — _seed_fixed_goal_for ignore DM routing (l.667)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** Utilise `_tg_goals_map(workspace_id)` pour tous les `workspace_id != 0`, sans distinguer DM (>0).
- **Fix:** Ajouté le 3-way dispatch (== 0 / > 0 / < 0).

### [FIXED] MEDIUM — run_agent_streaming hardcode --model bot (l.3903)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** Le `else` branch passait `extra_flags=["--model", "bot"]` au lieu de `wm`.
- **Fix:** Remplacé par `_claude_cmd(prompt, model=wm)`.

### [FIXED] MEDIUM — _token_usage global partagé entre steps concurrents (l.723-726)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** `_reset_tokens()` clear le dict global partagé entre tous les steps.
- **Fix:** `_token_usage` est maintenant thread-keyed (dict par thread_id). `_add_tokens()` helper pour les incréments. `_token_owner` dict pour que les heartbeat threads lisent les compteurs de leur thread parent.

### [FIXED] LOW — load_prompt charge le chatlog global (l.797)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** `load_prompt()` chargeait le chatlog global pour tous les workspace types.
- **Fix:** 3-way dispatch : workspace → `load_chatlog_group(chat_id)`, DM → pas de chatlog partagé (seed dans STATE.md), legacy → global.

### [FIXED] LOW — _workspace_json_path ignore DM (l.263)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Fix:** Route vers `DM_GOALS_DIR / str(workspace_id) / workspace.json` quand `workspace_id > 0`.

### [FIXED] LOW — _telegram_qa_goal_template_path ignore DM (l.614)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Fix:** 3-way dispatch : DM → cherche dans `DM_GOALS_DIR`, workspace → `WORKSPACES_DIR`, sinon fallback repo root.

### [OPEN] LOW — btcli shim false positive sur flags à valeur (tools/shims/btcli l.25)
- **Date:** 2026-03-22
- **Description:** `btcli --network wallet` serait bloqué à tort car le shim ne consomme pas la valeur des flags.
- **Impact:** L'agent ne peut pas spécifier un réseau nommé "wallet" (cas rare).

### [OPEN] LOW — Pas d'injection d'état crash dans STATE.md
- **Date:** 2026-03-22
- **Description:** Quand un step timeout ou crash, l'info n'est pas écrite dans STATE.md. Le step suivant redémarre sans savoir ce qui a échoué.
- **Impact:** L'agent peut répéter les mêmes erreurs.

### [OPEN] LOW — stderr pipe buffer deadlock potentiel (run_agent)
- **Date:** 2026-03-22
- **Description:** stderr est PIPE mais jamais lu pendant l'exécution. Si le child écrit >64KB sur stderr, deadlock jusqu'au timeout.
- **Impact:** Rare mais possible avec des tools verbeux.

---

## Améliorations appliquées

### [DONE] Crash recovery dans _goal_loop — 2026-03-22
- try/except double couche (inner run_step + outer fatal)
- `_deliver_ephemeral_crash()` pour les goals ephemeral
- Notification Telegram + backoff pour les goals regular
- Auto-restart via `_goal_manager_tick_map`

### [DONE] Heartbeat / progress editing — 2026-03-22
- Seeding `.step_msg` avec le message_id de "🔄 Recherche en cours…"
- `run_step()` réutilise le message au lieu d'en créer un nouveau
- Support `message_thread_id` dans `_send_telegram_new` pour topic groups
- Step messages atterrissent dans le bon topic via META.json

### [DONE] DM goal isolation — 2026-03-22
- `context/dm/<chat_id>/goals/<idx>/` pour chaque DM
- Sign-based routing : >0=DM, <0=workspace, 0=legacy
- `_tg_dm_goals_map()`, `_goals_map_for_chat()`
- `_load_goals()` charge les DM goals au démarrage

### [DONE] Ephemeral mini-goals /arbos — 2026-03-22
- `_create_ephemeral_arbos_goal()` : GOAL.md + STATE.md + META.json
- `_goal_loop_inner` : check RESPONSE.md, max_steps, timeout
- `_deliver_ephemeral_response/timeout/crash()` + `_cleanup_ephemeral_goal()`
- 4 handlers : handle_arbos, handle_voice, handle_document, handle_photo

### [DONE] ARBOS_TIMEOUT = 1800s (30 min) — 2026-03-22

---

## Patterns techniques à retenir

### 3-way workspace dispatch
Toute fonction qui route par `workspace_id` DOIT utiliser :
```python
if workspace_id == 0:
    # legacy CLI
elif workspace_id > 0:
    # DM chat → DM_GOALS_DIR / str(workspace_id)
else:
    # workspace group → WORKSPACES_DIR / str(workspace_id)
```

### Goal lifecycle
```
create → GoalState(started=True) → _goal_manager_tick_map spawns thread
→ _goal_loop → _goal_loop_inner (while not stop_event)
→ load_prompt → run_step → check RESPONSE.md (ephemeral) or STOP/PAUSE
→ cleanup or restart
```

### Ephemeral goal flow
```
bot.send_message("🔄") → capture msg_id → _create_ephemeral_arbos_goal(progress_msg_id=...)
→ seed .step_msg → _goal_loop_inner → run_step (reuse msg) → heartbeat edits
→ RESPONSE.md exists? → _deliver_ephemeral_response → _cleanup
→ max_steps/timeout? → _deliver_ephemeral_timeout → _cleanup
→ crash? → _deliver_ephemeral_crash → _cleanup
```

### Lock discipline
- `_goals_lock` : toujours acquérir avant de lire/écrire les goals maps ou appeler `_save_goals()`
- `_claude_semaphore` : acquérir dans run_agent/run_agent_streaming, release dans finally
- `_token_lock` : protège `_token_usage` (mais le dict est global — bug connu)
