"""Le moteur CSS : lit les feuilles de style et calcule le style final de chaque élément.

Trois idées clés :
  - les **sélecteurs** (« nav a.actif ») disent à quels éléments une règle s'applique ;
  - la **spécificité** départage les règles en conflit (#id > .classe > balise) ;
  - l'**héritage** : certaines propriétés (couleur, police…) passent des parents aux enfants.
"""

import re

from .html import Element, Texte

HERITEES = {
    "color": "#000000", "font-size": "16px", "font-weight": "normal", "font-style": "normal",
    "font-family": "sans-serif", "text-align": "left", "line-height": "normal", "white-space": "normal",
    "list-style-type": "disc", "text-decoration": "none", "visibility": "visible",
}
NON_HERITEES = {"display": "inline", "background-color": "transparent", "width": "auto", "max-width": "none"}
for _cote in ("top", "right", "bottom", "left"):
    NON_HERITEES[f"margin-{_cote}"] = "0"
    NON_HERITEES[f"padding-{_cote}"] = "0"
    NON_HERITEES[f"border-{_cote}-width"] = "0"
    NON_HERITEES[f"border-{_cote}-color"] = "currentcolor"

COULEURS = {
    "black": "#000000", "white": "#ffffff", "red": "#ff0000", "green": "#008000", "blue": "#0000ff",
    "yellow": "#ffff00", "orange": "#ffa500", "purple": "#800080", "pink": "#ffc0cb", "gray": "#808080",
    "grey": "#808080", "silver": "#c0c0c0", "maroon": "#800000", "navy": "#000080", "teal": "#008080",
    "olive": "#808000", "lime": "#00ff00", "aqua": "#00ffff", "cyan": "#00ffff", "fuchsia": "#ff00ff",
    "magenta": "#ff00ff", "brown": "#a52a2a", "gold": "#ffd700", "coral": "#ff7f50", "tomato": "#ff6347",
    "crimson": "#dc143c", "indigo": "#4b0082", "violet": "#ee82ee", "salmon": "#fa8072", "khaki": "#f0e68c",
    "beige": "#f5f5dc", "ivory": "#fffff0", "lavender": "#e6e6fa", "skyblue": "#87ceeb",
    "steelblue": "#4682b4", "royalblue": "#4169e1", "darkblue": "#00008b", "darkgreen": "#006400",
    "darkred": "#8b0000", "darkgray": "#a9a9a9", "darkgrey": "#a9a9a9", "lightgray": "#d3d3d3",
    "lightgrey": "#d3d3d3", "lightblue": "#add8e6", "lightgreen": "#90ee90", "lightyellow": "#ffffe0",
    "whitesmoke": "#f5f5f5", "gainsboro": "#dcdcdc", "slategray": "#708090", "dimgray": "#696969",
    "forestgreen": "#228b22", "seagreen": "#2e8b57", "chocolate": "#d2691e", "tan": "#d2b48c",
    "orangered": "#ff4500", "hotpink": "#ff69b4", "turquoise": "#40e0d0", "midnightblue": "#191970",
}
TAILLES_MOTS_CLES = {"xx-small": 9, "x-small": 10, "small": 13, "medium": 16, "large": 18, "x-large": 24,
                     "xx-large": 32}


# --- Valeurs ----------------------------------------------------------------------

def couleur(valeur):
    """Renvoie la couleur au format #rrggbb, ou None si ce n'est pas une couleur (ou si elle est transparente)."""
    valeur = valeur.strip().lower()
    if valeur in COULEURS:
        return COULEURS[valeur]
    if re.fullmatch(r"#[0-9a-f]{3,4}", valeur):
        return "#" + "".join(c * 2 for c in valeur[1:4])
    if re.fullmatch(r"#[0-9a-f]{6}([0-9a-f]{2})?", valeur):
        return valeur[:7]
    m = re.fullmatch(r"rgba?\(\s*([\d.]+)%?\s*[, ]\s*([\d.]+)%?\s*[, ]\s*([\d.]+)%?\s*(?:[,/]\s*([\d.]+%?))?\s*\)", valeur)
    if m:
        if m.group(4) and m.group(4) in ("0", "0%", "0.0"):
            return None
        return "#" + "".join(f"{min(255, int(float(c))):02x}" for c in m.groups()[:3])
    return None


def longueur(valeur, taille_police=16.0, reference=0.0):
    """« 2em », « 12px », « 50% » → nombre de pixels. None pour « auto » ou une valeur inconnue."""
    valeur = valeur.strip().lower()
    m = re.fullmatch(r"(-?[\d.]+)(px|em|rem|%|pt|vw|vh)?", valeur)
    if not m:
        return None
    try:
        nombre = float(m.group(1))
    except ValueError:
        return None
    unite = m.group(2) or "px"
    return {
        "px": nombre, "em": nombre * taille_police, "rem": nombre * 16.0, "%": nombre * reference / 100,
        "pt": nombre * 4 / 3, "vw": nombre * 8, "vh": nombre * 6,
    }[unite]


