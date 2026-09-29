import http.client
import json
import random
import threading
import unittest

from castagne import jeu as J
from castagne import regles as R
from castagne.base import Base
from castagne.combat import simuler
from castagne.serveur import Configuration, creer_serveur

APPARENCE = {"genre": "h", "peau": 1, "coiffure": 2, "cheveux": 3, "haut": 4, "bas": 5, "barbe": 1, "yeux": 0}


def brute(fiche, nom="A"):
    return {"nom": nom, "apparence": APPARENCE, "fiche": fiche}


class TestRegles(unittest.TestCase):
    def test_fiche_initiale(self):
        rng = random.Random(1)
        for _ in range(50):
            fiche = R.fiche_initiale(rng)
            self.assertEqual(sum(fiche[c] for c in R.CARACS), 20)
            self.assertTrue(all(fiche[c] >= 2 for c in R.CARACS))
            self.assertEqual(len(fiche["armes"]) + len(fiche["competences"]) + len(fiche["animaux"]), 1)

    def test_options_de_niveau(self):
        rng = random.Random(2)
        fiche = R.fiche_initiale(rng)
        for _ in range(300):  # même une brute qui a déjà tout reçoit toujours deux choix différents
            options = R.options_niveau(rng, fiche)
            self.assertEqual(len(options), 2)
            self.assertNotEqual(options[0], options[1])
            R.appliquer(fiche, options[0])
        self.assertEqual(len(set(fiche["armes"])), len(fiche["armes"]))
        self.assertLessEqual(fiche["animaux"].count("chien"), 3)
        self.assertLessEqual(fiche["animaux"].count("ours"), 1)

    def test_libelles_et_seuils(self):
        self.assertEqual(R.libelle({"type": "carac", "gains": {"force": 2, "agilite": 1}}), "Force +2 et Agilité +1")
        self.assertEqual(R.libelle({"type": "arme", "cle": "poele"}), "Nouvelle arme : Poêle")
        self.assertEqual(R.seuil_xp(1), 6)
        self.assertEqual(R.pv_max({"endurance": 5, "competences": ["vitalite"]}), 104)

    def test_noms_et_apparence(self):
        self.assertEqual(R.nom_valide("Grobul-2"), "Grobul-2")
        self.assertEqual(R.nom_valide("Éloïse"), "Éloïse")
        for mauvais in ("ab", "<script>", "a" * 21, "nom avec espace", ""):
            with self.assertRaises(ValueError):
                R.nom_valide(mauvais)
        self.assertEqual(R.apparence_valide({**APPARENCE, "genre": "f"})["barbe"], 0)  # pas de barbe forcée
        for mauvais in ({**APPARENCE, "peau": 99}, {**APPARENCE, "genre": "x"}, {**APPARENCE, "yeux": True}, "texte"):
            with self.assertRaises(ValueError):
                R.apparence_valide(mauvais)


class TestCombat(unittest.TestCase):
    def test_deterministe(self):
        rng = random.Random(3)
        a, b = brute(R.fiche_de_niveau(rng, 5)), brute(R.fiche_de_niveau(rng, 5), "B")
        self.assertEqual(simuler(a, b, 42), simuler(a, b, 42))

    def test_deroule_coherent(self):
        rng = random.Random(4)
        for _ in range(300):
            niveau = rng.choice((1, 4, 10))
            gagnant, evenements = simuler(brute(R.fiche_de_niveau(rng, niveau)), brute(R.fiche_de_niveau(rng, niveau), "B"), rng.random())
            self.assertEqual(evenements[0]["t"], "debut")
            self.assertEqual(evenements[-1], {"t": "fin", "gagnant": gagnant})
            combattants = {c["id"]: dict(c) for c in evenements[0]["combattants"]}
            for e in evenements[1:-1]:
                self.assertIn(e["id"], combattants)
                if e["t"] == "coup":
                    self.assertGreater(e["degats"], 0)
                    combattants[e["cible"]]["pv"] = e["pv"]
                if e["t"] == "ko":
                    self.assertEqual(combattants[e["id"]]["pv"], 0)
            brutes = [c for c in combattants.values() if not c["animal"]]
            perdante = brutes[1 - gagnant]
            self.assertTrue(perdante["pv"] == 0 or len(evenements) > 500)  # KO, sauf combat interminable

    def test_une_arme_aide(self):
        rng = random.Random(5)
        victoires = 0
        for _ in range(300):
            fiche = R.fiche_initiale(rng)
            fiche.update(armes=["epee"], competences=[], animaux=[])
            victoires += simuler(brute(fiche), brute({**fiche, "armes": []}, "B"), rng.random())[0] == 0
        self.assertGreater(victoires, 180)


