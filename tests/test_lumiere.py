import os
import tempfile
import unittest
import zlib

try:
    import numpy as np
except ImportError:  # NumPy n'est nécessaire que pour Lumière
    np = None

if np is not None:
    from lumiere.image import ecrire_png, vers_pixels
    from lumiere.moteur import ScenePreparee, intersecter, rendre_echantillons, tracer
    from lumiere.scene import Camera, Quad, Scene, Sphere, boite, diffus, lumiere, verre
    from lumiere.scenes import SCENES


@unittest.skipIf(np is None, "NumPy n'est pas installé")
class TestIntersections(unittest.TestCase):
    def setUp(self):
        self.scene = Scene(objets=[
            Sphere((0, 0, -5), 1.0, diffus((1, 0, 0))),
            Quad((-1, -1, -10), (2, 0, 0), (0, 2, 0), diffus((0, 1, 0))),
        ])
        self.sp = ScenePreparee(self.scene)

    def test_sphere_et_quad(self):
        origines = np.zeros((3, 3))
        directions = np.array([[0, 0, -1], [0, 0.8, -0.6], [0, 1.0, 0]], dtype=float)
        # Rayon 1 : touche la sphère à distance 4, avec une normale tournée vers nous.
        t, normales, materiaux = intersecter(self.sp, origines, directions)
        self.assertAlmostEqual(t[0], 4.0)
        np.testing.assert_allclose(normales[0], [0, 0, 1], atol=1e-9)
        self.assertEqual(materiaux[0], 0)
        # Rayon 3 : part vers le haut et ne touche rien.
        self.assertEqual(materiaux[2], -1)
        self.assertTrue(np.isinf(t[2]))

    def test_quad_derriere_la_sphere(self):
        sp = ScenePreparee(Scene(objets=[self.scene.objets[1]]))
        t, _, materiaux = intersecter(sp, np.zeros((2, 3)), np.array([[0, 0, -1.0], [0.6, 0, -0.8]]))
        self.assertAlmostEqual(t[0], 10.0)
        self.assertEqual(materiaux[1], -1)  # passe à côté du carré

    def test_boite_normales_exterieures(self):
        quads = boite((0, 0, 0), (2, 2, 2), diffus((1, 1, 1)), angle=30)
        self.assertEqual(len(quads), 6)
        for q in quads:
            centre_face = np.array(q.coin) + (np.array(q.u) + np.array(q.v)) / 2
            self.assertGreater(np.dot(np.cross(q.u, q.v), centre_face - np.array([0, 1, 0])), 0)