# --- Sélecteurs ---------------------------------------------------------------------

class SelecteurSimple:
    """Une balise, des classes et un id collés ensemble : « a.bouton.rouge », « #menu », « * »."""

    def __init__(self, texte):
        self.balise = None
        self.classes = []
        self.id = None
        self.valide = True
        for morceau in re.findall(r"[.#]?[^.#]+", texte):
            if morceau.startswith("."):
                self.classes.append(morceau[1:])
            elif morceau.startswith("#"):
                self.id = morceau[1:]
            elif morceau != "*":
                self.balise = morceau.lower()
        # Les pseudo-classes (:hover…) et les attributs ([type=…]) ne sont pas pris en charge.
        if any(c in texte for c in ":[]()"):
            self.valide = False

    def correspond(self, noeud):
        if not self.valide or not isinstance(noeud, Element):
            return False
        if self.balise and noeud.balise != self.balise:
            return False
        if self.id and noeud.attributs.get("id") != self.id:
            return False
        classes = noeud.attributs.get("class", "").split()
        return all(c in classes for c in self.classes)

    @property
    def specificite(self):
        return (1 if self.id else 0, len(self.classes), 1 if self.balise else 0)


class Selecteur:
    """Une suite de sélecteurs simples reliés par des espaces (descendant) ou des « > » (enfant direct)."""

    def __init__(self, texte):
        morceaux = re.findall(r">|[^\s>]+", texte.strip())
        self.etapes = []  # liste de (combinateur, SelecteurSimple) ; combinateur = " " ou ">"
        combinateur = " "
        for morceau in morceaux:
            if morceau == ">":
                combinateur = ">"
            else:
                self.etapes.append((combinateur, SelecteurSimple(morceau)))
                combinateur = " "
        self.valide = bool(self.etapes) and all(s.valide for _, s in self.etapes)

    @property
    def specificite(self):
        return tuple(sum(s.specificite[i] for _, s in self.etapes) for i in range(3))

    def correspond(self, noeud):
        if not self.valide:
            return False
        return self._correspond(noeud, len(self.etapes) - 1)

    def _correspond(self, noeud, indice):
        combinateur, simple = self.etapes[indice]
        if not simple.correspond(noeud):
            return False
        if indice == 0:
            return True
        parent = noeud.parent
        if combinateur == ">":
            return parent is not None and self._correspond(parent, indice - 1)
        while parent is not None:
            if self._correspond(parent, indice - 1):
                return True
            parent = parent.parent
        return False


# --- Analyse des feuilles de style ----------------------------------------------------

def developper(propriete, valeur):
    """Transforme les raccourcis (« margin: 4px 8px ») en propriétés détaillées."""
    valeur = valeur.strip()
    if propriete in ("margin", "padding"):
        v = valeur.split()
        if not 1 <= len(v) <= 4:
            return {}
        if len(v) == 1:
            v = v * 4
        elif len(v) == 2:
            v = v * 2
        elif len(v) == 3:
            v = v + [v[1]]
        haut, droite, bas, gauche = v  # dans le sens des aiguilles d'une montre
        return {f"{propriete}-top": haut, f"{propriete}-right": droite,
                f"{propriete}-bottom": bas, f"{propriete}-left": gauche}
    if propriete == "border" or re.fullmatch(r"border-(top|right|bottom|left)", propriete):
        cotes = ["top", "right", "bottom", "left"] if propriete == "border" else [propriete.split("-")[1]]
        largeur, teinte = "0", "currentcolor"
        for morceau in re.findall(r"rgba?\([^)]*\)|\S+", valeur):
            if longueur(morceau) is not None:
                largeur = morceau
            elif morceau in ("thin", "medium", "thick"):
                largeur = {"thin": "1px", "medium": "3px", "thick": "5px"}[morceau]
            elif couleur(morceau):
                teinte = morceau
            elif morceau in ("solid", "dashed", "dotted", "double", "groove", "ridge", "inset", "outset") and largeur == "0":
                largeur = "3px"  # « border: solid » a une épaisseur moyenne par défaut
            elif morceau in ("none", "hidden"):
                largeur = "0"
        resultat = {}
        for cote in cotes:
            resultat[f"border-{cote}-width"] = largeur
            resultat[f"border-{cote}-color"] = teinte
        return resultat
    if propriete == "border-width":
        return {f"border-{c}-width": valeur for c in ("top", "right", "bottom", "left")}
    if propriete == "border-color":
        return {f"border-{c}-color": valeur for c in ("top", "right", "bottom", "left")}
    if propriete == "background":
        for morceau in re.findall(r"rgba?\([^)]*\)|#[0-9a-fA-F]+|[a-zA-Z]+", valeur):
            if couleur(morceau) or morceau.lower() == "transparent":
                return {"background-color": morceau}
        return {}
    if propriete == "font":
        resultat = {}
        for morceau in valeur.split():
            if morceau in ("bold", "bolder") or morceau.isdigit() and int(morceau) >= 600:
                resultat["font-weight"] = "bold"
            elif morceau == "italic":
                resultat["font-style"] = "italic"
            elif longueur(morceau.split("/")[0]) is not None:
                resultat["font-size"] = morceau.split("/")[0]
                break
        return resultat
    if propriete == "list-style":
        return {"list-style-type": valeur.split()[0]} if valeur else {}
    return {propriete: valeur}


