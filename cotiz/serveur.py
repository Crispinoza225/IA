"""Le serveur web de Cotiz : les pages et l'API de l'application.

Bibliothèque standard de Python uniquement. En production, on le place derrière un serveur HTTPS.
"""

import csv
import datetime
import io
import json
import os
import re
import secrets
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from redigo.securite import Limiteur, hacher_mot_de_passe, mot_de_passe_acceptable, verifier_mot_de_passe

from . import tontine as T
from .base import Base, Interdit, Introuvable
from .calendrier import DEVISES, FREQUENCES, date_francaise, formater, vers_unites

DOSSIER = os.path.dirname(os.path.abspath(__file__))
TAILLE_MAX_CORPS = 256 * 1024
COOKIE = "cotiz_session"
PAGES = {"/": "accueil.html", "/app": "app.html"}
FICHIERS_STATIQUES = {"style.css": "text/css", "accueil.css": "text/css", "app.js": "text/javascript",
                      "commun.js": "text/javascript"}

# Les formules : ce que chacune permet à un organisateur.
FORMULES = {
    "gratuit": {"nom": "Gratuit", "tontines": 1, "membres": 15, "export": False},
    "organisateur": {"nom": "Organisateur", "tontines": 20, "membres": T.MEMBRES_MAX, "export": True},
}
PRIX_ORGANISATEUR = {"EUR": 300, "XOF": 2000, "XAF": 2000}  # par mois, dans la plus petite unité
DUREE_FORMULE = 30  # jours
STATUTS_COTISATION = {"declaree": "À confirmer", "confirmee": "Confirmé", "refusee": "Refusé"}


@dataclass
class Configuration:
    base: str = os.path.join(DOSSIER, "donnees", "cotiz.db")
    url: str = "http://127.0.0.1:8070"
    demo: bool = True               # sans prestataire de paiement : la formule s'active sans payer (pour essayer)
    derriere_proxy: bool = False
    options: dict = field(default_factory=dict)

    @classmethod
    def depuis_environnement(cls, **surcharges):
        env = os.environ
        config = cls(base=env.get("COTIZ_BASE", cls.base), url=env.get("COTIZ_URL", cls.url).rstrip("/"),
                     demo=env.get("COTIZ_DEMO", "1") == "1", derriere_proxy=env.get("COTIZ_DERRIERE_PROXY") == "1")
        for cle, valeur in surcharges.items():
            setattr(config, cle, valeur)
        return config


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
    server_version = "Cotiz/1.0"
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
        self.send_header("Referrer-Policy", "no-referrer")  # le code d'invitation ne fuit pas vers d'autres sites
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
        self.utilisateur = None
        chemin = urlsplit(self.path).path
        self.parametres = parse_qs(urlsplit(self.path).query)
        methode = "GET" if self.command == "HEAD" else self.command
        try:
            if methode in ("POST", "PUT", "DELETE"):
                try:
                    self.corps_brut()
                except ErreurHTTP:
                    self.close_connection = True
                    raise
            if methode == "GET" and (chemin in PAGES or chemin.startswith("/rejoindre/")):
                return self.page(PAGES.get(chemin, "app.html"))
            if methode == "GET" and chemin.startswith("/static/"):
                return self.statique(chemin[len("/static/"):])
            for methode_route, motif, fonction, connecte in ROUTES:
                trouve = motif.match(chemin)
                if not trouve or methode_route != methode:
                    continue
                # Protection CSRF : un autre site ne peut pas ajouter cet en-tête à une requête vers Cotiz.
                if methode != "GET" and self.headers.get("X-Cotiz") != "1":
                    raise ErreurHTTP(403, "Requête refusée.")
                self.utilisateur = self.base.utilisateur_de_session(self.jeton_session())
                if connecte and not self.utilisateur:
                    raise ErreurHTTP(401, "Connecte-toi pour continuer.")
                return fonction(self, *trouve.groups())
            raise ErreurHTTP(404, "Introuvable.")
        except ErreurHTTP as erreur:
            self.json({"erreur": str(erreur)}, erreur.code)
        except Introuvable as erreur:
            self.json({"erreur": str(erreur)}, 404)
        except Interdit as erreur:
            self.json({"erreur": str(erreur)}, 403)
        except ValueError as erreur:
            self.json({"erreur": str(erreur)}, 400)
        except Exception as erreur:
            if self.config.options.get("journal"):
                import traceback
                traceback.print_exc()
            self.json({"erreur": f"Erreur inattendue : {erreur}"}, 500)

    do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = traiter

    def page(self, nom):
        with open(os.path.join(DOSSIER, "web", nom), "rb") as f:
            self.envoyer(200, f.read(), "text/html; charset=utf-8")

    def statique(self, nom):
        if nom not in FICHIERS_STATIQUES:
            raise ErreurHTTP(404, "Introuvable.")
        with open(os.path.join(DOSSIER, "web", nom), "rb") as f:
            self.envoyer(200, f.read(), FICHIERS_STATIQUES[nom] + "; charset=utf-8")

    def limiter(self, nom, cle):
        if not self.limiteurs[nom].autorise(cle):
            raise ErreurHTTP(429, "Trop de tentatives. Réessaie dans quelques minutes.")

    def formule(self):
        fin = self.utilisateur.get("formule_jusqua")
        code = "organisateur" if fin and fin >= datetime.datetime.now(datetime.timezone.utc).isoformat() else "gratuit"
        return code, FORMULES[code], fin if code != "gratuit" else None


