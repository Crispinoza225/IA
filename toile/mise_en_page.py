"""La mise en page : décider où se place chaque boîte et chaque mot.

Deux façons de ranger le contenu :
  - en **blocs** (paragraphes, titres, listes…), empilés de haut en bas ;
  - **en ligne** (texte, liens, gras…), les mots posés de gauche à droite, avec un retour
    à la ligne quand il n'y a plus de place.
Le résultat est une liste d'ordres de dessin (« rectangle ici », « texte là ») qu'une
fenêtre ou une image n'a plus qu'à exécuter.
"""

import re
from dataclasses import dataclass

from .css import couleur, longueur
from .html import Element, Texte

AFFICHAGES_BLOC = {"block", "list-item", "flex", "grid", "table", "table-row", "table-row-group",
                   "table-header-group", "table-footer-group", "table-caption", "inline-block"}
REMPLACES = {"img", "input", "button", "textarea", "select", "svg", "video", "iframe", "canvas"}
COTES = ("top", "right", "bottom", "left")


# --- Ordres de dessin ------------------------------------------------------------------

@dataclass
class DessinRect:
    x1: float
    y1: float
    x2: float
    y2: float
    couleur: str


@dataclass
class DessinTexte:
    x: float
    y: float  # haut du texte
    texte: str
    police: tuple
    couleur: str


@dataclass
class DessinLigne:
    x1: float
    y1: float
    x2: float
    y2: float
    couleur: str
    epaisseur: float = 1


@dataclass
class ZoneLien:
    x1: float
    y1: float
    x2: float
    y2: float
    href: str


# --- Polices ------------------------------------------------------------------------------

def famille(style):
    """Ramène « "Helvetica Neue", Arial, sans-serif » à l'une des trois familles connues."""
    for nom in style.get("font-family", "").lower().replace('"', "").replace("'", "").split(","):
        nom = nom.strip()
        if nom in ("monospace", "courier", "courier new", "consolas", "menlo", "monaco") or "mono" in nom:
            return "monospace"
        if nom in ("serif", "times", "times new roman", "georgia", "garamond", "cambria"):
            return "serif"
        if nom in ("sans-serif", "arial", "helvetica", "verdana", "system-ui", "-apple-system", "segoe ui",
                   "roboto", "helvetica neue", "tahoma", "ubuntu"):
            return "sans-serif"
    return "sans-serif"


def police_de(style):
    """(famille, taille en pixels, gras ?, italique ?)"""
    taille = max(1, round(float(style["font-size"][:-2])))
    return (famille(style), taille, style["font-weight"] == "bold", style["font-style"] in ("italic", "oblique"))


def est_cache(noeud):
    return isinstance(noeud, Element) and (noeud.style.get("display") == "none" or noeud.balise == "head")


def est_bloc(noeud):
    return isinstance(noeud, Element) and noeud.style.get("display") in AFFICHAGES_BLOC


def hauteur_de_ligne(style, polices, police):
    ascendante, descendante = polices.metriques(police)
    valeur = style.get("line-height", "normal")
    taille = police[1]
    if valeur == "normal":
        return (ascendante + descendante) * 1.2
    try:
        return float(valeur) * taille  # « 1.5 » = 1,5 fois la taille de la police
    except ValueError:
        resultat = longueur(valeur, taille, taille)
        return resultat if resultat else (ascendante + descendante) * 1.2


# --- Mise en page des blocs ----------------------------------------------------------------

class Contexte:
    """Ce que toutes les boîtes partagent : les polices et les résultats (dessins, liens, ancres)."""

    def __init__(self, polices):
        self.polices = polices
        self.liens = []
        self.ancres = {}
        self.noeud_fond = None  # l'élément dont le fond recouvre toute la fenêtre


