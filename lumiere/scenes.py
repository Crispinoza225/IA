"""Scènes prêtes à rendre. Copie-en une et modifie-la pour créer la tienne !"""

import random

from .scene import Camera, Quad, Scene, Sphere, boite, damier, diffus, lumiere, metal, verre


def billes():
    """Des dizaines de billes en verre, en métal et mates sur un damier, sous le ciel."""
    rng = random.Random(4)
    scene = Scene(camera=Camera(position=(13, 2, 3), cible=(0, 0.6, 0), champ=20, ouverture=0.12, mise_au_point=10))
    scene.ajouter(Sphere((0, -1000, 0), 1000, damier((0.2, 0.3, 0.1), (0.9, 0.9, 0.9), taille=1.0)))

    grandes = [((0, 1, 0), verre(1.5)), ((-4, 1, 0), diffus((0.4, 0.2, 0.1))), ((4, 1, 0), metal((0.7, 0.6, 0.5)))]
    for centre, materiau in grandes:
        scene.ajouter(Sphere(centre, 1.0, materiau))

    for a in range(-6, 6):
        for b in range(-5, 5):
            centre = (a + 0.9 * rng.random(), 0.2, b + 0.9 * rng.random())
            if any((centre[0] - c[0]) ** 2 + (centre[2] - c[2]) ** 2 < 1.3 ** 2 for c, _ in grandes):
                continue
            tirage = rng.random()
            if tirage < 0.7:
                couleur = tuple(rng.random() * rng.random() for _ in range(3))
                materiau = diffus(couleur)
            elif tirage < 0.9:
                materiau = metal(tuple(0.5 + rng.random() / 2 for _ in range(3)), flou=rng.random() / 2)
            else:
                materiau = verre(1.5)
            scene.ajouter(Sphere(centre, 0.2, materiau))
    return scene


def boite_de_cornell():
    """La « boîte de Cornell » : la scène de référence des chercheurs en rendu depuis 1984.

    Une seule lampe au plafond éclaire tout : regarde les ombres douces, le rouge et le vert
    des murs qui déteignent sur les objets blancs, et la lumière concentrée par la sphère de verre.
    """
    rouge, vert, blanc = diffus((0.65, 0.05, 0.05)), diffus((0.12, 0.45, 0.15)), diffus((0.73, 0.73, 0.73))
    scene = Scene(camera=Camera(position=(278, 278, -800), cible=(278, 278, 0), champ=40),
                  ciel_haut=(0, 0, 0), ciel_bas=(0, 0, 0))
    scene.ajouter(
        Quad((555, 0, 0), (0, 555, 0), (0, 0, 555), vert),
        Quad((0, 0, 0), (0, 555, 0), (0, 0, 555), rouge),
        Quad((0, 0, 0), (555, 0, 0), (0, 0, 555), blanc),         # sol
        Quad((555, 555, 555), (-555, 0, 0), (0, 0, -555), blanc),  # plafond
        Quad((0, 0, 555), (555, 0, 0), (0, 555, 0), blanc),        # fond
        Quad((378, 554.9, 382), (-200, 0, 0), (0, 0, -170), lumiere((1.0, 0.85, 0.6), 7)),
        boite((347, 0, 377), (165, 330, 165), blanc, angle=15),
        Sphere((190, 90, 190), 90, verre(1.5)),
        Sphere((420, 50, 120), 50, metal((0.9, 0.9, 0.9), flou=0.05)),
    )
    return scene


def nuit():
    """Une scène nocturne éclairée uniquement par des sphères lumineuses colorées."""
    scene = Scene(camera=Camera(position=(0, 1.6, 7), cible=(0, 0.8, 0), champ=35, ouverture=0.05, mise_au_point=7),
                  ciel_haut=(0.01, 0.01, 0.03), ciel_bas=(0.0, 0.0, 0.0))
    scene.ajouter(
        Sphere((0, -1000, 0), 1000, damier((0.35, 0.35, 0.35), (0.05, 0.05, 0.05), taille=0.8)),
        Sphere((-2.4, 0.5, -0.5), 0.5, lumiere((1.0, 0.35, 0.1), 6)),
        Sphere((2.4, 0.5, -0.5), 0.5, lumiere((0.1, 0.4, 1.0), 6)),
        Sphere((0, 3.5, -3), 0.8, lumiere((1.0, 0.9, 0.8), 5)),
        Sphere((-0.9, 0.8, 0.4), 0.8, verre(1.5)),
        Sphere((1.0, 0.8, -0.2), 0.8, metal((0.9, 0.85, 0.8), flou=0.0)),
        Sphere((0.1, 0.3, 1.8), 0.3, diffus((0.8, 0.8, 0.8))),
        boite((0, 0, -2.2), (1.2, 1.4, 0.4), diffus((0.6, 0.6, 0.6)), angle=10),
    )
    return scene


SCENES = {
    "billes": billes,
    "cornell": boite_de_cornell,
    "nuit": nuit,
}
