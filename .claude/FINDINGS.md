# Technical Findings — Arbos Bittensor Bot

Ce fichier est la mémoire technique du projet. Chaque session d'audit (`/audit`) le met à jour.
Les skills `/fix`, `/improve`, `/status` le lisent pour prioriser le travail.

---

## Bugs

### [FIXED] HIGH — Legacy /clear nuke tout sans clear mémoire (l.4646-4670)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** `/clear` en mode legacy fait `shutil.rmtree(CONTEXT_DIR)` qui supprime TOUT (workspace, DM, goals) mais ne clear que `_goals` en mémoire. `_tg_workspace_goals` et `_tg_dm_goals` restent peuplés → threads zombies. Ne recrée pas `GOALS_DIR` ni `DM_GOALS_DIR` après.
- **Fix:** Clear les 3 maps (legacy + workspace + DM) avec stop_event, save_goals(0), recréer GOALS_DIR + DM_GOALS_DIR + WORKSPACES_DIR.

### [FIXED] HIGH — _step_count race condition (l.2918)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** `_step_count += 1` sans lock — multiple goal threads incrémentent en parallèle, pertes d'incréments.
- **Fix:** Déplacé l'incrément de `_step_count`, `gs.step_count`, et `gs.last_run` dans le bloc `with _goals_lock`.

### [FIXED] HIGH — _tg_goals_map() / _tg_dm_goals_map() init race (l.458-467)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** Check-then-set sans lock : deux threads peuvent initialiser le même workspace_id, le second écrase le dict du premier.
- **Fix:** Remplacé par `dict.setdefault()` (atomique pour CPython).

### [FIXED] HIGH — _total_registered_goals() lecture non synchronisée (l.603-609)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** Itère `_tg_workspace_goals` et `_tg_dm_goals` sans `_goals_lock` → `RuntimeError: dictionary changed size during iteration` possible.
- **Fix:** Ajouté `with _goals_lock` autour de la fonction.

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

### [FIXED] MEDIUM — RESPONSE.md missing-file race dans delivery (l.3630)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** `_deliver_ephemeral_response()` lit RESPONSE.md sans try/except après que `_goal_loop_inner` a vérifié son existence — le fichier peut disparaître entre le check et la lecture.
- **Fix:** Ajouté try/except FileNotFoundError + vérification contenu non vide.

### [FIXED] MEDIUM — META.json KeyError dans delivery functions
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** `meta["chat_id"]` crash si le JSON est valide mais incomplet. Affecte `_deliver_ephemeral_response`, `_deliver_ephemeral_timeout`, `_deliver_ephemeral_crash`.
- **Fix:** Remplacé par `meta.get("chat_id")` avec early return si absent.

### [FIXED] MEDIUM — Chatlog concurrent I/O crash (load_chatlog/load_chatlog_group)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** `f.read_text()` dans les fonctions chatlog sans protection — fichier peut être rotaté/supprimé par `_rolling_chatlog_append_locked()` pendant la lecture → `FileNotFoundError`.
- **Fix:** Ajouté try/except (OSError, FileNotFoundError) autour de chaque `f.read_text()` avec `continue`.

### [FIXED] MEDIUM — Fallback provider ping-pong (l.1863)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** `_try_primary()` appelé à chaque step quand en fallback — si primary toujours en quota exceeded, gaspille un appel API puis rebascule sur fallback immédiatement.
- **Fix:** Ajouté `_fallback_since` timestamp + `FALLBACK_COOLDOWN=300s`. `_try_primary()` refuse de tenter si le cooldown n'est pas écoulé.

### [FIXED] MEDIUM — /arbos double ephemeral goal (même user)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** Deux `/arbos` simultanés du même user créent deux goals éphémères → double coût, double réponse.
- **Fix:** Dedup dans `_create_ephemeral_arbos_goal()` : si un goal éphémère actif existe pour le même `user_id`, retourne son index sans en créer un nouveau.

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