def lire_declarations(texte):
    """« color: red; margin: 0 auto » → {"color": "red", "margin-top": "0", …}"""
    declarations = {}
    for declaration in texte.split(";"):
        propriete, deux_points, valeur = declaration.partition(":")
        if not deux_points:
            continue
        valeur = valeur.replace("!important", "").strip()
        if valeur:
            declarations.update(developper(propriete.strip().lower(), valeur))
    return declarations


def sauter_bloc(texte, debut):
    """Renvoie la position juste après le bloc { … } qui commence à `debut` (les blocs peuvent s'imbriquer)."""
    profondeur = 0
    for i in range(debut, len(texte)):
        if texte[i] == "{":
            profondeur += 1
        elif texte[i] == "}":
            profondeur -= 1
            if profondeur == 0:
                return i + 1
    return len(texte)


def analyser_css(texte):
    """Renvoie une liste de règles (sélecteur, déclarations)."""
    texte = re.sub(r"/\*.*?\*/", "", texte, flags=re.S)
    regles = []
    i = 0
    while i < len(texte):
        accolade = texte.find("{", i)
        if accolade == -1:
            break
        entete = texte[i:accolade].strip()
        if entete.startswith("@"):
            # @media, @font-face, @keyframes… : ignorés (sauf « @import », qui n'a pas de bloc).
            point_virgule = texte.find(";", i)
            if entete.startswith("@import") or (0 <= point_virgule < accolade):
                i = point_virgule + 1
                continue
            i = sauter_bloc(texte, accolade)
            continue
        fin = texte.find("}", accolade)
        fin = len(texte) if fin == -1 else fin
        declarations = lire_declarations(texte[accolade + 1:fin])
        for morceau in entete.split(","):
            selecteur = Selecteur(morceau)
            if selecteur.valide:
                regles.append((selecteur, declarations))
        i = fin + 1
    return regles


# --- Calcul du style de chaque élément ----------------------------------------------------

def taille_police(valeur, taille_parent):
    valeur = valeur.strip().lower()
    if valeur in TAILLES_MOTS_CLES:
        return float(TAILLES_MOTS_CLES[valeur])
    if valeur == "smaller":
        return taille_parent / 1.2
    if valeur == "larger":
        return taille_parent * 1.2
    resultat = longueur(valeur, taille_parent, taille_parent)
    return taille_parent if resultat is None else resultat


def appliquer_styles(noeud, regles, style_parent=None):
    """Calcule noeud.style pour tout l'arbre. Les règles doivent être dans l'ordre d'apparition."""
    style_parent = style_parent or HERITEES
    if isinstance(noeud, Texte):
        noeud.style = style_parent
        return
    style = {p: style_parent.get(p, defaut) for p, defaut in HERITEES.items()}
    style.update(NON_HERITEES)

    # La cascade : les règles les plus spécifiques gagnent ; à égalité, la dernière écrite.
    applicables = [(s.specificite, ordre, d) for ordre, (s, d) in enumerate(regles) if s.correspond(noeud)]
    for _, _, declarations in sorted(applicables, key=lambda r: (r[0], r[1])):
        style.update(declarations)
    if "style" in noeud.attributs:  # l'attribut style="…" passe avant tout
        style.update(lire_declarations(noeud.attributs["style"]))

    # Valeurs spéciales et calculs.
    parent_taille = float(style_parent["font-size"][:-2])
    for propriete, valeur in list(style.items()):
        if valeur == "inherit":
            style[propriete] = style_parent.get(propriete, HERITEES.get(propriete, NON_HERITEES.get(propriete)))
        elif valeur in ("initial", "unset"):
            style[propriete] = HERITEES.get(propriete, NON_HERITEES.get(propriete))
    style["font-size"] = f"{taille_police(style['font-size'], parent_taille)}px"
    poids = style["font-weight"]
    style["font-weight"] = "bold" if poids in ("bold", "bolder") or poids.isdigit() and int(poids) >= 600 else "normal"
    if couleur(style["color"]) is None:
        style["color"] = style_parent["color"]
    else:
        style["color"] = couleur(style["color"])
    noeud.style = style

    for enfant in noeud.enfants:
        appliquer_styles(enfant, regles, style)