class Boite:
    """Une boîte de bloc : marges, bordures, remplissage (padding), puis le contenu."""

    def __init__(self, noeud, parent, precedente, contexte, contenu_anonyme=None):
        self.noeud = noeud
        self.parent = parent
        self.precedente = precedente
        self.contexte = contexte
        self.contenu_anonyme = contenu_anonyme  # boîte « anonyme » qui regroupe du contenu en ligne
        self.style = noeud.style if contenu_anonyme is None else parent.style
        self.enfants = []
        self.lignes = []

    def valeur(self, propriete, reference):
        if self.contenu_anonyme is not None:
            return 0.0
        brut = self.style.get(propriete, "0")
        if brut == "auto":
            return None
        return longueur(brut, float(self.style["font-size"][:-2]), reference) or 0.0

    def calculer(self):
        ref = self.parent.largeur
        self.marge = {c: self.valeur(f"margin-{c}", ref) for c in COTES}
        self.remplissage = {c: self.valeur(f"padding-{c}", ref) or 0.0 for c in COTES}
        self.bordure = {c: self.valeur(f"border-{c}-width", ref) or 0.0 for c in COTES}
        m, r, b = self.marge, self.remplissage, self.bordure
        gauche_auto, droite_auto = m["left"] is None, m["right"] is None
        m["left"], m["right"] = m["left"] or 0.0, m["right"] or 0.0
        m["top"], m["bottom"] = m["top"] or 0.0, m["bottom"] or 0.0
        cadre = r["left"] + r["right"] + b["left"] + b["right"]

        # Largeur : celle demandée par le CSS, sinon toute la place disponible.
        disponible = ref - m["left"] - m["right"] - cadre
        largeur = self.valeur("width", ref) if self.contenu_anonyme is None else None
        maximum = longueur(self.style.get("max-width", "none"), float(self.style["font-size"][:-2]), ref) \
            if self.contenu_anonyme is None else None
        self.largeur = disponible if largeur is None else largeur
        if maximum is not None:
            self.largeur = min(self.largeur, maximum)
        self.largeur = max(0.0, self.largeur)
        # « margin: 0 auto » : on centre la boîte si elle est moins large que son parent.
        libre = ref - self.largeur - cadre - m["left"] - m["right"]
        if libre > 0 and gauche_auto and droite_auto:
            m["left"] += libre / 2
            m["right"] += libre / 2
        elif libre > 0 and gauche_auto:
            m["left"] += libre

        self.x = self.parent.x + m["left"] + b["left"] + r["left"]
        if self.precedente is None:
            haut_bordure = self.parent.y + m["top"]
        else:
            # Fusion des marges : entre deux blocs, c'est la plus grande des deux marges qui compte.
            haut_bordure = self.precedente.bas_bordure + max(self.precedente.marge["bottom"], m["top"])
        self.y = haut_bordure + b["top"] + r["top"]

        if isinstance(self.noeud, Element) and self.contenu_anonyme is None:
            for attribut in ("id", "name"):
                if self.noeud.attributs.get(attribut):
                    self.contexte.ancres.setdefault(self.noeud.attributs[attribut], haut_bordure)

        contenu = self.contenu_anonyme if self.contenu_anonyme is not None else self.noeud.enfants
        if self.contenu_anonyme is None and any(est_bloc(e) for e in contenu if not est_cache(e)):
            self.disposer_blocs(contenu)
            dernier = self.enfants[-1] if self.enfants else None
            self.hauteur = (dernier.bas_bordure + dernier.marge["bottom"] - self.y) if dernier else 0.0
        else:
            disposition = LignesEnCours(self)
            disposition.disposer(contenu)
            self.lignes = disposition.lignes
            self.hauteur = sum(ligne.hauteur for ligne in self.lignes)

        hauteur_css = self.valeur("height", 0) if self.contenu_anonyme is None else None
        if hauteur_css:
            self.hauteur = hauteur_css
        self.bas_bordure = self.y + self.hauteur + r["bottom"] + b["bottom"]

    def disposer_blocs(self, contenu):
        """Empile les enfants de type bloc ; le texte qui traîne entre eux va dans des boîtes anonymes."""
        en_ligne = []
        precedente = None

        def vider():
            nonlocal precedente, en_ligne
            if any(not (isinstance(n, Texte) and not n.texte.strip()) for n in en_ligne):
                boite = Boite(None, self, precedente, self.contexte, contenu_anonyme=en_ligne)
                boite.calculer()
                self.enfants.append(boite)
                precedente = boite
            en_ligne = []

        for enfant in contenu:
            if est_cache(enfant):
                continue
            if est_bloc(enfant):
                vider()
                boite = Boite(enfant, self, precedente, self.contexte)
                boite.calculer()
                self.enfants.append(boite)
                precedente = boite
            else:
                en_ligne.append(enfant)
        vider()

    def dessiner(self, dessins):
        r, b = self.remplissage, self.bordure
        x1, y1 = self.x - r["left"], self.y - r["top"]
        x2, y2 = self.x + self.largeur + r["right"], self.y + self.hauteur + r["bottom"]
        if self.contenu_anonyme is None:
            fond = couleur(self.style.get("background-color", "transparent"))
            if fond and self.noeud is not self.contexte.noeud_fond:  # ce fond-là recouvre déjà toute la fenêtre
                dessins.append(DessinRect(x1, y1, x2, y2, fond))
            for cote in COTES:
                if b[cote] > 0:
                    teinte = couleur(self.style.get(f"border-{cote}-color", "")) or self.style["color"]
                    rect = {
                        "top": (x1 - b["left"], y1 - b["top"], x2 + b["right"], y1),
                        "bottom": (x1 - b["left"], y2, x2 + b["right"], y2 + b["bottom"]),
                        "left": (x1 - b["left"], y1 - b["top"], x1, y2 + b["bottom"]),
                        "right": (x2, y1 - b["top"], x2 + b["right"], y2 + b["bottom"]),
                    }[cote]
                    dessins.append(DessinRect(*rect, teinte))
            if self.style.get("display") == "list-item":
                self.dessiner_puce(dessins)
        for enfant in self.enfants:
            enfant.dessiner(dessins)
        for ligne in self.lignes:
            ligne.dessiner(dessins, self.contexte)

    def dessiner_puce(self, dessins):
        type_puce = self.style.get("list-style-type", "disc")
        if type_puce == "none":
            return
        police = police_de(self.style)
        if type_puce in ("decimal", "lower-alpha", "upper-alpha", "lower-roman", "upper-roman"):
            freres = [e for e in self.noeud.parent.enfants if isinstance(e, Element) and e.balise == "li"]
            rang = freres.index(self.noeud) + 1 if self.noeud in freres else 1
            if "alpha" in type_puce:
                texte = chr(ord("a") + (rang - 1) % 26)
                texte = texte.upper() if type_puce.startswith("upper") else texte
            else:
                texte = str(rang)
            texte += "."
        else:
            texte = {"circle": "◦", "square": "▪"}.get(type_puce, "•")
        largeur = self.contexte.polices.mesurer(police, texte)
        premiere = self.premiere_ligne()
        y = premiere.base - self.contexte.polices.metriques(police)[0] if premiere else self.y
        dessins.append(DessinTexte(self.x - largeur - 8, y, texte, police, self.style["color"]))

    def premiere_ligne(self):
        if self.lignes:
            return self.lignes[0]
        for enfant in self.enfants:
            ligne = enfant.premiere_ligne()
            if ligne:
                return ligne
        return None


