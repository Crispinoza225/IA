"""Mesurer le texte. La mise en page a besoin de savoir quelle largeur occupe chaque mot.

Deux versions : l'une utilise Tkinter (pour la fenêtre du navigateur), l'autre Pillow
(pour produire des captures d'écran en PNG sans écran).
"""

import os


class PolicesTk:
    FAMILLES = {"sans-serif": "Helvetica", "serif": "Times", "monospace": "Courier"}

    def __init__(self):
        import tkinter.font
        self._font = tkinter.font
        self._cache = {}

    def police(self, police):
        if police not in self._cache:
            famille, taille, gras, italique = police
            self._cache[police] = self._font.Font(
                family=self.FAMILLES[famille], size=-taille,  # taille négative = en pixels
                weight="bold" if gras else "normal", slant="italic" if italique else "roman")
        return self._cache[police]

    def mesurer(self, police, texte):
        return self.police(police).measure(texte)

    def metriques(self, police):
        p = self.police(police)
        return p.metrics("ascent"), p.metrics("descent")


FICHIERS_POLICES = {
    # (famille, gras, italique) : fichiers possibles, du plus probable au moins probable
    ("sans-serif", False, False): ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "arial.ttf", "Arial.ttf"],
    ("sans-serif", True, False): ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"],
    ("sans-serif", False, True): ["DejaVuSans-Oblique.ttf", "LiberationSans-Italic.ttf", "ariali.ttf", "Arial Italic.ttf"],
    ("sans-serif", True, True): ["DejaVuSans-BoldOblique.ttf", "LiberationSans-BoldItalic.ttf", "arialbi.ttf"],
    ("serif", False, False): ["DejaVuSerif.ttf", "LiberationSerif-Regular.ttf", "times.ttf", "Times New Roman.ttf"],
    ("serif", True, False): ["DejaVuSerif-Bold.ttf", "LiberationSerif-Bold.ttf", "timesbd.ttf"],
    ("serif", False, True): ["DejaVuSerif-Italic.ttf", "LiberationSerif-Italic.ttf", "timesi.ttf"],
    ("serif", True, True): ["DejaVuSerif-BoldItalic.ttf", "LiberationSerif-BoldItalic.ttf", "timesbi.ttf"],
    ("monospace", False, False): ["DejaVuSansMono.ttf", "LiberationMono-Regular.ttf", "cour.ttf", "Courier New.ttf"],
    ("monospace", True, False): ["DejaVuSansMono-Bold.ttf", "LiberationMono-Bold.ttf", "courbd.ttf"],
    ("monospace", False, True): ["DejaVuSansMono-Oblique.ttf", "LiberationMono-Italic.ttf", "couri.ttf"],
    ("monospace", True, True): ["DejaVuSansMono-BoldOblique.ttf", "LiberationMono-BoldItalic.ttf", "courbi.ttf"],
}
DOSSIERS_POLICES = ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"),
                    "/Library/Fonts", "/System/Library/Fonts", "C:\\Windows\\Fonts"]


def trouver_fichiers_polices():
    """Parcourt une seule fois les dossiers de polices du système."""
    trouves = {}
    for dossier in DOSSIERS_POLICES:
        for racine, _, fichiers in os.walk(dossier):
            for fichier in fichiers:
                trouves.setdefault(fichier, os.path.join(racine, fichier))
    return trouves


class PolicesPillow:
    def __init__(self):
        from PIL import ImageFont
        self._image_font = ImageFont
        self._fichiers = trouver_fichiers_polices()
        self._cache = {}

    def police(self, police):
        if police not in self._cache:
            famille, taille, gras, italique = police
            for nom in FICHIERS_POLICES[(famille, gras, italique)] + FICHIERS_POLICES[(famille, False, False)]:
                if nom in self._fichiers:
                    self._cache[police] = self._image_font.truetype(self._fichiers[nom], taille)
                    break
            else:
                self._cache[police] = self._image_font.load_default(taille)
        return self._cache[police]

    def mesurer(self, police, texte):
        return self.police(police).getlength(texte)

    def metriques(self, police):
        return self.police(police).getmetrics()
