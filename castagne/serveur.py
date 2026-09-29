"""Le serveur web de Castagne : les pages et l'API du jeu.

Bibliothèque standard de Python uniquement. En production, on le place derrière un serveur HTTPS.
"""

import datetime
import json
import os
import re
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from redigo.securite import Limiteur, hacher_mot_de_passe, mot_de_passe_acceptable, verifier_mot_de_passe

from . import jeu as J
from . import regles as R
from .base import Base, Introuvable

DOSSIER = os.path.dirname(os.path.abspath(__file__))
TAILLE_MAX_CORPS = 16 * 1024
COOKIE = "castagne_session"
PAGES = {"/": "accueil.html", "/jeu": "jeu.html"}
FICHIERS_STATIQUES = {"style.css": "text/css", "commun.js": "text/javascript", "accueil.js": "text/javascript",
                      "jeu.js": "text/javascript", "combat.js": "text/javascript", "icone.svg": "image/svg+xml"}


@dataclass
class Configuration:
    base: str = os.path.join(DOSSIER, "donnees", "castagne.db")
    url: str = "http://127.0.0.1:8080"
    fuseau: str = "Europe/Paris"      # le jour de jeu (combats quotidiens, tournois) change à minuit, heure de ce fuseau
    derriere_proxy: bool = False
    options: dict = field(default_factory=dict)

    @classmethod
    def depuis_environnement(cls, **surcharges):
        env = os.environ
        config = cls(base=env.get("CASTAGNE_BASE", cls.base), url=env.get("CASTAGNE_URL", cls.url).rstrip("/"),
                     fuseau=env.get("CASTAGNE_FUSEAU", cls.fuseau), derriere_proxy=env.get("CASTAGNE_DERRIERE_PROXY") == "1")
        for cle, valeur in surcharges.items():
            setattr(config, cle, valeur)
        return config

    def aujourdhui(self):
        if "jour" in self.options:  # les tests fixent la date
            return self.options["jour"]
        try:
            from zoneinfo import ZoneInfo
            return datetime.datetime.now(ZoneInfo(self.fuseau)).date().isoformat()
        except Exception:  # base des fuseaux absente (certains Windows) : heure locale de la machine
            return datetime.date.today().isoformat()


