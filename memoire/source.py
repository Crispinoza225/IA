"""Lire le texte du mémoire (une syntaxe simple, proche du Markdown) et le transformer en blocs.

    # Titre de chapitre          ## Sous-partie          ### Sous-sous-partie
    Un paragraphe avec du **gras** et de l'*italique*.
    - un élément de liste        1. un élément numéroté
    > une citation longue
    | Colonne 1 | Colonne 2 |    (un tableau ; la première ligne est l'en-tête)
    ---saut de page---

Les titres comme « Introduction », « Conclusion » ou « Bibliographie » ne sont pas numérotés.
On peut aussi retirer le numéro d'un titre en ajoutant {-} à la fin : « # Avant-propos {-} ».
"""

import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree

TITRES_SANS_NUMERO = {
    "introduction", "introduction generale", "conclusion", "conclusion generale", "remerciements", "resume",
    "abstract", "bibliographie", "references", "references bibliographiques", "webographie", "annexes", "annexe",
    "sommaire", "table des matieres", "glossaire", "liste des abreviations", "sigles et abreviations",
    "dedicace", "avant-propos", "avant propos", "liste des figures", "liste des tableaux", "index",
}


def sans_accents(texte):
    texte = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in texte if unicodedata.category(c) != "Mn")


# --- Les blocs du document ------------------------------------------------------------

@dataclass
class Morceau:
    """Un bout de texte avec son style : « du **gras** » donne deux morceaux."""
    texte: str
    gras: bool = False
    italique: bool = False


@dataclass
class Titre:
    niveau: int
    texte: str
    numerote: bool = True
    numero: str = ""      # rempli par numeroter() : « 1.2. », « II. », …


@dataclass
class Paragraphe:
    morceaux: list


@dataclass
class Liste:
    ordonnee: bool
    elements: list = field(default_factory=list)  # chaque élément est une liste de morceaux


@dataclass
class Citation:
    morceaux: list


@dataclass
class Tableau:
    lignes: list  # liste de lignes, chaque ligne est une liste de cellules (listes de morceaux)


@dataclass
class SautDePage:
    pass


# --- Texte en ligne : gras et italique ---------------------------------------------------

def lire_morceaux(texte):
    """« un **mot** en *italique* » → [Morceau("un "), Morceau("mot", gras), Morceau(" en "), Morceau("italique", italique)]"""
    morceaux = []
    for partie in re.split(r"(\*\*\*.+?\*\*\*|\*\*.+?\*\*|\*[^*\s](?:[^*]*[^*\s])?\*)", texte):
        if not partie:
            continue
        if partie.startswith("***") and partie.endswith("***") and len(partie) > 6:
            morceaux.append(Morceau(partie[3:-3], gras=True, italique=True))
        elif partie.startswith("**") and partie.endswith("**") and len(partie) > 4:
            morceaux.append(Morceau(partie[2:-2], gras=True))
        elif partie.startswith("*") and partie.endswith("*") and len(partie) > 2:
            morceaux.append(Morceau(partie[1:-1], italique=True))
        else:
            morceaux.append(Morceau(partie))
    return morceaux


def texte_brut(morceaux):
    return "".join(m.texte for m in morceaux)


# --- Lecture du document --------------------------------------------------------------------

LIGNE_TITRE = re.compile(r"^(#{1,3})\s+(.*?)\s*$")
LIGNE_PUCE = re.compile(r"^\s*[-*•]\s+(.*)$")
LIGNE_NUMERO = re.compile(r"^\s*\d+[.)]\s+(.*)$")
LIGNE_SAUT = re.compile(r"^\s*-{3,}\s*saut de page\s*-{3,}\s*$", re.IGNORECASE)
SEPARATEUR_TABLEAU = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def cellules(ligne):
    ligne = ligne.strip()
    if ligne.startswith("|"):
        ligne = ligne[1:]
    if ligne.endswith("|"):
        ligne = ligne[:-1]
    return [lire_morceaux(c.strip()) for c in ligne.split("|")]


def lire(texte):
    """Transforme le texte en liste de blocs."""
    blocs = []
    paragraphe = []

    def finir_paragraphe():
        if paragraphe:
            blocs.append(Paragraphe(lire_morceaux(" ".join(paragraphe))))
            paragraphe.clear()

    lignes = texte.replace("\r\n", "\n").replace("\t", "    ").split("\n")
    i = 0
    while i < len(lignes):
        ligne = lignes[i]
        if not ligne.strip():
            finir_paragraphe()
        elif LIGNE_SAUT.match(ligne):
            finir_paragraphe()
            blocs.append(SautDePage())
        elif LIGNE_TITRE.match(ligne):
            finir_paragraphe()
            dieses, titre = LIGNE_TITRE.match(ligne).groups()
            numerote = True
            if titre.endswith("{-}"):
                titre, numerote = titre[:-3].strip(), False
            elif sans_accents(titre).strip(" .:") in TITRES_SANS_NUMERO:
                numerote = False
            blocs.append(Titre(len(dieses), titre, numerote))
        elif ligne.lstrip().startswith(">"):
            finir_paragraphe()
            citation = []
            while i < len(lignes) and lignes[i].lstrip().startswith(">"):
                citation.append(lignes[i].lstrip()[1:].strip())
                i += 1
            blocs.append(Citation(lire_morceaux(" ".join(citation))))
            continue
        elif LIGNE_PUCE.match(ligne) or LIGNE_NUMERO.match(ligne):
            finir_paragraphe()
            ordonnee = bool(LIGNE_NUMERO.match(ligne))
            motif = LIGNE_NUMERO if ordonnee else LIGNE_PUCE
            liste = Liste(ordonnee)
            while i < len(lignes) and motif.match(lignes[i]):
                liste.elements.append(lire_morceaux(motif.match(lignes[i]).group(1)))
                i += 1
            blocs.append(liste)
            continue
        elif ligne.strip().startswith("|") and i + 1 < len(lignes) and SEPARATEUR_TABLEAU.match(lignes[i + 1]):
            finir_paragraphe()
            tableau = [cellules(ligne)]
            i += 2
            while i < len(lignes) and lignes[i].strip().startswith("|"):
                tableau.append(cellules(lignes[i]))
                i += 1
            largeur = max(len(l) for l in tableau)
            blocs.append(Tableau([l + [[]] * (largeur - len(l)) for l in tableau]))
            continue
        else:
            paragraphe.append(ligne.strip())
        i += 1
    finir_paragraphe()
    return blocs