def texte(donnees, cle, maximum=200, obligatoire=False):
    valeur = donnees.get(cle, "")
    if not isinstance(valeur, str):
        raise ValueError(f"Le champ « {cle} » est invalide.")
    valeur = valeur.strip()
    if obligatoire and not valeur:
        raise ValueError(f"Le champ « {cle} » est obligatoire.")
    if len(valeur) > maximum:
        raise ValueError(f"Le champ « {cle} » est trop long.")
    return valeur


def entier(donnees, cle, defaut=0):
    try:
        return int(donnees.get(cle, defaut))
    except (TypeError, ValueError):
        raise ValueError(f"Le champ « {cle} » doit être un nombre entier.")


def resume_utilisateur(g):
    code, formule, fin = g.formule()
    return {"nom": g.utilisateur["nom"], "telephone": g.utilisateur["telephone"],
            "formule": {"code": code, "nom": formule["nom"], "fin": fin, **formule}}


# --- Comptes ----------------------------------------------------------------------------------------------------------

@route("GET", "/api/configuration", connecte=False)
def configuration(g):
    g.json({"devises": {k: v[0] for k, v in DEVISES.items()}, "frequences": FREQUENCES, "modes_ordre": T.MODES_ORDRE,
            "moyens": T.MOYENS, "formules": FORMULES, "mains_max": T.MAINS_MAX,
            "prix": {devise: formater(prix, devise) for devise, prix in PRIX_ORGANISATEUR.items()},
            "paiement": "demo" if g.config.demo else None})


@route("POST", "/api/inscription", connecte=False)
def inscription(g):
    g.limiter("inscription", g.adresse_ip())
    d = g.donnees()
    telephone = T.telephone_normalise(texte(d, "telephone", 30, True))
    nom = texte(d, "nom", 80, True)
    mot_de_passe = d.get("mot_de_passe") if isinstance(d.get("mot_de_passe"), str) else ""
    probleme = mot_de_passe_acceptable(mot_de_passe)
    if probleme:
        raise ValueError(probleme)
    if g.base.utilisateur_par_telephone(telephone):
        raise ErreurHTTP(409, "Un compte existe déjà avec ce numéro. Connecte-toi.")
    identifiant = g.base.creer_utilisateur(telephone, nom, hacher_mot_de_passe(mot_de_passe))
    g.utilisateur = g.base.utilisateur(identifiant)
    g.json(resume_utilisateur(g), 201, g.cookie_session(g.base.ouvrir_session(identifiant), 60 * 86400))


