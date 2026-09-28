"""L'index inversé et la recherche.

Un index inversé, c'est comme l'index à la fin d'un livre : pour chaque mot, on note
les pages où il apparaît. Chercher devient alors quasi instantané, même avec des millions de pages.
"""

import gzip
import json
import math
import re
import time
from collections import Counter, defaultdict

from .analyse import MOTS_VIDES, distance_edition, mots, raciner, sans_accents, termes
from .pagerank import pagerank

POIDS_TITRE = 3      # un mot dans le titre compte comme 3 mots dans le texte
POIDS_PAGERANK = 0.5  # influence de la popularité sur le classement
K1, B = 1.2, 0.75     # réglages classiques de BM25
TEXTE_CONSERVE = 5000  # caractères gardés par page pour fabriquer les extraits


class Index:
    def __init__(self):
        self.documents = []                  # {url, titre, description, texte}
        self.postings = defaultdict(dict)    # terme -> {id_document: fréquence pondérée}
        self.longueurs = []                  # nombre de termes de chaque document
        self.pagerank = []
        self.mots_connus = Counter()         # vrais mots, pour « Vouliez-vous dire… ? »

    # --- Construction -----------------------------------------------------
    @classmethod
    def construire(cls, pages):
        index = cls()
        ids = {}
        for page in pages:
            if page["url"] in ids:
                continue
            id_doc = len(index.documents)
            ids[page["url"]] = id_doc
            document = {k: page.get(k, "") for k in ("url", "titre", "description", "texte")}
            document["texte"] = document["texte"][:TEXTE_CONSERVE]  # assez pour afficher des extraits
            index.documents.append(document)
            frequences = Counter(termes(page["texte"] + " " + page.get("description", "")))
            for terme in termes(page["titre"]):
                frequences[terme] += POIDS_TITRE
            for terme, frequence in frequences.items():
                index.postings[terme][id_doc] = frequence
            index.longueurs.append(sum(frequences.values()))
            # On garde les mots avec leurs accents pour proposer des corrections bien écrites.
            index.mots_connus.update(
                m for m in re.findall(r"[^\W\d_]+", (page["titre"] + " " + page["texte"]).lower())
                if len(m) > 3 and sans_accents(m) not in MOTS_VIDES
            )

        # PageRank sur le graphe des liens entre les pages indexées.
        graphe = {
            ids[p["url"]]: [ids[lien] for lien in p.get("liens", []) if lien in ids]
            for p in pages if p["url"] in ids
        }
        rangs = pagerank(graphe)
        index.pagerank = [rangs.get(i, 0.0) for i in range(len(index.documents))]
        return index

    # --- Sauvegarde ------------------------------------------------------
    def sauvegarder(self, chemin):
        donnees = {
            "documents": self.documents,
            "postings": self.postings,
            "longueurs": self.longueurs,
            "pagerank": self.pagerank,
            "mots_connus": self.mots_connus,
        }
        with gzip.open(chemin, "wt", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False)

    @classmethod
    def charger(cls, chemin):
        with gzip.open(chemin, "rt", encoding="utf-8") as f:
            donnees = json.load(f)
        index = cls()
        index.documents = donnees["documents"]
        index.longueurs = donnees["longueurs"]
        index.pagerank = donnees["pagerank"]
        index.mots_connus = Counter(donnees["mots_connus"])
        for terme, docs in donnees["postings"].items():
            index.postings[terme] = {int(i): f for i, f in docs.items()}
        return index

    # --- Recherche -------------------------------------------------------
    def idf(self, terme):
        """Plus un mot est rare, plus il est informatif (« volcan » vaut plus que « chose »)."""
        n, df = len(self.documents), len(self.postings.get(terme, {}))
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def chercher(self, requete, nb_resultats=10, debut=0):
        """Renvoie un dictionnaire : résultats, nombre total, durée, suggestion d'orthographe."""
        chrono = time.perf_counter()
        exclus = {t for mot in re.findall(r"-(\w+)", requete) for t in termes(mot)}
        requete_positive = re.sub(r"-\w+", " ", requete)
        voulus = list(dict.fromkeys(termes(requete_positive)))

        scores = defaultdict(float)
        trouves = defaultdict(int)
        if self.documents:
            longueur_moyenne = sum(self.longueurs) / len(self.longueurs)
            for terme in voulus:
                idf = self.idf(terme)
                for id_doc, tf in self.postings.get(terme, {}).items():
                    # BM25 : la fréquence compte, mais avec des rendements décroissants,
                    # et on ne favorise pas les pages juste parce qu'elles sont longues.
                    normalisation = K1 * (1 - B + B * self.longueurs[id_doc] / longueur_moyenne)
                    scores[id_doc] += idf * tf * (K1 + 1) / (tf + normalisation)
                    trouves[id_doc] += 1

        pr_max = max(self.pagerank, default=0) or 1
        classement = []
        for id_doc, score in scores.items():
            if any(id_doc in self.postings.get(t, {}) for t in exclus):
                continue
            couverture = trouves[id_doc] / len(voulus)  # bonus aux pages qui contiennent tous les mots
            final = score * couverture ** 2 * (1 + POIDS_PAGERANK * self.pagerank[id_doc] / pr_max)
            classement.append((final, id_doc))
        classement.sort(reverse=True)

        resultats = []
        for final, id_doc in classement[debut:debut + nb_resultats]:
            doc = self.documents[id_doc]
            resultats.append({
                "url": doc["url"],
                "titre": doc["titre"],
                "extrait": extrait(doc["texte"] if doc["description"][:40] in doc["texte"]
                                   else doc["description"] + "\n" + doc["texte"], set(voulus)),
                "score": round(final, 3),
                "pagerank": self.pagerank[id_doc],
            })
        return {
            "resultats": resultats,
            "total": len(classement),
            "duree": time.perf_counter() - chrono,
            "suggestion": self.suggerer(requete_positive),
        }

    def suggerer(self, requete):
        """Propose une correction si un mot de la requête est inconnu mais ressemble à un mot connu."""
        corrigee, modifiee = [], False
        for mot in mots(requete):
            if mot in MOTS_VIDES or self.postings.get(raciner(mot)) or len(mot) < 4:
                corrigee.append(mot)
                continue
            candidats = [
                (distance_edition(mot, sans_accents(connu)), -frequence, connu)
                for connu, frequence in self.mots_connus.items()
                if abs(len(connu) - len(mot)) <= 2 and sans_accents(connu[0]) == mot[0]
            ]
            candidats = [c for c in candidats if c[0] <= (1 if len(mot) < 6 else 2)]
            if candidats:
                corrigee.append(min(candidats)[2])
                modifiee = True
            else:
                corrigee.append(mot)
        return " ".join(corrigee) if modifiee else None


