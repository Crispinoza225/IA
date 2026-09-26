# 🤖 MiniGPT — ton propre petit GPT

**MiniGPT** est un modèle de langage construit à partir de zéro, avec la **même architecture que GPT** :
un *Transformer décodeur*. Il lit des textes en français, apprend à deviner le caractère suivant, et
finit par écrire tout seul des phrases dans le style de ce qu'il a lu.

Chaque pièce (attention, blocs Transformer, génération) est écrite et commentée en français dans
`modele.py`. Seul PyTorch est utilisé, pour les calculs sur les tenseurs et la rétropropagation automatique.

## 🚀 Démarrage rapide

```bash
pip install -r requirements.txt        # installe PyTorch

python3 -m minigpt ecrire "Monsieur le Président, "   # utilise le modèle déjà entraîné
python3 -m minigpt discuter                           # mode interactif
```

Un modèle déjà entraîné est fourni dans `minigpt/modeles/minigpt.pt`, donc tu peux l'essayer tout de suite.

Exemples de textes écrits par ce modèle (5 000 étapes, ~22 minutes sur un processeur) :

> **Monsieur le Président,** je crois que cette ambition si nous devons constater sur le cas concrètement et aux
> phoses qui est accord avait présenté publiée par les principes du système de la priorité avec l'OMPI, pour
> l'environnement, ce livre blanc.

> **Je voudrais** souligner aux infrastructures, Monsieur le Président, j'ai demandé maintenant la Commission et
> que nous sommageons une proposition politique concernant le programme…

Il a appris **tout seul**, sans aucune règle de grammaire, à écrire des mots français, à accorder
(souvent !), à placer la ponctuation et à imiter le style des débats parlementaires. Le sens, lui, reste
approximatif : pour ça il faudrait un modèle bien plus grand et bien plus de texte.

## 🏋️ L'entraîner toi-même

```bash
python3 -m minigpt telecharger                    # récupère 3,5 millions de caractères de français
python3 -m minigpt entrainer                      # modèle « petit », 3 000 étapes (~15 min sur processeur)
python3 -m minigpt entrainer --taille mini        # très rapide, pour tester (~1 min)
python3 -m minigpt entrainer --taille moyen --iterations 10000   # bien meilleur, mais il faut une carte graphique
```

Pendant l'entraînement, tu vois la **perte** baisser et, régulièrement, un extrait de ce que MiniGPT sait écrire :
au début c'est du charabia, puis des mots apparaissent, puis des phrases.

### Utiliser tes propres textes

Le corpus fourni par défaut, ce sont les débats du **Parlement européen** : MiniGPT parle donc comme un député 😄.
Pour changer son style, mets n'importe quels fichiers `.txt` dans `minigpt/donnees/` (des romans de Victor Hugo
ou de Jules Verne sur [Gutenberg](https://www.gutenberg.org/browse/languages/fr), des paroles de chansons, tes
propres textes…) puis relance l'entraînement. Il vaut mieux avoir au moins 1 million de caractères.

### Options de génération

| Option | Effet |
|--------|-------|
| `--temperature 0.5` | texte plus sage et répétitif |
| `--temperature 1.2` | texte plus créatif… et plus fou |
| `--top-k 10` | ne choisit que parmi les 10 caractères les plus probables |
| `--longueur 1000` | écrit plus longtemps |
| `--graine 42` | obtient toujours le même texte |

## 🔬 Comment ça marche

```
"Le Parl"  →  [numéros des caractères]  →  plongements + positions
          →  Bloc 1 : attention causale → réseau feed-forward
          →  Bloc 2, 3, 4 …
          →  probabilités du caractère suivant  →  « e » (94 %)
```

1. **Tokeniseur** (`donnees.py`) : chaque caractère reçoit un numéro.
2. **Plongements** : chaque numéro devient un vecteur de 192 nombres, auquel on ajoute un vecteur qui dit *où* se
   trouve le caractère dans la phrase.
3. **Attention** (`AttentionCausale`) : c'est l'invention clé des Transformers. Chaque caractère « regarde » les
   caractères précédents et décide lesquels sont importants pour lui (requêtes, clés, valeurs). Un masque
   l'empêche de regarder le futur.
4. **Feed-forward** : un petit réseau de neurones qui traite l'information récoltée.
5. **Empilement** : 4 blocs l'un sur l'autre, reliés par des *connexions résiduelles*.
6. **Entraînement** (`entrainement.py`) : on compare la prédiction au vrai caractère suivant (entropie croisée),
   puis l'optimiseur AdamW ajuste les 1,8 million de paramètres pour faire un peu mieux.
7. **Génération** : on tire au sort le caractère suivant selon les probabilités, on l'ajoute, et on recommence.

## 🆚 MiniGPT et ChatGPT

| | MiniGPT (petit) | GPT-2 | Les grands modèles actuels |
|---|---|---|---|
| Paramètres | 1,8 million | 1,5 milliard | des centaines de milliards |
| Texte d'entraînement | 3,5 millions de caractères | ~40 Go | plusieurs dizaines de milliers de milliards de tokens |
| Entraînement | ~25 min sur un processeur | des jours sur des GPU | des mois sur des milliers de GPU |

L'architecture est la même. La différence vient de l'échelle et de deux étapes supplémentaires :
ChatGPT est ensuite **affiné** sur des conversations pour apprendre à répondre à des questions
(MiniGPT, lui, continue du texte), puis entraîné avec des retours humains.

## 💡 Pistes pour aller plus loin

- Remplacer le tokeniseur par caractères par un tokeniseur **BPE** (des morceaux de mots, comme GPT)
- Entraîner le modèle « moyen » sur une carte graphique (Google Colab est gratuit)
- **Affiner** le modèle sur des dialogues pour en faire un vrai chatbot
