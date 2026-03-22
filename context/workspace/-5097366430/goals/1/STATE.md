**Status as of 2026-03-22 (opérateur /arbos)**

**2026-03-22 — Opérateur : périmètre « trading + staking uniquement » (hors mining / validation)**  
- **Limite source** : le leaderboard TaoMarketCap ne filtre **pas** par type d’activité ; `total_pnl` reste un **agrégat portefeuille**. On ne peut donc **pas** déduire de cette page seule le PnL **uniquement** issu du trading + du staking dTAO, même si l’on exclut conceptuellement mining et validation. Une ventilation (staking vs trades vs autres) exigerait une autre source ou une analyse transactionnelle.

**2026-03-22 — Moyens possibles pour approcher une ventilation « staking dTAO / trading » (pas de bouton unique public aujourd’hui)**  
1. **Taostats — endpoint portfolio (clé API avec droits)** : `GET /api/dtao/stake_balance/portfolio/v1` (wrapper dépôt : `data_providers/taostats.py` → `get_dtao_stake_portfolio`). Sur plan gratuit testé ici : **403** ; un **plan / clé** avec accès pourrait fournir un **PnL de portefeuille dTAO** plus riche — **vérifier la doc Taostats** pour savoir si la réponse **distingue** réellement staking vs swaps ou reste un agrégat (à ne pas supposer sans schéma de réponse).  
2. **Reconstruction analytique (APIs Taostats déjà mappées, sans promesse de cohérence comptable)** :  
   - **Trading (swaps dTAO)** : `get_dtao_trades` (`/api/dtao/trade/v1`) — historique d’achats/ventes α vs TAO par `coldkey` ; un **PnL de trading** exige une **méthode de coût** (FIFO/moyenne) + agrégation multi-pages.  
   - **Staking / positions** : `get_dtao_stake_balance_history` + `get_dtao_stake_balance` — évolution des **balances α** et **valeur en τ** ; **émissions** liées au stake : `get_dtao_hotkey_emissions` (par hotkey/subnet, fenêtres bloc/timestamp). Combiner pour séparer **variation de valeur** vs **flux de trades** reste un **modèle** (pas une colonne officielle « staking PnL seul »).  

**2026-03-22 — Opérateur : « reconstruire les trades etc. » (recette)**  
- **But** : reconstituer **à la main** (script + API) des séries **compatibles** avec une ventilation *trading vs staking*, pas recalculer une colonne TaoMarketCap.  
- **1) Trades dTAO** : `get_dtao_trades` → `GET /api/dtao/trade/v1` — pour la **coldkey**, **paginer** (`page`, `limit` max autorisé) jusqu’à ne plus avoir de lignes ; trier par **bloc / timestamp**. Chaque événement = swap **α ⇄ τ** (champs selon schéma Taostats).  
- **2) PnL « trading » (réalisé)** : sur la série de swaps, appliquer une **méthode de lots** (**FIFO** ou **coût moyen**) par **(netuid, sens)** ; **documenter** la règle. Les **positions encore ouvertes** : PnL **non réalisé** = **MTM** (valorisation α en τ à partir des **prix pool** — voir `get_dtao_pool_history` / instantané `get_dtao_pools` selon la fenêtre).  
- **3) Staking (hors swap)** : **`get_dtao_stake_balance_history`** — suivi des **positions** ; **`get_dtao_hotkey_emissions`** — **récompenses d’émission** sur le stake (par **hotkey** / subnet). Ne pas additionner aveuglément **émissions** et **PnL de swap** : ce sont des **natures** différentes (flux de récompense vs réalisation de trade).  
- **4) Synthèse possible** : *trading* ≈ PnL **réalisé** sur swaps + **MTM** sur inventaire lié aux échanges ; *staking* ≈ cumul **émissions** + **variation de valeur** des α **détenues** sans vente (ou avec règles explicites de reclassement).  
- **5) Trous** : transferts **τ** purs, extrinsics **hors dTAO**, liens **multi-coldkey** — pas forcément dans `trade/v1` ; couverture complète ⇒ **indexeur** (voir point « Indexation on-chain » ci-dessous) ou **portfolio Taostats** si l’API est accessible.  

