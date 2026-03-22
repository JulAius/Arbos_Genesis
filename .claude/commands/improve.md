# /improve — Amélioration ciblée

Lis `.claude/FINDINGS.md` pour le contexte technique accumulé. Puis améliore le code selon l'argument fourni.

## $ARGUMENTS

Domaines possibles :
- `dm-routing` — Corriger toutes les fonctions qui ne distinguent pas DM (>0) vs workspace (<0)
- `concurrency` — Fixer les race conditions et les ressources partagées
- `crash-recovery` — Renforcer la résilience aux crashes
- `streaming` — Améliorer le feedback en temps réel vers Telegram
- `cleanup` — Nettoyer le code mort, les imports inutilisés, les TODO
- `prompt` — Améliorer l'assemblage des prompts (chatlog per-user, contexte workspace)

Sans argument : propose les 3 améliorations les plus impactantes d'après FINDINGS.md.

## Règles

1. Un domaine à la fois
2. Vérifie la syntaxe après chaque modification
3. Met à jour FINDINGS.md avec les améliorations appliquées
4. Ne modifie pas ce qui marche déjà