class TestPartie(unittest.TestCase):
    def setUp(self):
        self.base = Base(":memory:")
        self.rng = random.Random(6)
        self.id = J.creer_brute(self.base, "Grobul", "x", APPARENCE, rng=self.rng)

    def test_nom_unique(self):
        with self.assertRaises(J.Refus):
            J.creer_brute(self.base, "grobul", "x", APPARENCE)

    def test_combats_du_jour(self):
        adversaires = J.adversaires(self.base, self.base.brute(self.id), self.rng)
        self.assertEqual(len(adversaires), 6)
        self.assertTrue(all(a["bot"] and abs(a["niveau"] - 1) <= 1 for a in adversaires))
        for i in range(R.COMBATS_PAR_JOUR):
            if self.base.brute(self.id)["choix"]:
                J.choisir(self.base, self.id, 0, self.rng)
            J.combattre(self.base, self.id, adversaires[i]["nom"], "2026-10-01", self.rng)
        if self.base.brute(self.id)["choix"]:
            J.choisir(self.base, self.id, 0, self.rng)
        with self.assertRaises(J.Refus):
            J.combattre(self.base, self.id, adversaires[0]["nom"], "2026-10-01", self.rng)
        J.combattre(self.base, self.id, adversaires[0]["nom"], "2026-10-02", self.rng)  # le lendemain, c'est reparti
        b = self.base.brute(self.id)
        self.assertEqual(b["victoires"] + b["defaites"], 7)
        self.assertEqual(len(J.historique(self.base, self.id)), 7)

    def test_passage_de_niveau(self):
        with self.base.transaction() as c:
            J.gagner_xp(c, self.id, 7, self.rng)
        b = self.base.brute(self.id)
        self.assertEqual((b["niveau"], b["xp"], len(b["choix"])), (2, 1, 2))
        with self.assertRaises(J.Refus):  # il faut choisir avant de combattre
            J.combattre(self.base, self.id, J.adversaires(self.base, b, self.rng)[0]["nom"], "2026-10-01", self.rng)
        option = b["choix"][1]
        avant = b["fiche"]
        J.choisir(self.base, self.id, 1, self.rng)
        apres = self.base.brute(self.id)
        self.assertIsNone(apres["choix"])
        self.assertEqual(apres["fiche"], R.appliquer(avant, option))
        with self.assertRaises(J.Refus):
            J.choisir(self.base, self.id, 0, self.rng)

    def test_experience_accumulee_pendant_le_choix(self):
        with self.base.transaction() as c:
            J.gagner_xp(c, self.id, 6, self.rng)   # niveau 2, choix en attente
            J.gagner_xp(c, self.id, 8, self.rng)   # de quoi passer niveau 3, mais le choix n'est pas fait
        self.assertEqual(self.base.brute(self.id)["niveau"], 2)
        J.choisir(self.base, self.id, 0, self.rng)
        b = self.base.brute(self.id)
        self.assertEqual((b["niveau"], b["xp"]), (3, 0))
        self.assertIsNotNone(b["choix"])

    def test_eleves(self):
        eleve = J.creer_brute(self.base, "Petiot", "x", APPARENCE, maitre="GROBUL", rng=self.rng)
        self.assertEqual(self.base.brute(eleve)["maitre_id"], self.id)
        with self.base.transaction() as c:
            faible = J.creer_bot(c, 1, self.rng)
        nom = self.base.brute(faible)["nom"]
        victoires = 0
        for jour in range(1, 30):
            if self.base.brute(eleve)["choix"]:
                J.choisir(self.base, eleve, 0, self.rng)
            _, victoire, _ = J.combattre(self.base, eleve, nom, f"2026-10-{jour:02d}", self.rng)
            victoires += victoire
        maitre = self.base.brute(self.id)
        self.assertGreater(victoires, 0)
        self.assertEqual(maitre["xp"] + sum(R.seuil_xp(n) for n in range(1, maitre["niveau"])), victoires * R.XP_MAITRE)
        self.assertEqual(J.resume(self.base, maitre)["eleves"][0]["nom"], "Petiot")

    def test_pas_de_gloire_contre_plus_faible(self):
        with self.base.transaction() as c:
            J.gagner_xp(c, self.id, 200, self.rng)
        while self.base.brute(self.id)["choix"]:
            J.choisir(self.base, self.id, 0, self.rng)
        with self.base.transaction() as c:
            faible = self.base.brute(J.creer_bot(c, 1, self.rng), c)
        _, victoire, xp = J.combattre(self.base, self.id, faible["nom"], "2026-10-01", self.rng)
        self.assertEqual(xp, 0 if victoire else R.XP_DEFAITE)

    def test_tournoi(self):
        ids = [self.id] + [J.creer_brute(self.base, f"Joueur{i}", "x", APPARENCE, rng=self.rng) for i in range(9)]
        for i in ids:
            J.inscrire(self.base, i, "2026-10-01")
        J.resoudre_tournois(self.base, "2026-10-01", self.rng)  # le jour même : pas encore disputé
        self.assertIsNone(J.tournoi(self.base, self.id))
        J.resoudre_tournois(self.base, "2026-10-02", self.rng)
        J.resoudre_tournois(self.base, "2026-10-03", self.rng)  # une seule fois
        self.assertEqual(self.base.un("SELECT COUNT(*) AS n FROM tournois")["n"], 2)  # 10 inscrits : deux tableaux
        for i in ids:
            t = J.tournoi(self.base, i)
            self.assertEqual([len(m) for m in t["tours"]], [4, 2, 1])
            self.assertEqual(t["tours"][2][0]["gagnant"], t["vainqueur"])
        vainqueur = self.base.brute_par_nom(J.tournoi(self.base, self.id)["vainqueur"])
        self.assertGreater(vainqueur["niveau"] * 100 + vainqueur["xp"], 100)


