"""Le moteur de rendu : un « path tracer », la technique utilisée pour les films d'animation.

Pour chaque pixel, on lance des rayons depuis la caméra. À chaque fois qu'un rayon touche un
objet, il rebondit dans une direction qui dépend du matériau (au hasard pour une surface mate,
en miroir pour un métal, dévié pour du verre). Quand il atteint une lumière ou le ciel, on sait
quelle couleur il ramène. En faisant la moyenne de centaines de rayons par pixel, les ombres
douces, les reflets, les caustiques et les couleurs qui « bavent » d'un mur à l'autre
apparaissent tout seuls, sans les programmer : c'est la physique de la lumière qui les crée.

Tout est calculé avec NumPy sur des milliers de rayons à la fois.
"""

import math

import numpy as np

from .scene import DIFFUS, LUMIERE, METAL, VERRE, Quad, Sphere

EPSILON = 1e-4        # distance minimale d'impact, pour qu'un rayon ne se touche pas lui-même
LUMINANCE_MAX = 20.0  # plafond par rayon, pour éviter les pixels « lucioles » trop brillants


class ScenePreparee:
    """La scène convertie en tableaux NumPy, prête pour des calculs rapides."""

    def __init__(self, scene):
        materiaux = []
        index_materiau = {}

        def numero(m):
            if id(m) not in index_materiau:
                index_materiau[id(m)] = len(materiaux)
                materiaux.append(m)
            return index_materiau[id(m)]

        spheres = [o for o in scene.objets if isinstance(o, Sphere)]
        quads = [o for o in scene.objets if isinstance(o, Quad)]

        self.centres = np.array([s.centre for s in spheres], dtype=float).reshape(-1, 3)
        self.rayons = np.array([s.rayon for s in spheres], dtype=float)
        self.mat_spheres = np.array([numero(s.materiau) for s in spheres], dtype=int)

        self.coins = np.array([q.coin for q in quads], dtype=float).reshape(-1, 3)
        self.u = np.array([q.u for q in quads], dtype=float).reshape(-1, 3)
        self.v = np.array([q.v for q in quads], dtype=float).reshape(-1, 3)
        n = np.cross(self.u, self.v)
        self.normales_quads = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        self.w = n / np.maximum(np.sum(n * n, axis=1, keepdims=True), 1e-12)
        self.plans = np.sum(self.normales_quads * self.coins, axis=1)
        self.mat_quads = np.array([numero(q.materiau) for q in quads], dtype=int)

        self.type = np.array([m.type for m in materiaux], dtype=int)
        self.couleur = np.array([m.couleur for m in materiaux], dtype=float).reshape(-1, 3)
        self.couleur_damier = np.array([m.couleur_damier or m.couleur for m in materiaux], dtype=float).reshape(-1, 3)
        self.a_damier = np.array([m.couleur_damier is not None for m in materiaux], dtype=bool)
        self.taille_damier = np.array([m.taille_damier for m in materiaux], dtype=float)
        self.flou = np.array([m.flou for m in materiaux], dtype=float)
        self.indice = np.array([m.indice for m in materiaux], dtype=float)
        self.emission = np.array([m.emission for m in materiaux], dtype=float).reshape(-1, 3)

        # Les objets lumineux, pour pouvoir viser directement les lampes (échantillonnage direct).
        self.lampes_spheres = np.flatnonzero(self.type[self.mat_spheres] == LUMIERE) if len(spheres) else np.zeros(0, int)
        self.lampes_quads = np.flatnonzero(self.type[self.mat_quads] == LUMIERE) if len(quads) else np.zeros(0, int)
        self.nb_lampes = len(self.lampes_spheres) + len(self.lampes_quads)

        self.ciel_haut = np.array(scene.ciel_haut, dtype=float)
        self.ciel_bas = np.array(scene.ciel_bas, dtype=float)
        self.camera = scene.camera


# --- Géométrie ----------------------------------------------------------------