### [FIXED] LOW — _token_usage / _token_owner entries never cleaned (l.734)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** Entrées dans `_token_usage` et `_token_owner` ne sont jamais supprimées après la mort du thread.
- **Fix:** Pruning des threads morts dans `_reset_tokens()` — supprime les entrées dont le thread n'est plus dans `threading.enumerate()`.

### [FIXED] LOW — Empty DM goals maps accumulate (l.464)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** `_tg_dm_goals[chat_id] = {}` créé pour chaque DM, jamais nettoyé après cleanup du dernier goal.
- **Fix:** `_cleanup_ephemeral_goal()` supprime l'entrée DM de `_tg_dm_goals` quand la map est vide.

### [FIXED] LOW — shutil manquant dans make_run_dir (l.826)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** `shutil.rmtree` utilisé dans `make_run_dir` mais `shutil` non importé au module-level ni localement.
- **Fix:** Ajouté `import shutil` dans la fonction.

### [FIXED] LOW — STATE.md sans limite de taille dans load_prompt
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** STATE.md chargé intégralement → overflow du contexte si l'agent écrit beaucoup.
- **Fix:** Capped à `MAX_STATE_CHARS=30000`, garde la queue (contenu le plus récent).

### [FIXED] LOW — Voice temp file collision entre threads (l.5075)
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** Nom de fichier statique `_voice_tmp.{ext}` — deux /arbos voice simultanés écrasent le même fichier.
- **Fix:** Nom unique par request : `_voice_tmp_{thread_ident}_{timestamp}.{ext}`.

### [FIXED] LOW — Run dirs accumulent sans limite
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** `make_run_dir()` crée des répertoires `runs/YYYYMMDD_HHMMSS` sans jamais les nettoyer.
- **Fix:** Pruning dans `make_run_dir()` : garde les `MAX_RUN_DIRS=50` plus récents, supprime les anciens.

### [OPEN] LOW — btcli shim false positive sur flags à valeur (tools/shims/btcli l.25)
- **Date:** 2026-03-22
- **Description:** `btcli --network wallet` serait bloqué à tort car le shim ne consomme pas la valeur des flags.
- **Impact:** L'agent ne peut pas spécifier un réseau nommé "wallet" (cas rare).

### [FIXED] LOW — Pas d'injection d'état crash dans STATE.md
- **Date:** 2026-03-22 | **Fixed:** 2026-03-22
- **Description:** Quand un step timeout ou crash, l'info n'est pas écrite dans STATE.md. Le step suivant redémarre sans savoir ce qui a échoué.
- **Fix:** `_inject_state_crash()` ajoute un header `## ⚠️ Step N — CRASH/ÉCHEC` dans STATE.md avec le type d'erreur et un rappel d'éviter la même approche.

### [OPEN] LOW — stderr pipe buffer deadlock potentiel (run_agent)
- **Date:** 2026-03-22
- **Description:** stderr est PIPE mais jamais lu pendant l'exécution. Si le child écrit >64KB sur stderr, deadlock jusqu'au timeout.
- **Impact:** Rare mais possible avec des tools verbeux.

### [OPEN] LOW — Non-atomic file writes (GOAL.md, STATE.md, META.json)
- **Date:** 2026-03-22
- **Description:** `.write_text()` n'est pas atomique — si le processus agent lit pendant l'écriture, il peut obtenir un contenu partiel. Risque théorique avec les fichiers goal écrits par `_create_ephemeral_arbos_goal`.
- **Impact:** Très rare en pratique (les écritures sont petites), mais possible.

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

### [DONE] Concurrency hardening — 2026-03-22
- `_step_count` sous `_goals_lock`
- `_tg_goals_map()`/`_tg_dm_goals_map()` → `dict.setdefault()` (atomique CPython)
- `_total_registered_goals()` sous `_goals_lock`
- Token tracking thread-keyed + dead thread pruning
- Chatlog reads protégés contre FileNotFoundError (rotation concurrente)

