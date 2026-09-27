"""Les réglages de mise en forme d'un mémoire, et les normes prêtes à l'emploi."""

from dataclasses import asdict, dataclass, field, fields

POLICES = ["Times New Roman", "Arial", "Calibri", "Garamond", "Georgia", "Cambria"]
ALIGNEMENTS = {"justifie": "Justifié", "gauche": "À gauche"}
NUMEROTATIONS = {
    "decimale": "1. / 1.1. / 1.1.1.",
    "romaine": "I. / A. / 1.",
    "aucune": "Sans numéro",
}
POSITIONS_PAGINATION = {"centre": "En bas, au centre", "droite": "En bas, à droite", "aucune": "Pas de numéro"}


@dataclass
class PageDeGarde:
    afficher: bool = True
    universite: str = ""
    faculte: str = ""
    type_document: str = "Mémoire de Master"
    titre: str = "Titre du mémoire"
    sous_titre: str = ""
    auteur: str = ""
    directeur: str = ""
    annee: str = ""


@dataclass
class Reglages:
    police: str = "Times New Roman"
    taille: float = 12            # points
    interligne: float = 1.5       # 1 = simple, 1.5 = une ligne et demie, 2 = double
    alignement: str = "justifie"
    retrait: float = 1.25         # retrait de première ligne des paragraphes, en cm
    espace_apres: float = 6       # espace après chaque paragraphe, en points
    marge_haut: float = 2.5       # en cm
    marge_bas: float = 2.5
    marge_gauche: float = 3.0     # plus large à gauche, pour la reliure
    marge_droite: float = 2.5
    numerotation: str = "decimale"
    prefixe_chapitre: str = ""    # par exemple « Chapitre » → « Chapitre 1. Titre »
    tailles_titres: tuple = (16, 14, 12)
    couleur_titres: str = "#000000"
    chapitre_nouvelle_page: bool = True
    sommaire: bool = True
    titre_sommaire: str = "Sommaire"
    profondeur_sommaire: int = 3
    pagination: str = "centre"
    garde: PageDeGarde = field(default_factory=PageDeGarde)

    def vers_dict(self):
        return asdict(self)

    @classmethod
    def depuis_dict(cls, donnees):
        """Construit des réglages à partir d'un dictionnaire (venu du navigateur), en ignorant les clés inconnues
        et en ramenant les valeurs dans des limites raisonnables."""
        donnees = dict(donnees or {})
        garde, valeurs_garde = PageDeGarde(), donnees.get("garde") or {}
        for f in fields(PageDeGarde):
            if f.name in valeurs_garde:
                valeur = valeurs_garde[f.name]
                setattr(garde, f.name, bool(valeur) if f.type is bool else str(valeur)[:300])
        reglages = cls(garde=garde)
        for f in fields(cls):
            if f.name == "garde" or f.name not in donnees:
                continue
            defaut = getattr(reglages, f.name)
            valeur = donnees[f.name]
            try:
                if isinstance(defaut, bool):
                    valeur = bool(valeur)
                elif isinstance(defaut, (int, float)):
                    valeur = type(defaut)(float(valeur))
                elif isinstance(defaut, tuple):
                    valeur = tuple(float(v) for v in valeur)[:3]
                    valeur = valeur + defaut[len(valeur):]
                else:
                    valeur = str(valeur)
            except (TypeError, ValueError):
                continue
            setattr(reglages, f.name, valeur)
        return reglages.valide()

    def valide(self):
        borne = lambda v, a, b: min(max(v, a), b)  # noqa: E731
        self.taille = borne(self.taille, 8, 20)
        self.interligne = borne(self.interligne, 1.0, 3.0)
        self.retrait = borne(self.retrait, 0, 5)
        self.espace_apres = borne(self.espace_apres, 0, 36)
        for nom in ("marge_haut", "marge_bas", "marge_gauche", "marge_droite"):
            setattr(self, nom, borne(getattr(self, nom), 0.5, 6))
        self.tailles_titres = tuple(borne(t, 8, 36) for t in self.tailles_titres)
        self.profondeur_sommaire = int(borne(self.profondeur_sommaire, 1, 3))
        if self.police not in POLICES:
            self.police = "Times New Roman"
        if self.alignement not in ALIGNEMENTS:
            self.alignement = "justifie"
        if self.numerotation not in NUMEROTATIONS:
            self.numerotation = "decimale"
        if self.pagination not in POSITIONS_PAGINATION:
            self.pagination = "centre"
        if not (len(self.couleur_titres) == 7 and self.couleur_titres.startswith("#")):
            self.couleur_titres = "#000000"
        return self


NORMES = {
    "universite": ("Université (standard français)", {}),
    "apa": ("APA 7ᵉ édition", dict(police="Times New Roman", taille=12, interligne=2.0, alignement="gauche",
                                   retrait=1.27, espace_apres=0, marge_haut=2.54, marge_bas=2.54, marge_gauche=2.54,
                                   marge_droite=2.54, numerotation="aucune", tailles_titres=(12, 12, 12),
                                   pagination="droite", titre_sommaire="Table des matières")),
    "sobre": ("Moderne et sobre", dict(police="Calibri", taille=11, interligne=1.15, alignement="justifie",
                                       retrait=0, espace_apres=8, marge_gauche=2.5, numerotation="decimale",
                                       tailles_titres=(18, 14, 12), couleur_titres="#1f3864")),
    "plan_francais": ("Plan à la française (I. A. 1.)", dict(numerotation="romaine", prefixe_chapitre="",
                                                             tailles_titres=(15, 13, 12))),
}


def norme(nom):
    _, valeurs = NORMES.get(nom, NORMES["universite"])
    return Reglages.depuis_dict(valeurs)
