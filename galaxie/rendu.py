"""Transformer des positions d'étoiles en une belle image : projection, accumulation de lumière, halo."""

import numpy as np


def matrice_vue(elevation, azimut):
    """Rotation qui place la caméra à `elevation` degrés au-dessus du plan, tournée de `azimut` degrés."""
    e, a = np.radians(elevation), np.radians(azimut)
    rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    # On regarde depuis l'axe z (elevation = 90) jusqu'à la tranche du disque (elevation = 0).
    rx = np.array([[1, 0, 0], [0, np.sin(e), np.cos(e)], [0, -np.cos(e), np.sin(e)]])
    return rx @ rz


def flou(image, rayon):
    """Flou rapide : trois passages d'une moyenne glissante approchent un flou gaussien."""
    if rayon < 1:
        return image
    for axe in (0, 1):
        for _ in range(3):
            cumul = np.cumsum(np.pad(image, [(rayon + 1, rayon) if a == axe else (0, 0) for a in range(3)],
                                     mode="edge"), axis=axe)
            debut = [slice(None)] * 3
            fin = [slice(None)] * 3
            debut[axe] = slice(0, -2 * rayon - 1)
            fin[axe] = slice(2 * rayon + 1, None)
            image = (cumul[tuple(fin)] - cumul[tuple(debut)]) / (2 * rayon + 1)
    return image


def dessiner(univers, largeur=640, hauteur=480, champ=8.0, vue=(30, 20), centre=(0.0, 0.0, 0.0), exposition=1.0):
    """Renvoie une image (hauteur, largeur, 3) en octets.

    champ : largeur de la zone visible, dans les unités de la simulation.
    """
    pos = (univers.positions - np.array(centre)) @ matrice_vue(*vue).T
    echelle = largeur / champ
    x = (pos[:, 0] * echelle + largeur / 2).astype(np.int64)
    y = (-pos[:, 1] * echelle + hauteur / 2).astype(np.int64)
    visible = (x >= 0) & (x < largeur) & (y >= 0) & (y < hauteur)
    pixel = y[visible] * largeur + x[visible]
    poids = univers.luminosite[visible]
    image = np.zeros((hauteur * largeur, 3))
    for k in range(3):
        image[:, k] = np.bincount(pixel, poids * univers.couleurs[visible, k], minlength=hauteur * largeur)
    image = image.reshape(hauteur, largeur, 3)

    # Normalisation : la même image doit avoir le même éclat quel que soit le nombre d'étoiles.
    densite_type = len(univers.positions) / (largeur * hauteur) * 40
    image = image / max(densite_type, 1e-9) * exposition
    # Halo lumineux autour des zones denses, comme sur les photos de galaxies à longue pose.
    lumiere = image + 0.6 * flou(image, max(1, largeur // 160)) + 0.25 * flou(image, max(2, largeur // 40))
    # Compression des fortes lumières (le cœur des galaxies) pour garder des détails partout.
    lumiere = 1 - np.exp(-lumiere * 2.0)
    fond = np.array([0.0, 0.0, 0.0015])  # presque noir, avec une pointe de bleu nuit
    image = np.clip(fond + lumiere, 0, 1) ** (1 / 2.2)
    return (image * 255 + 0.5).astype(np.uint8)
