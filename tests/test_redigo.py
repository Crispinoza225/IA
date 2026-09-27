import http.client
import io
import json
import threading
import time
import unittest
import zipfile

from memoire.source import Reference, Titre, lire, numeroter
from redigo import bibliographie as biblio
from redigo import paiement
from redigo.base import Base
from redigo.securite import Limiteur, hacher_mot_de_passe, verifier_mot_de_passe
from redigo.serveur import Configuration, creer_serveur

try:
    import reportlab  # noqa: F401
    PDF = True
except ImportError:
    PDF = False

REFERENCES = [biblio.nettoyer(r) for r in [
    dict(cle="dupont2020", type="livre", auteurs="Dupont, Jean-Pierre ; Martin, Paul", annee="2020",
         titre="La pédagogie numérique", editeur="Dunod", lieu="Paris", edition="2"),
    dict(cle="dupont2020b", type="article", auteurs="Dupont, Jean-Pierre ; Martin, Paul", annee="2020",
         titre="Apprendre en ligne", revue="Revue française de pédagogie", volume="12", numero="3", pages="45-67",
         doi="https://doi.org/10.4000/rfp.123"),
    dict(cle="leroy", type="chapitre", auteurs="Leroy, Anne ; Petit, Bruno ; Durand, Claire", annee="2019",
         titre="Le tutorat", ouvrage="Manuel", directeurs="Bernard, Sophie", editeur="PUF", pages="10-20"),
    dict(cle="oms", type="site", auteurs="Organisation mondiale de la santé", annee="",
         titre="Santé mentale des étudiants", url="https://who.int/x", consulte="2024-03-01"),
]]


def texte_de(morceaux):
    return "".join(f"_{m.texte}_" if m.italique else m.texte for m in morceaux)


class TestBibliographie(unittest.TestCase):
    def test_auteurs(self):
        self.assertEqual(biblio.initiales("Jean-Pierre"), "J.-P.")
        self.assertEqual(biblio.initiales("Marie Anne"), "M. A.")
        liste = biblio.auteurs("Dupont, Jean ; Ministère de l'Éducation et de la Recherche")
        self.assertEqual(liste, [("Dupont", "Jean"), ("Ministère de l'Éducation et de la Recherche", "")])
        self.assertEqual(biblio.auteurs_courts(biblio.auteurs("A, B ; C, D ; E, F")), "A et al.")

    def test_apa(self):
        entrees = [texte_de(e) for e in biblio.entrees(REFERENCES, "apa")]
        self.assertIn("Dupont, J.-P. et Martin, P. (2020a). Apprendre en ligne. _Revue française de pédagogie_, "
                      "_12_(3), 45–67. https://doi.org/10.4000/rfp.123", entrees)
        self.assertIn("Dupont, J.-P. et Martin, P. (2020b). _La pédagogie numérique_ (2ᵉ éd.). Dunod.", entrees)
        self.assertIn("Leroy, A., Petit, B. et Durand, C. (2019). Le tutorat. Dans S. Bernard (dir.), _Manuel_ "
                      "(p. 10–20). PUF.", entrees)
        self.assertTrue(entrees[0].startswith("Dupont"))  # triées par auteur

    def test_iso690(self):
        entrees = [texte_de(e) for e in biblio.entrees(REFERENCES, "iso690")]
        self.assertIn("DUPONT, Jean-Pierre et MARTIN, Paul. _La pédagogie numérique_. 2ᵉ éd. Paris : Dunod, 2020b.",
                      entrees)
        site = next(e for e in entrees if e.startswith("ORGANISATION"))
        self.assertIn("[en ligne]", site)
        self.assertIn("[Consulté le 1er mars 2024]", site)

    def test_citations_et_placement(self):
        texte = ("# Introduction\n\nSelon [@dupont2020, p. 12] et @dupont2020b, puis [@leroy; @oms] "
                 "et [@inconnue]. Écrire à a@b.fr ou @quelqu_un.\n\n# Annexes\n\nTexte")
        blocs, citees, inconnues = biblio.appliquer(lire(texte), REFERENCES, "apa")
        paragraphe = texte_de(blocs[1].morceaux)
        self.assertEqual(paragraphe, "Selon (Dupont et Martin, 2020b, p. 12) et Dupont et Martin (2020a), puis "
                                     "(Leroy et al., 2019 ; Organisation mondiale de la santé, s.d.) et [@inconnue]. "
                                     "Écrire à a@b.fr ou @quelqu_un.")
        self.assertEqual(sorted(citees), ["dupont2020", "dupont2020b", "leroy", "oms"])
        self.assertEqual(inconnues, ["inconnue"])
        titres = [b.texte for b in blocs if isinstance(b, Titre)]
        self.assertEqual(titres, ["Introduction", "Bibliographie", "Annexes"])  # avant les annexes
        self.assertEqual(sum(isinstance(b, Reference) for b in blocs), 4)

    def test_placement_choisi(self):
        blocs, _, _ = biblio.appliquer(lire("# Références\n\nIntro\n\n# Fin\n\n[@leroy]"), REFERENCES, "apa")
        self.assertIsInstance(blocs[1], Reference)  # juste sous le titre existant
        blocs, _, _ = biblio.appliquer(lire("A [@leroy]\n\n[bibliographie]\n\nB"), REFERENCES, "apa")
        self.assertEqual([type(b).__name__ for b in blocs], ["Paragraphe", "Reference", "Paragraphe"])
        blocs, _, _ = biblio.appliquer(lire("Rien de cité"), REFERENCES, "apa", toutes=True)
        self.assertEqual(sum(isinstance(b, Reference) for b in blocs), 4)

    def test_bibtex(self):
        references = biblio.importer_bibtex(r"""
@comment{Exporté par Zotero}
@article{smith2019, author = {Smith, John and Jane M. Doe}, title = {{Deep} learning \'et\'e},
  journal = "Nature", year = 2019, volume = {5}, number = {2}, pages = {1--10}, doi = {10.1/x}}
@incollection{c, author={Durand, Luc}, title={Chapitre}, booktitle={Le livre}, editor={Martin, Paul},
  publisher={Seuil}, address={Paris}, year={2001}, pages={3--9}}
""")
        self.assertEqual(len(references), 2)
        smith, chapitre = references
        self.assertEqual((smith["cle"], smith["type"], smith["auteurs"], smith["titre"], smith["pages"]),
                         ("smith2019", "article", "Smith, John ; Doe, Jane M.", "Deep learning été", "1-10"))
        self.assertEqual((chapitre["type"], chapitre["ouvrage"], chapitre["directeurs"]),
                         ("chapitre", "Le livre", "Martin, Paul"))

    def test_bout_en_bout_docx(self):
        from memoire.docx import ecrire_docx
        from memoire.reglages import Reglages
        blocs, _, _ = biblio.appliquer(lire("# Intro\n\nVoir [@leroy]."), REFERENCES, "apa")
        contenu = ecrire_docx(numeroter(blocs, "decimale"), Reglages(), mention="Version gratuite")
        with zipfile.ZipFile(io.BytesIO(contenu)) as archive:
            document = archive.read("word/document.xml").decode()
            self.assertIn('w:val="Bibliography"', document)
            self.assertIn("Version gratuite", archive.read("word/footer1.xml").decode())
            self.assertIn('w:styleId="Bibliography"', archive.read("word/styles.xml").decode())


