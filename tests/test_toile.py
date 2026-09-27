import gzip
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from toile.css import Selecteur, analyser_css, appliquer_styles, couleur, longueur
from toile.html import Element, Texte, analyser, parcourir
from toile.mise_en_page import DessinRect, DessinTexte, Disposition
from toile.page import Page, charger
from toile.reseau import URL


class PolicesFactices:
    """Chaque caractère fait 10 px de large : la mise en page devient facile à vérifier."""

    def mesurer(self, police, texte):
        return 10 * len(texte)

    def metriques(self, police):
        return 12, 4


def elements(arbre, balise):
    return [n for n in parcourir(arbre) if isinstance(n, Element) and n.balise == balise]


class TestHTML(unittest.TestCase):
    def test_balises_implicites(self):
        arbre = analyser("<title>T</title><p>Bonjour")
        self.assertEqual(arbre.balise, "html")
        self.assertEqual([e.balise for e in arbre.enfants], ["head", "body"])

    def test_fermetures_automatiques(self):
        arbre = analyser("<ul><li>un<li>deux</ul><p>a<p>b")
        self.assertEqual(len(elements(arbre, "li")), 2)
        self.assertEqual([p.texte_contenu() for p in elements(arbre, "p")], ["a", "b"])

    def test_attributs_et_entites(self):
        arbre = analyser("""<a href="x.html?a=1&amp;b=2" data-x='a>b' class=lien checked>&eacute;t&eacute; &lt;3</a>""")
        lien = elements(arbre, "a")[0]
        self.assertEqual(lien.attributs, {"href": "x.html?a=1&b=2", "data-x": "a>b", "class": "lien", "checked": ""})
        self.assertEqual(lien.texte_contenu(), "été <3")

    def test_script_non_analyse(self):
        arbre = analyser("<script>if (a<b && c>d) {}</script><p>ok</p>")
        self.assertEqual(elements(arbre, "script")[0].texte_contenu(), "if (a<b && c>d) {}")
        self.assertEqual(len(elements(arbre, "p")), 1)

    def test_commentaires_et_balises_vides(self):
        arbre = analyser("<p>a<!-- <b>caché</b> --><br>b<img src=x>c</p>")
        p = elements(arbre, "p")[0]
        self.assertEqual([e.balise if isinstance(e, Element) else e.texte for e in p.enfants], ["a", "br", "b", "img", "c"])


class TestCSS(unittest.TestCase):
    def style_de(self, html, css, balise, rang=0):
        arbre = analyser(html)
        appliquer_styles(arbre, analyser_css(css))
        return elements(arbre, balise)[rang].style

    def test_specificite(self):
        css = "#special { color: red } p.a { color: green } p { color: blue } .a { color: yellow }"
        self.assertEqual(self.style_de('<p class="a" id="special">x</p>', css, "p")["color"], "#ff0000")
        self.assertEqual(self.style_de('<p class="a">x</p>', css, "p")["color"], "#008000")
        self.assertEqual(self.style_de("<p>x</p>", css, "p")["color"], "#0000ff")

    def test_ordre_et_style_en_ligne(self):
        css = "p { color: red } p { color: blue }"
        self.assertEqual(self.style_de("<p>x</p>", css, "p")["color"], "#0000ff")
        self.assertEqual(self.style_de('<p style="color: #0f0">x</p>', css, "p")["color"], "#00ff00")

    def test_heritage_et_tailles(self):
        style = self.style_de('<div style="font-size: 20px; color: navy"><p><b>x</b></p></div>', "p { font-size: 1.5em }", "b")
        self.assertEqual(style["color"], "#000080")
        self.assertEqual(style["font-size"], "30.0px")
        self.assertEqual(style["background-color"], "transparent")  # non héritée

    def test_selecteurs_descendant_et_enfant(self):
        arbre = analyser("<div class=menu><ul><li><a>x</a></li></ul></div><a>y</a>")
        a_menu, a_seul = elements(arbre, "a")
        self.assertTrue(Selecteur(".menu a").correspond(a_menu))
        self.assertFalse(Selecteur(".menu a").correspond(a_seul))
        self.assertTrue(Selecteur("li > a").correspond(a_menu))
        self.assertFalse(Selecteur("div > a").correspond(a_menu))
        self.assertFalse(Selecteur("a:hover").valide)

    def test_raccourcis(self):
        style = self.style_de("<p>x</p>", "p { margin: 1px 2px 3px; border: 2px solid #abc; padding: 5px }", "p")
        self.assertEqual([style[f"margin-{c}"] for c in ("top", "right", "bottom", "left")], ["1px", "2px", "3px", "2px"])
        self.assertEqual(style["border-left-width"], "2px")
        self.assertEqual(couleur(style["border-left-color"]), "#aabbcc")
        self.assertEqual(style["padding-bottom"], "5px")

    def test_regles_ignorees(self):
        regles = analyser_css("@media print { p { color: red } } @import url(x.css); /* rien */ h1 { color: blue }")
        self.assertEqual(len(regles), 1)

    def test_valeurs(self):
        self.assertEqual(couleur("rgb(255, 128, 0)"), "#ff8000")
        self.assertIsNone(couleur("transparent"))
        self.assertEqual(longueur("2em", 10), 20)
        self.assertEqual(longueur("50%", 16, 300), 150)
        self.assertIsNone(longueur("auto"))