@unittest.skipIf(np is None, "NumPy n'est pas installé")
class TestLumiere(unittest.TestCase):
    def test_ciel_blanc_seul(self):
        """Sans objet, on voit exactement la couleur du ciel."""
        sp = ScenePreparee(Scene(ciel_haut=(1, 1, 1), ciel_bas=(1, 1, 1)))
        couleur = tracer(sp, np.zeros((5, 3)), np.tile([0, 0, -1.0], (5, 1)), np.random.default_rng(0))
        np.testing.assert_allclose(couleur, 1.0)

    def test_four_blanc(self):
        """Dans une sphère blanche parfaite éclairée uniformément, chaque rebond renvoie toute la lumière.

        C'est le test classique du « four blanc » : si l'énergie est conservée, on doit retrouver
        la couleur du ciel. Ici le sol mat (albédo 0,5) sous un ciel blanc doit donner environ 0,5.
        """
        sp = ScenePreparee(Scene(objets=[Sphere((0, -1000, 0), 999.0, diffus((0.5, 0.5, 0.5)))],
                                 ciel_haut=(1, 1, 1), ciel_bas=(1, 1, 1)))
        n = 20000
        couleur = tracer(sp, np.zeros((n, 3)), np.tile([0, -1.0, 0], (n, 1)), np.random.default_rng(1))
        self.assertAlmostEqual(couleur.mean(), 0.5, delta=0.02)

    def test_eclairage_direct_juste(self):
        """L'échantillonnage direct des lampes ne doit pas changer le résultat moyen, seulement le bruit."""
        def scene():
            return Scene(objets=[Quad((-50, 0, -50), (100, 0, 0), (0, 0, 100), diffus((0.5, 0.5, 0.5))),
                                 Sphere((0, 3, 0), 1.0, lumiere((1, 1, 1), 2.0))],
                         ciel_haut=(0, 0, 0), ciel_bas=(0, 0, 0))
        sp = ScenePreparee(scene())
        n = 40000
        origines = np.tile([0, 0.001, 0], (n, 1)) + np.array([0.3, 0, 0])
        vers_le_sol = np.tile([0, -1.0, 0], (n, 1))
        avec = tracer(sp, origines + [0, 1, 0], vers_le_sol, np.random.default_rng(2), rebonds_max=2).mean()
        sp.nb_lampes = 0  # désactive l'échantillonnage direct
        sans = tracer(sp, origines + [0, 1, 0], vers_le_sol, np.random.default_rng(3), rebonds_max=2).mean()
        self.assertAlmostEqual(avec, sans, delta=0.1 * sans)

    def test_verre_transparent(self):
        """Une sphère de verre devant un ciel uniforme laisse passer toute la lumière (en moyenne :
        la roulette russe arrête quelques rayons et renforce les autres pour compenser)."""
        sp = ScenePreparee(Scene(objets=[Sphere((0, 0, -3), 1.0, verre())], ciel_haut=(1, 1, 1), ciel_bas=(1, 1, 1)))
        couleur = tracer(sp, np.zeros((20000, 3)), np.tile([0, 0, -1.0], (20000, 1)), np.random.default_rng(0))
        self.assertAlmostEqual(couleur.mean(), 1.0, delta=0.02)


@unittest.skipIf(np is None, "NumPy n'est pas installé")
class TestImage(unittest.TestCase):
    def test_vers_pixels(self):
        pixels = vers_pixels(np.array([[[0.0, 1.0, 5.0], [4.0, 2.0, 0.0]]]))
        vert_attendu = int(255 * 0.2 ** (1 / 2.2) + 0.5)  # 1/5 de la luminosité, après correction gamma
        np.testing.assert_array_equal(pixels[0, 0], [0, vert_attendu, 255])  # teinte gardée
        self.assertEqual(pixels[0, 1, 0], 255)
        self.assertGreater(pixels[0, 1, 1], pixels[0, 1, 2])

    def test_png_valide(self):
        pixels = np.zeros((3, 4, 3), dtype=np.uint8)
        pixels[1, 2] = [255, 128, 0]
        with tempfile.TemporaryDirectory() as dossier:
            chemin = os.path.join(dossier, "test.png")
            ecrire_png(chemin, pixels)
            with open(chemin, "rb") as f:
                donnees = f.read()
        self.assertTrue(donnees.startswith(b"\x89PNG\r\n\x1a\n"))
        idat = donnees[donnees.index(b"IDAT") + 4:donnees.index(b"IEND") - 8]
        brut = zlib.decompress(idat)
        self.assertEqual(len(brut), 3 * (1 + 4 * 3))
        self.assertEqual(brut[1 * 13 + 1 + 2 * 3:1 * 13 + 1 + 3 * 3], bytes([255, 128, 0]))


@unittest.skipIf(np is None, "NumPy n'est pas installé")
class TestScenes(unittest.TestCase):
    def test_toutes_les_scenes_se_rendent(self):
        for nom, fabrique in SCENES.items():
            image = rendre_echantillons(ScenePreparee(fabrique()), 16, 9, 1, graine=0)
            self.assertEqual(image.shape, (9, 16, 3), nom)
            self.assertTrue(np.isfinite(image).all(), nom)
            self.assertGreater(image.mean(), 0.01, nom)

    def test_flou_de_profondeur(self):
        scene = Scene(objets=[Sphere((0, 0, -3), 1.0, diffus((0.5, 0.5, 0.5)))],
                      camera=Camera(ouverture=0.5, mise_au_point=3))
        image = rendre_echantillons(ScenePreparee(scene), 8, 8, 2, graine=0)
        self.assertTrue(np.isfinite(image).all())


if __name__ == "__main__":
    unittest.main()