class TestSecurite(unittest.TestCase):
    def test_mots_de_passe(self):
        empreinte = hacher_mot_de_passe("secret123")
        self.assertTrue(verifier_mot_de_passe("secret123", empreinte))
        self.assertFalse(verifier_mot_de_passe("secret124", empreinte))
        self.assertFalse(verifier_mot_de_passe("x", "n'importe quoi"))
        self.assertNotEqual(empreinte, hacher_mot_de_passe("secret123"))  # sel différent

    def test_limiteur(self):
        limiteur = Limiteur(3, 60)
        self.assertEqual([limiteur.autorise("ip", t) for t in (0, 1, 2, 3)], [True, True, True, False])
        self.assertTrue(limiteur.autorise("ip", 61))
        self.assertTrue(limiteur.autorise("autre", 3))


class TestBaseEtPaiement(unittest.TestCase):
    def setUp(self):
        self.base = Base(":memory:")
        self.id = self.base.creer_utilisateur("lea@etu.univ-exemple.fr", "Léa", "x")

    def test_formules_et_licences(self):
        self.assertEqual(self.base.formule(self.base.utilisateur(self.id))[0], "gratuit")
        self.base.ajouter_licence("univ-exemple.fr", "Université Exemple", "2999-01-01", {"police": "Arial"})
        code, _, licence = self.base.formule(self.base.utilisateur(self.id))
        self.assertEqual((code, licence["universite"]), ("universite", "Université Exemple"))  # sous-domaine compris
        self.base.ajouter_licence("univ-exemple.fr", "Université Exemple", "2000-01-01")
        self.assertEqual(self.base.formule(self.base.utilisateur(self.id))[0], "gratuit")  # licence expirée

    def test_paiement_compte_une_seule_fois(self):
        self.assertTrue(self.base.activer_pass(self.id, "stripe", "cs_1", 990))
        fin = self.base.utilisateur(self.id)["pass_jusqua"]
        self.assertFalse(self.base.activer_pass(self.id, "stripe", "cs_1", 990))  # notification reçue deux fois
        self.assertEqual(self.base.utilisateur(self.id)["pass_jusqua"], fin)
        self.assertTrue(self.base.activer_pass(self.id, "stripe", "cs_2", 990))  # un second achat prolonge
        self.assertGreater(self.base.utilisateur(self.id)["pass_jusqua"], fin)
        self.assertEqual(self.base.formule(self.base.utilisateur(self.id))[0], "pass")

    def test_signature_stripe(self):
        corps, secret, t = b'{"type":"x"}', "whsec_test", int(time.time())
        entete = f"t={t},v1={paiement.signer(corps, secret, t)}"
        self.assertTrue(paiement.verifier_signature(corps, entete, secret))
        self.assertFalse(paiement.verifier_signature(corps + b" ", entete, secret))
        self.assertFalse(paiement.verifier_signature(corps, entete, "autre"))
        self.assertFalse(paiement.verifier_signature(corps, entete, secret, maintenant=t + 3600))  # trop vieux
        self.assertFalse(paiement.verifier_signature(corps, "", secret))

    def test_evenement_stripe(self):
        evenement = {"type": "checkout.session.completed", "data": {"object": {
            "id": "cs_9", "payment_status": "paid", "client_reference_id": str(self.id), "amount_total": 990}}}
        self.assertTrue(paiement.traiter_evenement(self.base, evenement))
        self.assertFalse(paiement.traiter_evenement(self.base, evenement))
        evenement["data"]["object"].update(id="cs_10", payment_status="unpaid")
        self.assertFalse(paiement.traiter_evenement(self.base, evenement))

    def test_versions_limitees(self):
        projet = self.base.creer_projet(self.id, "M", "", {})
        for i in range(8):
            self.base.creer_version(projet, f"v{i}", {}, "", True, 1, garder=5)
        self.base.creer_version(projet, "nommée", {}, "Envoyée", False, 1, garder=5)
        versions = self.base.versions(projet)
        self.assertEqual(len(versions), 6)  # 5 automatiques + la version nommée, jamais effacée