@route("POST", "/api/connexion", connecte=False)
def connexion(g):
    d = g.donnees()
    try:
        telephone = T.telephone_normalise(texte(d, "telephone", 30))
    except ValueError:
        raise ErreurHTTP(401, "Numéro ou mot de passe incorrect.")
    g.limiter("connexion", g.adresse_ip())
    g.limiter("connexion", telephone)
    utilisateur = g.base.utilisateur_par_telephone(telephone)
    mot_de_passe = d.get("mot_de_passe") if isinstance(d.get("mot_de_passe"), str) else ""
    if not utilisateur or not verifier_mot_de_passe(mot_de_passe, utilisateur["hash"]):
        raise ErreurHTTP(401, "Numéro ou mot de passe incorrect.")
    g.utilisateur = utilisateur
    g.json(resume_utilisateur(g), 200, g.cookie_session(g.base.ouvrir_session(utilisateur["id"]), 60 * 86400))


@route("POST", "/api/deconnexion", connecte=False)
def deconnexion(g):
    g.base.fermer_session(g.jeton_session())
    g.json({"ok": True}, 200, g.cookie_session("", 0))


@route("GET", "/api/moi")
def moi(g):
    g.json(resume_utilisateur(g))


@route("POST", "/api/compte/mot-de-passe")
def changer_mot_de_passe(g):
    d = g.donnees()
    if not verifier_mot_de_passe(str(d.get("actuel", "")), g.utilisateur["hash"]):
        raise ErreurHTTP(403, "Le mot de passe actuel est incorrect.")
    nouveau = str(d.get("nouveau", ""))
    probleme = mot_de_passe_acceptable(nouveau)
    if probleme:
        raise ValueError(probleme)
    g.base.changer_mot_de_passe(g.utilisateur["id"], hacher_mot_de_passe(nouveau))
    g.json({"ok": True}, 200, g.cookie_session(g.base.ouvrir_session(g.utilisateur["id"]), 60 * 86400))


@route("POST", "/api/formule/commande")
def commander(g):
    if not g.config.demo:
        raise ErreurHTTP(503, "Le paiement en ligne n'est pas encore ouvert. Contacte-nous pour activer la formule.")
    g.base.activer_formule(g.utilisateur["id"], "demo", f"demo-{secrets.token_hex(8)}", 0, DUREE_FORMULE)
    g.utilisateur = g.base.utilisateur(g.utilisateur["id"])
    g.json(resume_utilisateur(g))


# --- Tableau de bord et tontines -----------------------------------------------------------------------------------------

@route("GET", "/api/tableau")
def tableau(g):
    g.json({"tontines": T.resume_pour(g.base, g.utilisateur),
            "fiabilite": T.fiabilite(g.base, g.utilisateur["telephone"])})


def lire_reglages_groupe(d):
    devise = texte(d, "devise", 5) or "XOF"
    if devise not in DEVISES:
        raise ValueError("Monnaie inconnue.")
    return {
        "nom": texte(d, "nom", 80, True), "description": texte(d, "description", 500), "devise": devise,
        "montant": vers_unites(d.get("montant", ""), devise),
        "frequence": texte(d, "frequence", 20) or "mensuelle",
        "date_debut": texte(d, "date_debut", 10, True),
        "mode_ordre": texte(d, "mode_ordre", 20) or "tirage",
        "penalite": vers_unites(d.get("penalite") or 0, devise),
        "jours_grace": entier(d, "jours_grace", 0),
    }


@route("POST", "/api/tontines")
def creer_tontine(g):
    _, formule, _ = g.formule()
    actives = g.base.un("SELECT count(*) AS n FROM groupes WHERE createur_id = ? AND statut != 'termine'",
                        (g.utilisateur["id"],))["n"]
    if actives >= formule["tontines"]:
        raise ErreurHTTP(402, "La formule gratuite permet d'organiser une tontine à la fois. Passe à la formule "
                              "Organisateur pour en gérer plusieurs." if formule["tontines"] == 1 else
                         f"Tu organises déjà {actives} tontines, le maximum de ta formule.")
    identifiant = T.creer_groupe(g.base, g.utilisateur, **lire_reglages_groupe(g.donnees()))
    g.json({"id": identifiant}, 201)


