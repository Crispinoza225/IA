import unittest

try:
    import numpy as np
except ImportError:  # NumPy n'est nécessaire que pour le simulateur de galaxies
    np = None

if np is not None:
    from galaxie.gravite import Octree, acceleration, acceleration_directe
    from galaxie.rendu import dessiner
    from galaxie.scenes import SCENES, collision, disque_toomre, orbite_parabolique
    from galaxie.simulation import Univers


def univers_simple(positions, vitesses, masses, douceur=0.0, **options):
    positions, vitesses = np.array(positions, float), np.array(vitesses, float)
    return Univers(positions, vitesses, np.array(masses, float), np.ones_like(positions), douceur=douceur, **options)


@unittest.skipIf(np is None, "NumPy n'est pas installé")
class TestGravite(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(0)
        self.pos = rng.normal(size=(3000, 3))
        self.m = rng.random(3000) / 3000

    def test_deux_masses(self):
        """Une masse 2 à distance 2 : accélération G·m/r² = 0,5, dirigée vers elle."""
        acc = acceleration_directe(np.array([[2.0, 0, 0]]), np.array([2.0]), np.zeros((1, 3)), douceur=0)
        np.testing.assert_allclose(acc, [[0.5, 0, 0]])

    def test_barnes_hut_exact_avec_theta_nul(self):
        exacte = acceleration_directe(self.pos, self.m, self.pos, 0.01)
        np.testing.assert_allclose(Octree(self.pos, self.m).acceleration(self.pos, 0.01, theta=0.0), exacte, atol=1e-10)

    def test_barnes_hut_precis(self):
        exacte = acceleration_directe(self.pos, self.m, self.pos, 0.01)
        approchee = Octree(self.pos, self.m).acceleration(self.pos, 0.01, theta=0.7)
        erreur = np.linalg.norm(approchee - exacte, axis=1) / np.linalg.norm(exacte, axis=1)
        self.assertLess(np.median(erreur), 0.01)

    def test_racine_de_l_arbre(self):
        arbre = Octree(self.pos, self.m)
        racine = arbre.etages[0]
        self.assertAlmostEqual(racine["masse"][0], self.m.sum())
        np.testing.assert_allclose(racine["centre"][0], (self.m[:, None] * self.pos).sum(0) / self.m.sum())
        self.assertEqual(arbre.etages[-1]["nombre"].sum(), len(self.pos))

    def test_etoiles_sans_masse(self):
        """Une étoile sans masse subit la gravité mais n'en crée pas."""
        pos = np.array([[0.0, 0, 0], [1.0, 0, 0]])
        acc = acceleration(pos, np.array([1.0, 0.0]), douceur=0)
        np.testing.assert_allclose(acc, [[0, 0, 0], [-1, 0, 0]])


@unittest.skipIf(np is None, "NumPy n'est pas installé")
class TestSimulation(unittest.TestCase):
    def test_orbite_circulaire(self):
        """Une planète en orbite circulaire autour d'une étoile garde son rayon et revient à son point de départ."""
        u = univers_simple([[0, 0, 0], [1, 0, 0]], [[0, 0, 0], [0, 1, 0]], [1.0, 0.0])
        periode = 2 * np.pi
        pas = 2000
        rayons = []
        for _ in range(pas):
            u.pas(periode / pas)
            rayons.append(np.linalg.norm(u.positions[1] - u.positions[0]))
        self.assertLess(max(abs(r - 1) for r in rayons), 1e-4)
        np.testing.assert_allclose(u.positions[1], [1, 0, 0], atol=1e-3)

    def test_conservation(self):
        """Sur un petit amas, l'énergie et la quantité de mouvement sont conservées."""
        rng = np.random.default_rng(1)
        u = univers_simple(rng.normal(size=(60, 3)), rng.normal(0, 0.1, (60, 3)), np.full(60, 1 / 60),
                           douceur=0.1, methode="directe")
        energie, elan = u.energie(), u.quantite_de_mouvement()
        for _ in range(500):
            u.pas(0.01)
        self.assertLess(abs(u.energie() - energie) / abs(energie), 1e-3)
        np.testing.assert_allclose(u.quantite_de_mouvement(), elan, atol=1e-12)

    def test_disque_de_toomre_stable(self):
        """Seul, un disque d'étoiles tests autour de son noyau reste en place."""
        rng = np.random.default_rng(2)
        p, v = disque_toomre(rng, 500, masse_centre=1.0, rayon=1.0, douceur=0.1)
        u = univers_simple(np.vstack([[0, 0, 0], p]), np.vstack([[0, 0, 0], v]), [1.0] + [0.0] * 500, douceur=0.1)
        rayon_depart = np.linalg.norm(u.positions[1:, :2], axis=1)
        for _ in range(600):
            u.pas(0.01)
        rayon_fin = np.linalg.norm(u.positions[1:, :2], axis=1)
        self.assertLess(np.max(np.abs(rayon_fin - rayon_depart)), 0.03)

    def test_orbite_parabolique(self):
        """Sur une parabole, énergie nulle : v²/2 = G·M/r."""
        position, vitesse = orbite_parabolique(2.0, pericentre=1.0, distance=8.0)
        self.assertAlmostEqual(np.linalg.norm(position), 8.0)
        self.assertAlmostEqual(0.5 * vitesse @ vitesse - 2.0 / np.linalg.norm(position), 0.0)

    def test_collision_rapprochement(self):
        """Les deux noyaux se rapprochent jusqu'au péricentre prévu, puis s'éloignent."""
        u = collision(nb_etoiles=200, pericentre=1.4)
        noyaux = np.flatnonzero(u.masses > 0)
        distances = []
        for _ in range(1500):
            u.pas(0.01)
            distances.append(np.linalg.norm(u.positions[noyaux[0]] - u.positions[noyaux[1]]))
        self.assertAlmostEqual(min(distances), 1.4, delta=0.1)
        self.assertGreater(distances[-1], min(distances))


@unittest.skipIf(np is None, "NumPy n'est pas installé")
class TestRendu(unittest.TestCase):
    def test_image(self):
        u = univers_simple([[0, 0, 0]], [[0, 0, 0]], [1.0])
        image = dessiner(u, largeur=64, hauteur=48, champ=4.0, vue=(90, 0))
        self.assertEqual(image.shape, (48, 64, 3))
        self.assertEqual(image.dtype, np.uint8)
        self.assertGreater(image[24, 32].sum(), image[2, 2].sum())  # l'étoile brille au centre, pas dans le coin

    def test_toutes_les_scenes(self):
        for nom, (fabrique, reglages) in SCENES.items():
            u = fabrique(nb_etoiles=300)
            u.pas(reglages["dt"])
            self.assertTrue(np.isfinite(u.positions).all(), nom)
            self.assertEqual(dessiner(u, 32, 32, champ=reglages["champ"], vue=reglages["vue"]).shape, (32, 32, 3))


if __name__ == "__main__":
    unittest.main()
