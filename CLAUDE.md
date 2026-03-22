# Arbos Bittensor — Instructions Claude Code

## Projet
Bot Telegram Bittensor dans `arbos.py` (~5500 lignes). Architecture : monolith avec goal system, workspace isolation, DM isolation, ephemeral goals.

## Auto-amélioration
Ce projet utilise un système de **findings techniques persistants** dans `.claude/FINDINGS.md`.

**IMPORTANT :** Avant toute modification de `arbos.py`, lis `.claude/FINDINGS.md` pour connaître les bugs connus et les patterns à respecter. Après toute modification significative, mets à jour FINDINGS.md (nouveaux bugs trouvés, bugs fixés marqués `[FIXED]`, patterns appris).

## Skills disponibles
- `/audit` — Audit approfondi, compare avec FINDINGS.md, met à jour
- `/fix [bug-name]` — Corrige les bugs de FINDINGS.md par priorité
- `/improve [domain]` — Amélioration ciblée (dm-routing, concurrency, crash-recovery, streaming, cleanup, prompt)
- `/push` — Commit + push (arbos.py + .claude/ seulement)
- `/status` — État rapide : git, syntaxe, bugs ouverts, taille
- `/trace [flow]` — Trace un flux de bout en bout pour vérifier la cohérence

## Conventions
- **3-way dispatch** : `workspace_id == 0` (legacy), `> 0` (DM), `< 0` (workspace group)
- **Lock discipline** : `_goals_lock` pour les maps, `_claude_semaphore` pour les agents
- **Syntaxe check** : toujours `python3 -c "import py_compile; py_compile.compile('arbos.py', doraise=True)"` après modification
- **Commit style** : anglais, conventional commits (feat/fix/refactor/chore)
- **Ne pas commiter** : context/chat/, context/*/goals/*/STATE.md, logs runtime

## Structure des contextes
```
context/
├── goals/           # Legacy CLI goals (workspace_id=0)
├── workspace/<cid>/ # Workspace groups (cid < 0)
│   ├── goals/<idx>/ # GOAL.md, STATE.md, INBOX.md, runs/
│   ├── GOAL_TELEGRAM_BITTENSOR.md
│   └── workspace.json
├── dm/<cid>/        # DM chats (cid > 0)
│   └── goals/<idx>/
├── chat/            # Chat logs (global + per-user + per-group)
└── tools/           # Shared tools & data providers
```
