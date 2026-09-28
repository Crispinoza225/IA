"""Dessiner une page dans une image PNG (avec Pillow), sans ouvrir de fenêtre."""

from .mise_en_page import DessinLigne, DessinRect, DessinTexte, Disposition
from .page import charger
from .polices import PolicesPillow


def capturer(adresse, chemin, largeur=1000, hauteur=None):
    """Enregistre une capture de la page. hauteur=None : toute la page, du haut jusqu'en bas."""
    from PIL import Image, ImageDraw

    polices = PolicesPillow()
    page = charger(adresse)
    disposition = Disposition(page.arbre, polices, largeur)
    hauteur = hauteur or max(1, int(disposition.hauteur) + 1)
    image = Image.new("RGB", (largeur, hauteur), disposition.fond)
    dessin = ImageDraw.Draw(image)
    for ordre in disposition.dessins:
        if isinstance(ordre, DessinRect):
            if ordre.x2 > ordre.x1 and ordre.y2 > ordre.y1:
                dessin.rectangle([ordre.x1, ordre.y1, ordre.x2 - 1, ordre.y2 - 1], fill=ordre.couleur)
        elif isinstance(ordre, DessinTexte):
            dessin.text((ordre.x, ordre.y), ordre.texte, font=polices.police(ordre.police), fill=ordre.couleur)
        elif isinstance(ordre, DessinLigne):
            dessin.line([ordre.x1, ordre.y1, ordre.x2, ordre.y2], fill=ordre.couleur, width=round(ordre.epaisseur))
    image.save(chemin)
    return page
