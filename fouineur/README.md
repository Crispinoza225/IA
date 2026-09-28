# 🔎 Fouineur — un moteur de recherche fait maison

**Fouineur** est un moteur de recherche complet écrit en Python pur, **sans aucune bibliothèque** :
il explore le web, construit un index, classe les pages avec **BM25** et **PageRank** (l'algorithme
d'origine de Google), et affiche les résultats dans une interface web.

![Résultats de recherche](capture.png)

## 🚀 Essayer tout de suite

```bash
python3 -m fouineur demo
```

Puis ouvre http://127.0.0.1:8000/ dans ton navigateur. La démo lance un **mini-web local** de 20 pages
(une petite encyclopédie : espace, animaux, informatique, histoire), l'explore, l'indexe, puis ouvre le moteur.
Essaie `plus grand volcan`, `planète rouge`, `intelligence -fourmi` ou `plannete rouje`.

## 🌍 Explorer le vrai web

```bash
# Explore 200 pages à partir d'une adresse (en restant sur le même site)
python3 -m fouineur explorer https://fr.wikipedia.org/wiki/Volcan --pages 200

# Cherche depuis le terminal…
python3 -m fouineur chercher éruption du Vésuve

# … ou dans le navigateur
python3 -m fouineur serveur
```

| Option | Effet |
|--------|-------|
| `--pages 500` | nombre maximal de pages à visiter |
| `--delai 2` | attente entre deux pages, en secondes (par défaut 1 : sois poli avec les sites !) |
| `--tous-domaines` | suit aussi les liens vers d'autres sites |

L'index est enregistré dans `fouineur/donnees/index.json.gz`.

## ✨ Fonctionnalités

- 🕷️ **Robot d'exploration** poli : il respecte `robots.txt`, attend entre les requêtes et s'identifie
- 📇 **Index inversé** compressé, avec racinisation (« planètes » trouve « planète ») et mots vides ignorés
- 🎯 **Classement BM25**, avec un bonus pour les mots présents dans le titre
- 👑 **PageRank** : les pages vers lesquelles pointent beaucoup de pages importantes remontent
- ✏️ **« Vouliez-vous dire… ? »** grâce à la distance de Levenshtein
- ➖ **Exclusion** d'un mot avec `-mot`
- 🖍️ **Extraits** avec les mots cherchés surlignés
- 📱 **Interface web** qui s'adapte au téléphone et au mode sombre

## 🔬 Comment ça marche

```
  web  ──►  explorateur.py  ──►  pages (titre, texte, liens)
                                    │
                                    ▼
                               index.py  ──►  index inversé  { "volcan": {page 3: 4 fois, page 7: 1 fois} }
                                    │
                               pagerank.py ──►  importance de chaque page
                                    │
  requête  ──►  BM25 × couverture × (1 + PageRank)  ──►  résultats classés
```

1. **Exploration** (`explorateur.py`) : parcours en largeur. On part d'une page, on note tous ses liens dans
   une file d'attente, puis on visite les pages une par une. `html.parser` extrait le titre, le texte visible
   (sans les scripts ni les menus) et les liens.
2. **Analyse** (`analyse.py`) : chaque texte est mis en minuscules, sans accents, découpé en mots, débarrassé des
   mots vides (« le », « de »…), puis chaque mot est réduit à sa racine.
3. **Index inversé** (`index.py`) : pour chaque terme, la liste des pages qui le contiennent et combien de fois.
   Chercher un mot revient à lire une seule ligne de l'index, au lieu de relire toutes les pages.
4. **BM25** : une page est pertinente si elle contient les mots cherchés souvent (avec des rendements
   décroissants), si ces mots sont rares ailleurs (IDF), et sans favoriser les pages simplement parce qu'elles sont longues.
5. **PageRank** (`pagerank.py`) : on imagine un internaute qui clique au hasard de lien en lien. Le PageRank
   d'une page est la proportion du temps qu'il y passe. On le calcule en répétant la distribution jusqu'à stabilité.
6. **Interface** (`serveur.py`) : un petit serveur `http.server` qui affiche la page d'accueil et les résultats.

## 💡 Pistes pour aller plus loin

- Chercher une **expression exacte** entre guillemets (il faut mémoriser la position des mots)
- Explorer **plusieurs pages en parallèle** avec des threads
- Stocker l'index dans **SQLite** pour gérer des centaines de milliers de pages
- Ajouter l'**autocomplétion** pendant la frappe
- Brancher **MiniGPT** ou Claude pour générer un résumé des résultats
