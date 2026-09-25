"""Récupération du corpus de textes et transformation en nombres (tokenisation)."""

import glob
import io
import json
import os
import re
import urllib.request
import zipfile

DOSSIER_DONNEES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "donnees")
URL_EUROPARL = "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/europarl_raw.zip"


def nettoyer_europarl(texte):
    """Le corpus Europarl met des espaces partout (« l' an 2000 , ») : on remet une typographie normale."""
    # Le corpus a perdu les « œ » : on répare les mots les plus courants.
    for faux, vrai in (("uvre", "œuvre"), ("manuvre", "manœuvre"), ("vux", "vœux"),
                       ("cur", "cœur"), ("buf", "bœuf"), ("ufs", "œufs")):
        texte = re.sub(rf"\b{faux}(s?)\b", rf"{vrai}\1", texte)
    texte = re.sub(r" ([.,)])", r"\1", texte)
    texte = re.sub(r"([(]) ", r"\1", texte)
    texte = re.sub(r"(\w') ", r"\1", texte)
    texte = re.sub(r'" (.*?) "', r"« \1 »", texte)
    lignes = [ligne.strip() for ligne in texte.splitlines()]
    # On retire les lignes vides et les balises du corpus.
    return "\n".join(ligne for ligne in lignes if ligne and not ligne.startswith("<"))


def telecharger_europarl():
    """Télécharge les débats du Parlement européen en français (≈ 3,7 millions de caractères)."""
    os.makedirs(DOSSIER_DONNEES, exist_ok=True)
    destination = os.path.join(DOSSIER_DONNEES, "europarl_fr.txt")
    if os.path.exists(destination):
        print(f"Déjà téléchargé : {destination}")
        return destination
    print(f"Téléchargement de {URL_EUROPARL}…")
    with urllib.request.urlopen(URL_EUROPARL) as reponse:
        archive = zipfile.ZipFile(io.BytesIO(reponse.read()))
    morceaux = []
    for nom in sorted(archive.namelist()):
        if "/french/" in nom and not nom.endswith("/"):
            morceaux.append(nettoyer_europarl(archive.read(nom).decode("utf-8", errors="ignore")))
    with open(destination, "w", encoding="utf-8") as f:
        f.write("\n".join(morceaux))
    print(f"✅ {destination} ({os.path.getsize(destination) / 1e6:.1f} Mo)")
    return destination


def charger_corpus():
    """Lit tous les fichiers .txt du dossier donnees/ : ajoute tes propres livres ici !"""
    fichiers = sorted(glob.glob(os.path.join(DOSSIER_DONNEES, "*.txt")))
    if not fichiers:
        raise SystemExit("Aucun texte trouvé. Lance d'abord : python3 -m minigpt telecharger")
    textes = []
    for chemin in fichiers:
        with open(chemin, encoding="utf-8", errors="ignore") as f:
            textes.append(f.read())
        print(f"  📖 {os.path.basename(chemin)}")
    return "\n".join(textes)


class Tokeniseur:
    """Tokeniseur au niveau du caractère : chaque caractère différent reçoit un numéro.

    ChatGPT découpe plutôt en morceaux de mots (« tokens »), mais le principe est le même.
    """

    INCONNU = "�"

    def __init__(self, caracteres):
        self.caracteres = list(caracteres)
        if self.INCONNU not in self.caracteres:
            self.caracteres.append(self.INCONNU)
        self.vers_id = {c: i for i, c in enumerate(self.caracteres)}

    @classmethod
    def depuis_texte(cls, texte, frequence_min=5):
        compte = {}
        for c in texte:
            compte[c] = compte.get(c, 0) + 1
        # Les caractères très rares (symboles bizarres) sont ignorés.
        return cls(sorted(c for c, n in compte.items() if n >= frequence_min))

    @property
    def taille(self):
        return len(self.caracteres)

    def encoder(self, texte):
        inconnu = self.vers_id[self.INCONNU]
        return [self.vers_id.get(c, inconnu) for c in texte]

    def decoder(self, ids):
        return "".join(self.caracteres[i] for i in ids)

    def vers_json(self):
        return json.dumps(self.caracteres, ensure_ascii=False)

    @classmethod
    def depuis_json(cls, donnees):
        return cls(json.loads(donnees))
