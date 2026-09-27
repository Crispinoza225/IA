"""Charger une page : télécharger le HTML, construire l'arbre et appliquer toutes les feuilles de style."""

import os
from html import escape

from .css import analyser_css, appliquer_styles
from .html import Element, Texte, analyser, parcourir
from .reseau import URL, ErreurReseau

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "navigateur.css"), encoding="utf-8") as _f:
    REGLES_NAVIGATEUR = analyser_css(_f.read())


class Page:
    def __init__(self, url, source):
        self.url = url
        self.arbre = analyser(source)
        self.titre = ""
        feuilles = []
        for noeud in parcourir(self.arbre):
            if not isinstance(noeud, Element):
                continue
            if noeud.balise == "title" and not self.titre:
                self.titre = " ".join(noeud.texte_contenu().split())
            elif noeud.balise == "style":
                feuilles.append(noeud.texte_contenu())
            elif (noeud.balise == "link" and "stylesheet" in noeud.attributs.get("rel", "").lower()
                  and noeud.attributs.get("href") and "print" not in noeud.attributs.get("media", "")):
                feuilles.append(self.telecharger_css(noeud.attributs["href"]))
        self.regles = list(REGLES_NAVIGATEUR)
        for feuille in feuilles:
            self.regles.extend(analyser_css(feuille))
        appliquer_styles(self.arbre, self.regles)

    def telecharger_css(self, href):
        try:
            return self.url.resoudre(href).telecharger(delai=5).texte
        except (ErreurReseau, ValueError):
            return ""  # une feuille de style introuvable n'empêche pas d'afficher la page

    def texte(self):
        """Le texte visible de la page (pratique pour les tests)."""
        morceaux = []
        for noeud in parcourir(self.arbre):
            if isinstance(noeud, Texte) and noeud.parent.style.get("display") != "none":
                if not any(p.balise in ("head", "script", "style") for p in ancetres(noeud)):
                    morceaux.append(noeud.texte)
        return " ".join(" ".join(morceaux).split())


def ancetres(noeud):
    noeud = noeud.parent
    while noeud is not None:
        yield noeud
        noeud = noeud.parent


def page_erreur(url, message):
    return f"""<html><head><title>Erreur</title></head>
<body style="background:#fdf2f2; font-family:sans-serif; margin:40px">
<h1 style="color:#b42318">😕 Impossible d'afficher la page</h1>
<p><b>{escape(str(url))}</b></p><p>{escape(message)}</p>
<p><a href="about:accueil">Retour à l'accueil</a></p></body></html>"""


def charger(adresse):
    """Renvoie toujours une Page : en cas de problème, une page d'erreur explique ce qui s'est passé."""
    try:
        url = adresse if isinstance(adresse, URL) else URL(adresse)
    except (ErreurReseau, ValueError) as erreur:
        return Page(URL("about:erreur"), page_erreur(adresse, str(erreur)))
    try:
        reponse = url.telecharger()
    except (ErreurReseau, OSError, ValueError) as erreur:
        return Page(url, page_erreur(url, str(erreur)))
    type_contenu = reponse.entetes.get("content-type", "text/html")
    if "html" not in type_contenu and not type_contenu.startswith("text/"):
        return Page(url, page_erreur(url, f"Ce n'est pas une page web ({type_contenu})."))
    texte = reponse.texte
    if "html" not in type_contenu:
        texte = f"<pre>{escape(texte)}</pre>"  # un fichier texte s'affiche tel quel
    if reponse.statut >= 400:
        texte = texte or page_erreur(url, f"Le serveur a répondu {reponse.statut}.")
    return Page(reponse.url, texte)