class Client:
    """Un petit navigateur : garde le cookie de session et réutilise la connexion (comme un vrai navigateur)."""

    ouverts = []

    def __init__(self, port):
        self.connexion = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        self.cookie = None
        Client.ouverts.append(self)

    @classmethod
    def fermer_tous(cls):
        for client in cls.ouverts:
            client.connexion.close()
        cls.ouverts.clear()

    def __call__(self, methode, chemin, donnees=None, entetes=None, brut=None):
        corps = brut if brut is not None else (json.dumps(donnees).encode() if donnees is not None else None)
        tous = {"X-Redigo": "1", "Content-Type": "application/json", **(entetes or {})}
        if self.cookie:
            tous["Cookie"] = self.cookie
        self.connexion.request(methode, chemin, body=corps, headers=tous)
        reponse = self.connexion.getresponse()
        contenu = reponse.read()
        cookie = reponse.getheader("Set-Cookie")
        if cookie:
            self.cookie = cookie.split(";")[0]
        if reponse.getheader("Content-Type", "").startswith("application/json"):
            contenu = json.loads(contenu)
        return reponse.status, contenu, reponse


class TestServeur(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = Configuration(base=":memory:", url="http://test", demo=True, stripe_secret_webhook="whsec_test")
        cls.serveur = creer_serveur(cls.config, "127.0.0.1", 0)
        threading.Thread(target=cls.serveur.serve_forever, daemon=True).start()
        cls.port = cls.serveur.server_address[1]

    def tearDown(self):
        Client.fermer_tous()

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()
        cls.serveur.server_close()

    def inscrire(self, email):
        client = Client(self.port)
        statut, moi, _ = client("POST", "/api/inscription", {"email": email, "nom": "Awa", "mot_de_passe": "secret123"})
        self.assertEqual(statut, 201, moi)
        return client

    def test_pages(self):
        client = Client(self.port)
        for chemin in ("/", "/app", "/partage/abc", "/static/app.js", "/static/style.css"):
            statut, _, reponse = client("GET", chemin)
            self.assertEqual(statut, 200, chemin)
            self.assertIn("frame-ancestors 'none'", reponse.getheader("Content-Security-Policy"))
        self.assertEqual(client("GET", "/static/../base.py")[0], 404)

    def test_parcours_complet(self):
        client = self.inscrire("awa@exemple.fr")
        statut, projet, _ = client("POST", "/api/projets", {"titre": "Mon mémoire", "exemple": True})
        self.assertEqual(statut, 201)
        pid = projet["id"]
        self.assertEqual(projet["reglages"]["garde"]["auteur"], "Awa")
        # formule gratuite : un seul mémoire
        self.assertEqual(client("POST", "/api/projets", {"titre": "Deux"})[0], 402)
        # l'aperçu contient la bibliographie construite à partir des citations
        _, apercu, _ = client("POST", f"/api/projets/{pid}/apercu", {})
        self.assertIn("Holec, H. (1981)", apercu["html"])
        self.assertEqual(apercu["inconnues"], [])
        # enregistrement, puis conflit si la révision est périmée
        statut, reponse, _ = client("PUT", f"/api/projets/{pid}", {"revision": projet["revision"], "texte": "# A\n\n[@holec1981]"})
        self.assertEqual(statut, 200)
        self.assertEqual(client("PUT", f"/api/projets/{pid}", {"revision": projet["revision"], "texte": "x"})[0], 409)
        # références
        statut, ref, _ = client("POST", f"/api/projets/{pid}/references", {"type": "livre", "auteurs": "Kone, Awa",
                                                                           "annee": "2024", "titre": "Titre"})
        self.assertEqual((statut, ref["cle"]), (201, "kone2024"))
        self.assertEqual(client("POST", f"/api/projets/{pid}/references", {"cle": "kone2024", "titre": "B"})[0], 400)
        _, resultat, _ = client("POST", f"/api/projets/{pid}/references/bibtex",
                                {"bibtex": "@book{kone2024, title={Doublon}}\n@book{neuf, title={Nouveau}, year={2020}}"})
        self.assertEqual((resultat["ajoutees"], resultat["ignorees"]), (1, ["kone2024"]))
        # exports gratuits : la mention est présente
        statut, docx, _ = client("POST", f"/api/projets/{pid}/export/docx", {})
        with zipfile.ZipFile(io.BytesIO(docx)) as archive:
            self.assertIn("version gratuite", archive.read("word/footer1.xml").decode())
        # versions
        statut, _, _ = client("POST", f"/api/projets/{pid}/versions", {"libelle": "Envoyée"})
        _, versions, _ = client("GET", f"/api/projets/{pid}/versions")
        vid = next(v["id"] for v in versions["versions"] if v["libelle"] == "Envoyée")
        client("PUT", f"/api/projets/{pid}", {"revision": reponse["revision"], "texte": "tout effacé"})
        _, restaure, _ = client("POST", f"/api/projets/{pid}/versions/{vid}/restaurer", {})
        self.assertEqual(restaure["texte"], "# A\n\n[@holec1981]")
        # partage et commentaires du directeur, sans compte
        _, partage, _ = client("POST", f"/api/projets/{pid}/partages", {"nom": "Mme Bernard"})
        directeur = Client(self.port)
        statut, vue, _ = directeur("GET", f"/api/partage/{partage['jeton']}")
        self.assertEqual((statut, vue["etudiant"]), (200, "Awa"))
        statut, _, _ = directeur("POST", f"/api/partage/{partage['jeton']}/commentaires",
                                 {"auteur": "S. Bernard", "texte": "Précise ta source.", "extrait": "[@holec1981]"})
        self.assertEqual(statut, 201)
        self.assertEqual(directeur("GET", f"/api/projets/{pid}")[0], 401)  # le lien ne donne pas accès au reste
        _, liste, _ = client("GET", "/api/projets")
        self.assertEqual(liste["projets"][0]["nouveaux_commentaires"], 1)
        _, commentaires, _ = client("GET", f"/api/projets/{pid}/commentaires?lu=1")
        cid = commentaires["commentaires"][0]["id"]
        client("POST", f"/api/projets/{pid}/commentaires", {"texte": "C'est fait.", "parent_id": cid})
        client("POST", f"/api/projets/{pid}/commentaires/{cid}/resolu", {"resolu": True})
        _, liste, _ = client("GET", "/api/projets")
        self.assertEqual(liste["projets"][0]["nouveaux_commentaires"], 0)
        # un lien désactivé ne fonctionne plus
        _, partages, _ = client("GET", f"/api/projets/{pid}/partages")
        client("DELETE", f"/api/projets/{pid}/partages/{partages['partages'][0]['id']}")
        self.assertEqual(directeur("GET", f"/api/partage/{partage['jeton']}")[0], 404)
        # Pass (mode démonstration) : plus de mention, plusieurs mémoires
        _, moi, _ = client("POST", "/api/paiement/commande", {})
        self.assertEqual(moi["formule"]["code"], "pass")
        _, docx, _ = client("POST", f"/api/projets/{pid}/export/docx", {})
        with zipfile.ZipFile(io.BytesIO(docx)) as archive:
            self.assertNotIn("version gratuite", archive.read("word/footer1.xml").decode())
        self.assertEqual(client("POST", "/api/projets", {"titre": "Deux"})[0], 201)

    def test_securite(self):
        alice = self.inscrire("alice@exemple.fr")
        _, projet, _ = alice("POST", "/api/projets", {"titre": "Secret"})
        bob = self.inscrire("bob@exemple.fr")
        for methode, chemin in [("GET", f"/api/projets/{projet['id']}"), ("POST", f"/api/projets/{projet['id']}/apercu"),
                                ("GET", f"/api/projets/{projet['id']}/partages"),
                                ("DELETE", f"/api/projets/{projet['id']}")]:
            self.assertEqual(bob(methode, chemin, {} if methode == "POST" else None)[0], 404, chemin)
        # sans l'en-tête X-Redigo (requête venue d'un autre site), rien ne passe
        statut, _, _ = alice("POST", "/api/projets", {"titre": "x"}, entetes={"X-Redigo": "0"})
        self.assertEqual(statut, 403)
        # mauvais mot de passe
        inconnu = Client(self.port)
        self.assertEqual(inconnu("POST", "/api/connexion", {"email": "alice@exemple.fr", "mot_de_passe": "faux"})[0], 401)
        self.assertEqual(inconnu("POST", "/api/connexion", {"email": "alice@exemple.fr", "mot_de_passe": "secret123"})[0], 200)
        # déconnexion
        alice("POST", "/api/deconnexion", {})
        self.assertEqual(alice("GET", "/api/moi")[0], 401)
        # réglages hostiles ramenés à des valeurs sûres
        _, projet, _ = bob("POST", "/api/projets", {"titre": "T", "reglages": {"couleur_titres": "#</sty", "police": "<b>"}})
        self.assertEqual((projet["reglages"]["couleur_titres"], projet["reglages"]["police"]), ("#000000", "Times New Roman"))

    def test_webhook_stripe(self):
        client = self.inscrire("paie@exemple.fr")
        _, moi, _ = client("GET", "/api/moi")
        utilisateur = self.serveur.base.utilisateur_par_email("paie@exemple.fr")
        corps = json.dumps({"type": "checkout.session.completed", "data": {"object": {
            "id": "cs_test_1", "payment_status": "paid", "client_reference_id": str(utilisateur["id"]),
            "amount_total": 990}}}).encode()
        t = int(time.time())
        anonyme = Client(self.port)
        statut, _, _ = anonyme("POST", "/api/paiement/webhook", brut=corps, entetes={"X-Redigo": "", "Stripe-Signature": f"t={t},v1=faux"})
        self.assertEqual(statut, 400)
        signature = f"t={t},v1={paiement.signer(corps, 'whsec_test', t)}"
        statut, _, _ = anonyme("POST", "/api/paiement/webhook", brut=corps, entetes={"X-Redigo": "", "Stripe-Signature": signature})
        self.assertEqual(statut, 200)
        self.assertEqual(client("GET", "/api/moi")[1]["formule"]["code"], "pass")

    def test_mot_de_passe_oublie(self):
        self.inscrire("oubli@exemple.fr")
        utilisateur = self.serveur.base.utilisateur_par_email("oubli@exemple.fr")
        jeton = self.serveur.base.demander_reinitialisation(utilisateur["id"])
        client = Client(self.port)
        self.assertEqual(client("POST", "/api/mot-de-passe/reinitialiser", {"jeton": jeton, "mot_de_passe": "nouveau123"})[0], 200)
        self.assertEqual(client("POST", "/api/mot-de-passe/reinitialiser", {"jeton": jeton, "mot_de_passe": "encore123"})[0], 400)
        self.assertEqual(Client(self.port)("POST", "/api/connexion", {"email": "oubli@exemple.fr", "mot_de_passe": "nouveau123"})[0], 200)

    @unittest.skipUnless(PDF, "reportlab n'est pas installé")
    def test_pdf_avec_mention(self):
        client = self.inscrire("pdf@exemple.fr")
        _, projet, _ = client("POST", "/api/projets", {"titre": "PDF", "exemple": True})
        statut, contenu, reponse = client("POST", f"/api/projets/{projet['id']}/export/pdf", {})
        self.assertEqual(statut, 200)
        self.assertTrue(contenu.startswith(b"%PDF"))
        self.assertIn(".pdf", reponse.getheader("Content-Disposition"))


if __name__ == "__main__":
    unittest.main()