def extrait(texte, termes_voulus, taille=30):
    """Choisit le passage de ~30 mots qui contient le plus de mots cherchés.

    Les mots trouvés sont entourés de [[ ]] pour pouvoir les surligner à l'affichage.
    """
    mots_texte = texte.split()
    correspond = [any(t in termes_voulus for t in termes(m)) for m in mots_texte]
    cumul = [0]
    for c in correspond:
        cumul.append(cumul[-1] + c)
    # Fenêtre glissante : la somme sur [debut, debut + taille) vaut cumul[fin] - cumul[debut].
    departs = range(max(1, len(mots_texte) - taille + 1))
    meilleur_debut = max(departs, key=lambda d: (cumul[min(d + taille, len(mots_texte))] - cumul[d], -d))
    if any(correspond):
        # On décale un peu pour laisser du contexte avant le premier mot trouvé.
        premier = correspond.index(True, meilleur_debut)
        meilleur_debut = max(0, min(premier - taille // 3, len(mots_texte) - taille))
    fin = min(len(mots_texte), meilleur_debut + taille)
    fenetre = [f"[[{m}]]" if correspond[i] else m
               for i, m in enumerate(mots_texte[meilleur_debut:fin], meilleur_debut)]
    prefixe = "… " if meilleur_debut > 0 else ""
    suffixe = " …" if fin < len(mots_texte) else ""
    return prefixe + " ".join(fenetre) + suffixe