def vue_tontine(g, groupe_id):
    groupe = T.groupe(g.base, groupe_id)
    moi_ = T.membre_de(g.base, groupe_id, g.utilisateur)
    organisateur = moi_["role"] == "organisateur"
    devise = groupe["devise"]
    membres = g.base.tous("SELECT * FROM membres WHERE groupe_id = ? ORDER BY rang, id", (groupe_id,))
    total_mains = sum(m["mains"] for m in membres)
    tours = g.base.tous("SELECT t.*, m.nom AS beneficiaire FROM tours t JOIN membres m ON m.id = t.beneficiaire_id "
                        "WHERE t.groupe_id = ? ORDER BY numero", (groupe_id,))
    courant = T.tour_courant(g.base, groupe_id) if groupe["statut"] == "en_cours" else None
    etat = None
    if courant:
        e = T.etat_tour(g.base, groupe, courant)
        etat = {"tour": courant["numero"], "tour_id": courant["id"], "echeance": courant["echeance"],
                "limite": T.limite_paiement(groupe, courant).isoformat(),
                "beneficiaire": next(t["beneficiaire"] for t in tours if t["id"] == courant["id"]),
                "collecte": formater(e["collecte"], devise), "attendu": formater(e["attendu"], devise),
                "progression": round(100 * e["collecte"] / e["attendu"]) if e["attendu"] else 0, "complet": e["complet"],
                "lignes": [{"membre_id": l["membre_id"], "nom": l["nom"], "statut": l["statut"],
                            "du": formater(l["du"], devise), "du_brut": l["du"], "verse": formater(l["verse"], devise),
                            "cotisations": [{"id": c["id"], "montant": formater(c["montant"], devise),
                                             "moyen": T.MOYENS[c["moyen"]], "reference": c["reference"],
                                             "statut": c["statut"], "declare_le": c["declare_le"],
                                             "penalite": formater(c["penalite"], devise) if c["penalite"] else ""}
                                            for c in l["cotisations"]]}
                           for l in e["lignes"]]}
    g.json({
        "id": groupe["id"], "nom": groupe["nom"], "description": groupe["description"], "statut": groupe["statut"],
        "devise": devise, "montant": formater(groupe["montant"], devise), "montant_brut": groupe["montant"],
        "frequence": FREQUENCES[groupe["frequence"]], "frequence_code": groupe["frequence"],
        "date_debut": groupe["date_debut"], "mode_ordre": T.MODES_ORDRE[groupe["mode_ordre"]],
        "mode_ordre_code": groupe["mode_ordre"],
        "penalite": formater(groupe["penalite"], devise) if groupe["penalite"] else "", "jours_grace": groupe["jours_grace"],
        "cagnotte": formater(groupe["montant"] * total_mains, devise), "nombre_tours": total_mains,
        "moi": {"membre_id": moi_["id"], "role": moi_["role"], "mains": moi_["mains"],
                "du": formater(T.du_par_tour(groupe, moi_), devise), "du_brut": T.du_par_tour(groupe, moi_)},
        "organisateur": organisateur,
        "invitation": f"{g.config.url}/rejoindre/{groupe['code']}" if organisateur else None,
        "membres": [{"id": m["id"], "nom": m["nom"], "role": m["role"], "mains": m["mains"], "rang": m["rang"],
                     "compte": m["utilisateur_id"] is not None,
                     # Le numéro et la fiabilité ne sont montrés qu'à l'organisateur.
                     **({"telephone": m["telephone"], "fiabilite": T.fiabilite(g.base, m["telephone"])} if organisateur else {})}
                    for m in membres],
        "tours": [{"id": t["id"], "numero": t["numero"], "echeance": t["echeance"], "beneficiaire": t["beneficiaire"],
                   "beneficiaire_id": t["beneficiaire_id"], "statut": t["statut"], "verse_le": t["verse_le"],
                   "montant_verse": formater(t["montant_verse"], devise) if t["montant_verse"] is not None else None}
                  for t in tours],
        "tour_courant": etat,
    })


@route("GET", r"/api/tontines/(\d+)")
def lire_tontine(g, groupe_id):
    vue_tontine(g, int(groupe_id))


