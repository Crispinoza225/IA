"""Le calcul de la gravité : l'accélération que chaque étoile subit à cause de toutes les autres.

Loi de Newton (avec G = 1) : a = Σ m · d / |d|³, où d va de l'étoile vers chaque autre masse.
On ajoute un petit « adoucissement » ε (|d|² + ε²) pour que deux étoiles très proches ne
s'envoient pas à l'infini : dans une vraie galaxie, les collisions entre étoiles n'arrivent jamais.

Deux méthodes :
  - directe : exacte, mais le nombre de calculs grandit comme N² (4 fois plus pour 2 fois plus d'étoiles) ;
  - Barnes-Hut : un groupe d'étoiles lointaines est remplacé par une seule masse placée en son
    centre de gravité. Le nombre de calculs grandit comme N·log N : on peut simuler bien plus d'étoiles.
"""

import numpy as np


def inverse_cube(r2):
    """1 / r³ à partir de r², avec 0 quand r = 0 : une étoile ne s'attire pas elle-même."""
    resultat = np.zeros_like(r2)
    np.divide(1.0, r2 * np.sqrt(r2), out=resultat, where=r2 > 0)
    return resultat


def acceleration_directe(sources, masses, cibles, douceur, taille_paquet=1024):
    """Accélération subie par chaque cible, due à toutes les sources (calcul exact)."""
    acc = np.zeros_like(cibles)
    for debut in range(0, len(cibles), taille_paquet):
        paquet = cibles[debut:debut + taille_paquet]
        d = sources[None, :, :] - paquet[:, None, :]          # (paquet, sources, 3)
        r2 = np.einsum("psk,psk->ps", d, d) + douceur ** 2
        facteur = inverse_cube(r2) * masses[None, :]          # m / r³
        acc[debut:debut + taille_paquet] = np.einsum("ps,psk->pk", facteur, d)
    return acc


# --- Barnes-Hut -----------------------------------------------------------------------

def code_morton(cellules, niveaux):
    """Entrelace les bits de (x, y, z) : les cellules voisines dans l'espace ont des codes voisins.

    Avec ce code, les étoiles d'un même cube de l'octree se suivent une fois triées, et le cube
    parent d'un code s'obtient en retirant 3 bits : code >> 3.
    """
    code = np.zeros(len(cellules), dtype=np.int64)
    for bit in range(niveaux):
        for axe in range(3):
            code |= ((cellules[:, axe] >> bit) & 1) << (3 * bit + axe)
    return code


class Octree:
    """Un arbre qui découpe l'espace en 8 cubes, puis chaque cube en 8, etc.

    Pour chaque niveau, on range : les codes des cubes non vides, leur masse totale, leur centre
    de gravité, leur nombre d'étoiles, et où trouver leurs 8 enfants au niveau suivant.
    """

    def __init__(self, positions, masses, niveaux=16):
        self.niveaux = niveaux
        mini = positions.min(axis=0)
        cote = float((positions.max(axis=0) - mini).max()) * 1.0001 + 1e-9
        nb_cellules = 1 << niveaux
        cellules = np.clip(((positions - mini) / cote * nb_cellules).astype(np.int64), 0, nb_cellules - 1)
        codes = code_morton(cellules, niveaux)
        ordre = np.argsort(codes, kind="stable")
        codes, pos, m = codes[ordre], positions[ordre], masses[ordre]

        self.etages = []
        for niveau in range(niveaux + 1):
            cles = codes >> (3 * (niveaux - niveau))
            nouveau = np.empty(len(cles), dtype=bool)
            nouveau[0] = True
            nouveau[1:] = cles[1:] != cles[:-1]
            groupe = np.cumsum(nouveau) - 1
            masse = np.bincount(groupe, m)
            poids = np.where(masse > 0, masse, 1.0)
            centre = np.stack([np.bincount(groupe, m * pos[:, k]) for k in range(3)], axis=1) / poids[:, None]
            self.etages.append({
                "cles": cles[nouveau],
                "masse": masse,
                "centre": centre,
                "nombre": np.bincount(groupe),
                "cote": cote / (1 << niveau),
            })
        # Les enfants d'un cube sont rangés à la suite au niveau suivant : on note où ils commencent et finissent.
        for niveau in range(niveaux):
            cles, suivantes = self.etages[niveau]["cles"], self.etages[niveau + 1]["cles"]
            self.etages[niveau]["debut"] = np.searchsorted(suivantes, cles << 3)
            self.etages[niveau]["fin"] = np.searchsorted(suivantes, (cles + 1) << 3)

    def acceleration(self, cibles, douceur, theta=0.7, taille_paquet=4096):
        """Parcourt l'arbre pour toutes les cibles à la fois (vectorisé avec NumPy).

        Un cube est « assez loin » si  côté / distance < θ : on utilise alors sa masse totale.
        Sinon on l'ouvre et on regarde ses enfants. θ = 0 donne le calcul exact ; θ = 1 va très vite.
        """
        acc = np.zeros_like(cibles)
        for debut in range(0, len(cibles), taille_paquet):
            paquet = cibles[debut:debut + taille_paquet]
            n = len(paquet)
            etoile = np.arange(n)
            noeud = np.zeros(n, dtype=np.int64)  # tout le monde commence à la racine
            resultat = np.zeros((n, 3))
            for niveau, etage in enumerate(self.etages):
                if not len(etoile):
                    break
                d = etage["centre"][noeud] - paquet[etoile]
                r2 = np.einsum("ik,ik->i", d, d)
                dernier = niveau == self.niveaux
                accepte = dernier | (etage["nombre"][noeud] == 1) | (etage["cote"] ** 2 < theta ** 2 * r2)
                if accepte.any():
                    e, nd, dd = etoile[accepte], noeud[accepte], d[accepte]
                    r2d = r2[accepte] + douceur ** 2
                    facteur = etage["masse"][nd] * inverse_cube(r2d)
                    for k in range(3):
                        resultat[:, k] += np.bincount(e, facteur * dd[:, k], minlength=n)
                if dernier:
                    break
                # Les cubes trop proches sont ouverts : chaque couple (étoile, cube) devient (étoile, enfant).
                etoile, noeud = etoile[~accepte], noeud[~accepte]
                premier, nombre = etage["debut"][noeud], etage["fin"][noeud] - etage["debut"][noeud]
                etoile = np.repeat(etoile, nombre)
                decalage = np.arange(nombre.sum()) - np.repeat(np.cumsum(nombre) - nombre, nombre)
                noeud = np.repeat(premier, nombre) + decalage
            acc[debut:debut + n] = resultat
        return acc


def acceleration(positions, masses, douceur, methode="auto", theta=0.7):
    """Accélération de toutes les particules. Les particules de masse nulle subissent la gravité sans en créer."""
    pesantes = masses > 0
    sources, masses_sources = positions[pesantes], masses[pesantes]
    if not len(sources):
        return np.zeros_like(positions)
    if methode == "auto":
        methode = "directe" if len(sources) * len(positions) < 4e7 else "barnes-hut"
    if methode == "directe":
        return acceleration_directe(sources, masses_sources, positions, douceur)
    return Octree(sources, masses_sources).acceleration(positions, douceur, theta)
