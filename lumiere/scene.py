"""Description d'une scène 3D : des objets, leurs matériaux, une caméra et un ciel."""

import math
from dataclasses import dataclass, field

import numpy as np

# --- Matériaux --------------------------------------------------------------

DIFFUS, METAL, VERRE, LUMIERE = range(4)


@dataclass
class Materiau:
    type: int = DIFFUS
    couleur: tuple = (0.8, 0.8, 0.8)
    flou: float = 0.0             # métal : 0 = miroir parfait, 1 = métal brossé
    indice: float = 1.5           # verre : indice de réfraction (eau 1.33, verre 1.5, diamant 2.4)
    emission: tuple = (0.0, 0.0, 0.0)
    couleur_damier: tuple = None  # si présent, la surface est un damier de deux couleurs
    taille_damier: float = 1.0


def diffus(couleur):
    """Surface mate (plâtre, bois, tissu) : renvoie la lumière dans toutes les directions."""
    return Materiau(DIFFUS, couleur)


def metal(couleur, flou=0.0):
    """Surface métallique : réfléchit la lumière comme un miroir, plus ou moins flou."""
    return Materiau(METAL, couleur, flou=min(flou, 1.0))


def verre(indice=1.5, couleur=(1.0, 1.0, 1.0)):
    """Matière transparente : la lumière la traverse en étant déviée (réfraction) ou se reflète."""
    return Materiau(VERRE, couleur, indice=indice)


def lumiere(couleur=(1.0, 1.0, 1.0), intensite=4.0):
    """Objet qui émet de la lumière : c'est lui qui éclaire la scène."""
    return Materiau(LUMIERE, (0.0, 0.0, 0.0), emission=tuple(c * intensite for c in couleur))


def damier(couleur1, couleur2, taille=1.0):
    return Materiau(DIFFUS, couleur1, couleur_damier=couleur2, taille_damier=taille)


# --- Objets -----------------------------------------------------------------

@dataclass
class Sphere:
    centre: tuple
    rayon: float
    materiau: Materiau


@dataclass
class Quad:
    """Un parallélogramme : un coin et deux côtés. Parfait pour les murs, sols et lampes."""
    coin: tuple
    u: tuple
    v: tuple
    materiau: Materiau


def boite(centre, taille, materiau, angle=0.0):
    """Une boîte posée sur le sol, tournée de `angle` degrés autour de l'axe vertical. Renvoie 6 quads."""
    cx, cy, cz = centre
    lx, ly, lz = taille
    a = math.radians(angle)
    ex = np.array([math.cos(a), 0.0, -math.sin(a)]) * lx
    ey = np.array([0.0, ly, 0.0])
    ez = np.array([math.sin(a), 0.0, math.cos(a)]) * lz
    o = np.array([cx, cy, cz]) - ex / 2 - ez / 2  # coin inférieur
    milieu = o + (ex + ey + ez) / 2
    quads = []
    for c, u, v in [(o, ex, ey), (o + ez, ex, ey), (o, ey, ez), (o + ex, ey, ez), (o, ex, ez), (o + ey, ex, ez)]:
        # La normale (u × v) doit pointer vers l'extérieur : important pour une boîte en verre.
        if np.dot(np.cross(u, v), c + (u + v) / 2 - milieu) < 0:
            u, v = v, u
        quads.append(Quad(tuple(c), tuple(u), tuple(v), materiau))
    return quads


# --- Caméra et scène --------------------------------------------------------

@dataclass
class Camera:
    position: tuple = (0.0, 0.0, 0.0)
    cible: tuple = (0.0, 0.0, -1.0)
    haut: tuple = (0.0, 1.0, 0.0)
    champ: float = 40.0         # angle de vue vertical, en degrés
    ouverture: float = 0.0      # > 0 : flou de profondeur, comme un vrai objectif photo
    mise_au_point: float = None  # distance nette (par défaut : la cible)


@dataclass
class Scene:
    objets: list = field(default_factory=list)
    camera: Camera = field(default_factory=Camera)
    ciel_haut: tuple = (0.5, 0.7, 1.0)  # couleur du ciel vers le haut ((0, 0, 0) : nuit noire)
    ciel_bas: tuple = (1.0, 1.0, 1.0)

    def ajouter(self, *objets):
        for objet in objets:
            if isinstance(objet, list):
                self.objets.extend(objet)
            else:
                self.objets.append(objet)
        return self