@route("PUT", r"/api/tontines/(\d+)")
def modifier_tontine(g, groupe_id):
    groupe_id = int(groupe_id)
    T.exiger_organisateur(g.base, groupe_id, g.utilisateur)
    if T.groupe(g.base, groupe_id)["statut"] != "brouillon":
        raise ValueError("La tontine a commencé : ses règles ne peuvent plus changer.")
    r = lire_reglages_groupe(g.donnees())
    for cle, valeurs in (("frequence", FREQUENCES), ("mode_ordre", T.MODES_ORDRE)):
        if r[cle] not in valeurs:
            raise ValueError("Valeur inconnue.")
    datetime.date.fromisoformat(r["date_debut"])
    if r["montant"] <= 0:
        raise ValueError("La cotisation doit être supérieure à zéro.")
    with g.base.transaction() as c:
        c.execute("UPDATE groupes SET nom = ?, description = ?, devise = ?, montant = ?, frequence = ?, date_debut = ?, "
                  "mode_ordre = ?, penalite = ?, jours_grace = ? WHERE id = ?",
                  (r["nom"], r["description"], r["devise"], r["montant"], r["frequence"], r["date_debut"],
                   r["mode_ordre"], r["penalite"], max(0, min(30, r["jours_grace"])), groupe_id))
        T.journaliser(c, groupe_id, g.utilisateur["nom"], "reglages", {
            "cotisation": formater(r["montant"], r["devise"]), "frequence": FREQUENCES[r["frequence"]],
            "debut": r["date_debut"], "ordre": T.MODES_ORDRE[r["mode_ordre"]]})
    vue_tontine(g, groupe_id)


@route("DELETE", r"/api/tontines/(\d+)")
def supprimer_tontine(g, groupe_id):
    groupe_id = int(groupe_id)
    T.exiger_organisateur(g.base, groupe_id, g.utilisateur)
    if T.groupe(g.base, groupe_id)["statut"] == "en_cours":
        raise ValueError("Une tontine en cours ne peut pas être supprimée : son historique appartient à tous ses membres.")
    g.base.modifier("DELETE FROM groupes WHERE id = ?", (groupe_id,))
    g.json({"ok": True})


# --- Membres -----------------------------------------------------------------------------------------------------------------

@route("POST", r"/api/tontines/(\d+)/membres")
def ajouter_membre(g, groupe_id):
    groupe_id = int(groupe_id)
    T.exiger_organisateur(g.base, groupe_id, g.utilisateur)
    _, formule, _ = g.formule()
    nombre = g.base.un("SELECT count(*) AS n FROM membres WHERE groupe_id = ?", (groupe_id,))["n"]
    if nombre >= formule["membres"]:
        raise ErreurHTTP(402, f"La formule gratuite permet {formule['membres']} membres par tontine. Passe à la formule "
                              "Organisateur pour en accueillir davantage.")
    d = g.donnees()
    T.ajouter_membre(g.base, groupe_id, g.utilisateur["nom"], texte(d, "nom", 80, True), texte(d, "telephone", 30, True),
                     entier(d, "mains", 1))
    vue_tontine(g, groupe_id)


@route("PUT", r"/api/tontines/(\d+)/membres/(\d+)")
def modifier_membre(g, groupe_id, membre_id):
    groupe_id = int(groupe_id)
    T.exiger_organisateur(g.base, groupe_id, g.utilisateur)
    d = g.donnees()
    T.modifier_membre(g.base, groupe_id, int(membre_id), g.utilisateur["nom"],
                      entier(d, "mains") if "mains" in d else None, entier(d, "rang") if "rang" in d else None)
    vue_tontine(g, groupe_id)


@route("DELETE", r"/api/tontines/(\d+)/membres/(\d+)")
def retirer_membre(g, groupe_id, membre_id):
    groupe_id = int(groupe_id)
    T.exiger_organisateur(g.base, groupe_id, g.utilisateur)
    T.retirer_membre(g.base, groupe_id, int(membre_id), g.utilisateur["nom"])
    vue_tontine(g, groupe_id)