# --- Mise en page du texte (en ligne) -------------------------------------------------------

@dataclass
class Morceau:
    x: float
    largeur: float
    texte: str
    police: tuple
    couleur: str
    lien: str
    decoration: str
    boite: dict = None  # pour les éléments « remplacés » (image, bouton…) : hauteur, fond, bordure


class Ligne:
    def __init__(self, y, hauteur, base, morceaux):
        self.y, self.hauteur, self.base, self.morceaux = y, hauteur, base, morceaux

    def dessiner(self, dessins, contexte):
        precedent = None
        for m in self.morceaux:
            if m.boite:
                haut = self.base - m.boite["hauteur"]
                dessins.append(DessinRect(m.x, haut, m.x + m.largeur, self.base, m.boite["fond"]))
                for rect in ((m.x, haut, m.x + m.largeur, haut + 1), (m.x, self.base - 1, m.x + m.largeur, self.base),
                             (m.x, haut, m.x + 1, self.base), (m.x + m.largeur - 1, haut, m.x + m.largeur, self.base)):
                    dessins.append(DessinRect(*rect, m.boite["bordure"]))
                if m.texte:
                    ascendante, descendante = contexte.polices.metriques(m.police)
                    y_texte = haut + (m.boite["hauteur"] - ascendante - descendante) / 2
                    dessins.append(DessinTexte(m.x + 6, y_texte, m.texte, m.police, m.couleur))
                haut_zone = haut
            else:
                ascendante, _ = contexte.polices.metriques(m.police)
                haut_zone = self.base - ascendante
                dessins.append(DessinTexte(m.x, haut_zone, m.texte, m.police, m.couleur))
                if "underline" in m.decoration:
                    # Le soulignement continue sous l'espace qui précède, si le mot d'avant est souligné aussi.
                    debut = m.x
                    if precedent and not precedent.boite and "underline" in precedent.decoration \
                            and precedent.lien == m.lien:
                        debut = precedent.x + precedent.largeur
                    dessins.append(DessinLigne(debut, self.base + 2, m.x + m.largeur, self.base + 2, m.couleur))
                if "line-through" in m.decoration:
                    y = self.base - ascendante * 0.3
                    dessins.append(DessinLigne(m.x, y, m.x + m.largeur, y, m.couleur))
            if m.lien:
                contexte.liens.append(ZoneLien(m.x, haut_zone, m.x + m.largeur, self.y + self.hauteur, m.lien))
            precedent = m