def normaliser(v):
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def intersecter(sp, origines, directions):
    """Trouve, pour chaque rayon, l'objet le plus proche touché.

    Renvoie (distance, normale extérieure, numéro de matériau). Matériau = -1 si le rayon ne touche rien.
    Les directions doivent être de longueur 1.
    """
    n = len(origines)
    meilleure = np.full(n, np.inf)
    normales = np.zeros((n, 3))
    materiaux = np.full(n, -1)

    if len(sp.rayons):
        # Sphère : on résout |O + tD - C|² = r², une équation du second degré en t.
        oc = origines[:, None, :] - sp.centres[None, :, :]
        demi_b = np.einsum("nsk,nk->ns", oc, directions)
        c = np.einsum("nsk,nsk->ns", oc, oc) - sp.rayons ** 2
        discriminant = demi_b ** 2 - c
        racine = np.sqrt(np.maximum(discriminant, 0.0))
        t1, t2 = -demi_b - racine, -demi_b + racine
        t = np.where(t1 > EPSILON, t1, np.where(t2 > EPSILON, t2, np.inf))
        t = np.where(discriminant > 0, t, np.inf)
        plus_proche = np.argmin(t, axis=1)
        t_min = t[np.arange(n), plus_proche]
        touche = t_min < meilleure
        meilleure[touche] = t_min[touche]
        s = plus_proche[touche]
        point = origines[touche] + directions[touche] * t_min[touche, None]
        normales[touche] = (point - sp.centres[s]) / sp.rayons[s, None]
        materiaux[touche] = sp.mat_spheres[s]

    if len(sp.coins):
        # Quad : on coupe d'abord le plan, puis on vérifie que le point est dans le parallélogramme.
        denominateur = directions @ sp.normales_quads.T
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (sp.plans[None, :] - origines @ sp.normales_quads.T) / denominateur
        t = np.where((np.abs(denominateur) > 1e-9) & (t > EPSILON), t, np.inf)
        p = origines[:, None, :] + directions[:, None, :] * np.where(np.isfinite(t), t, 0)[..., None] - sp.coins
        alpha = np.einsum("qk,nqk->nq", sp.w, np.cross(p, sp.v[None]))
        beta = np.einsum("qk,nqk->nq", sp.w, np.cross(sp.u[None], p))
        dedans = (alpha >= 0) & (alpha <= 1) & (beta >= 0) & (beta <= 1)
        t = np.where(dedans, t, np.inf)
        plus_proche = np.argmin(t, axis=1)
        t_min = t[np.arange(n), plus_proche]
        touche = t_min < meilleure
        meilleure[touche] = t_min[touche]
        normales[touche] = sp.normales_quads[plus_proche[touche]]
        materiaux[touche] = sp.mat_quads[plus_proche[touche]]

    return meilleure, normales, materiaux


# --- Hasard ---------------------------------------------------------------------

def vecteurs_unitaires_aleatoires(rng, n):
    return normaliser(rng.normal(size=(n, 3)))


def points_dans_disque(rng, n):
    rayon = np.sqrt(rng.random(n))
    angle = 2 * np.pi * rng.random(n)
    return rayon * np.cos(angle), rayon * np.sin(angle)


# --- Caméra ---------------------------------------------------------------------