@route("POST", r"/api/tontines/(\d+)/demarrer")
def demarrer(g, groupe_id):
    groupe_id = int(groupe_id)
    T.exiger_organisateur(g.base, groupe_id, g.utilisateur)
    T.demarrer(g.base, groupe_id, g.utilisateur["nom"])
    vue_tontine(g, groupe_id)


# --- Invitation ----------------------------------------------------------------------------------------------------------------

@route("GET", r"/api/invitation/([\w-]{6,40})", connecte=False)
def voir_invitation(g, code):
    groupe = g.base.un("SELECT * FROM groupes WHERE code = ?", (code,))
    if not groupe:
        raise Introuvable("Ce lien d'invitation n'est pas valable.")
    organisateur = g.base.un("SELECT nom FROM utilisateurs WHERE id = ?", (groupe["createur_id"],))
    membres = g.base.un("SELECT count(*) AS n FROM membres WHERE groupe_id = ?", (groupe["id"],))["n"]
    g.json({"nom": groupe["nom"], "description": groupe["description"], "organisateur": organisateur["nom"],
            "montant": formater(groupe["montant"], groupe["devise"]), "frequence": FREQUENCES[groupe["frequence"]],
            "debut": date_francaise(groupe["date_debut"]), "membres": membres, "statut": groupe["statut"]})


@route("POST", r"/api/invitation/([\w-]{6,40})/rejoindre")
def rejoindre(g, code):
    groupe = g.base.un("SELECT * FROM groupes WHERE code = ?", (code,))
    if groupe:
        createur = g.base.utilisateur(groupe["createur_id"])
        limite = FORMULES["organisateur" if (createur.get("formule_jusqua") or "") >= datetime.datetime.now(
            datetime.timezone.utc).isoformat() else "gratuit"]["membres"]
        nombre = g.base.un("SELECT count(*) AS n FROM membres WHERE groupe_id = ?", (groupe["id"],))["n"]
        deja = g.base.un("SELECT 1 FROM membres WHERE groupe_id = ? AND (utilisateur_id = ? OR telephone = ?)",
                         (groupe["id"], g.utilisateur["id"], g.utilisateur["telephone"]))
        if not deja and nombre >= limite:
            raise ErreurHTTP(402, "Cette tontine est complète.")
    g.json({"id": T.rejoindre(g.base, code, g.utilisateur)})


# --- Tours et cotisations -----------------------------------------------------------------------------------------------------

@route("POST", r"/api/tontines/(\d+)/tours/(\d+)/cotisations")
def cotiser(g, groupe_id, tour_id):
    groupe_id = int(groupe_id)
    moi_ = T.membre_de(g.base, groupe_id, g.utilisateur)
    groupe = T.groupe(g.base, groupe_id)
    d = g.donnees()
    organisateur = moi_["role"] == "organisateur"
    membre_id = entier(d, "membre_id", moi_["id"]) if organisateur else moi_["id"]
    # Un membre déclare son propre paiement ; l'organisateur enregistre directement ce qu'il a reçu.
    T.enregistrer_cotisation(g.base, groupe_id, int(tour_id), membre_id, g.utilisateur["nom"],
                             vers_unites(d.get("montant", ""), groupe["devise"]), texte(d, "moyen", 20),
                             texte(d, "reference", 100), confirmee=organisateur)
    vue_tontine(g, groupe_id)


@route("POST", r"/api/tontines/(\d+)/cotisations/(\d+)/decision")
def decider(g, groupe_id, cotisation_id):
    groupe_id = int(groupe_id)
    T.exiger_organisateur(g.base, groupe_id, g.utilisateur)
    T.decider_cotisation(g.base, groupe_id, int(cotisation_id), g.utilisateur["nom"], bool(g.donnees().get("accepter")))
    vue_tontine(g, groupe_id)


@route("POST", r"/api/tontines/(\d+)/tours/(\d+)/verser")
def verser(g, groupe_id, tour_id):
    groupe_id = int(groupe_id)
    T.exiger_organisateur(g.base, groupe_id, g.utilisateur)
    T.verser(g.base, groupe_id, int(tour_id), g.utilisateur["nom"], bool(g.donnees().get("forcer")))
    vue_tontine(g, groupe_id)