class LignesEnCours:
    """Pose les mots un par un et passe à la ligne quand il n'y a plus de place."""

    def __init__(self, boite):
        self.boite = boite
        self.polices = boite.contexte.polices
        self.lignes = []
        self.courante = []
        self.x = boite.x
        self.y = boite.y
        self.espace_en_attente = False

    def disposer(self, noeuds):
        for noeud in noeuds:
            self.noeud(noeud)
        self.finir_ligne()

    def noeud(self, noeud):
        if isinstance(noeud, Texte):
            self.texte(noeud)
        elif not est_cache(noeud):
            if noeud.balise == "br":
                self.finir_ligne(forcer=True)
            elif noeud.balise in REMPLACES:
                self.element_remplace(noeud)
            else:
                for enfant in noeud.enfants:
                    self.noeud(enfant)

    @staticmethod
    def lien_de(noeud):
        while noeud is not None:
            if isinstance(noeud, Element) and noeud.balise == "a" and "href" in noeud.attributs:
                return noeud.attributs["href"]
            noeud = noeud.parent
        return None

    def texte(self, noeud):
        style = noeud.style
        if style.get("visibility") == "hidden":
            return
        police = police_de(style)
        options = dict(police=police, couleur=style["color"], lien=self.lien_de(noeud),
                       decoration=style.get("text-decoration", "none"))
        if style.get("white-space") in ("pre", "pre-wrap"):
            for numero, ligne in enumerate(noeud.texte.split("\n")):
                if numero:
                    self.finir_ligne(forcer=True)
                if ligne:
                    self.ajouter(ligne.expandtabs(4), coupable=style["white-space"] == "pre-wrap", **options)
            return
        for morceau in re.split(r"(\s+)", noeud.texte):
            if not morceau:
                continue
            if morceau.isspace():
                self.espace_en_attente = bool(self.courante)
            else:
                self.ajouter(morceau, **options)

    def element_remplace(self, noeud):
        """Images, boutons, champs de saisie : une boîte avec un texte à l'intérieur."""
        style = noeud.style
        police = police_de(style)
        if noeud.balise != "img":
            police = ("sans-serif",) + police[1:]  # les champs de formulaire utilisent la police du système
        a = noeud.attributs
        balise, type_champ = noeud.balise, a.get("type", "text").lower()
        couleur_texte, fond, bordure = style["color"], "#f0f0f0", "#8f8f8f"
        if balise == "input" and type_champ == "hidden":
            return
        if balise == "img":
            texte = a.get("alt", "") or "[image]"
            fond, bordure, couleur_texte = "#eef2f7", "#b8c4d4", "#555555"
        elif balise == "input" and type_champ in ("checkbox", "radio"):
            texte = "✓" if "checked" in a else ""
        elif balise == "input" and type_champ in ("submit", "button", "reset"):
            texte = a.get("value", "Envoyer")
        elif balise == "input":
            texte = a.get("value") or a.get("placeholder", "")
            couleur_texte = couleur_texte if a.get("value") else "#8a8a8a"
            fond = "#ffffff"
        elif balise == "select":
            options = [e for e in noeud.enfants if isinstance(e, Element) and e.balise == "option"]
            texte = (options[0].texte_contenu().strip() if options else "") + " ▾"
        else:
            texte = " ".join(noeud.texte_contenu().split())
            fond = "#ffffff" if balise == "textarea" else fond
        ascendante, descendante = self.polices.metriques(police)
        largeur = self.polices.mesurer(police, texte) + 12
        hauteur = ascendante + descendante + 8
        if balise == "input" and type_champ in ("checkbox", "radio"):
            largeur = hauteur = 16
        elif balise in ("input", "textarea") and type_champ not in ("submit", "button", "reset"):
            largeur = max(largeur, 180)
        if balise == "textarea":
            hauteur *= 2
        taille = float(style["font-size"][:-2])
        largeur = longueur(a.get("width", ""), taille, self.boite.largeur) or longueur(style.get("width", "auto"), taille, self.boite.largeur) or largeur
        hauteur = longueur(a.get("height", ""), taille) or longueur(style.get("height", "auto"), taille) or hauteur
        self.ajouter(texte, police=police, couleur=couleur_texte, lien=self.lien_de(noeud), decoration="none",
                     boite={"hauteur": hauteur, "fond": fond, "bordure": bordure}, largeur_imposee=min(largeur, self.boite.largeur))

    def ajouter(self, texte, police, couleur, lien, decoration, boite=None, coupable=True, largeur_imposee=None):
        largeur = largeur_imposee if largeur_imposee is not None else self.polices.mesurer(police, texte)
        espace = self.polices.mesurer(police, " ") if self.espace_en_attente and self.courante else 0
        if coupable and self.courante and self.x + espace + largeur > self.boite.x + self.boite.largeur:
            self.finir_ligne()
            espace = 0
        self.x += espace
        self.courante.append(Morceau(self.x, largeur, texte, police, couleur, lien, decoration, boite))
        self.x += largeur
        self.espace_en_attente = False

    def finir_ligne(self, forcer=False):
        if not self.courante and not forcer:
            return
        police_bloc = police_de(self.boite.style)
        if self.courante:
            hauts, bas, hauteurs = [], [], []
            for m in self.courante:
                ascendante, descendante = self.polices.metriques(m.police)
                if m.boite:
                    hauts.append(m.boite["hauteur"])
                    bas.append(2)
                    hauteurs.append(m.boite["hauteur"] + 6)
                else:
                    hauts.append(ascendante)
                    bas.append(descendante)
                    hauteurs.append(hauteur_de_ligne(self.boite.style, self.polices, m.police))
            ascendante, descendante = max(hauts), max(bas)
            hauteur = max(max(hauteurs), ascendante + descendante)
        else:  # ligne vide (plusieurs <br> à la suite)
            ascendante, descendante = self.polices.metriques(police_bloc)
            hauteur = hauteur_de_ligne(self.boite.style, self.polices, police_bloc)
        base = self.y + (hauteur - ascendante - descendante) / 2 + ascendante

        # Alignement du texte : à gauche, centré ou à droite.
        if self.courante:
            utilise = self.courante[-1].x + self.courante[-1].largeur - self.boite.x
            reste = self.boite.largeur - utilise
            alignement = self.boite.style.get("text-align", "left")
            decalage = reste / 2 if alignement == "center" else reste if alignement in ("right", "end") else 0
            if decalage > 0:
                for m in self.courante:
                    m.x += decalage

        self.lignes.append(Ligne(self.y, hauteur, base, self.courante))
        self.y += hauteur
        self.courante = []
        self.x = self.boite.x
        self.espace_en_attente = False


