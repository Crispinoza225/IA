import datetime
import http.client
import json
import threading
import unittest

from cotiz import tontine as T
from cotiz.base import Base, Interdit, Introuvable
from cotiz.calendrier import ajouter_mois, echeance, formater, vers_unites
from cotiz.serveur import Configuration, creer_serveur

JOUR = datetime.date


class TestCalendrier(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(ajouter_mois(JOUR(2026, 1, 31), 1), JOUR(2026, 2, 28))
        self.assertEqual(ajouter_mois(JOUR(2028, 1, 31), 1), JOUR(2028, 2, 29))  # année bissextile
        self.assertEqual(ajouter_mois(JOUR(2026, 11, 15), 3), JOUR(2027, 2, 15))
        self.assertEqual(echeance(JOUR(2026, 10, 1), "hebdomadaire", 2), JOUR(2026, 10, 15))
        self.assertEqual(echeance(JOUR(2026, 10, 1), "quinzaine", 2), JOUR(2026, 10, 29))

    def test_montants(self):
        self.assertEqual(vers_unites("10 000", "XOF"), 10000)
        self.assertEqual(vers_unites("12,50", "EUR"), 1250)
        self.assertEqual(formater(1_500_000, "XOF"), "1 500 000 FCFA")
        self.assertEqual(formater(1250, "EUR"), "12,50 €")
        with self.assertRaises(ValueError):
            vers_unites("dix", "XOF")
        with self.assertRaises(ValueError):
            vers_unites("-5", "XOF")

    def test_telephones(self):
        self.assertEqual(T.telephone_normalise("+221 77 123 45 67"), "+221771234567")
        self.assertEqual(T.telephone_normalise("00221-77-123-45-67"), "+221771234567")
        with self.assertRaises(ValueError):
            T.telephone_normalise("123")


class TestTontine(unittest.TestCase):
    def setUp(self):
        self.base = Base(":memory:")
        self.awa = self.base.utilisateur(self.base.creer_utilisateur("+221770000001", "Awa", "x"))
        self.gid = T.creer_groupe(self.base, self.awa, "Les amies", "XOF", 10000, "mensuelle", "2026-10-05",
                                  "inscription", penalite=1000, jours_grace=2)
        self.fatou = T.ajouter_membre(self.base, self.gid, "Awa", "Fatou", "+221770000002", mains=2)
        self.moussa = T.ajouter_membre(self.base, self.gid, "Awa", "Moussa", "+221770000003")

    def test_calendrier_et_mains(self):
        T.demarrer(self.base, self.gid, "Awa")
        tours = self.base.tous("SELECT * FROM tours WHERE groupe_id = ? ORDER BY numero", (self.gid,))
        self.assertEqual([t["echeance"] for t in tours], ["2026-10-05", "2026-11-05", "2026-12-05", "2027-01-05"])
        noms = [self.base.un("SELECT nom FROM membres WHERE id = ?", (t["beneficiaire_id"],))["nom"] for t in tours]
        self.assertEqual(noms, ["Awa", "Fatou", "Fatou", "Moussa"])  # Fatou a deux mains : elle reçoit deux fois
        etat = T.etat_tour(self.base, T.groupe(self.base, self.gid), tours[0], JOUR(2026, 10, 1))
        self.assertEqual(etat["attendu"], 40000)
        self.assertEqual([l["du"] for l in etat["lignes"]], [10000, 20000, 10000])
        with self.assertRaises(ValueError):
            T.ajouter_membre(self.base, self.gid, "Awa", "Tard", "+221770000009")  # trop tard, la tontine a commencé

    def test_tirage_au_sort(self):
        self.base.modifier("UPDATE groupes SET mode_ordre = 'tirage' WHERE id = ?", (self.gid,))
        T.demarrer(self.base, self.gid, "Awa")
        beneficiaires = sorted(t["beneficiaire_id"] for t in self.base.tous("SELECT * FROM tours WHERE groupe_id = ?", (self.gid,)))
        self.assertEqual(beneficiaires, sorted([1, self.fatou, self.fatou, self.moussa]))

    def test_cycle_de_paiement(self):
        T.demarrer(self.base, self.gid, "Awa")
        g = T.groupe(self.base, self.gid)
        tour = T.tour_courant(self.base, self.gid)
        # Fatou déclare à temps, l'organisatrice confirme plus tard : pas de pénalité.
        cid = T.enregistrer_cotisation(self.base, self.gid, tour["id"], self.fatou, "Fatou", 20000, "mobile_money",
                                       "MP123", jour=JOUR(2026, 10, 4))
        self.assertEqual(T.etat_tour(self.base, g, tour, JOUR(2026, 10, 4))["lignes"][1]["statut"], "a_confirmer")
        T.decider_cotisation(self.base, self.gid, cid, "Awa", True, jour=JOUR(2026, 10, 20))
        with self.assertRaises(ValueError):
            T.decider_cotisation(self.base, self.gid, cid, "Awa", True)  # déjà traité
        # Awa paie en espèces à temps ; Moussa paie après la fin du délai de grâce : pénalité.
        T.enregistrer_cotisation(self.base, self.gid, tour["id"], 1, "Awa", 10000, "especes", confirmee=True, jour=JOUR(2026, 10, 5))
        self.assertEqual(T.etat_tour(self.base, g, tour, JOUR(2026, 10, 8))["lignes"][2]["statut"], "en_retard")
        rappels = T.rappels(self.base, self.gid, JOUR(2026, 10, 8))
        self.assertEqual([r["nom"] for r in rappels], ["Moussa"])
        self.assertTrue(rappels[0]["whatsapp"].startswith("https://wa.me/221770000003?text="))
        with self.assertRaises(ValueError):
            T.verser(self.base, self.gid, tour["id"], "Awa", jour=JOUR(2026, 10, 8))  # Moussa n'a pas payé
        T.enregistrer_cotisation(self.base, self.gid, tour["id"], self.moussa, "Awa", 10000, "especes", confirmee=True,
                                 jour=JOUR(2026, 10, 8))
        penalites = self.base.tous("SELECT membre_id, penalite FROM cotisations ORDER BY id")
        self.assertEqual([p["penalite"] for p in penalites], [0, 0, 1000])
        T.verser(self.base, self.gid, tour["id"], "Awa", jour=JOUR(2026, 10, 9))
        self.assertEqual(self.base.un("SELECT montant_verse FROM tours WHERE id = ?", (tour["id"],))["montant_verse"], 40000)
        self.assertEqual(T.tour_courant(self.base, self.gid)["numero"], 2)
        # Fiabilité : Fatou à temps (100 %), Moussa en retard (0 %).
        self.assertEqual(T.fiabilite(self.base, "+221770000002", JOUR(2026, 10, 9)), 100)
        self.assertEqual(T.fiabilite(self.base, "+221770000003", JOUR(2026, 10, 9)), 0)
        self.assertIsNone(T.fiabilite(self.base, "+221779999999"))

    def test_verser_de_force_et_fin(self):
        T.demarrer(self.base, self.gid, "Awa")
        for numero in range(1, 5):
            tour = T.tour_courant(self.base, self.gid)
            self.assertEqual(tour["numero"], numero)
            T.verser(self.base, self.gid, tour["id"], "Awa", forcer=True)
        self.assertEqual(T.groupe(self.base, self.gid)["statut"], "termine")
        dernier = self.base.un("SELECT * FROM journal WHERE groupe_id = ? AND action = 'versement' ORDER BY id DESC", (self.gid,))
        self.assertIn("impayes", json.loads(dernier["details"]))  # les impayés restent notés

    def test_journal_infalsifiable(self):
        T.demarrer(self.base, self.gid, "Awa")
        intact, n = T.verifier_journal(self.base, self.gid)
        self.assertTrue(intact)
        self.assertEqual(n, 4)  # création, deux ajouts, démarrage
        self.base.modifier("UPDATE journal SET details = '{\"membre\": \"Quelqu''un d''autre\"}' WHERE id = 2")
        self.assertEqual(T.verifier_journal(self.base, self.gid), (False, 2))
        self.base.modifier("DELETE FROM journal WHERE id = 2")
        self.assertEqual(T.verifier_journal(self.base, self.gid), (False, 2))  # une ligne effacée casse aussi la chaîne

    def test_droits_et_invitation(self):
        bob = self.base.utilisateur(self.base.creer_utilisateur("+221770000005", "Bob", "x"))
        with self.assertRaises(Introuvable):
            T.membre_de(self.base, self.gid, bob)
        code = T.groupe(self.base, self.gid)["code"]
        T.rejoindre(self.base, code, bob)
        with self.assertRaises(Interdit):
            T.exiger_organisateur(self.base, self.gid, bob)
        self.assertEqual(T.rejoindre(self.base, code, bob), self.gid)  # rejoindre deux fois ne crée pas de doublon
        self.assertEqual(self.base.un("SELECT count(*) AS n FROM membres WHERE groupe_id = ?", (self.gid,))["n"], 4)

    def test_compte_cree_apres_coup(self):
        """Moussa a été ajouté sans compte ; en s'inscrivant avec son numéro, il retrouve sa tontine."""
        moussa = self.base.utilisateur(self.base.creer_utilisateur("+221770000003", "Moussa", "x"))
        self.assertEqual(T.membre_de(self.base, self.gid, moussa)["id"], self.moussa)


class Client:
    ouverts = []

    def __init__(self, port):
        self.connexion = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        self.cookie = None
        Client.ouverts.append(self)

    def __call__(self, methode, chemin, donnees=None, entetes=None):
        tous = {"X-Cotiz": "1", "Content-Type": "application/json", **(entetes or {})}
        if self.cookie:
            tous["Cookie"] = self.cookie
        self.connexion.request(methode, chemin, body=json.dumps(donnees).encode() if donnees is not None else None, headers=tous)
        reponse = self.connexion.getresponse()
        contenu = reponse.read()
        if reponse.getheader("Set-Cookie"):
            self.cookie = reponse.getheader("Set-Cookie").split(";")[0]
        if reponse.getheader("Content-Type", "").startswith("application/json"):
            contenu = json.loads(contenu)
        return reponse.status, contenu


class TestServeur(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.serveur = creer_serveur(Configuration(base=":memory:", url="http://test", demo=True), "127.0.0.1", 0)
        threading.Thread(target=cls.serveur.serve_forever, daemon=True).start()
        cls.port = cls.serveur.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()
        cls.serveur.server_close()

    def tearDown(self):
        for c in Client.ouverts:
            c.connexion.close()
        Client.ouverts.clear()

    def inscrire(self, telephone, nom):
        client = Client(self.port)
        statut, reponse = client("POST", "/api/inscription", {"telephone": telephone, "nom": nom, "mot_de_passe": "secret123"})
        self.assertEqual(statut, 201, reponse)
        return client

    def test_pages(self):
        client = Client(self.port)
        for chemin in ("/", "/app", "/rejoindre/abcdef", "/static/app.js", "/static/style.css"):
            self.assertEqual(client("GET", chemin)[0], 200, chemin)

    def test_parcours_complet(self):
        awa = self.inscrire("+221 77 200 00 01", "Awa")
        statut, cree = awa("POST", "/api/tontines", {"nom": "Tontine", "montant": "5 000", "devise": "XOF",
                                                     "frequence": "hebdomadaire", "date_debut": "2030-01-06",
                                                     "mode_ordre": "inscription"})
        self.assertEqual(statut, 201)
        tid = cree["id"]
        # formule gratuite : une seule tontine organisée à la fois
        self.assertEqual(awa("POST", "/api/tontines", {"nom": "Deux", "montant": "1000", "date_debut": "2030-01-01"})[0], 402)
        _, vue = awa("POST", f"/api/tontines/{tid}/membres", {"nom": "Sans téléphone", "telephone": "+221772000009"})
        self.assertEqual(len(vue["membres"]), 2)
        code = vue["invitation"].rsplit("/", 1)[1]
        fatou = self.inscrire("+221772000002", "Fatou")
        _, invitation = fatou("GET", f"/api/invitation/{code}")
        self.assertEqual((invitation["nom"], invitation["organisateur"]), ("Tontine", "Awa"))
        self.assertEqual(fatou("POST", f"/api/invitation/{code}/rejoindre", {})[0], 200)
        # un membre ne voit pas les numéros et ne peut pas démarrer
        _, vue_fatou = fatou("GET", f"/api/tontines/{tid}")
        self.assertNotIn("telephone", vue_fatou["membres"][0])
        self.assertIsNone(vue_fatou["invitation"])
        self.assertEqual(fatou("POST", f"/api/tontines/{tid}/demarrer", {})[0], 403)
        _, vue = awa("POST", f"/api/tontines/{tid}/demarrer", {})
        tour = vue["tour_courant"]
        self.assertEqual((tour["tour"], tour["attendu"]), (1, "15 000 FCFA"))
        # Fatou déclare, Awa confirme ; un membre ne peut pas déclarer pour un autre
        membre_absent = next(m["id"] for m in vue["membres"] if m["nom"] == "Sans téléphone")
        _, vue_fatou = fatou("POST", f"/api/tontines/{tid}/tours/{tour['tour_id']}/cotisations",
                             {"montant": "5000", "moyen": "mobile_money", "reference": "MP1", "membre_id": membre_absent})
        ligne_fatou = next(l for l in vue_fatou["tour_courant"]["lignes"] if l["nom"] == "Fatou")
        ligne_absent = next(l for l in vue_fatou["tour_courant"]["lignes"] if l["nom"] == "Sans téléphone")
        self.assertEqual((ligne_fatou["statut"], ligne_absent["statut"]), ("a_confirmer", "a_payer"))
        cid = ligne_fatou["cotisations"][0]["id"]
        self.assertEqual(fatou("POST", f"/api/tontines/{tid}/cotisations/{cid}/decision", {"accepter": True})[0], 403)
        awa("POST", f"/api/tontines/{tid}/cotisations/{cid}/decision", {"accepter": True})
        for membre in vue["membres"]:
            if membre["nom"] != "Fatou":
                awa("POST", f"/api/tontines/{tid}/tours/{tour['tour_id']}/cotisations",
                    {"montant": "5000", "moyen": "especes", "membre_id": membre["id"]})
        _, vue = awa("POST", f"/api/tontines/{tid}/tours/{tour['tour_id']}/verser", {})
        self.assertEqual(vue["tour_courant"]["tour"], 2)
        self.assertEqual(vue["tours"][0]["montant_verse"], "15 000 FCFA")
        # journal visible par tous, intact
        _, journal = fatou("GET", f"/api/tontines/{tid}/journal")
        self.assertTrue(journal["intact"])
        self.assertEqual(journal["entrees"][0]["action"], "versement")
        # tableau de bord de Fatou
        _, tableau = fatou("GET", "/api/tableau")
        self.assertEqual(tableau["tontines"][0]["je_recois"]["tour"], 3)  # Awa, puis le membre sans téléphone, puis Fatou
        # export : formule Organisateur requise
        self.assertEqual(awa("GET", f"/api/tontines/{tid}/export.csv")[0], 402)
        awa("POST", "/api/formule/commande", {})
        statut, csv = awa("GET", f"/api/tontines/{tid}/export.csv")
        self.assertEqual(statut, 200)
        self.assertIn("Confirmé", csv.decode("utf-8-sig"))
        # une tontine en cours ne peut pas être supprimée
        self.assertEqual(awa("DELETE", f"/api/tontines/{tid}")[0], 400)

    def test_securite(self):
        awa = self.inscrire("+221773000001", "Awa")
        _, cree = awa("POST", "/api/tontines", {"nom": "Secret", "montant": "1000", "date_debut": "2030-01-01"})
        intrus = self.inscrire("+221773000002", "Intrus")
        for methode, chemin in (("GET", f"/api/tontines/{cree['id']}"), ("GET", f"/api/tontines/{cree['id']}/journal"),
                                ("POST", f"/api/tontines/{cree['id']}/demarrer")):
            self.assertEqual(intrus(methode, chemin, {} if methode == "POST" else None)[0], 404, chemin)
        self.assertEqual(awa("POST", "/api/tontines", {"nom": "x"}, entetes={"X-Cotiz": "0"})[0], 403)  # CSRF
        inconnu = Client(self.port)
        self.assertEqual(inconnu("GET", "/api/tableau")[0], 401)
        self.assertEqual(inconnu("POST", "/api/connexion", {"telephone": "+221773000001", "mot_de_passe": "faux"})[0], 401)
        self.assertEqual(inconnu("POST", "/api/connexion", {"telephone": "77 300 00 01", "mot_de_passe": "x"})[0], 401)
        self.assertEqual(inconnu("POST", "/api/connexion", {"telephone": "+221 77 300 00 01", "mot_de_passe": "secret123"})[0], 200)
        doublon = Client(self.port)
        self.assertEqual(doublon("POST", "/api/inscription", {"telephone": "+221773000001", "nom": "X",
                                                              "mot_de_passe": "secret123"})[0], 409)


if __name__ == "__main__":
    unittest.main()
