# 🧠 IA — des intelligences artificielles faites maison

Ce dépôt contient des projets construits à partir de zéro, pour comprendre de l'intérieur comment ces technologies fonctionnent :

| Projet | Ce que c'est | Dépendances |
|--------|--------------|-------------|
| 🧠 **[Neurone](#-neurone--un-chatbot-fait-maison)** | Un chatbot qui comprend tes questions grâce à un réseau de neurones codé à la main | aucune |
| 🤖 **[MiniGPT](minigpt/README.md)** | Un petit modèle de langage de type GPT (Transformer) qui écrit du texte en français | PyTorch |
| 🔎 **[Fouineur](fouineur/README.md)** | Un moteur de recherche : robot d'exploration, index inversé, BM25, PageRank et interface web | aucune |
| ✨ **[Lumière](lumiere/README.md)** | Un moteur de rendu photoréaliste (path tracing) : verre, métal, ombres douces, flou de profondeur | NumPy |
| 🕸️ **[Toile](toile/README.md)** | Un navigateur web : HTTP, analyse du HTML, moteur CSS, mise en page et fenêtre | Tkinter |
| 🌌 **[Galaxie](galaxie/README.md)** | Un simulateur de galaxies : gravité de Barnes-Hut, collisions, bras spiraux | NumPy, Pillow |
| § **[Mémoire](memoire/README.md)** | Une plateforme de mise en forme de mémoire : styles, numérotation, sommaire, export Word et PDF | reportlab (PDF) |
| ✍️ **[Rédigo](redigo/README.md)** | La même plateforme en ligne (SaaS) : comptes, bibliographie APA / ISO 690, commentaires du directeur, versions, abonnements | reportlab (PDF) |

```bash
python3 -m ia                                        # discuter avec Neurone
pip install -r requirements.txt
python3 -m minigpt ecrire "Monsieur le Président, "   # faire écrire MiniGPT
python3 -m fouineur demo                             # moteur de recherche sur http://127.0.0.1:8000/
python3 -m lumiere rendre cornell                    # image photoréaliste dans lumiere/rendus/
python3 -m toile about:demo                          # ouvrir le navigateur
python3 -m galaxie collision                         # animation de deux galaxies qui se croisent
python3 -m memoire                                   # plateforme de mise en forme de mémoire
python3 -m redigo                                    # Rédigo, la version en ligne, sur http://127.0.0.1:8060/
```

---

# 🧠 Neurone — un chatbot fait maison

**Neurone** est un chatbot en français propulsé par un **réseau de neurones écrit entièrement à la main**, en Python pur :
pas de TensorFlow, pas de PyTorch, pas même NumPy. Tout le code de l'IA tient dans quelques fichiers qu'on peut lire et comprendre.

## ✨ Ce qu'elle sait faire

- 💬 Discuter (salutations, « ça va ? », « qui es-tu ? »…)
- 😂 Raconter des blagues
- ⏰ Donner l'heure et la date
- 🧮 Faire des calculs : « calcule 12 * 7 + 3 », « combien font 3 fois 4 »
- 🎓 **Apprendre** : quand elle ne comprend pas, elle te demande quoi répondre, s'en souvient et se réentraîne

## 🚀 Lancer l'IA

Il faut seulement Python 3.8 ou plus récent :

```bash
git clone https://github.com/Crispinoza225/IA.git
cd IA
python3 -m ia
```

Exemple de conversation :

```
Toi    > salut
Neurone> Salut ! Content de te parler.
Toi    > combien font 3 fois 4
Neurone> 3 * 4 = 12
Toi    > quel est ton plat préféré
Neurone> Je ne sais pas encore répondre à ça. Que devrais-je dire ? (Entrée pour passer)
Toi    > Les pâtes carbonara !
Neurone> Merci, j'ai appris quelque chose de nouveau ! 🎓
Toi    > c'est quoi ton plat préféré ?
Neurone> Les pâtes carbonara !
```

## 🔬 Comment ça marche

1. **Texte → nombres** (`ia/texte.py`) : la phrase est mise en minuscules, sans accents, découpée en mots,
   et chaque mot est réduit à sa racine (« calcule » → « calcul »). On obtient un *sac de mots* :
   un vecteur avec un 1 pour chaque mot connu présent dans la phrase.
2. **Réseau de neurones** (`ia/reseau.py`) : une couche cachée (activation `tanh`) puis une couche de sortie
   (`softmax`) qui donne la probabilité de chaque *intention* (salutation, blague, calcul…).
3. **Apprentissage** : descente de gradient et **rétropropagation**, avec l'entropie croisée comme fonction de perte.
   Tu vois la perte diminuer au démarrage.
4. **Réponse** (`ia/chatbot.py`) : si l'intention la plus probable est assez sûre, Neurone choisit une réponse ;
   sinon il avoue ne pas savoir et te propose de lui apprendre.

Les connaissances de base sont dans `ia/intentions.json`, et ce que tu lui apprends est enregistré dans `ia/appris.json`.

## 🛠️ Ajouter des connaissances

Ajoute une intention dans `ia/intentions.json` :

```json
{
  "nom": "meteo",
  "exemples": ["quel temps fait il", "il fait beau", "la météo stp"],
  "reponses": ["Je n'ai pas de fenêtre, mais j'espère qu'il fait beau ! ☀️"]
}
```

Relance `python3 -m ia` : le réseau se réentraîne automatiquement.

## ✅ Tests

```bash
python3 -m unittest discover -s tests
```

## 💡 Idées pour aller plus loin

- Ajouter une interface web (Flask) ou graphique (Tkinter)
- Ajouter une deuxième couche cachée
- Remplacer le sac de mots par des *embeddings* de mots
- Brancher un vrai grand modèle de langage (API Claude) quand Neurone ne sait pas répondre
