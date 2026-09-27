"""Les conditions de départ : fabriquer des galaxies et les lancer l'une vers l'autre."""

import numpy as np

from .simulation import Univers

BLEU = (0.55, 0.72, 1.0)
OR = (1.0, 0.78, 0.45)
BLANC = (1.0, 0.95, 0.85)


def rotation(inclinaison, orientation):
    """Matrice qui incline le disque de `inclinaison` degrés puis le tourne de `orientation` degrés."""
    i, w = np.radians(inclinaison), np.radians(orientation)
    rx = np.array([[1, 0, 0], [0, np.cos(i), -np.sin(i)], [0, np.sin(i), np.cos(i)]])
    rz = np.array([[np.cos(w), -np.sin(w), 0], [np.sin(w), np.cos(w), 0], [0, 0, 1]])
    return rz @ rx


def disque_toomre(rng, nb_etoiles, masse_centre, rayon, douceur, sens=1):
    """Un disque d'étoiles « tests » (sans masse) en orbite circulaire autour d'un noyau massif.

    C'est l'astuce des frères Toomre (1972) : seuls les noyaux attirent. Les étoiles se contentent
    de suivre la gravité, ce qui permet d'en simuler des dizaines de milliers très vite.
    """
    # Un disque (de 0,1 R à R) et un bulbe d'étoiles serrées au centre, comme dans une vraie galaxie.
    r = rayon * (0.1 + 0.9 * np.sqrt(rng.random(nb_etoiles)))
    bulbe = rng.random(nb_etoiles) < 0.2
    r[bulbe] = rayon * 0.25 * rng.random(bulbe.sum()) ** 1.5 + 0.02
    angle = 2 * np.pi * rng.random(nb_etoiles)
    positions = np.stack([r * np.cos(angle), r * np.sin(angle), rng.normal(0, 0.01 * rayon, nb_etoiles)], axis=1)
    # Vitesse circulaire autour d'une masse adoucie : v² = G·M·r² / (r² + ε²)^(3/2)
    v = np.sqrt(masse_centre * r ** 2 / (r ** 2 + douceur ** 2) ** 1.5)
    vitesses = sens * np.stack([-v * np.sin(angle), v * np.cos(angle), np.zeros(nb_etoiles)], axis=1)
    return positions, vitesses


def orbite_parabolique(masse_totale, pericentre, distance):
    """Position et vitesse relatives de deux galaxies sur une orbite parabolique (juste assez rapides pour se croiser)."""
    mu = masse_totale
    moment = np.sqrt(2 * mu * pericentre)
    anomalie = -np.arccos(2 * pericentre / distance - 1)  # on part avant le passage au plus près
    position = distance * np.array([np.cos(anomalie), np.sin(anomalie), 0.0])
    radiale, tangentielle = mu / moment * np.sin(anomalie), moment / distance
    vitesse = radiale * np.array([np.cos(anomalie), np.sin(anomalie), 0]) + \
        tangentielle * np.array([-np.sin(anomalie), np.cos(anomalie), 0])
    return position, vitesse


def collision(nb_etoiles=40000, graine=1, inclinaisons=((15, 0), (60, -30)), rapport_masses=1.0,
              pericentre=1.4, distance=8.0, sens=(1, 1)):
    """Deux galaxies spirales se frôlent : des « queues de marée » et un pont d'étoiles apparaissent."""
    rng = np.random.default_rng(graine)
    masses_noyaux = np.array([1.0, rapport_masses])
    douceur = 0.1
    relatif_pos, relatif_vit = orbite_parabolique(masses_noyaux.sum(), pericentre, distance)
    # Chaque galaxie se place par rapport au centre de gravité commun.
    parts = [-masses_noyaux[1] / masses_noyaux.sum(), masses_noyaux[0] / masses_noyaux.sum()]

    positions, vitesses, masses, couleurs, lumieres = [], [], [], [], []
    nombres = [int(nb_etoiles * masses_noyaux[0] / masses_noyaux.sum()), 0]
    nombres[1] = nb_etoiles - nombres[0]
    for g in range(2):
        centre, elan = parts[g] * relatif_pos, parts[g] * relatif_vit
        p, v = disque_toomre(rng, nombres[g], masses_noyaux[g], rayon=1.0 * masses_noyaux[g] ** 0.5,
                             douceur=douceur, sens=sens[g])
        tourne = rotation(*inclinaisons[g])
        positions += [centre[None], centre + p @ tourne.T]
        vitesses += [elan[None], elan + v @ tourne.T]
        masses += [[masses_noyaux[g]], np.zeros(nombres[g])]
        teinte = BLEU if g == 0 else OR
        couleurs += [[BLANC], np.tile(teinte, (nombres[g], 1))]
        lumieres += [[25.0], np.ones(nombres[g])]
    return Univers(np.concatenate(positions), np.concatenate(vitesses), np.concatenate(masses).astype(float),
                   np.concatenate(couleurs).astype(float), douceur=douceur, methode="directe",
                   luminosite=np.concatenate(lumieres).astype(float))