3. **Indexation on-chain** : indexer les extrinsics Subtensor pertinents (stake/unstake, swaps dTAO, transferts) pour une coldkey, puis classifier et valoriser — **travail d’infra** (nœud + base), définition métier du PnL inchangée.  
4. **Product** : demander à **Taostats / TaoMarketCap** une métrique ou un export **filtré** si leur feuille de route le prévoit — aucune garantie côté utilisateur final.

**2026-03-22 — Coldkey au plus fort PnL (leaderboard dTAO / Traders, TaoMarketCap)**  
- **Source** : [TaoMarketCap — Leaderboard](https://taomarketcap.com/leaderboard?ordering=-total_pnl) (données `__NEXT_DATA__`, tri **`ordering=-total_pnl`**).  
- **Définition** : `total_pnl` = **PnL de portefeuille** (réalisé + non réalisé), pas un décompte séparé « récompenses de staking uniquement » ; l’API Taostats `dtao-portfolio` (PnL détaillé) reste **403** sur le plan courant.  
- **#1** : **`5D1tX2W1wuDhP8Kn5m79s3VSUA82VUjg6ivGp6wGt497zKRe`** — **total_pnl** ≈ **5761,55 τ** (rao `5761549196609`). *Réf.* stake affiché côté ligne : **staked_balance** ≈ **50,13 τ** (rao `50129082602`).

**2026-03-21 — Liste complète (ordre croissant sur A) — même snapshot**  
- **Demande** : tous les subnets avec **A** = coldkeys distinctes (mineurs rémunérés) et **B** = validateurs `validator_trust` &gt; 0,98, triés en **ordre croissant sur A** (du plus petit A au plus grand).  
- **Fichier** : `context/workspace/-5097366430/subnet_miner_ck_vtrust_20260321_asc.csv` (**129** lignes, `rank_asc` 1 = **A** minimal, 129 = **A** maximal). **Extrêmes** : **A** = 0 sur **54** netuids (rangs 1–54) ; **A** max = **199** (**netuid 82**).  
- **2026-03-21 — Opérateur : CSV complet en un bloc** (copie ci-dessous, identique au fichier).

```
rank_asc,netuid,distinct_miner_coldkeys_emission_gt0,validators_vtrust_gt_0_98
1,126,0,7
2,125,0,11
3,124,0,12
4,122,0,9
5,121,0,13
6,119,0,10
7,117,0,8
8,115,0,19
9,113,0,8
10,112,0,13
11,110,0,15
12,109,0,13
13,108,0,11
14,107,0,9
15,106,0,9
16,102,0,8
17,101,0,12
18,98,0,11
19,97,0,5
20,96,0,5
21,95,0,12
22,92,0,11
23,91,0,8
24,90,0,11
25,87,0,8
26,84,0,10
27,76,0,9
28,69,0,15
29,67,0,6
30,63,0,12
31,62,0,13
32,60,0,9
33,58,0,15
34,55,0,7
35,53,0,13
36,52,0,12
37,47,0,11
38,46,0,9
39,38,0,10
40,37,0,13
41,31,0,13
42,30,0,9
43,29,0,8
44,27,0,13
45,26,0,13
46,25,0,10
47,24,0,8
48,23,0,11
49,21,0,12
50,19,0,14
51,10,0,14
52,7,0,13
53,3,0,3
54,0,0,0
55,116,1,13
56,105,1,4
57,104,1,1
58,99,1,3
59,94,1,10
60,86,1,10
61,81,1,4
62,80,1,4
63,70,1,2
64,66,1,10
65,49,1,10
66,48,1,9
67,43,1,6
68,40,1,12
69,39,1,9
70,28,1,14
71,20,1,9
72,17,1,7
73,15,1,11
74,12,1,7
75,11,1,5
76,9,1,10
77,5,1,14
78,89,2,11
79,73,2,11
80,68,2,1
81,44,2,7
82,36,2,9
83,35,2,10
84,1,2,9
85,127,3,11
86,56,4,13
87,45,4,12
88,18,4,7
89,4,4,1
90,120,5,10
91,32,5,1
92,93,6,7
93,14,6,12
94,83,8,10
95,77,8,11
96,85,9,1
97,16,9,15
98,33,10,11
99,22,10,1
100,54,12,4
101,2,12,1
102,41,14,10
103,114,15,8
104,111,17,1
105,74,17,10
106,42,18,6
107,103,19,5
108,59,23,7
109,51,29,9
110,34,29,7
111,128,30,12
112,79,30,1
113,64,30,8
114,71,33,1
115,61,35,12
116,72,37,2
117,100,40,5
118,8,41,6
119,65,43,5
120,50,45,7
121,57,52,9
122,75,70,9
123,118,75,14
124,13,82,3
125,123,90,2
126,78,116,3
127,88,146,12
128,6,152,11
129,82,199,1
```

**2026-03-21 — Opérateur : même classement en tableaux Markdown (5 blocs, 129 lignes)**  
- **Colonnes** : **Rang** = ordre croissant sur **A** ; **netuid** ; **Nom** = `agcli subnet list` (Finney, lu au moment de la mise en forme — peut différer légèrement du libellé à l’instant T) ; **A** = coldkeys distinctes (mineurs rémunérés) ; **B** = validateurs avec vTrust **&gt; 0,98**.  
- **Telegram** : envoyer **bloc par bloc** (limite ~4096 caractères / message) : **Tableaux 1 → 5** ci-dessous.

### Tableau 1 (rangs 1–26)

| Rang | netuid | Nom | A (coldkeys) | B (vTrust &gt; 0,98) |
|---:|---:|:---|---:|---:|
| 1 | 126 | Poker44 | 0 | 7 |
| 2 | 125 | 8 Ball | 0 | 11 |
| 3 | 124 | Swarm | 0 | 12 |
| 4 | 122 | Bitrecs | 0 | 9 |
| 5 | 121 | sundae_bar | 0 | 13 |
| 6 | 119 | Satori | 0 | 10 |
| 7 | 117 | BrainPlay | 0 | 8 |
| 8 | 115 | HashiChain | 0 | 19 |
| 9 | 113 | TensorUSD | 0 | 8 |
| 10 | 112 | minotaur | 0 | 13 |
| 11 | 110 | Rich Kids of TAO | 0 | 15 |
| 12 | 109 | Reserved | 0 | 13 |
| 13 | 108 | TalkHead | 0 | 11 |
| 14 | 107 | Minos | 0 | 9 |
| 15 | 106 | VoidAI | 0 | 9 |
| 16 | 102 | Vocence | 0 | 8 |
| 17 | 101 | eni | 0 | 12 |
| 18 | 98 | ForeverMoney | 0 | 11 |
| 19 | 97 | Constantinople | 0 | 5 |
| 20 | 96 | X | 0 | 5 |
| 21 | 95 | nion | 0 | 12 |
| 22 | 92 | LUCID | 0 | 11 |
| 23 | 91 | Bitstarter #1 | 0 | 8 |
| 24 | 90 | ogham | 0 | 11 |
| 25 | 87 | Luminar Network | 0 | 8 |
| 26 | 84 | ChipForge (Tatsu) | 0 | 10 |

### Tableau 2 (rangs 27–52)

| Rang | netuid | Nom | A (coldkeys) | B (vTrust &gt; 0,98) |
|---:|---:|:---|---:|---:|
| 27 | 76 | nun | 0 | 9 |
| 28 | 69 | ain | 0 | 15 |
| 29 | 67 | ta | 0 | 6 |
| 30 | 63 | Quantum Innovate | 0 | 12 |
| 31 | 62 | Ridges | 0 | 13 |
| 32 | 60 | Bitsec.ai | 0 | 9 |
| 33 | 58 | Handshake | 0 | 15 |
| 34 | 55 | NIOME | 0 | 7 |
| 35 | 53 | EfficientFrontier | 0 | 13 |
| 36 | 52 | Dojo | 0 | 12 |
| 37 | 47 | EvolAI | 0 | 11 |
| 38 | 46 | RESI | 0 | 9 |
| 39 | 38 | colosseum | 0 | 10 |
| 40 | 37 | Aurelius | 0 | 13 |
| 41 | 31 | Halftime | 0 | 13 |
| 42 | 30 | Pending | 0 | 9 |
| 43 | 29 | Coldint | 0 | 8 |
| 44 | 27 | Nodexo | 0 | 13 |
| 45 | 26 | Kinitro | 0 | 13 |
| 46 | 25 | Mainframe | 0 | 10 |
| 47 | 24 | Quasar | 0 | 8 |
| 48 | 23 | Trishool | 0 | 11 |
| 49 | 21 | OMEGA.inc: The Awakening | 0 | 12 |
| 50 | 19 | blockmachine | 0 | 14 |
| 51 | 10 | Swap | 0 | 14 |
| 52 | 7 | subvortex | 0 | 13 |

### Tableau 3 (rangs 53–78)

| Rang | netuid | Nom | A (coldkeys) | B (vTrust &gt; 0,98) |
|---:|---:|:---|---:|---:|
| 53 | 3 | τemplar | 0 | 3 |
| 54 | 0 | root | 0 | 0 |
| 55 | 116 | TaoLend | 1 | 13 |
| 56 | 105 | Beam | 1 | 4 |
| 57 | 104 | for sale (burn to uid1) | 1 | 1 |
| 58 | 99 | Leoma | 1 | 3 |
| 59 | 94 | Bitsota | 1 | 10 |
| 60 | 86 | ⚒ | 1 | 10 |
| 61 | 81 | grail | 1 | 4 |
| 62 | 80 | dogelayer | 1 | 4 |
| 63 | 70 | ghayn | 1 | 2 |
| 64 | 66 | AlphaCore | 1 | 10 |
| 65 | 49 | Nepher Robotics | 1 | 10 |
| 66 | 48 | Quantum Compute | 1 | 9 |
| 67 | 43 | Graphite | 1 | 6 |
| 68 | 40 | Chunking | 1 | 12 |
| 69 | 39 | basilica | 1 | 9 |
| 70 | 28 | oracle | 1 | 14 |
| 71 | 20 | GroundLayer | 1 | 9 |
| 72 | 17 | 404—GEN | 1 | 7 |
| 73 | 15 | deval | 1 | 11 |
| 74 | 12 | Compute Horde | 1 | 7 |
| 75 | 11 | TrajectoryRL | 1 | 5 |
| 76 | 9 | iota | 1 | 10 |
| 77 | 5 | Hone | 1 | 14 |
| 78 | 89 | InfiniteHash | 2 | 11 |

### Tableau 4 (rangs 79–104)

| Rang | netuid | Nom | A (coldkeys) | B (vTrust &gt; 0,98) |
|---:|---:|:---|---:|---:|
| 79 | 73 | MetaHash | 2 | 11 |
| 80 | 68 | NOVA | 2 | 1 |
| 81 | 44 | Score | 2 | 7 |
| 82 | 36 | Web Agents - Autoppia | 2 | 9 |
| 83 | 35 | Cartha | 2 | 10 |
| 84 | 1 | Apex | 2 | 9 |
| 85 | 127 | Astrid | 3 | 11 |
| 86 | 56 | Gradients | 4 | 13 |
| 87 | 45 | Talisman AI | 4 | 12 |
| 88 | 18 | Zeus | 4 | 7 |
| 89 | 4 | Targon | 4 | 1 |
| 90 | 120 | Affine | 5 | 10 |
| 91 | 32 | ItsAI | 5 | 1 |
| 92 | 93 | Bitcast | 6 | 7 |
| 93 | 14 | TAOHash | 6 | 12 |
| 94 | 83 | CliqueAI | 8 | 10 |
| 95 | 77 | Liquidity | 8 | 11 |
| 96 | 85 | Vidaio | 9 | 1 |
| 97 | 16 | BitAds | 9 | 15 |
| 98 | 33 | ReadyAI | 10 | 11 |
| 99 | 22 | Desearch | 10 | 1 |
| 100 | 54 | Yanez MIID | 12 | 4 |
| 101 | 2 | DSperse | 12 | 1 |
| 102 | 41 | Almanac | 14 | 10 |
| 103 | 114 | SOMA | 15 | 8 |
| 104 | 111 | oneoneone | 17 | 1 |

### Tableau 5 (rangs 105–129)

| Rang | netuid | Nom | A (coldkeys) | B (vTrust &gt; 0,98) |
|---:|---:|:---|---:|---:|
| 105 | 74 | Gittensor | 17 | 10 |
| 106 | 42 | Gopher | 18 | 6 |
| 107 | 103 | Djinn | 19 | 5 |
| 108 | 59 | Babelbit | 23 | 7 |
| 109 | 51 | lium.io | 29 | 9 |
| 110 | 34 | BitMind | 29 | 7 |
| 111 | 128 | ByteLeap | 30 | 12 |
| 112 | 79 | MVTRX | 30 | 1 |
| 113 | 64 | Chutes | 30 | 8 |
| 114 | 71 | Leadpoet | 33 | 1 |
| 115 | 61 | RedTeam | 35 | 12 |
| 116 | 72 | StreetVision by NATIX | 37 | 2 |
| 117 | 100 | Plaτform | 40 | 5 |
| 118 | 8 | Vanta | 41 | 6 |
| 119 | 65 | TAO Private Network | 43 | 5 |
| 120 | 50 | Synth | 45 | 7 |
| 121 | 57 | Sparket.AI | 52 | 9 |
| 122 | 75 | Hippius | 70 | 9 |
| 123 | 118 | HODL ETF | 75 | 14 |
| 124 | 13 | Data Universe | 82 | 3 |
| 125 | 123 | MANTIS | 90 | 2 |
| 126 | 78 | Loosh | 116 | 3 |
| 127 | 88 | Investing | 146 | 12 |
| 128 | 6 | Numinous | 152 | 11 |
| 129 | 82 | Hermes | 199 | 1 |

**2026-03-21 — Top 5 subnets : coldkeys distinctes (mineurs rémunérés) + validateurs vTrust &gt; 0,98**  
- **Méthode** : même snapshot que `subnet_miner_ck_vtrust_20260321.json` — `agcli view metagraph --netuid N --output json` (Finney), netuid **0→128**. Mineur rémunéré = `validator_permit` faux **et** `emission &gt; 0` ; **A** = coldkeys **distinctes** ; **B** = validateurs avec `validator_permit` vrai **et** `validator_trust` &gt; **0,98**.  
- **Top 5 (décroissant sur A)** :

| Rang | netuid | Nom | A (coldkeys distinctes) | B (vTrust &gt; 0,98) |
|------|--------|-----|-------------------------|----------------------|
| 1 | 82 | Hermes | 199 | 1 |
| 2 | 6 | Numinous | 152 | 11 |
| 3 | 88 | Investing | 146 | 12 |
| 4 | 78 | Loosh | 116 | 3 |
| 5 | 123 | MANTIS | 90 | 2 |

---

**Status as of 2026-03-20 (historique)**

Original goal: "trouve le nom du subnet 3"
→ COMPLETED in Step 7 with full subnet 3 (τemplar) details delivered to Telegram.

**Dernière demande salon (coldkeys mineurs rémunérés)** — Finney, `agcli view metagraph` pour chaque `netuid` 0→128, bloc ref. **≈ 7 789 410**.  
Mineur = `validator_permit == false` ; rémunéré = `emission > 0`. Métrique = **nombre de coldkeys distinctes** parmi ces neurones.

**Résultat :** le subnet avec le **plus** de coldkeys distinctes de mineurs rémunérés est **netuid 82 — Hermes** (**196** coldkeys, **247** slots mineurs avec émission sur 256 neurones).  
Top suivants : **6 Numinous** (154), **88 Investing** (144), **78 Loosh** (106), **13 Data Universe** (90), **123 MANTIS** (90).

Recent activity:
- Operator sent test messages: "test", "hello (acknowledged in Step 11)
- Process restarted twice (Steps 8, 10) — stable now
- No pending tasks in INBOX

Current state: Goal complete, system stable, awaiting new operator instructions.

---

**2026-03-21 — Demande opérateur : fiche subnet 100 (rôle mineur)**  
Subnet **100** = **Plaτform** (α100), mécanisme 0, 256/256, tempo 360. Mineurs : exécuter le client subnet Platform et les **jobs de challenges** (architecture sous-subnets / SDK, doc CortexLM Platform). Réponse détaillée livrée à l’opérateur / Telegram.

**2026-03-21 — SN100 : coût d’inscription + coldkeys rémunérées (Finney, bloc ~7792134)**  
- **Burn (prix pour s’enregistrer / miner sur le subnet)** : **0,0005 τ** (`agcli subnet show --netuid 100`).  
- **Prix TAO/α (spot pool)** : **~0,01685 τ/α** (même commande — variable).  
- **Coldkeys distinctes avec `emission > 0`** sur SN100 : **54** au total ; dont **42** si on ne compte que les **mineurs** (`validator_permit` faux) et **12** côté validateurs (VP) avec émission.

**2026-03-21 — « Subnets qui burn l’émission owner » — correction (Taostats *Incentive burn*)**  
- L’ancienne réponse utilisait **`RecycleOrBurn`** on-chain (autre mécanisme). La demande visait la métrique **Taostats → Incentive burn** (`incentive_burn` dans le JSON de la page **Subnets**).  
- **Snapshot** (extraction HTML **taostats.io/subnets**, 2026-03-21) sur **128** netuids (1–128 ; **0** absent du jeu de données embarqué) :  
  - **Brûlage 100 %** (`incentive_burn` = 1) : **60** subnets.  
  - **Brûlage partiel** (0 &lt; x &lt; 1) : **47** subnets (ex. **SN100** ≈ 0,55).  
  - **Aucun brûlage** (= 0) : **21** subnets.  
- Listes netuid : `context/workspace/-5097366430/taostats_incentive_burn_20260321.txt`.

**2026-03-21 — Plus de « nouveaux mineurs » (inscriptions) sur 30 jours**  
- Source : Taostats `GET /api/subnet/neuron/registration/v1`, fenêtre **UTC** ≈ **30 jours** (`timestamp_start` / `timestamp_end`), compteur = `pagination.total_items` par `netuid`.  
- **Gagnant : netuid 1 — Apex (α1)** : **1893** événements d’inscription sur la période (revérifié avec borne `timestamp_end`).  
- **Périmètre** : l’API ne distingue pas mineur vs validateur — ce sont **toutes** les inscriptions de neurones sur le subnet.  
- **Contexte** : scan 0→128 avec rate-limit (429 sur une partie des netuids) ; parmi les totaux obtenus, le **2e** était **netuid 59** (**683**), soit un écart massif vs SN1 — SN1 reste le leader quasi certain.

**2026-03-21 — SN64 : validateurs avec vTrust &gt; 0,98**  
- Source : Taostats `GET /api/metagraph/latest/v1` (`netuid=64`, `limit=256`).  
- Définition : neurones avec **`validator_permit` = vrai** et **`validator_trust` &gt; 0,98**.  
- **Résultat : 8** validateurs (UID : 1, 6, 69, 84, 127, 182, 205, 234). **17** validateurs au total sur le métagraphe.

**2026-03-21 — Top 10 coldkeys par PnL (subnets / dTAO, onglet Traders)**  
- **Source** : [TaoMarketCap — Leaderboard](https://taomarketcap.com/leaderboard) (données embarquées page, tri **`ordering=-total_pnl`**). L’API Taostats `dtao-portfolio` retourne **403** sur notre plan (PnL agrégé réservé).  
- **Unité** : `total_pnl` en **rao** → τ (÷10⁹). Instantané cohérent avec la page (#1 ≈ **+5574 τ**).

| # | Coldkey | Total PnL (τ) |
|---|---------|---------------|
| 1 | `5D1tX2W1wuDhP8Kn5m79s3VSUA82VUjg6ivGp6wGt497zKRe` | ≈ 5574,36 |
| 2 | `5D5B37KukhXN7PjAwESaaNY8P6aNRbHizHURWER2KACuNTJB` | ≈ 5314,41 |
| 3 | `5G6wJYFxGo7eyvTwkVPViPMr9GEPhSiGfSYFaCAr4UjueBQh` | ≈ 3365,19 |
| 4 | `5HQqnVk75cxBs27g1Q9T66AQ78yZ4GRJqm69kUpsfdRAiN6A` | ≈ 2963,66 |
| 5 | `5FxxxgRKuvs6UFMXVcCnHjE15UsJSin78Lxdb7t5QjVgZsuo` | ≈ 2747,78 |
| 6 | `5GKYVYof1CbEuNcnBSa2wXx3rs5StYYVBPdg8C5CQ8MifCBc` | ≈ 2633,65 |
| 7 | `5GENm6gYbgzcMAAufZbYvnGq8co8hjRRbotmSHD3kLkLrhyN` | ≈ 2631,10 |
| 8 | `5GhSdA8G4q7mNW9s9RqS4tLjtowFYTBMptEQ8b6WPBnRA8R5` | ≈ 2018,59 |
| 9 | `5DAhuVPzEbEM1P4XruGR9aNHWmHgw5ZyGR7jefVC9rp6Egow` | ≈ 1680,75 |
| 10 | `5Ey8GCkGjkoHFqGk4qo1PTv5W3x7P5pquwB3b4rNgHKfAFAq` | ≈ 1494,51 |

**2026-03-21 — dTAO / « stratégie la plus profitable » + subnets « potentiel / gains rapides » (demande opérateur)**  
- **Cadre** : réponse **pédagogique**, pas un conseil financier ; **aucun** rendement ou « meilleure stratégie » garanti.  
- **Émission (Finney)** : `agcli subnet list` → top `emission_value` (hors root) à l’instant du scan : **3 τemplar**, **4 Targon**, **75 Hippius**, **9 iota**, **81 grail**, **39 basilica**, **68 NOVA**, **19 blockmachine**, **93 Bitcast**, **24 Quasar**, **85 Vidaio**, **63 Quantum Innovate**.  
- **Liquidité AMM (échantillon)** : `agcli subnet liquidity --netuid <n>` — profondeur **TAO** indicative : **64 Chutes** ≈ **220k τ** en pool (`tao_in`), **3 τemplar** ≈ **125k τ**, **4 Targon** ≈ **116k τ** ; **prix spot τ/α** très différent selon les subnets (ex. **1 Apex** prix α bas vs **3 τemplar** plus élevé au même instant).  
- **Lecture** : forte **émission** ≠ prix α qui monte « vite » ; **gains rapides** = surtout **volatilité**, risque de **slippage** / pools moins profonds, et cycles **tempo** — à croiser avec ta tolérance au risque et la taille des ordres.

**2026-03-21 — Tous les subnets : coldkeys distinctes (mineurs rémunérés) + validateurs vTrust &gt; 0,98**  
- **Source** : `agcli view metagraph --netuid N --output json` (Finney), boucle **netuid 0→128**, script `context/workspace/-5097366430/tools/subnet_miner_ck_and_vtrust.py`.  
- **Mineurs rémunérés** : `validator_permit == false` **et** `emission &gt; 0` ; métrique **A** = nombre de **coldkeys distinctes** parmi ces neurones.  
- **Validateurs** : `validator_permit == true` **et** `validator_trust &gt; 0,98` (même critère que SN64 Taostats) ; métrique **B** = décompte.  
- **Snapshot** : 2026-03-21 (~6 min de scan séquentiel). **#1 sur A** : **netuid 82** (**199** coldkeys distinctes, **246** slots mineurs avec émission ; **B** = **1**). **54** netuids avec **A = 0** (souvent subnets 100 % validateurs / pas de slot mineur avec émission).  
- **Fichiers** : `subnet_miner_ck_vtrust_20260321.json` (JSON complet) ; `subnet_miner_ck_vtrust_20260321.csv` (**classement décroissant** sur A, rang 1 = max) ; `subnet_miner_ck_vtrust_20260321_asc.csv` (**ordre croissant** sur A, rang 1 = min).

**2026-03-21 — Stratégie d’accumulation TAO + exposition multi-subnets (court / moyen terme)**  
- **Demande** : cadre pour viser **plus de TAO** en s’exposant à **plusieurs subnets** (pas une reco personnalisée).  
- **Clarification** : « plus de TAO » peut vouloir dire (a) **solde TAO root** après ventes, ou (b) **valeur de portefeuille en τ** incluant les **α** — ce n’est pas la même chose : les **α** cotent en **τ** sur les pools **dTAO** et fluctuent.  
- **Pistes de cadre** : (1) **staking root** sur le subnet 0 si l’objectif est surtout l’**exposition TAO** « réseau » sans pari α ; (2) **dTAO** : exposition **directionnelle** subnet par subnet (risque de **slippage**, liquidité, cycles **tempo**) ; (3) **diversification** entre subnets = réduction du risque **idiosyncratique** d’un seul netuid, **sans** garantir un surplus de TAO vs une autre allocation.  
- **Limites** : pas de stratégie universelle « rentable » ni gains court terme **assurés** ; croiser **liquidité** (`agcli subnet liquidity`), **émissions** (`agcli subnet list`), et ta **taille d’ordre** / horizon.

**2026-03-21 — Subnet qui « fait le plus d’argent en fiat » via le produit (comparaison)**  
- **Limite** : pas de **CA fiat** unifié et audité on-chain pour tous les subnets ; les comparateurs utilisent des **définitions** (flux **τ**, conversion **USD**, fenêtre **24h/7j/30j**).  
- **Source** : [Tao Revenue](https://www.taorevenue.com/) — colonne **Inflow (30D)** avec **τ** et **USD** (méthodo : FAQ du site ; pas un compte de résultat certifié).  
- **Snapshot page** (2026-03-21) : **plus forte Inflow 30j** ≈ **netuid 20 — GroundLayer** (~**4 055 τ** / ~**$1,11 M** USD équivalent) ; **2e** ≈ **netuid 3 — τemplar** (~**3 784 τ** / ~**$1,03 M**) ; **3e** ≈ **netuid 8 — Vanta (Taoshi)** (~**3 665 τ** / ~**$1,00 M**). Le classement **varie** avec la fenêtre et la métrique (ex. **surplus**, **émissions**, blogs tiers).

**2026-03-21 — Opérateur : 5 coldkeys les plus exposés au dTAO (valeur des α en τ)**  
- **Définition** : somme des **`balance_as_tao`** Taostats (`taostats dtao-stake`) sur toutes les positions avec **`netuid` &gt; 0** (staking **α** sur subnets, hors subnet root 0).  
- **Méthode** : [TaoMarketCap — Leaderboard](https://taomarketcap.com/leaderboard?sort=staked) (tri **Staked**, pagination SSR **page=1…22**) → **25** plus gros **Staked** (colonne site) → pour chaque coldkey, agrégation Taostats comme ci-dessus. Un classement **absolu** sur **tous** les coldkeys exigerait un balayage complet de l’API Taostats (429 en rafale) ; ici les **5** ci-dessous sont les plus fortes **expositions dTAO mesurées** parmi ce **top 25 Staked** TaoMarketCap (instant **2026-03-21**).  

| # | Coldkey | Σ α en τ (dTAO, Taostats) | Staked (TaoMarketCap, ref.) |
|---|---------|---------------------------|------------------------------|
| 1 | `5E4wXrX56ktEbzhLKBd3vmk57xbpQtQVaJvgboFf5Q25ezdV` | ≈ **4509,41** | ≈ 6651,60 |
| 2 | `5D5B37KukhXN7PjAwESaaNY8P6aNRbHizHURWER2KACuNTJB` | ≈ **2108,47** | ≈ 2108,53 |
| 3 | `5E5BPxkfkqxuZgHzPPJjNcJf8nhDmtwsXag1Tchj5i57HGoV` | ≈ **1482,61** | ≈ 1519,78 |
| 4 | `5Fo2FyEgKcHnCDouNKe862PSV3QrZ2VBDyK4GShCGpc4e7g5` | ≈ **1465,91** | ≈ 1466,03 |
| 5 | `5Cw9kWG4YVapVuXekuGUH1mzGFZg4jjw7Q1UcLaGwc57xm3e` | ≈ **1308,85** | ≈ 1309,00 |