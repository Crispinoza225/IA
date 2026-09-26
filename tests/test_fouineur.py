import os
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from fouineur.analyse import distance_edition, termes
from fouineur.demo import demarrer_serveur_demo
from fouineur.explorateur import Explorateur, analyser_page, normaliser_url
from fouineur.index import Index, extrait
from fouineur.pagerank import pagerank
from fouineur.serveur import creer_gestionnaire, surligner


class TestAnalyse(unittest.TestCase):
    def test_termes(self):
        self.assertEqual(termes("Les Planètes rouges"), termes("planete rouge"))
        self.assertNotIn("les", termes("les chats"))

    def test_distance(self):
        self.assertEqual(distance_edition("chat", "chat"), 0)
        self.assertEqual(distance_edition("chat", "chats"), 1)
        self.assertEqual(distance_edition("plannete", "planete"), 1)


class TestPageRank(unittest.TestCase):
    def test_page_populaire(self):
        # Tout le monde pointe vers « a » : elle doit avoir le plus grand PageRank.
        rangs = pagerank({"a": ["b"], "b": ["a"], "c": ["a"], "d": ["a"]})
        self.assertEqual(max(rangs, key=rangs.get), "a")
        self.assertAlmostEqual(sum(rangs.values()), 1.0)

    def test_cul_de_sac(self):
        rangs = pagerank({"a": ["b"], "b": []})
        self.assertAlmostEqual(sum(rangs.values()), 1.0)
        self.assertGreater(rangs["b"], rangs["a"])


class TestExtraction(unittest.TestCase):
    def test_analyser_page(self):
        html = """<html><head><title> Mon titre </title><meta name="description" content="Résumé">
        <script>var cache = 1;</script></head><body><nav>Menu</nav><h1>Bonjour</h1><p>Un <b>texte</b>.</p>
        <a href="/autre#section">lien</a><a href="mailto:x@y.fr">mail</a><a href="page2">relatif</a></body></html>"""
        page = analyser_page("https://exemple.fr/dossier/page", html)
        self.assertEqual(page["titre"], "Mon titre")
        self.assertEqual(page["description"], "Résumé")
        self.assertIn("Un texte.", page["texte"])
        self.assertNotIn("cache", page["texte"])
        self.assertNotIn("Menu", page["texte"])
        self.assertEqual(page["liens"], ["https://exemple.fr/autre", "https://exemple.fr/dossier/page2"])

    def test_normaliser_url(self):
        self.assertEqual(normaliser_url("HTTPS://Exemple.FR#haut"), "https://exemple.fr/")
        self.assertIsNone(normaliser_url("javascript:alert(1)"))


class TestMoteurComplet(unittest.TestCase):
    """Explore le mini-web de démonstration, puis cherche dedans."""

    @classmethod
    def setUpClass(cls):
        cls.serveur, cls.adresse = demarrer_serveur_demo()
        cls.pages = Explorateur(delai=0, afficher=lambda *a: None).explorer([cls.adresse], max_pages=100)
        cls.index = Index.construire(cls.pages)

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()
        cls.serveur.server_close()

    def titres(self, requete):
        return [r["titre"] for r in self.index.chercher(requete)["resultats"]]

    def test_exploration(self):
        self.assertEqual(len(self.pages), 20)

    def test_respecte_robots_txt(self):
        self.assertFalse(any("/prive/" in p["url"] for p in self.pages))
        self.assertEqual(self.titres("licorne"), [])

    def test_ignore_les_scripts(self):
        self.assertEqual(self.titres("console"), [])

    def test_pertinence(self):
        self.assertEqual(self.titres("volcan")[0], "Les volcans")
        self.assertEqual(self.titres("planète rouge")[0], "Mars, la planète rouge")
        self.assertEqual(self.titres("chats")[0], "Le chat domestique")

    def test_exclusion(self):
        self.assertIn("La fourmi", self.titres("intelligence"))
        self.assertNotIn("La fourmi", self.titres("intelligence -fourmi"))

    def test_pagerank_accueil(self):
        meilleure = max(range(len(self.index.documents)), key=self.index.pagerank.__getitem__)
        self.assertIn("Accueil", self.index.documents[meilleure]["titre"])

    def test_suggestion(self):
        self.assertEqual(self.index.chercher("plannete rouje")["suggestion"], "planète rouge")
        self.assertIsNone(self.index.chercher("volcan")["suggestion"])

    def test_sauvegarde(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = os.path.join(dossier, "index.json.gz")
            self.index.sauvegarder(chemin)
            copie = Index.charger(chemin)
        self.assertEqual(copie.chercher("dauphin")["resultats"], self.index.chercher("dauphin")["resultats"])

    def test_interface_web(self):
        serveur = ThreadingHTTPServer(("127.0.0.1", 0), creer_gestionnaire(self.index))
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        try:
            base = f"http://127.0.0.1:{serveur.server_address[1]}"
            with urllib.request.urlopen(base + "/recherche?q=%3Cscript%3Evolcan") as reponse:
                html = reponse.read().decode("utf-8")
            self.assertIn("Les volcans", html)
            self.assertNotIn("<script>volcan", html)  # le texte tapé est bien échappé
        finally:
            serveur.shutdown()
            serveur.server_close()


class TestAffichage(unittest.TestCase):
    def test_extrait(self):
        texte = " ".join(["mot"] * 50 + ["volcans", "rouges"] + ["mot"] * 50)
        self.assertIn("[[volcans]]", extrait(texte, set(termes("volcan")), taille=10))

    def test_surligner_echappe(self):
        self.assertEqual(surligner("a [[<b>]] c"), "a <mark>&lt;b&gt;</mark> c")


if __name__ == "__main__":
    unittest.main()