@route("GET", r"/api/tontines/(\d+)/rappels")
def rappels(g, groupe_id):
    groupe_id = int(groupe_id)
    T.exiger_organisateur(g.base, groupe_id, g.utilisateur)
    g.json({"rappels": T.rappels(g.base, groupe_id)})


@route("GET", r"/api/tontines/(\d+)/journal")
def journal(g, groupe_id):
    groupe_id = int(groupe_id)
    T.membre_de(g.base, groupe_id, g.utilisateur)
    intact, n = T.verifier_journal(g.base, groupe_id)
    entrees = g.base.tous("SELECT date, auteur, action, details, empreinte FROM journal WHERE groupe_id = ? "
                          "ORDER BY id DESC", (groupe_id,))
    g.json({"intact": intact, "verification": n,
            "entrees": [dict(e, details=json.loads(e["details"])) for e in entrees]})


@route("GET", r"/api/tontines/(\d+)/export\.csv")
def exporter(g, groupe_id):
    groupe_id = int(groupe_id)
    T.exiger_organisateur(g.base, groupe_id, g.utilisateur)
    _, formule, _ = g.formule()
    if not formule["export"]:
        raise ErreurHTTP(402, "L'export Excel fait partie de la formule Organisateur.")
    groupe = T.groupe(g.base, groupe_id)
    lignes = g.base.tous(
        "SELECT t.numero, t.echeance, b.nom AS beneficiaire, m.nom, c.montant, c.penalite, c.moyen, c.reference, c.statut, "
        "c.declare_le, c.confirme_le, c.confirme_par FROM cotisations c JOIN tours t ON t.id = c.tour_id "
        "JOIN membres m ON m.id = c.membre_id JOIN membres b ON b.id = t.beneficiaire_id "
        "WHERE c.groupe_id = ? ORDER BY t.numero, c.id", (groupe_id,))
    tampon = io.StringIO()
    ecrivain = csv.writer(tampon, delimiter=";")  # le point-virgule est le séparateur qu'Excel attend en français
    ecrivain.writerow(["Tour", "Échéance", "Bénéficiaire", "Membre", f"Montant ({groupe['devise']})", "Pénalité",
                       "Moyen", "Référence", "Statut", "Déclaré le", "Confirmé le", "Confirmé par"])
    decimales = DEVISES[groupe["devise"]][2]
    for l in lignes:
        valeur = lambda x: f"{x / 10 ** decimales:.{decimales}f}".replace(".", ",")  # noqa: E731
        ecrivain.writerow([l["numero"], l["echeance"], l["beneficiaire"], l["nom"], valeur(l["montant"]),
                           valeur(l["penalite"]), T.MOYENS[l["moyen"]], l["reference"], STATUTS_COTISATION[l["statut"]], l["declare_le"],
                           l["confirme_le"] or "", l["confirme_par"] or ""])
    nom = re.sub(r"[^A-Za-z0-9]+", "-", groupe["nom"]).strip("-") or "tontine"
    g.envoyer(200, "﻿" + tampon.getvalue(), "text/csv",  # le BOM fait lire les accents correctement par Excel
              {"Content-Disposition": f'attachment; filename="{nom}.csv"'})


# --- Démarrage -------------------------------------------------------------------------------------------------------------------

def creer_serveur(config, hote="127.0.0.1", port=8070):
    base = Base(config.base)
    limiteurs = {"connexion": Limiteur(10, 15 * 60), "inscription": Limiteur(10, 3600)}
    gestionnaire = type("GestionnaireCotiz", (Gestionnaire,), {"config": config, "base": base, "limiteurs": limiteurs})
    serveur = ThreadingHTTPServer((hote, port), gestionnaire)
    serveur.daemon_threads = True
    serveur.base = base
    return serveur


def servir(config, hote="127.0.0.1", port=8070):
    serveur = creer_serveur(config, hote, port)
    print(f"🤝 Cotiz est en ligne : {config.url}/")
    print(f"   Base de données : {config.base}")
    if config.demo:
        print("   Mode démonstration : la formule Organisateur s'active sans payer.")
    print("   (Ctrl+C pour arrêter)")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nAu revoir !")
    finally:
        serveur.server_close()
