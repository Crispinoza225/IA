import os
import tempfile
import unittest

from ia.chatbot import Chatbot, calculer
from ia.reseau import ReseauNeurones
from ia.texte import jetons


class TestTexte(unittest.TestCase):
    def test_normalisation(self):
        self.assertEqual(jetons("Ça VA ?"), ["ca", "va"])
        self.assertEqual(jetons("calcule 12 + 3"), ["calcul", "nombr", "nombr"])


class TestReseau(unittest.TestCase):
    def test_apprend_ou_exclusif(self):
        donnees = [([0, 0], 0), ([0, 1], 1), ([1, 0], 1), ([1, 1], 0)]
        donnees = [([float(a), float(b), 1.0], c) for (a, b), c in donnees]
        reseau = ReseauNeurones(3, 8, 2)
        reseau.entrainer(donnees, epoques=2000, taux=0.2)
        for x, c in donnees:
            probas = reseau.predire(x)
            self.assertEqual(probas.index(max(probas)), c)

    def test_sauvegarde(self):
        reseau = ReseauNeurones(4, 3, 2)
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "modele.json")
            reseau.sauvegarder(chemin)
            copie = ReseauNeurones.charger(chemin)
        self.assertEqual(reseau.predire([1, 0, 1, 0]), copie.predire([1, 0, 1, 0]))


class TestCalcul(unittest.TestCase):
    def test_calculs(self):
        self.assertEqual(calculer("calcule 12 * 7 + 3"), "12 * 7 + 3 = 87")
        self.assertEqual(calculer("combien font 3 fois 4"), "3 * 4 = 12")
        self.assertEqual(calculer("10 divisé par 4"), "10 / 4 = 2.5")
        self.assertIn("zéro", calculer("calcule 1 / 0"))

    def test_pas_de_code_arbitraire(self):
        self.assertIn("pas réussi", calculer("calcule __import__('os') 1"))


class TestChatbot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bot = Chatbot(fichier_appris=None, graine=0)
        cls.bot.entrainer()

    def test_intentions(self):
        cas = {
            "Salut !": "salutation",
            "raconte moi une blague": "blague",
            "quelle heure est-il ?": "heure",
            "qui es-tu ?": "identite",
            "merci beaucoup": "remerciement",
            "calcule 5 + 5": "calcul",
        }
        for phrase, attendu in cas.items():
            self.assertEqual(self.bot.classer(phrase)[0], attendu, phrase)

    def test_inconnu(self):
        self.assertIsNone(self.bot.repondre("quel est ton plat préféré"))

    def test_apprentissage(self):
        bot = Chatbot(fichier_appris=None, graine=0)
        bot.entrainer()
        bot.apprendre("quel est ton plat préféré", "Les pâtes !")
        self.assertEqual(bot.repondre("c'est quoi ton plat préféré"), "Les pâtes !")


if __name__ == "__main__":
    unittest.main()