class TestMiseEnPage(unittest.TestCase):
    def disposer(self, html, largeur=200):
        page = Page(URL("about:test"), html)
        return page, Disposition(page.arbre, PolicesFactices(), largeur)

    def textes(self, disposition):
        return [(d.texte, d.x, d.y) for d in disposition.dessins if isinstance(d, DessinTexte)]

    def test_retour_a_la_ligne(self):
        # Largeur utile : 200 - 2×8 de marge = 184 px, soit 18 caractères par ligne.
        _, d = self.disposer("<p>aaaa bbbb cccc dddd eeee</p>")
        lignes = sorted({y for _, _, y in self.textes(d)})
        self.assertEqual(len(lignes), 2)
        self.assertEqual([t for t, _, _ in self.textes(d)], ["aaaa", "bbbb", "cccc", "dddd", "eeee"])

    def test_blocs_empiles(self):
        _, d = self.disposer("<div style='height:50px'></div><p style='margin:0'>x</p>")
        (texte, x, y), = self.textes(d)
        self.assertEqual(x, 8)
        self.assertGreaterEqual(y, 8 + 50)

    def test_centrage(self):
        _, d = self.disposer("<div style='width:100px; margin: 0 auto; background: red'>x</div>", largeur=316)
        fond = [r for r in d.dessins if isinstance(r, DessinRect) and r.couleur == "#ff0000"][0]
        self.assertEqual((fond.x1, fond.x2), (108, 208))

    def test_display_none(self):
        _, d = self.disposer("<p>visible</p><p style='display:none'>caché</p>")
        self.assertEqual([t for t, _, _ in self.textes(d)], ["visible"])

    def test_liens_et_ancres(self):
        _, d = self.disposer("<p><a href='page2.html'>clic</a></p><h2 id='fin'>Fin</h2>")
        zone = d.liens[0]
        self.assertEqual(d.lien_a(zone.x1 + 1, zone.y1 + 1), "page2.html")
        self.assertIsNone(d.lien_a(zone.x2 + 50, zone.y1 + 1))
        self.assertIn("fin", d.ancres)

    def test_texte_preformate(self):
        _, d = self.disposer("<pre>a  b\nc</pre>")
        self.assertEqual([t for t, _, _ in self.textes(d)], ["a  b", "c"])

    def test_fond_de_page(self):
        _, d = self.disposer("<body style='background:#123456'><p>x</p></body>")
        self.assertEqual(d.fond, "#123456")


class ServeurTest(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/redirection":
            self.send_response(301)
            self.send_header("Location", "/gzip")
            self.end_headers()
        elif self.path == "/gzip":
            corps = gzip.compress("<title>Compressé</title><p>données gzip</p>".encode())
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)
        elif self.path == "/morceaux":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for morceau in ("<p>premier ", "morceau, ", "deuxième</p>"):
                donnees = morceau.encode()
                self.wfile.write(f"{len(donnees):x}\r\n".encode() + donnees + b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
        elif self.path == "/style.css":
            self.send_response(200)
            self.send_header("Content-Type", "text/css")
            self.end_headers()
            self.wfile.write(b"p { color: #ff0000 }")
        elif self.path == "/avec-css":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b'<link rel="stylesheet" href="style.css"><p>rouge</p>')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


class TestReseau(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.serveur = ThreadingHTTPServer(("127.0.0.1", 0), ServeurTest)
        threading.Thread(target=cls.serveur.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.serveur.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()
        cls.serveur.server_close()

    def test_redirection_et_gzip(self):
        page = charger(self.base + "/redirection")
        self.assertEqual(page.titre, "Compressé")
        self.assertEqual(str(page.url), self.base + "/gzip")

    def test_envoi_par_morceaux(self):
        self.assertEqual(charger(self.base + "/morceaux").texte(), "premier morceau, deuxième")

    def test_feuille_de_style_externe(self):
        page = charger(self.base + "/avec-css")
        self.assertEqual(elements(page.arbre, "p")[0].style["color"], "#ff0000")

    def test_erreurs(self):
        self.assertIn("Impossible", charger("http://127.0.0.1:1/").texte())
        self.assertIn("Impossible", charger("ftp://exemple.fr").texte())

    def test_urls(self):
        url = URL("https://exemple.fr/dossier/page.html?x=1#haut")
        self.assertEqual((url.hote, url.port, url.chemin, url.ancre), ("exemple.fr", 443, "/dossier/page.html?x=1", "haut"))
        self.assertEqual(str(url.resoudre("../img/a.png")), "https://exemple.fr/img/a.png")
        self.assertEqual(str(url.resoudre("//autre.fr/b")), "https://autre.fr/b")
        self.assertEqual(str(URL("exemple.fr")), "https://exemple.fr/")

    def test_fichier_local_et_data(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = os.path.join(dossier, "page.html")
            with open(chemin, "w", encoding="utf-8") as f:
                f.write("<h1>Fichier local</h1>")
            self.assertEqual(charger("file://" + chemin).texte(), "Fichier local")
        self.assertEqual(charger("data:text/html,<b>Bonjour%20!</b>").texte(), "Bonjour !")

    def test_pages_integrees(self):
        for nom in ("accueil", "demo", "fonctionnement"):
            page = charger(f"about:{nom}")
            self.assertTrue(page.titre, nom)
            Disposition(page.arbre, PolicesFactices(), 800)


class TestCapture(unittest.TestCase):
    def test_capture_png(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow n'est pas installé")
        from toile.capture import capturer
        with tempfile.TemporaryDirectory() as dossier:
            chemin = os.path.join(dossier, "capture.png")
            capturer("data:text/html,<h1 style='color:red'>Salut</h1>", chemin, largeur=300)
            with open(chemin, "rb") as f:
                self.assertTrue(f.read(8).startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
