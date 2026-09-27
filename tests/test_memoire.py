import io
import json
import threading
import unittest
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from xml.etree import ElementTree

from memoire.apercu import apercu
from memoire.docx import ecrire_docx
from memoire.reglages import Reglages, norme
from memoire.serveur import Gestionnaire
from memoire.source import Citation, Liste, Paragraphe, SautDePage, Tableau, Titre, importer_docx, lire, numeroter

try:
    import reportlab  # noqa: F401
    PDF = True
except ImportError:
    PDF = False

TEXTE = """# Introduction

Un paragraphe avec du **gras** et de l'*italique*,
sur deux lignes.

# Premier chapitre

## Contexte

- un
- **deux**

1. étape
2. étape

> Une citation.

| A | B |
|---|---|
| 1 | 2 |

### Détail

---saut de page---

# Deuxième chapitre

## Suite

# Avant-propos tardif {-}

# Conclusion
"""


def titres(blocs):
    return [(b.niveau, b.numero, b.texte) for b in blocs if isinstance(b, Titre)]


class TestSource(unittest.TestCase):
    def test_blocs(self):
        blocs = lire(TEXTE)
        types = [type(b) for b in blocs]
        for attendu in (Titre, Paragraphe, Liste, Citation, Tableau, SautDePage):
            self.assertIn(attendu, types)
        paragraphe = next(b for b in blocs if isinstance(b, Paragraphe))
        self.assertEqual([(m.texte, m.gras, m.italique) for m in paragraphe.morceaux],
                         [("Un paragraphe avec du ", False, False), ("gras", True, False), (" et de l'", False, False),
                          ("italique", False, True), (",  sur deux lignes.".replace("  ", " "), False, False)])

    def test_numerotation_decimale(self):
        self.assertEqual(titres(numeroter(lire(TEXTE), "decimale")), [
            (1, "", "Introduction"), (1, "1.", "Premier chapitre"), (2, "1.1.", "Contexte"), (3, "1.1.1.", "Détail"),
            (1, "2.", "Deuxième chapitre"), (2, "2.1.", "Suite"), (1, "", "Avant-propos tardif"), (1, "", "Conclusion")])

    def test_numerotation_romaine(self):
        numeros = [n for _, n, _ in titres(numeroter(lire(TEXTE), "romaine")) if n]
        self.assertEqual(numeros, ["I.", "A.", "1.", "II.", "A."])

    def test_listes_et_tableau(self):
        blocs = lire(TEXTE)
        listes = [b for b in blocs if isinstance(b, Liste)]
        self.assertEqual([l.ordonnee for l in listes], [False, True])
        self.assertTrue(listes[0].elements[1][0].gras)
        tableau = next(b for b in blocs if isinstance(b, Tableau))
        self.assertEqual([[c[0].texte for c in ligne] for ligne in tableau.lignes], [["A", "B"], ["1", "2"]])


class TestReglages(unittest.TestCase):
    def test_valeurs_bornees_et_inconnues(self):
        r = Reglages.depuis_dict({"taille": 99, "interligne": "1.5", "police": "Comic Sans", "inconnu": 1,
                                  "tailles_titres": [20], "garde": {"auteur": "Alex", "afficher": False}})
        self.assertEqual(r.taille, 20)
        self.assertEqual(r.interligne, 1.5)
        self.assertEqual(r.police, "Times New Roman")
        self.assertEqual(r.tailles_titres, (20, 14, 12))
        self.assertEqual((r.garde.auteur, r.garde.afficher), ("Alex", False))

    def test_normes(self):
        self.assertEqual(norme("apa").interligne, 2.0)
        self.assertEqual(norme("plan_francais").numerotation, "romaine")


