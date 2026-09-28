import os
import tempfile
import unittest

try:
    import torch
except ImportError:  # PyTorch n'est nécessaire que pour MiniGPT
    torch = None

if torch is not None:
    from minigpt.donnees import Tokeniseur, nettoyer_europarl
    from minigpt.entrainement import charger, sauvegarder, taux_apprentissage
    from minigpt.modele import Config, MiniGPT


@unittest.skipIf(torch is None, "PyTorch n'est pas installé")
class TestTokeniseur(unittest.TestCase):
    def test_aller_retour(self):
        tok = Tokeniseur.depuis_texte("bonjour le monde", frequence_min=1)
        self.assertEqual(tok.decoder(tok.encoder("le monde")), "le monde")

    def test_caractere_inconnu(self):
        tok = Tokeniseur.depuis_texte("abc", frequence_min=1)
        self.assertEqual(tok.decoder(tok.encoder("abz")), "ab�")

    def test_nettoyage(self):
        texte = nettoyer_europarl("le grand \" bogue de l' an 2000 \" ne s' est pas produit .\nqu ' il\nmes vux")
        self.assertEqual(texte, "le grand « bogue de l'an 2000 » ne s'est pas produit.\nqu'il\nmes vœux")


@unittest.skipIf(torch is None, "PyTorch n'est pas installé")
class TestModele(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(0)
        self.cfg = Config(taille_vocab=10, taille_contexte=16, nb_couches=2, nb_tetes=2, dim=16, dropout=0.0)
        self.modele = MiniGPT(self.cfg)

    def test_dimensions(self):
        x = torch.randint(10, (3, 16))
        logits, perte = self.modele(x, x)
        self.assertEqual(logits.shape, (3, 16, 10))
        self.assertGreater(perte.item(), 0)

    def test_ne_regarde_pas_le_futur(self):
        """Changer le dernier caractère ne doit pas modifier les prédictions des positions précédentes."""
        self.modele.eval()
        x = torch.randint(10, (1, 16))
        y = x.clone()
        y[0, -1] = (x[0, -1] + 1) % 10
        self.assertTrue(torch.allclose(self.modele(x)[0][:, :-1], self.modele(y)[0][:, :-1], atol=1e-6))

    def test_apprend_par_coeur(self):
        """Sur une petite séquence répétitive, la perte doit s'effondrer."""
        motif = torch.tensor([[1, 2, 3, 4, 5, 6, 7, 8] * 2])
        x, y = motif[:, :-1], motif[:, 1:]
        optimiseur = torch.optim.AdamW(self.modele.parameters(), lr=1e-2)
        for _ in range(200):
            _, perte = self.modele(x, y)
            optimiseur.zero_grad()
            perte.backward()
            optimiseur.step()
        self.assertLess(perte.item(), 0.1)

    def test_generation(self):
        idx = torch.zeros((1, 1), dtype=torch.long)
        sortie = list(self.modele.generer(idx, 40, top_k=3))
        self.assertEqual(len(sortie), 40)
        self.assertTrue(all(0 <= i < 10 for i in sortie))

    def test_sauvegarde(self):
        tok = Tokeniseur(list("abcdefghi"))
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "m.pt")
            sauvegarder(self.modele, tok, chemin)
            copie, tok2 = charger(chemin)
        self.assertEqual(tok2.caracteres, tok.caracteres)
        x = torch.randint(10, (1, 8))
        self.modele.eval()
        self.assertTrue(torch.equal(self.modele(x)[0], copie(x)[0]))

    def test_taux_apprentissage(self):
        self.assertLess(taux_apprentissage(0, 1000, 1.0), 0.05)
        self.assertAlmostEqual(taux_apprentissage(100, 1000, 1.0), 1.0)
        self.assertAlmostEqual(taux_apprentissage(1000, 1000, 1.0), 0.1)


if __name__ == "__main__":
    unittest.main()