def romain(nombre):
    valeurs = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
               (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    resultat = ""
    for valeur, lettres in valeurs:
        while nombre >= valeur:
            resultat += lettres
            nombre -= valeur
    return resultat


def lettre(nombre):
    resultat = ""
    while nombre > 0:
        nombre, reste = divmod(nombre - 1, 26)
        resultat = chr(ord("A") + reste) + resultat
    return resultat


def numeroter(blocs, style):
    """Calcule le numéro de chaque titre : « 2.1. » (décimale) ou « II. », « A. », « 1. » (romaine)."""
    compteurs = [0, 0, 0]
    for bloc in blocs:
        if not isinstance(bloc, Titre):
            continue
        if not bloc.numerote or style == "aucune":
            bloc.numero = ""
            continue
        n = bloc.niveau - 1
        compteurs[n] += 1
        for suivant in range(n + 1, 3):
            compteurs[suivant] = 0
        if style == "romaine":
            bloc.numero = [romain, lettre, str][n](compteurs[n]) + "."
        else:
            bloc.numero = ".".join(str(c) for c in compteurs[:n + 1]) + "."
    return blocs


# --- Import d'un document Word ----------------------------------------------------------------

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# L'ancien sommaire et l'ancienne page de garde ne sont pas importés : la plateforme les refait elle-même.
STYLES_IGNORES = r"^(toc|tm ?\d|contents|table des mati|table of contents|en-tête de table des mati|page de garde|title$|titre$|subtitle|sous-titre)"


def importer_docx(contenu):
    """Transforme un fichier .docx (en octets) en texte dans notre syntaxe : titres, gras, italique, listes."""
    import io
    with zipfile.ZipFile(io.BytesIO(contenu)) as archive:
        racine = ElementTree.fromstring(archive.read("word/document.xml"))
        noms_styles = {}
        if "word/styles.xml" in archive.namelist():
            for style in ElementTree.fromstring(archive.read("word/styles.xml")).iter(W + "style"):
                nom = style.find(W + "name")
                noms_styles[style.get(W + "styleId")] = (nom.get(W + "val") if nom is not None else "").lower()
    lignes = []
    for p in racine.iter(W + "p"):
        style = p.find(f"{W}pPr/{W}pStyle")
        nom_style = noms_styles.get(style.get(W + "val"), style.get(W + "val").lower()) if style is not None else ""
        morceaux = []
        for run in p.iter(W + "r"):
            texte = "".join(t.text or "" for t in run.iter(W + "t"))
            if not texte:
                continue
            proprietes = run.find(W + "rPr")
            gras = proprietes is not None and proprietes.find(W + "b") is not None \
                and proprietes.find(W + "b").get(W + "val") not in ("0", "false")
            italique = proprietes is not None and proprietes.find(W + "i") is not None \
                and proprietes.find(W + "i").get(W + "val") not in ("0", "false")
            if texte.strip() and (gras or italique):
                marque = "***" if gras and italique else "**" if gras else "*"
                debut, fin = len(texte) - len(texte.lstrip()), len(texte.rstrip())
                texte = texte[:debut] + marque + texte[debut:fin] + marque + texte[fin:]
            morceaux.append(texte)
        texte = "".join(morceaux).strip()
        if not texte or re.match(STYLES_IGNORES, nom_style):
            continue
        niveau = re.search(r"(?:heading|titre)\s*(\d)", nom_style)
        if niveau and 1 <= int(niveau.group(1)) <= 3:
            # Les numéros tapés à la main (« 1.2 Titre ») sont retirés : la plateforme numérote elle-même.
            texte = re.sub(r"^\*+|\*+$", "", texte)
            texte = re.sub(r"^((\d+\.)+\d*|[IVXLC]+\.|[A-Z]\.)\s+", "", texte)
            lignes.append("#" * int(niveau.group(1)) + " " + texte)
        elif p.find(f"{W}pPr/{W}numPr") is not None or "list" in nom_style or "liste" in nom_style:
            lignes.append("- " + texte)
        elif "quote" in nom_style or "citation" in nom_style:
            lignes.append("> " + texte)
        else:
            lignes.append(texte)
        lignes.append("")
    return re.sub(r"(\n- [^\n]*)\n\n(?=- )", r"\1\n", "\n".join(lignes)).strip() + "\n"