def spirale(nb_etoiles=25000, graine=2, masse_disque=0.6, v_halo=0.8, coeur_halo=0.6, agitation=0.15):
    """Un disque d'étoiles qui s'attirent toutes entre elles (Barnes-Hut), dans un halo de matière noire.

    Le disque est assez « froid » (les étoiles tournent presque en cercle) : de petites irrégularités
    s'amplifient d'elles-mêmes et des bras spiraux se forment, se cassent et se reforment.
    """
    rng = np.random.default_rng(graine)
    echelle = 0.8
    # Disque exponentiel : la densité d'étoiles diminue avec la distance au centre.
    r = rng.gamma(2.0, echelle / 2, nb_etoiles) + 0.05
    r = np.minimum(r, 3.5 * echelle)
    angle = 2 * np.pi * rng.random(nb_etoiles)
    epaisseur = 0.03
    positions = np.stack([r * np.cos(angle), r * np.sin(angle), rng.normal(0, epaisseur, nb_etoiles)], axis=1)
    masses = np.full(nb_etoiles, masse_disque / nb_etoiles)

    # Vitesse circulaire exacte : on mesure la vraie attraction (disque + halo) au départ, en moyenne par
    # anneau, puis v² = r × attraction vers le centre. Ainsi le disque démarre en équilibre.
    univers = Univers(positions, np.zeros_like(positions), masses, np.zeros_like(positions), douceur=0.04,
                      methode="barnes-hut", theta=0.5, halo=(v_halo, coeur_halo))
    acc = univers.accelerations()
    vers_centre = -(acc[:, 0] * np.cos(angle) + acc[:, 1] * np.sin(angle))
    anneaux = np.linspace(0, r.max() + 1e-9, 41)
    numero = np.digitize(r, anneaux) - 1
    moyenne = np.bincount(numero, vers_centre, minlength=40) / np.maximum(np.bincount(numero, minlength=40), 1)
    milieux = (anneaux[:-1] + anneaux[1:]) / 2
    v = np.sqrt(np.maximum(r * np.interp(r, milieux, moyenne), 0.0))
    # Un peu de vitesse désordonnée : trop peu, le disque se brise en amas ; trop, il reste lisse.
    vitesses = np.stack([-v * np.sin(angle), v * np.cos(angle), np.zeros(nb_etoiles)], axis=1)
    vitesses += rng.normal(0, 1, (nb_etoiles, 3)) * (agitation * v)[:, None] * np.array([1, 1, 0.3])

    melange = np.clip(r / (3 * echelle), 0, 1)[:, None]
    couleurs = (1 - melange) * np.array(OR) + melange * np.array(BLEU)  # cœur doré, bords bleus
    return Univers(positions, vitesses, masses, couleurs, douceur=0.04, methode="barnes-hut", theta=0.8,
                   halo=(v_halo, coeur_halo))


def amas(nb_etoiles=4000, graine=3):
    """Une boule d'étoiles immobiles s'effondre sur elle-même puis rebondit (« relaxation violente »)."""
    rng = np.random.default_rng(graine)
    direction = rng.normal(size=(nb_etoiles, 3))
    direction /= np.linalg.norm(direction, axis=1, keepdims=True)
    positions = direction * rng.random(nb_etoiles)[:, None] ** (1 / 3) * 2.0
    vitesses = rng.normal(0, 0.05, (nb_etoiles, 3))
    couleurs = np.tile(BLANC, (nb_etoiles, 1)) * (0.7 + 0.3 * rng.random((nb_etoiles, 1)))
    return Univers(positions, vitesses, np.full(nb_etoiles, 1.0 / nb_etoiles), couleurs, douceur=0.03, methode="auto")


SCENES = {
    "collision": (collision, dict(dt=0.01, pas=1700, champ=12.0, vue=(20, 35))),
    "spirale": (spirale, dict(dt=0.01, pas=1200, champ=6.0, vue=(90, 0))),
    "amas": (amas, dict(dt=0.01, pas=600, champ=5.0, vue=(20, 30))),
}