class Client:
    def __init__(self, port):
        self.port, self.cookie = port, None

    def appel(self, methode, chemin, corps=None, csrf=True):
        connexion = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        entetes = {"Content-Type": "application/json"}
        if csrf:
            entetes["X-Castagne"] = "1"
        if self.cookie:
            entetes["Cookie"] = self.cookie
        connexion.request(methode, chemin, json.dumps(corps) if corps is not None else None, entetes)
        reponse = connexion.getresponse()
        cookie = reponse.getheader("Set-Cookie")
        if cookie:
            self.cookie = cookie.split(";")[0]
        donnees = reponse.read()
        connexion.close()
        try:
            return reponse.status, json.loads(donnees)
        except ValueError:
            return reponse.status, donnees.decode("utf-8")


class TestServeur(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = Configuration(base=":memory:", url="http://test", options={"jour": "2026-10-01"})
        cls.serveur = creer_serveur(cls.config, "127.0.0.1", 0)
        threading.Thread(target=cls.serveur.serve_forever, daemon=True).start()
        cls.port = cls.serveur.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()
        cls.serveur.server_close()

    def test_parcours(self):
        visiteur = Client(self.port)
        statut, page = visiteur.appel("GET", "/")
        self.assertEqual(statut, 200)
        self.assertIn("<title>Castagne</title>", page)
        self.assertEqual(visiteur.appel("GET", "/api/moi")[0], 401)

        joueur = Client(self.port)
        self.assertEqual(joueur.appel("POST", "/api/creer", {"nom": "Brutus", "mot_de_passe": "court", "apparence": APPARENCE})[0], 400)
        statut, _ = joueur.appel("POST", "/api/creer", {"nom": "Brutus", "mot_de_passe": "motdepasse", "apparence": APPARENCE}, csrf=False)
        self.assertEqual(statut, 403)  # sans l'en-tête anti-CSRF
        statut, r = joueur.appel("POST", "/api/creer", {"nom": "Brutus", "mot_de_passe": "motdepasse", "apparence": APPARENCE})
        self.assertEqual((statut, r["nom"]), (201, "Brutus"))
        self.assertEqual(Client(self.port).appel("POST", "/api/creer", {"nom": "brutus", "mot_de_passe": "motdepasse", "apparence": APPARENCE})[0], 409)

        statut, moi = joueur.appel("GET", "/api/moi")
        self.assertEqual((statut, moi["niveau"], moi["combats_restants"]), (200, 1, R.COMBATS_PAR_JOUR))
        statut, adversaires = joueur.appel("GET", "/api/adversaires")
        self.assertEqual(len(adversaires), 6)
        statut, r = joueur.appel("POST", "/api/combattre", {"adversaire": adversaires[0]["nom"]})
        self.assertEqual(statut, 200)
        self.assertIn(r["xp"], (R.XP_DEFAITE, R.XP_VICTOIRE))

        statut, combat = visiteur.appel("GET", f"/api/combats/{r['combat']}")  # un combat se revoit sans compte
        self.assertEqual((statut, combat["brutes"][0]["nom"]), (200, "Brutus"))
        self.assertEqual(combat["evenements"][-1]["t"], "fin")
        statut, fiche = visiteur.appel("GET", "/api/brutes/BRUTUS")
        self.assertEqual((statut, fiche["victoires"] + fiche["defaites"]), (200, 1))
        self.assertNotIn("choix", fiche)  # les informations privées ne sont pas publiques
        self.assertEqual(visiteur.appel("GET", "/api/brutes/inconnu")[0], 404)
        self.assertEqual(joueur.appel("POST", "/api/combattre", {"adversaire": "Brutus"})[0], 409)

        self.assertEqual(joueur.appel("POST", "/api/tournoi", {})[0], 200)
        self.assertTrue(joueur.appel("GET", "/api/moi")[1]["inscrit_tournoi"])
        statut, classement = visiteur.appel("GET", "/api/classement")
        self.assertEqual([b["nom"] for b in classement], ["Brutus"])  # les brutes du jeu n'y figurent pas

        joueur.appel("POST", "/api/deconnexion", {})
        self.assertEqual(joueur.appel("GET", "/api/moi")[0], 401)
        self.assertEqual(joueur.appel("POST", "/api/connexion", {"nom": "Brutus", "mot_de_passe": "mauvais!!"})[0], 401)
        bot = adversaires[0]["nom"]
        self.assertEqual(joueur.appel("POST", "/api/connexion", {"nom": bot, "mot_de_passe": ""})[0], 401)
        self.assertEqual(joueur.appel("POST", "/api/connexion", {"nom": "brutus", "mot_de_passe": "motdepasse"})[0], 200)
        self.assertEqual(joueur.appel("GET", "/api/moi")[1]["combats_restants"], R.COMBATS_PAR_JOUR - 1)

    def test_statiques(self):
        client = Client(self.port)
        for fichier in ("style.css", "commun.js", "jeu.js", "combat.js", "accueil.js", "icone.svg"):
            self.assertEqual(client.appel("GET", f"/static/{fichier}")[0], 200)
        self.assertEqual(client.appel("GET", "/static/../serveur.py")[0], 404)


if __name__ == "__main__":
    unittest.main()