def rayons_camera(sp, largeur, hauteur, pixels, rng):
    """Crée un rayon par pixel demandé, avec un petit décalage aléatoire (anticrénelage)."""
    cam = sp.camera
    position = np.array(cam.position, dtype=float)
    cible = np.array(cam.cible, dtype=float)
    w = normaliser(position - cible)
    u = normaliser(np.cross(cam.haut, w))
    v = np.cross(w, u)
    distance = cam.mise_au_point or np.linalg.norm(position - cible)
    h = math.tan(math.radians(cam.champ) / 2)
    hauteur_vue = 2 * h * distance
    largeur_vue = hauteur_vue * largeur / hauteur

    x = (pixels % largeur + rng.random(len(pixels))) / largeur - 0.5
    y = 0.5 - (pixels // largeur + rng.random(len(pixels))) / hauteur
    cibles = position - distance * w + x[:, None] * largeur_vue * u + y[:, None] * hauteur_vue * v

    origines = np.repeat(position[None], len(pixels), axis=0)
    if cam.ouverture > 0:
        # Flou de profondeur : les rayons partent d'un petit disque (l'objectif) au lieu d'un point.
        dx, dy = points_dans_disque(rng, len(pixels))
        rayon = cam.ouverture / 2
        origines = origines + rayon * (dx[:, None] * u + dy[:, None] * v)
    return origines, normaliser(cibles - origines)


# --- Le trajet de la lumière ------------------------------------------------------

def couleur_ciel(sp, directions):
    melange = 0.5 * (directions[:, 1:2] + 1.0)
    return (1 - melange) * sp.ciel_bas + melange * sp.ciel_haut


def reflechir(d, n):
    return d - 2 * np.sum(d * n, axis=1, keepdims=True) * n


def lumiere_directe(sp, points, normales, rng):
    """Vise un point au hasard sur une lampe et renvoie la lumière reçue si rien ne la cache.

    C'est ce qui rend les petites lampes utilisables : sans cela, un rayon qui rebondit au
    hasard ne tomberait presque jamais dessus, et l'image serait couverte de grain.
    Renvoie la lumière déjà divisée par la probabilité du tirage (estimateur de Monte-Carlo).
    """
    n = len(points)
    choix = rng.integers(sp.nb_lampes, size=n)
    cibles = np.zeros((n, 3))
    normales_lampe = np.zeros((n, 3))
    aires = np.zeros(n)
    materiaux = np.zeros(n, dtype=int)

    en_sphere = choix < len(sp.lampes_spheres)
    if en_sphere.any():
        s = sp.lampes_spheres[choix[en_sphere]]
        centre, rayon = sp.centres[s], sp.rayons[s]
        # Point au hasard sur la moitié de la sphère tournée vers nous.
        d = vecteurs_unitaires_aleatoires(rng, len(s))
        vers_nous = points[en_sphere] - centre
        d = np.where(np.sum(d * vers_nous, axis=1, keepdims=True) < 0, -d, d)
        cibles[en_sphere] = centre + d * rayon[:, None]
        normales_lampe[en_sphere] = d
        aires[en_sphere] = 2 * np.pi * rayon ** 2
        materiaux[en_sphere] = sp.mat_spheres[s]

    en_quad = ~en_sphere
    if en_quad.any():
        q = sp.lampes_quads[choix[en_quad] - len(sp.lampes_spheres)]
        r1, r2 = rng.random((2, len(q)))
        cibles[en_quad] = sp.coins[q] + r1[:, None] * sp.u[q] + r2[:, None] * sp.v[q]
        normales_lampe[en_quad] = sp.normales_quads[q]
        aires[en_quad] = np.linalg.norm(np.cross(sp.u[q], sp.v[q]), axis=1)
        materiaux[en_quad] = sp.mat_quads[q]

    vers_lampe = cibles - points
    distance2 = np.sum(vers_lampe ** 2, axis=1)
    distance = np.sqrt(distance2)
    direction = vers_lampe / distance[:, None]
    cos_surface = np.sum(direction * normales, axis=1)
    cos_lampe = np.abs(np.sum(direction * normales_lampe, axis=1))

    # Rayon d'ombre : la lampe est visible si le premier objet touché est à la bonne distance.
    utiles = cos_surface > 0
    visible = np.zeros(n, dtype=bool)
    if utiles.any():
        t, _, _ = intersecter(sp, points[utiles], direction[utiles])
        visible[utiles] = t >= distance[utiles] * (1 - 1e-4) - EPSILON
    # Probabilité du tirage : 1 / (nombre de lampes × aire), convertie en angle solide.
    poids = np.where(visible, cos_surface * cos_lampe * aires * sp.nb_lampes / np.maximum(distance2, 1e-12), 0.0)
    return sp.emission[materiaux] * poids[:, None] / np.pi


def tracer(sp, origines, directions, rng, rebonds_max=10):
    """Suit chaque rayon de rebond en rebond et renvoie la couleur qu'il rapporte."""
    n = len(origines)
    couleur = np.zeros((n, 3))
    debit = np.ones((n, 3))    # quelle part de la lumière survit encore aux rebonds
    actifs = np.arange(n)
    # Après un rebond mat, les lampes ont déjà été visées directement : si le rayon tombe
    # ensuite sur une lampe par hasard, on ne la compte pas une deuxième fois.
    compter_lampes = np.ones(n, dtype=bool)

    for rebond in range(rebonds_max):
        if not len(actifs):
            break
        t, normale, mat = intersecter(sp, origines, directions)

        # Rayons perdus dans le ciel : ils ramènent la couleur du ciel.
        rate = mat < 0
        couleur[actifs[rate]] += debit[rate] * couleur_ciel(sp, directions[rate])
        garde = ~rate
        actifs, origines, directions = actifs[garde], origines[garde], directions[garde]
        t, normale, mat, debit = t[garde], normale[garde], mat[garde], debit[garde]
        compter_lampes = compter_lampes[garde]
        if not len(actifs):
            break

        point = origines + directions * t[:, None]
        exterieur = np.sum(directions * normale, axis=1) < 0  # le rayon arrive-t-il de l'extérieur ?
        normale = np.where(exterieur[:, None], normale, -normale)
        type_mat = sp.type[mat]

        couleur[actifs] += debit * sp.emission[mat] * compter_lampes[:, None]

        # Couleur de la surface (avec l'éventuel damier).
        albedo = sp.couleur[mat]
        motif = sp.a_damier[mat]
        if motif.any():
            p = point[motif] / sp.taille_damier[mat[motif], None]
            case = (np.floor(p[:, 0]) + np.floor(p[:, 2])) % 2 == 1  # damier horizontal (axes x et z)
            albedo[motif] = np.where(case[:, None], sp.couleur_damier[mat[motif]], albedo[motif])

        nouvelle = np.zeros_like(directions)
        vivant = type_mat != LUMIERE  # une lumière ne renvoie pas de rayon

        # Surface mate : on vise d'abord directement une lampe…
        mates = type_mat == DIFFUS
        if mates.any() and sp.nb_lampes:
            directe = lumiere_directe(sp, point[mates], normale[mates], rng)
            couleur[actifs[mates]] += np.minimum(debit[mates] * albedo[mates] * directe, LUMINANCE_MAX)
        # … puis on repart dans une direction aléatoire autour de la normale (distribution de Lambert).
        if mates.any():
            d = normale[mates] + vecteurs_unitaires_aleatoires(rng, mates.sum())
            degenere = np.linalg.norm(d, axis=1) < 1e-8
            d[degenere] = normale[mates][degenere]
            nouvelle[mates] = normaliser(d)

        # Métal : réflexion miroir, brouillée par le flou.
        m = type_mat == METAL
        if m.any():
            d = normaliser(reflechir(directions[m], normale[m]))
            d = d + sp.flou[mat[m], None] * vecteurs_unitaires_aleatoires(rng, m.sum()) * rng.random((m.sum(), 1))
            nouvelle[m] = normaliser(d)
            vivant[np.flatnonzero(m)] &= np.sum(nouvelle[m] * normale[m], axis=1) > 0

        # Verre : réfraction (loi de Snell-Descartes) ou réflexion (coefficients de Fresnel, approximation de Schlick).
        m = type_mat == VERRE
        if m.any():
            d, nm = directions[m], normale[m]
            rapport = np.where(exterieur[m], 1.0 / sp.indice[mat[m]], sp.indice[mat[m]])
            cos = np.minimum(-np.sum(d * nm, axis=1), 1.0)
            sin = np.sqrt(np.maximum(0.0, 1.0 - cos ** 2))
            r0 = ((1 - rapport) / (1 + rapport)) ** 2
            reflet = (rapport * sin > 1.0) | (r0 + (1 - r0) * (1 - cos) ** 5 > rng.random(m.sum()))
            perpendiculaire = rapport[:, None] * (d + cos[:, None] * nm)
            parallele = -np.sqrt(np.abs(1.0 - np.sum(perpendiculaire ** 2, axis=1)))[:, None] * nm
            refracte = perpendiculaire + parallele
            nouvelle[m] = normaliser(np.where(reflet[:, None], reflechir(d, nm), refracte))

        debit = debit * albedo
        compter_lampes = ~mates | (sp.nb_lampes == 0)

        # Roulette russe : après quelques rebonds, on arrête au hasard les rayons qui ne transportent
        # presque plus rien, en compensant ceux qui continuent. Le résultat reste juste en moyenne.
        if rebond >= 3:
            survie = np.clip(debit.max(axis=1), 0.05, 0.95)
            reste = rng.random(len(survie)) < survie
            debit = debit / survie[:, None]
            vivant &= reste

        actifs, origines, directions, debit = actifs[vivant], point[vivant], nouvelle[vivant], debit[vivant]
        compter_lampes = compter_lampes[vivant]

    return np.minimum(couleur, LUMINANCE_MAX)


def rendre_echantillons(sp, largeur, hauteur, nb_echantillons, graine, rebonds_max=10, taille_paquet=16384):
    """Calcule la somme de `nb_echantillons` passes sur toute l'image. Renvoie un tableau (hauteur, largeur, 3)."""
    rng = np.random.default_rng(graine)
    image = np.zeros((largeur * hauteur, 3))
    pixels = np.arange(largeur * hauteur)
    for _ in range(nb_echantillons):
        for debut in range(0, len(pixels), taille_paquet):
            paquet = pixels[debut:debut + taille_paquet]
            origines, directions = rayons_camera(sp, largeur, hauteur, paquet, rng)
            image[paquet] += tracer(sp, origines, directions, rng, rebonds_max)
    return image.reshape(hauteur, largeur, 3)