### [DONE] Resource management — 2026-03-22
- Run dir rotation (MAX_RUN_DIRS=50)
- STATE.md truncation (MAX_STATE_CHARS=30000)
- Voice temp file unique par request
- Dead `_token_usage`/`_token_owner` entries prunées
- Empty DM goals maps nettoyées après cleanup

### [DONE] Fallback provider robustness — 2026-03-22
- `FALLBACK_COOLDOWN=300s` pour éviter le ping-pong primary/fallback
- Ephemeral goal dedup par user (même workspace)

### [DONE] Rate limiting Telegram — 2026-03-22
- `time.sleep(0.35)` entre les chunks dans `_telegram_send_final_chunks`

### [DONE] Knowledge persistence (ephemeral → template) — 2026-03-22
- `_harvest_ephemeral_knowledge()` : avant cleanup, extrait les findings techniques du STATE.md du goal éphémère
- Cherche les sections `## Connaissances techniques`, `## Findings`, `## Découvert`, etc.
- Dédup contre les entrées existantes dans le template GOAL_TELEGRAM_BITTENSOR.md
- Supporte aussi un fichier KNOWLEDGE.md explicite dans le goal dir
- Instructions mises à jour dans `_create_ephemeral_arbos_goal()` : point 6 demande à l'agent d'écrire ses findings dans STATE.md

### [DONE] Crash/failure injection dans STATE.md — 2026-03-22
- `_inject_state_crash()` : append un header `## ⚠️ Step N — CRASH/ÉCHEC` dans STATE.md
- Appelé sur Exception (avec traceback) ET sur failure (exit code non-zéro)
- Le step suivant lit STATE.md et voit l'erreur → évite de reproduire la même approche

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
→ step fail? → _inject_state_crash() → next step reads crash info
→ RESPONSE.md exists? → _deliver_ephemeral_response → _harvest_knowledge → _cleanup
→ max_steps/timeout? → _deliver_ephemeral_timeout → _harvest_knowledge → _cleanup
→ crash? → _deliver_ephemeral_crash → _harvest_knowledge → _cleanup
```

### Knowledge persistence loop
```
Agent discovers workaround → writes "## Connaissances techniques" in STATE.md
→ _cleanup_ephemeral_goal() calls _harvest_ephemeral_knowledge()
→ reads STATE.md findings, dedup against template entries
→ appends truly new findings to GOAL_TELEGRAM_BITTENSOR.md
→ next /arbos reads template → agent has accumulated knowledge
```

### Lock discipline
- `_goals_lock` : toujours acquérir avant de lire/écrire les goals maps, `_step_count`, ou appeler `_save_goals()`
- `_claude_semaphore` : acquérir dans run_agent/run_agent_streaming, release dans finally
- `_token_lock` : protège `_token_usage` (thread-keyed dict) et `_token_owner`
- `_chatlog_lock` : protège les écritures chatlog ; les lectures utilisent try/except pour la rotation

### Wallet PnL 48h — Taostats vs TaoMarketCap (`tools/wallet_pnl_48h.py`)
- Un **PnL glissant sur 48 h** par wallet repose sur l’**API portfolio Taostats** (ex. `get_dtao_stake_portfolio`, fenêtre en jours ≈ `ceil(heures/24)`) ou une **reconstitution on-chain**.
- **TaoMarketCap** (`internal/v1/leaderboard/coldkeys/`, requête par `coldkey=`) renvoie surtout du **cumul** (`total_pnl`, `realized_pnl`, etc.) ; **pas de métrique `pnl_48h` / fenêtre glissante** dans ce leaderboard public testé.
- **`--tmc-only`** sert de **référence cumulée** lorsque Taostats est indisponible ou sans clé ; à ne pas présenter comme un PnL sur 48 h.