class TestDocx(unittest.TestCase):
    def fichiers(self, reglages=None):
        reglages = reglages or Reglages()
        contenu = ecrire_docx(numeroter(lire(TEXTE), reglages.numerotation), reglages)
        with zipfile.ZipFile(io.BytesIO(contenu)) as archive:
            return {nom: archive.read(nom).decode("utf-8") for nom in archive.namelist()}, contenu

    def test_archive_valide(self):
        fichiers, _ = self.fichiers()
        for nom, xml in fichiers.items():
            ElementTree.fromstring(xml.encode("utf-8"))  # lève une erreur si le XML est mal formé
        document = fichiers["word/document.xml"]
        self.assertIn('TOC \\o "1-3"', document)            # le sommaire
        self.assertIn('w:val="Heading2"', document)          # les vrais styles de titres
        self.assertIn("<w:titlePg/>", document)              # pas de numéro sur la page de garde
        self.assertIn('<w:updateFields w:val="true"/>', fichiers["word/settings.xml"])
        self.assertIn("PAGE", fichiers["word/footer1.xml"])

    def test_pas_de_page_blanche(self):
        """Aucun paragraphe de saut : les changements de page passent par « saut de page avant »."""
        fichiers, _ = self.fichiers()
        document = fichiers["word/document.xml"]
        self.assertNotIn('w:type="page"', document)
        # le titre du sommaire (après la page de garde), le premier titre (après le sommaire) et
        # « Deuxième chapitre » (après le saut de page tapé dans le texte)
        self.assertEqual(document.count("<w:pageBreakBefore/>"), 3)

    def test_reglages_appliques(self):
        r = Reglages(police="Arial", taille=11, interligne=2.0, numerotation="romaine", prefixe_chapitre="Partie",
                     pagination="aucune")
        r.garde.afficher = False
        fichiers, _ = self.fichiers(r)
        styles = fichiers["word/styles.xml"]
        self.assertIn('w:ascii="Arial"', styles)
        self.assertIn('<w:sz w:val="22"/>', styles)          # 11 pt = 22 demi-points
        self.assertIn('w:line="480"', styles)                # interligne double
        self.assertIn('w:lvlText w:val="Partie %1."', fichiers["word/numbering.xml"])
        self.assertIn("upperRoman", fichiers["word/numbering.xml"])
        self.assertNotIn("word/footer1.xml", fichiers)
        self.assertNotIn("<w:titlePg/>", fichiers["word/document.xml"])

    def test_aller_retour_word(self):
        """Un .docx produit par la plateforme peut être réimporté sans perdre titres ni gras."""
        _, contenu = self.fichiers()
        texte = importer_docx(contenu)
        blocs = numeroter(lire(texte), "decimale")
        self.assertEqual([t[2] for t in titres(blocs)], [t[2] for t in titres(numeroter(lire(TEXTE), "decimale"))])
        self.assertIn("**gras**", texte)
        self.assertIn("*italique*", texte)
        # L'ancien sommaire et la page de garde ne sont pas réimportés : chaque titre n'apparaît qu'une fois.
        self.assertEqual(texte.count("Premier chapitre"), 1)
        self.assertNotIn("Sommaire", texte)


class TestApercu(unittest.TestCase):
    def test_texte_echappe(self):
        html = apercu(lire("# Titre <script>\n\nTexte <img src=x onerror=alert(1)>"), Reglages())
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;script&gt;", html)

    def test_feuilles(self):
        r = Reglages()
        html = apercu(numeroter(lire(TEXTE), "decimale"), r)
        # page de garde + sommaire + Introduction + 2 chapitres + 2 titres sans numéro ; le saut de page
        # juste avant « Deuxième chapitre » ne crée pas de feuille vide.
        self.assertEqual(html.count('<section class="feuille'), 7)
        self.assertIn("1.1. Contexte", html)


@unittest.skipUnless(PDF, "reportlab n'est pas installé")
class TestPdf(unittest.TestCase):
    def test_sommaire_et_pages(self):
        from memoire.pdf import ecrire_pdf
        contenu, entrees = ecrire_pdf(numeroter(lire(TEXTE), "decimale"), Reglages())
        self.assertTrue(contenu.startswith(b"%PDF"))
        self.assertEqual([t for _, t, _ in entrees][:3], ["Introduction", "1. Premier chapitre", "1.1. Contexte"])
        pages = [p for _, _, p in entrees]
        self.assertEqual(pages, sorted(pages))
        self.assertEqual(pages[0], 3)  # page de garde, sommaire, puis l'introduction


class TestServeur(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestionnaire)
        threading.Thread(target=cls.serveur.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.serveur.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()
        cls.serveur.server_close()

    def requete(self, chemin, donnees=None, brut=None):
        corps = brut if brut is not None else (json.dumps(donnees).encode() if donnees is not None else None)
        with urllib.request.urlopen(urllib.request.Request(self.base + chemin, data=corps)) as reponse:
            return reponse.headers, reponse.read()

    def test_interface_et_configuration(self):
        _, page = self.requete("/")
        self.assertIn(b"Mise en forme", page)
        _, config = self.requete("/api/configuration")
        self.assertIn("universite", json.loads(config)["normes"])

    def test_apercu_et_exports(self):
        donnees = {"texte": TEXTE, "reglages": {"police": "Arial"}}
        _, reponse = self.requete("/api/apercu", donnees)
        reponse = json.loads(reponse)
        self.assertIn("Premier chapitre", reponse["html"])
        self.assertGreater(reponse["mots"], 10)
        entetes, docx = self.requete("/api/docx", donnees)
        self.assertTrue(docx.startswith(b"PK"))
        self.assertIn(".docx", entetes["Content-Disposition"])
        _, importe = self.requete("/api/importer-docx", brut=docx)
        self.assertIn("# Premier chapitre", json.loads(importe)["texte"])


if __name__ == "__main__":
    unittest.main()
