"""L'analyseur HTML : transforme le texte d'une page en arbre de balises (le « DOM »).

  <body><p>Salut <b>toi</b></p></body>   →   body
                                               └─ p
                                                  ├─ "Salut "
                                                  └─ b
                                                     └─ "toi"

Le vrai HTML est souvent mal écrit (balises oubliées, jamais fermées…) : comme les vrais
navigateurs, on corrige les erreurs les plus courantes au lieu d'abandonner.
"""

from html import unescape

# Balises qui n'ont jamais de contenu ni de balise fermante.
VIDES = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
# Balises dont le contenu est du texte brut, à ne pas analyser comme du HTML.
TEXTE_BRUT = {"script", "style", "textarea", "title"}
# Balises qui vont dans <head>.
TETE = {"base", "basefont", "bgsound", "noscript", "link", "meta", "title", "style", "script"}
# Ouvrir l'une de ces balises ferme automatiquement un <p> resté ouvert.
FERMENT_P = {"p", "div", "ul", "ol", "table", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote",
             "section", "article", "header", "footer", "nav", "form", "hr", "main", "aside", "figure"}


class Texte:
    def __init__(self, texte, parent):
        self.texte = texte
        self.parent = parent
        self.enfants = []
        self.style = {}

    def __repr__(self):
        return repr(self.texte)


class Element:
    def __init__(self, balise, attributs, parent):
        self.balise = balise
        self.attributs = attributs
        self.parent = parent
        self.enfants = []
        self.style = {}

    def __repr__(self):
        return f"<{self.balise}>"

    def texte_contenu(self):
        return "".join(e.texte if isinstance(e, Texte) else e.texte_contenu() for e in self.enfants)


def lire_attributs(contenu):
    """« a href="x.html" class=lien checked » → ("a", {"href": "x.html", "class": "lien", "checked": ""})"""
    i, n = 0, len(contenu)
    while i < n and not contenu[i].isspace() and contenu[i] != "/":
        i += 1
    balise = contenu[:i].lower()
    attributs = {}
    while i < n:
        while i < n and (contenu[i].isspace() or contenu[i] == "/"):
            i += 1
        debut = i
        while i < n and not contenu[i].isspace() and contenu[i] not in "=/":
            i += 1
        nom = contenu[debut:i].lower()
        if not nom:
            i += 1
            continue
        while i < n and contenu[i].isspace():
            i += 1
        valeur = ""
        if i < n and contenu[i] == "=":
            i += 1
            while i < n and contenu[i].isspace():
                i += 1
            if i < n and contenu[i] in "\"'":
                guillemet = contenu[i]
                fin = contenu.find(guillemet, i + 1)
                fin = n if fin == -1 else fin
                valeur = contenu[i + 1:fin]
                i = fin + 1
            else:
                debut = i
                while i < n and not contenu[i].isspace():
                    i += 1
                valeur = contenu[debut:i]
        attributs[nom] = unescape(valeur)
    return balise, attributs


def fin_de_balise(source, debut):
    """Position du « > » qui ferme la balise, en ignorant ceux entre guillemets (href="a>b")."""
    guillemet = None
    for i in range(debut, len(source)):
        c = source[i]
        if guillemet:
            if c == guillemet:
                guillemet = None
        elif c in "\"'" and source[i - 1] in "= \t\n":
            guillemet = c
        elif c == ">":
            return i
    return -1


class AnalyseurHTML:
    def __init__(self, source):
        self.source = source
        self.ouverts = []   # pile des éléments pas encore fermés
        self.titre = ""

    def analyser(self):
        s, i, n = self.source, 0, len(self.source)
        while i < n:
            if s.startswith("<!--", i):
                fin = s.find("-->", i + 4)
                i = n if fin == -1 else fin + 3
            elif s.startswith("<", i) and i + 1 < n and (s[i + 1].isalpha() or s[i + 1] in "/!?"):
                fin = fin_de_balise(s, i + 1)
                if fin == -1:
                    self.ajouter_texte(s[i:])
                    break
                balise = self.ajouter_balise(s[i + 1:fin])
                i = fin + 1
                if balise in TEXTE_BRUT:
                    fermeture = s.lower().find(f"</{balise}", i)
                    fermeture = n if fermeture == -1 else fermeture
                    # <title> et <textarea> décodent quand même les entités (&amp; …), pas <script> ni <style>.
                    self.ajouter_texte(s[i:fermeture], brut=balise in ("script", "style"))
                    i = fermeture
            else:
                fin = s.find("<", i + 1)
                fin = n if fin == -1 else fin
                self.ajouter_texte(s[i:fin])
                i = fin
        return self.terminer()

    def ajouter_texte(self, texte, brut=False):
        if not brut:
            texte = unescape(texte)
        if not texte or (texte.isspace() and not self.ouverts):
            return
        self.balises_implicites(None)
        parent = self.ouverts[-1]
        if parent.enfants and isinstance(parent.enfants[-1], Texte):
            parent.enfants[-1].texte += texte
        else:
            parent.enfants.append(Texte(texte, parent))

    def ajouter_balise(self, contenu):
        if contenu.startswith(("!", "?")):
            return None  # <!doctype html>, <?xml … ?>
        if contenu.startswith("/"):
            self.fermer(contenu[1:].strip().lower())
            return None
        balise, attributs = lire_attributs(contenu)
        self.balises_implicites(balise)
        if balise in FERMENT_P or balise == "li":
            self.fermer_automatiquement(balise)
        parent = self.ouverts[-1] if self.ouverts else None
        element = Element(balise, attributs, parent)
        if parent is not None:
            parent.enfants.append(element)
        if balise not in VIDES:
            self.ouverts.append(element)
        return balise

    def fermer_automatiquement(self, balise):
        """<p>un<p>deux  → le deuxième <p> ferme le premier ; pareil pour <li>."""
        bloquants = {"ul", "ol", "div", "body", "td", "th", "section", "article", "blockquote"}
        for element in reversed(self.ouverts):
            if balise == "li" and element.balise == "li" or balise != "li" and element.balise == "p":
                self.fermer(element.balise)
                return
            if element.balise in bloquants:
                return

    def fermer(self, balise):
        """Ferme la balise indiquée, et toutes celles oubliées à l'intérieur."""
        for position in range(len(self.ouverts) - 1, 0, -1):
            if self.ouverts[position].balise == balise:
                del self.ouverts[position:]
                return
        # Balise fermante sans balise ouvrante correspondante : on l'ignore.

    def balises_implicites(self, balise):
        """Ajoute les <html>, <head> et <body> que les auteurs oublient souvent."""
        while True:
            ouvertes = [e.balise for e in self.ouverts]
            if not ouvertes and balise != "html":
                self.ajouter_balise("html")
            elif ouvertes == ["html"] and balise not in ("head", "body", "/html"):
                self.ajouter_balise("head" if balise in TETE else "body")
            elif ouvertes == ["html", "head"] and balise not in TETE:
                self.fermer("head")
            else:
                break

    def terminer(self):
        if not self.ouverts:
            self.balises_implicites(None)
        return self.ouverts[0]


def analyser(source):
    return AnalyseurHTML(source).analyser()


def parcourir(noeud):
    """Tous les nœuds de l'arbre, dans l'ordre du document."""
    yield noeud
    for enfant in noeud.enfants:
        yield from parcourir(enfant)