class ErreurHTTP(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


ROUTES = []


def route(methode, motif, connecte=True):
    def enregistrer(fonction):
        ROUTES.append((methode, re.compile(f"^{motif}$"), fonction, connecte))
        return fonction
    return enregistrer


class Gestionnaire(BaseHTTPRequestHandler):
    server_version = "Castagne/1.0"
    protocol_version = "HTTP/1.1"
    config = None
    base = None
    limiteurs = None

    def log_message(self, format, *args):
        if self.config and self.config.options.get("journal"):
            super().log_message(format, *args)

    def envoyer(self, code, contenu, type_contenu, entetes=None):
        if isinstance(contenu, str):
            contenu = contenu.encode("utf-8")
            type_contenu += "; charset=utf-8"
        self.send_response(code)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(contenu)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                         "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for nom, valeur in (entetes or {}).items():
            self.send_header(nom, valeur)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(contenu)

    def json(self, objet, code=200, entetes=None):
        self.envoyer(code, json.dumps(objet, ensure_ascii=False), "application/json", entetes)

    def cookie_session(self, jeton, duree):
        securise = "; Secure" if self.config.url.startswith("https://") else ""
        return {"Set-Cookie": f"{COOKIE}={jeton}; Path=/; HttpOnly; SameSite=Lax; Max-Age={duree}{securise}"}

    def adresse_ip(self):
        if self.config.derriere_proxy and self.headers.get("X-Forwarded-For"):
            return self.headers["X-Forwarded-For"].split(",")[0].strip()
        return self.client_address[0]

    def jeton_session(self):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except Exception:
            return None
        return cookies[COOKIE].value if COOKIE in cookies else None

    def corps_brut(self):
        if not hasattr(self, "_corps"):
            longueur = int(self.headers.get("Content-Length") or 0)
            if longueur > TAILLE_MAX_CORPS:
                raise ErreurHTTP(413, "Requête trop volumineuse.")
            self._corps = self.rfile.read(longueur) if longueur else b""
        return self._corps

    def donnees(self):
        try:
            donnees = json.loads(self.corps_brut() or b"{}")
        except ValueError:
            raise ErreurHTTP(400, "Requête illisible.")
        if not isinstance(donnees, dict):
            raise ErreurHTTP(400, "Requête illisible.")
        return donnees

    def traiter(self):
        # Avec HTTP/1.1, le même objet sert plusieurs requêtes d'une même connexion : on repart de zéro.
        self.__dict__.pop("_corps", None)
        self.brute = None
        chemin = urlsplit(self.path).path
        methode = "GET" if self.command == "HEAD" else self.command
        try:
            if methode == "POST":
                try:
                    self.corps_brut()
                except ErreurHTTP:
                    self.close_connection = True
                    raise
            if methode == "GET" and chemin in PAGES:
                return self.page(PAGES[chemin])
            if methode == "GET" and chemin.startswith("/static/"):
                return self.statique(chemin[len("/static/"):])
            for methode_route, motif, fonction, connecte in ROUTES:
                trouve = motif.match(chemin)
                if not trouve or methode_route != methode:
                    continue
                # Protection CSRF : un autre site ne peut pas ajouter cet en-tête à une requête vers Castagne.
                if methode != "GET" and self.headers.get("X-Castagne") != "1":
                    raise ErreurHTTP(403, "Requête refusée.")
                self.brute = self.base.brute_de_session(self.jeton_session())
                if connecte and not self.brute:
                    raise ErreurHTTP(401, "Connecte-toi pour continuer.")
                return fonction(self, *(unquote(g) for g in trouve.groups()))
            raise ErreurHTTP(404, "Introuvable.")
        except ErreurHTTP as erreur:
            self.json({"erreur": str(erreur)}, erreur.code)
        except Introuvable as erreur:
            self.json({"erreur": str(erreur)}, 404)
        except J.Refus as erreur:
            self.json({"erreur": str(erreur)}, 409)
        except ValueError as erreur:
            self.json({"erreur": str(erreur)}, 400)
        except Exception as erreur:
            if self.config.options.get("journal"):
                import traceback
                traceback.print_exc()
            self.json({"erreur": f"Erreur inattendue : {erreur}"}, 500)

    do_GET = do_POST = do_HEAD = traiter

    def page(self, nom):
        with open(os.path.join(DOSSIER, "web", nom), "rb") as f:
            self.envoyer(200, f.read(), "text/html; charset=utf-8")

    def statique(self, nom):
        if nom not in FICHIERS_STATIQUES:
            raise ErreurHTTP(404, "Introuvable.")
        with open(os.path.join(DOSSIER, "web", nom), "rb") as f:
            self.envoyer(200, f.read(), FICHIERS_STATIQUES[nom] + ("; charset=utf-8" if "svg" not in nom else ""))

    def limiter(self, nom, cle):
        if not self.limiteurs[nom].autorise(cle):
            raise ErreurHTTP(429, "Trop de tentatives. Réessaie dans quelques minutes.")


def texte(donnees, cle, maximum=200):
    valeur = donnees.get(cle, "")
    if not isinstance(valeur, str) or len(valeur) > maximum:
        raise ValueError(f"Le champ « {cle} » est invalide.")
    return valeur.strip()


# --- Règles et comptes ------------------------------------------------------------------------------------------------

@route("GET", "/api/regles", connecte=False)
def regles(g):
    g.json({"armes": {k: {"nom": a["nom"], "jet": bool(a.get("jet"))} for k, a in R.ARMES.items()},
            "competences": {k: {"nom": n, "texte": t} for k, (n, t) in R.COMPETENCES.items()},
            "animaux": {k: a["nom"] for k, a in R.ANIMAUX.items()}, "caracs": R.NOMS_CARACS,
            "apparence": R.APPARENCE, "combats_par_jour": R.COMBATS_PAR_JOUR})


@route("POST", "/api/creer", connecte=False)
def creer(g):
    g.limiter("creation", g.adresse_ip())
    d = g.donnees()
    mot_de_passe = texte(d, "mot_de_passe", 200)
    probleme = mot_de_passe_acceptable(mot_de_passe)
    if probleme:
        raise ValueError(probleme)
    identifiant = J.creer_brute(g.base, texte(d, "nom", 40), hacher_mot_de_passe(mot_de_passe), d.get("apparence"),
                                texte(d, "maitre", 40) or None)
    g.json({"nom": g.base.brute(identifiant)["nom"]}, 201, g.cookie_session(g.base.ouvrir_session(identifiant), 90 * 86400))


@route("POST", "/api/connexion", connecte=False)
def connexion(g):
    g.limiter("connexion", g.adresse_ip())
    d = g.donnees()
    brute = g.base.brute_par_nom(texte(d, "nom", 40))
    if not brute or brute["bot"] or not verifier_mot_de_passe(texte(d, "mot_de_passe", 200), brute["hash"] or ""):
        raise ErreurHTTP(401, "Nom de brute ou mot de passe incorrect.")
    g.json({"nom": brute["nom"]}, 200, g.cookie_session(g.base.ouvrir_session(brute["id"]), 90 * 86400))


@route("POST", "/api/deconnexion", connecte=False)
def deconnexion(g):
    g.base.fermer_session(g.jeton_session())
    g.json({"ok": True}, 200, g.cookie_session("", 0))


# --- Le jeu -------------------------------------------------------------------------------------------------------

@route("GET", "/api/moi")
def moi(g):
    jour = g.config.aujourdhui()
    J.resoudre_tournois(g.base, jour)
    g.json(J.resume(g.base, g.base.brute(g.brute["id"]), public=False, jour=jour))


@route("GET", "/api/adversaires")
def adversaires(g):
    g.json([{"nom": b["nom"], "niveau": b["niveau"], "apparence": b["apparence"], "victoires": b["victoires"],
             "defaites": b["defaites"], "pv": R.pv_max(b["fiche"])} for b in J.adversaires(g.base, g.brute)])


@route("POST", "/api/combattre")
def combattre(g):
    combat_id, victoire, xp = J.combattre(g.base, g.brute["id"], texte(g.donnees(), "adversaire", 40), g.config.aujourdhui())
    g.json({"combat": combat_id, "victoire": victoire, "xp": xp})


@route("POST", "/api/choisir")
def choisir(g):
    index = g.donnees().get("choix")
    if not isinstance(index, int):
        raise ValueError("Choix invalide.")
    g.json({"libelle": R.libelle(J.choisir(g.base, g.brute["id"], index))})


@route("POST", "/api/tournoi")
def inscrire(g):
    if g.brute["choix"]:
        raise J.Refus("Choisis d'abord ton bonus de niveau.")
    J.inscrire(g.base, g.brute["id"], g.config.aujourdhui())
    g.json({"ok": True})


@route("GET", r"/api/brutes/([^/]+)", connecte=False)
def brute_publique(g, nom):
    brute = g.base.brute_par_nom(nom)
    if not brute:
        raise Introuvable("Cette brute n'existe pas.")
    g.json(J.resume(g.base, brute))


@route("GET", r"/api/combats/(\d+)", connecte=False)
def combat(g, combat_id):
    g.json(J.combat(g.base, int(combat_id)))


@route("GET", "/api/classement", connecte=False)
def classement(g):
    g.json([{**l, "apparence": json.loads(l["apparence"])} for l in J.classement(g.base)])


# --- Démarrage -------------------------------------------------------------------------------------------------------------------

def creer_serveur(config, hote="127.0.0.1", port=8080):
    base = Base(config.base)
    limiteurs = {"connexion": Limiteur(10, 15 * 60), "creation": Limiteur(10, 3600)}
    gestionnaire = type("GestionnaireCastagne", (Gestionnaire,), {"config": config, "base": base, "limiteurs": limiteurs})
    serveur = ThreadingHTTPServer((hote, port), gestionnaire)
    serveur.daemon_threads = True
    serveur.base = base
    return serveur


def servir(config, hote="127.0.0.1", port=8080):
    serveur = creer_serveur(config, hote, port)
    print(f"🥊 Castagne est en ligne : {config.url}/")
    print(f"   Base de données : {config.base}")
    print("   (Ctrl+C pour arrêter)")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nAu revoir !")
    finally:
        serveur.server_close()