# --- Le document entier -------------------------------------------------------------------------

class _Fenetre:
    def __init__(self, largeur):
        self.x, self.y, self.largeur = 0.0, 0.0, float(largeur)


class Disposition:
    """Le résultat complet de la mise en page d'un document pour une largeur de fenêtre donnée."""

    def __init__(self, racine, polices, largeur):
        self.contexte = Contexte(polices)
        self.racine = Boite(racine, _Fenetre(largeur), None, self.contexte)
        self.racine.calculer()
        # Comme dans les vrais navigateurs, le fond de <html> (ou à défaut de <body>) recouvre toute la fenêtre.
        self.fond = "#ffffff"
        corps = next((e for e in racine.enfants if isinstance(e, Element) and e.balise == "body"), None)
        for noeud in (racine, corps):
            if noeud is not None and couleur(noeud.style.get("background-color", "transparent")):
                self.fond = couleur(noeud.style["background-color"])
                self.contexte.noeud_fond = noeud
                break
        self.dessins = []
        self.racine.dessiner(self.dessins)
        self.liens = self.contexte.liens
        self.ancres = self.contexte.ancres
        self.hauteur = self.racine.bas_bordure + self.racine.marge["bottom"]

    def lien_a(self, x, y):
        for zone in self.liens:
            if zone.x1 <= x <= zone.x2 and zone.y1 <= y <= zone.y2:
                return zone.href
        return None
