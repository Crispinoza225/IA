"""Faire avancer le temps : l'intégrateur « saute-mouton » (leapfrog).

À chaque pas : demi-coup de vitesse, déplacement complet, nouveau calcul des forces, demi-coup de
vitesse. Cette méthode toute simple a une propriété précieuse : l'énergie totale ne dérive pas au fil
des milliers de pas, et les orbites restent fermées au lieu de spiraler vers le centre ou vers l'infini.
"""

from dataclasses import dataclass, field

import numpy as np

from .gravite import acceleration


@dataclass
class Univers:
    positions: np.ndarray
    vitesses: np.ndarray
    masses: np.ndarray
    couleurs: np.ndarray            # couleur de chaque particule (pour le rendu), valeurs entre 0 et 1
    douceur: float = 0.05
    methode: str = "auto"           # "directe", "barnes-hut" ou "auto"
    theta: float = 0.7
    halo: tuple = None              # (vitesse, rayon de cœur) : halo de matière noire fixe, ou None
    temps: float = 0.0
    luminosite: np.ndarray = field(default=None)  # poids de chaque particule dans l'image

    def __post_init__(self):
        if self.luminosite is None:
            self.luminosite = np.ones(len(self.positions))
        self._acc = None

    def accelerations(self):
        acc = acceleration(self.positions, self.masses, self.douceur, self.methode, self.theta)
        if self.halo is not None:
            # Halo « logarithmique » : il fait tourner les étoiles à vitesse presque constante,
            # comme la matière noire le fait dans les vraies galaxies spirales.
            v0, coeur = self.halo
            r2 = np.einsum("ik,ik->i", self.positions, self.positions)
            acc -= (v0 ** 2 / (r2 + coeur ** 2))[:, None] * self.positions
        return acc

    def pas(self, dt):
        if self._acc is None:
            self._acc = self.accelerations()
        self.vitesses += 0.5 * dt * self._acc
        self.positions += dt * self.vitesses
        self._acc = self.accelerations()
        self.vitesses += 0.5 * dt * self._acc
        self.temps += dt

    def energie(self):
        """Énergie cinétique + potentielle (calcul exact, pour vérifier la simulation sur de petits systèmes)."""
        cinetique = 0.5 * np.sum(self.masses * np.einsum("ik,ik->i", self.vitesses, self.vitesses))
        pesantes = self.masses > 0
        p, m = self.positions[pesantes], self.masses[pesantes]
        d = p[:, None, :] - p[None, :, :]
        r = np.sqrt(np.einsum("ijk,ijk->ij", d, d) + self.douceur ** 2)
        potentielle = -np.sum(np.triu(m[:, None] * m[None, :] / r, 1))  # chaque paire comptée une fois
        return cinetique + potentielle

    def quantite_de_mouvement(self):
        return np.sum(self.masses[:, None] * self.vitesses, axis=0)
