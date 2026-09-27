"""Le serveur web de Rédigo : les pages, et l'API utilisée par l'application.

Il ne dépend que de la bibliothèque standard de Python (et de reportlab pour le PDF). En production, on le place
derrière un serveur HTTPS (Caddy, Nginx…) qui lui transmet les requêtes.
"""

import json
import os
import re
import secrets
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from memoire.apercu import apercu
from memoire.docx import ecrire_docx
from memoire.reglages import ALIGNEMENTS, NORMES, NUMEROTATIONS, POLICES, POSITIONS_PAGINATION, Reglages
from memoire.serveur import nom_de_fichier, pdf_disponible, statistiques
from memoire.source import importer_docx, lire, numeroter

from . import bibliographie, courriel, paiement
from .base import FORMULES, MENTION, PRIX_PASS, Base, Introuvable
from .securite import Limiteur, hacher_mot_de_passe, mot_de_passe_acceptable, verifier_mot_de_passe

DOSSIER = os.path.dirname(os.path.abspath(__file__))
DOSSIER_MEMOIRE = os.path.join(os.path.dirname(DOSSIER), "memoire")
TAILLE_MAX_CORPS = 20 * 1024 * 1024
TAILLE_MAX_TEXTE = 2 * 1024 * 1024
INTERVALLE_VERSIONS = 10 * 60  # une version automatique au plus toutes les 10 minutes d'écriture
COOKIE = "redigo_session"
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")

PAGES = {"/": "accueil.html", "/app": "app.html"}
FICHIERS_STATIQUES = {"style.css": "text/css", "app.js": "text/javascript", "accueil.css": "text/css",
                      "partage.js": "text/javascript", "commun.js": "text/javascript"}


@dataclass
class Configuration:
    base: str = os.path.join(DOSSIER, "donnees", "redigo.db")
    url: str = "http://127.0.0.1:8060"
    stripe_cle: str = ""
    stripe_secret_webhook: str = ""
    demo: bool = True               # sans Stripe : un bouton active le Pass sans payer (pour essayer)
    smtp_hote: str = ""
    smtp_port: int = 587
    smtp_utilisateur: str = ""
    smtp_mot_de_passe: str = ""
    smtp_expediteur: str = "Rédigo <ne-pas-repondre@redigo.local>"
    derriere_proxy: bool = False    # faire confiance à X-Forwarded-For pour l'adresse du visiteur
    options: dict = field(default_factory=dict)

    @classmethod
    def depuis_environnement(cls, **surcharges):
        env = os.environ
        config = cls(
            base=env.get("REDIGO_BASE", cls.base),
            url=env.get("REDIGO_URL", cls.url).rstrip("/"),
            stripe_cle=env.get("STRIPE_SECRET_KEY", ""),
            stripe_secret_webhook=env.get("STRIPE_WEBHOOK_SECRET", ""),
            smtp_hote=env.get("REDIGO_SMTP_HOTE", ""),
            smtp_port=int(env.get("REDIGO_SMTP_PORT", "587")),
            smtp_utilisateur=env.get("REDIGO_SMTP_UTILISATEUR", ""),
            smtp_mot_de_passe=env.get("REDIGO_SMTP_MOT_DE_PASSE", ""),
            smtp_expediteur=env.get("REDIGO_SMTP_EXPEDITEUR", cls.smtp_expediteur),
            derriere_proxy=env.get("REDIGO_DERRIERE_PROXY") == "1",
        )
        config.demo = env.get("REDIGO_DEMO", "0" if config.stripe_cle else "1") == "1"
        for cle, valeur in surcharges.items():
            setattr(config, cle, valeur)
        return config

    @property
    def paiement(self):
        return "stripe" if self.stripe_cle else ("demo" if self.demo else None)


class ErreurHTTP(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# --- Routes -----------------------------------------------------------------------------------------------

ROUTES = []


def route(methode, motif, connecte=True):
    def enregistrer(fonction):
        ROUTES.append((methode, re.compile(f"^{motif}$"), fonction, connecte))
        return fonction
    return enregistrer


class Gestionnaire(BaseHTTPRequestHandler):
    server_version = "Redigo/1.0"
    protocol_version = "HTTP/1.1"
    config = None     # renseignés par creer_serveur()
    base = None
    limiteurs = None

    def log_message(self, format, *args):
        if self.config and self.config.options.get("journal"):
            super().log_message(format, *args)

    # --- Réponses ---

    def envoyer(self, code, contenu, type_contenu, entetes=None):
        if isinstance(contenu, str):
            contenu = contenu.encode("utf-8")
            type_contenu += "; charset=utf-8"
        self.send_response(code)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(contenu)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")  # les liens de partage ne fuient pas vers d'autres sites
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

    def fichier(self, contenu, type_contenu, nom):
        self.envoyer(200, contenu, type_contenu, {"Content-Disposition": f'attachment; filename="{nom}"'})

    def cookie_session(self, jeton, duree):
        securise = "; Secure" if self.config.url.startswith("https://") else ""
        return {"Set-Cookie": f"{COOKIE}={jeton}; Path=/; HttpOnly; SameSite=Lax; Max-Age={duree}{securise}"}

    # --- Requêtes ---

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
                raise ErreurHTTP(413, "Fichier trop volumineux (20 Mo au maximum).")
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
                    self.corps_brut()  # lu tout de suite : la connexion reste propre même si on refuse la requête
                except ErreurHTTP:
                    self.close_connection = True
                    raise
            if methode == "GET" and chemin in PAGES:
                return self.page(PAGES[chemin])
            if methode == "GET" and chemin.startswith("/partage/"):
                return self.page("partage.html")
            if methode == "GET" and chemin.startswith("/static/"):
                return self.statique(chemin[len("/static/"):])
            for methode_route, motif, fonction, connecte in ROUTES:
                trouve = motif.match(chemin)
                if not trouve or methode_route != methode:
                    continue
                # Protection CSRF : un autre site ne peut pas ajouter cet en-tête à une requête vers Rédigo.
                if methode != "GET" and self.headers.get("X-Redigo") != "1" and fonction is not webhook_stripe:
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
        except ValueError as erreur:
            self.json({"erreur": str(erreur)}, 400)
        except paiement.ErreurPaiement as erreur:
            self.json({"erreur": str(erreur)}, 502)
        except Exception as erreur:  # un fichier importé peut être abîmé de mille façons
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

    # --- Outils communs ---

    def formule(self):
        code, fin, licence = self.base.formule(self.utilisateur)
        return code, FORMULES[code], fin, licence

    def projet(self, projet_id):
        return self.base.projet(int(projet_id), self.utilisateur["id"])

    def limiter(self, nom, cle):
        if not self.limiteurs[nom].autorise(cle):
            raise ErreurHTTP(429, "Trop de tentatives. Réessaie dans quelques minutes.")


# --- Préparation du document ---------------------------------------------------------------------------------

def preparer(base, projet):
    """Texte + réglages + bibliographie → blocs prêts à mettre en forme."""
    reglages = Reglages.depuis_dict(projet["reglages"])
    blocs = lire(projet["texte"])
    blocs, citees, inconnues = bibliographie.appliquer(blocs, base.references(projet["id"]), projet["style_biblio"],
                                                       bool(projet["biblio_toutes"]))
    return numeroter(blocs, reglages.numerotation), reglages, citees, inconnues


def rendu_apercu(base, projet):
    blocs, reglages, citees, inconnues = preparer(base, projet)
    entrees = None
    if reglages.sommaire and pdf_disponible() and len(projet["texte"]) < 400_000:
        from memoire.pdf import ecrire_pdf
        _, entrees = ecrire_pdf(blocs, reglages)  # pour afficher les vrais numéros de page du sommaire
    return {"html": apercu(blocs, reglages, entrees), **statistiques(blocs, projet["texte"]),
            "citees": citees, "inconnues": inconnues}


def exporter(base, projet, format, mention):
    blocs, reglages, _, _ = preparer(base, projet)
    if format == "docx":
        return (ecrire_docx(blocs, reglages, mention),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document", nom_de_fichier(reglages, "docx"))
    if not pdf_disponible():
        raise ErreurHTTP(501, "L'export PDF n'est pas disponible sur ce serveur (reportlab manquant).")
    from memoire.pdf import ecrire_pdf
    return ecrire_pdf(blocs, reglages, mention)[0], "application/pdf", nom_de_fichier(reglages, "pdf")


def texte(donnees, cle, maximum=300, obligatoire=False):
    valeur = donnees.get(cle, "")
    if not isinstance(valeur, str):
        raise ValueError(f"Le champ « {cle} » est invalide.")
    valeur = valeur.strip()
    if obligatoire and not valeur:
        raise ValueError(f"Le champ « {cle} » est obligatoire.")
    if len(valeur) > maximum:
        raise ValueError(f"Le champ « {cle} » est trop long ({maximum} caractères au maximum).")
    return valeur


def resume_utilisateur(g):
    code, formule, fin, licence = g.formule()
    return {"email": g.utilisateur["email"], "nom": g.utilisateur["nom"],
            "formule": {"code": code, "nom": formule["nom"], "fin": fin, "projets": formule["projets"],
                        "versions": formule["versions"], "mention": formule["mention"],
                        "universite": licence["universite"] if licence else None}}


# --- Configuration et comptes -------------------------------------------------------------------------------------

@route("GET", "/api/configuration", connecte=False)
def configuration(g):
    g.json({
        "polices": POLICES, "alignements": ALIGNEMENTS, "numerotations": NUMEROTATIONS,
        "paginations": POSITIONS_PAGINATION, "pdf": pdf_disponible(),
        "normes": {cle: {"nom": nom, "reglages": Reglages.depuis_dict(valeurs).vers_dict()}
                   for cle, (nom, valeurs) in NORMES.items()},
        "defaut": Reglages().vers_dict(), "styles_biblio": bibliographie.STYLES, "types_references": bibliographie.TYPES,
        "formules": FORMULES, "prix_pass": PRIX_PASS, "paiement": g.config.paiement,
    })


@route("POST", "/api/inscription", connecte=False)
def inscription(g):
    g.limiter("inscription", g.adresse_ip())
    d = g.donnees()
    email = texte(d, "email", 254, True).lower()
    nom = texte(d, "nom", 100)
    mot_de_passe = d.get("mot_de_passe") if isinstance(d.get("mot_de_passe"), str) else ""
    if not EMAIL.match(email):
        raise ValueError("Cette adresse e-mail n'est pas valide.")
    probleme = mot_de_passe_acceptable(mot_de_passe)
    if probleme:
        raise ValueError(probleme)
    if g.base.utilisateur_par_email(email):
        raise ErreurHTTP(409, "Un compte existe déjà avec cette adresse. Connecte-toi.")
    identifiant = g.base.creer_utilisateur(email, nom, hacher_mot_de_passe(mot_de_passe))
    jeton = g.base.ouvrir_session(identifiant)
    g.utilisateur = g.base.utilisateur(identifiant)
    g.json(resume_utilisateur(g), 201, g.cookie_session(jeton, 30 * 86400))


@route("POST", "/api/connexion", connecte=False)
def connexion(g):
    d = g.donnees()
    email = texte(d, "email", 254).lower()
    g.limiter("connexion", g.adresse_ip())
    g.limiter("connexion", email)
    utilisateur = g.base.utilisateur_par_email(email)
    mot_de_passe = d.get("mot_de_passe") if isinstance(d.get("mot_de_passe"), str) else ""
    if not utilisateur or not verifier_mot_de_passe(mot_de_passe, utilisateur["hash"]):
        raise ErreurHTTP(401, "E-mail ou mot de passe incorrect.")
    g.utilisateur = utilisateur
    g.json(resume_utilisateur(g), 200, g.cookie_session(g.base.ouvrir_session(utilisateur["id"]), 30 * 86400))


@route("POST", "/api/deconnexion", connecte=False)
def deconnexion(g):
    g.base.fermer_session(g.jeton_session())
    g.json({"ok": True}, 200, g.cookie_session("", 0))


@route("GET", "/api/moi")
def moi(g):
    g.json(resume_utilisateur(g))


@route("POST", "/api/mot-de-passe/oubli", connecte=False)
def mot_de_passe_oublie(g):
    g.limiter("oubli", g.adresse_ip())
    email = texte(g.donnees(), "email", 254).lower()
    g.limiter("oubli", email)
    utilisateur = g.base.utilisateur_par_email(email)
    if utilisateur:
        jeton = g.base.demander_reinitialisation(utilisateur["id"])
        courriel.envoyer(g.config, email, "Rédigo — nouveau mot de passe",
                         "Bonjour,\n\nPour choisir un nouveau mot de passe, ouvre ce lien (valable une heure) :\n"
                         f"{g.config.url}/app#reinitialiser={jeton}\n\n"
                         "Si tu n'as rien demandé, ignore simplement ce message.\n\nRédigo")
    g.json({"ok": True})  # même réponse si le compte n'existe pas : on ne révèle pas qui est inscrit


@route("POST", "/api/mot-de-passe/reinitialiser", connecte=False)
def reinitialiser(g):
    g.limiter("oubli", g.adresse_ip())
    d = g.donnees()
    mot_de_passe = d.get("mot_de_passe") if isinstance(d.get("mot_de_passe"), str) else ""
    probleme = mot_de_passe_acceptable(mot_de_passe)
    if probleme:
        raise ValueError(probleme)
    identifiant = g.base.utiliser_reinitialisation(texte(d, "jeton", 100))
    if not identifiant:
        raise ErreurHTTP(400, "Ce lien a expiré ou a déjà servi. Fais une nouvelle demande.")
    g.base.changer_mot_de_passe(identifiant, hacher_mot_de_passe(mot_de_passe))
    g.utilisateur = g.base.utilisateur(identifiant)
    g.json(resume_utilisateur(g), 200, g.cookie_session(g.base.ouvrir_session(identifiant), 30 * 86400))


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
    g.json({"ok": True}, 200, g.cookie_session(g.base.ouvrir_session(g.utilisateur["id"]), 30 * 86400))


@route("GET", "/api/compte/export")
def exporter_compte(g):
    """Toutes les données du compte, en JSON (droit à la portabilité)."""
    projets = []
    for resume in g.base.projets(g.utilisateur["id"]):
        projet = g.base.projet(resume["id"])
        projets.append({"titre": projet["titre"], "texte": projet["texte"], "reglages": projet["reglages"],
                        "style_biblio": projet["style_biblio"], "references": g.base.references(projet["id"]),
                        "commentaires": g.base.commentaires(projet["id"]), "modifie_le": projet["modifie_le"]})
    contenu = {"compte": {"email": g.utilisateur["email"], "nom": g.utilisateur["nom"],
                          "cree_le": g.utilisateur["cree_le"]}, "memoires": projets}
    g.fichier(json.dumps(contenu, ensure_ascii=False, indent=2).encode(), "application/json", "redigo-export.json")


@route("POST", "/api/compte/supprimer")
def supprimer_compte(g):
    if not verifier_mot_de_passe(str(g.donnees().get("mot_de_passe", "")), g.utilisateur["hash"]):
        raise ErreurHTTP(403, "Mot de passe incorrect.")
    g.base.supprimer_utilisateur(g.utilisateur["id"])
    g.json({"ok": True}, 200, g.cookie_session("", 0))


# --- Paiement ------------------------------------------------------------------------------------------------------

@route("POST", "/api/paiement/commande")
def commander(g):
    if g.config.paiement == "stripe":
        url = paiement.creer_session_stripe(g.config.stripe_cle, g.utilisateur, PRIX_PASS, g.config.url)
        return g.json({"url": url})
    if g.config.paiement == "demo":
        g.base.activer_pass(g.utilisateur["id"], "demo", f"demo-{secrets.token_hex(8)}", 0)
        g.utilisateur = g.base.utilisateur(g.utilisateur["id"])
        return g.json({"active": True, **resume_utilisateur(g)})
    raise ErreurHTTP(503, "Le paiement n'est pas encore ouvert.")


@route("POST", "/api/paiement/webhook", connecte=False)
def webhook_stripe(g):
    corps = g.corps_brut()
    if not g.config.stripe_secret_webhook or not paiement.verifier_signature(
            corps, g.headers.get("Stripe-Signature"), g.config.stripe_secret_webhook):
        raise ErreurHTTP(400, "Signature invalide.")
    paiement.traiter_evenement(g.base, json.loads(corps))
    g.json({"recu": True})


# --- Modèles ------------------------------------------------------------------------------------------------------

@route("GET", "/api/modeles")
def modeles(g):
    _, _, _, licence = g.formule()
    g.json({
        "licence": {"nom": f"Modèle officiel — {licence['universite']}", "reglages":
                    Reglages.depuis_dict(json.loads(licence["reglages"])).vers_dict()}
        if licence and licence.get("reglages") else None,
        "perso": g.base.modeles(g.utilisateur["id"]),
    })


@route("POST", "/api/modeles")
def creer_modele(g):
    d = g.donnees()
    if len(g.base.modeles(g.utilisateur["id"])) >= 30:
        raise ValueError("Tu as déjà 30 modèles : supprimes-en un.")
    reglages = Reglages.depuis_dict(d.get("reglages")).vers_dict()
    reglages.pop("garde")  # un modèle décrit la mise en forme, pas la page de garde d'un mémoire précis
    identifiant = g.base.creer_modele(g.utilisateur["id"], texte(d, "nom", 80, True), reglages)
    g.json({"id": identifiant}, 201)


@route("DELETE", r"/api/modeles/(\d+)")
def supprimer_modele(g, modele_id):
    g.base.supprimer_modele(g.utilisateur["id"], int(modele_id))
    g.json({"ok": True})


# --- Mémoires ------------------------------------------------------------------------------------------------------

def vue_projet(base, projet):
    return {k: projet[k] for k in ("id", "titre", "texte", "reglages", "style_biblio", "revision", "modifie_le")} | {
        "biblio_toutes": bool(projet["biblio_toutes"])}


@route("GET", "/api/projets")
def liste_projets(g):
    g.json({"projets": g.base.projets(g.utilisateur["id"])})


@route("POST", "/api/projets")
def creer_projet(g):
    _, formule, _, _ = g.formule()
    if g.base.nombre_de_projets(g.utilisateur["id"]) >= formule["projets"]:
        raise ErreurHTTP(402, "La formule gratuite permet un seul mémoire. Passe au Pass Mémoire pour en créer d'autres."
                         if formule["projets"] == 1 else f"Tu as atteint la limite de {formule['projets']} mémoires.")
    d = g.donnees()
    reglages = Reglages.depuis_dict(d.get("reglages")).vers_dict()
    titre = texte(d, "titre", 200) or "Mon mémoire"
    reglages["garde"]["titre"] = titre
    if g.utilisateur["nom"] and not reglages["garde"]["auteur"]:
        reglages["garde"]["auteur"] = g.utilisateur["nom"]
    contenu = "# Introduction\n\n"
    if d.get("exemple"):
        with open(os.path.join(DOSSIER, "exemple.md"), encoding="utf-8") as f:
            contenu = f.read()
    identifiant = g.base.creer_projet(g.utilisateur["id"], titre, contenu, reglages)
    if d.get("exemple"):
        for reference in EXEMPLE_REFERENCES:
            g.base.enregistrer_reference(identifiant, bibliographie.nettoyer(reference))
    g.json(vue_projet(g.base, g.base.projet(identifiant)), 201)


@route("GET", r"/api/projets/(\d+)")
def lire_projet(g, projet_id):
    g.json(vue_projet(g.base, g.projet(projet_id)))


@route("PUT", r"/api/projets/(\d+)")
def enregistrer_projet(g, projet_id):
    projet = g.projet(projet_id)
    d = g.donnees()
    champs = {}
    if "texte" in d:
        if not isinstance(d["texte"], str) or len(d["texte"]) > TAILLE_MAX_TEXTE:
            raise ValueError("Le texte est trop long (2 millions de caractères au maximum).")
        champs["texte"] = d["texte"]
    if "reglages" in d:
        champs["reglages"] = Reglages.depuis_dict(d["reglages"]).vers_dict()
    if "titre" in d:
        champs["titre"] = texte(d, "titre", 200) or "Sans titre"
    if "style_biblio" in d:
        if d["style_biblio"] not in bibliographie.STYLES:
            raise ValueError("Style de bibliographie inconnu.")
        champs["style_biblio"] = d["style_biblio"]
    if "biblio_toutes" in d:
        champs["biblio_toutes"] = int(bool(d["biblio_toutes"]))
    revision = g.base.enregistrer_projet(projet["id"], int(d.get("revision", 0)), champs)
    if revision is None:
        raise ErreurHTTP(409, "Ce mémoire a été modifié ailleurs (dans un autre onglet ?). Recharge la page.")
    projet.update(champs)
    version_automatique(g, projet)
    g.json({"revision": revision})


def version_automatique(g, projet):
    """Garde une version de temps en temps, pour pouvoir revenir en arrière."""
    import datetime
    derniere = g.base.derniere_version(projet["id"])
    reglages = projet["reglages"] if isinstance(projet["reglages"], dict) else json.loads(projet["reglages"])
    if derniere:
        age = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(derniere["cree_le"]))
        if age.total_seconds() < INTERVALLE_VERSIONS or derniere["texte"] == projet["texte"]:
            return
    _, formule, _, _ = g.formule()
    mots = statistiques([], projet["texte"])["mots"]
    g.base.creer_version(projet["id"], projet["texte"], reglages, "", True, mots, formule["versions"])


@route("DELETE", r"/api/projets/(\d+)")
def supprimer_projet(g, projet_id):
    g.base.supprimer_projet(g.projet(projet_id)["id"])
    g.json({"ok": True})


@route("POST", r"/api/projets/(\d+)/apercu")
def apercu_projet(g, projet_id):
    g.json(rendu_apercu(g.base, g.projet(projet_id)))


@route("POST", r"/api/projets/(\d+)/export/(docx|pdf)")
def exporter_projet(g, projet_id, format):
    _, formule, _, _ = g.formule()
    contenu, type_contenu, nom = exporter(g.base, g.projet(projet_id), format, MENTION if formule["mention"] else "")
    g.fichier(contenu, type_contenu, nom)


@route("POST", "/api/importer-docx")
def importer_word(g):
    try:
        g.json({"texte": importer_docx(g.corps_brut())})
    except Exception:
        raise ValueError("Ce fichier n'est pas un document Word (.docx) lisible.")


# --- Versions ------------------------------------------------------------------------------------------------------

@route("GET", r"/api/projets/(\d+)/versions")
def versions(g, projet_id):
    g.json({"versions": g.base.versions(g.projet(projet_id)["id"])})


@route("POST", r"/api/projets/(\d+)/versions")
def creer_version(g, projet_id):
    projet = g.projet(projet_id)
    _, formule, _, _ = g.formule()
    libelle = texte(g.donnees(), "libelle", 100) or "Version enregistrée"
    mots = statistiques([], projet["texte"])["mots"]
    identifiant = g.base.creer_version(projet["id"], projet["texte"], projet["reglages"], libelle, False, mots,
                                       formule["versions"])
    g.json({"id": identifiant}, 201)


@route("GET", r"/api/projets/(\d+)/versions/(\d+)")
def lire_version(g, projet_id, version_id):
    version = g.base.version(g.projet(projet_id)["id"], int(version_id))
    g.json({k: version[k] for k in ("id", "texte", "libelle", "cree_le")})


@route("POST", r"/api/projets/(\d+)/versions/(\d+)/restaurer")
def restaurer_version(g, projet_id, version_id):
    projet = g.projet(projet_id)
    version = g.base.version(projet["id"], int(version_id))
    _, formule, _, _ = g.formule()
    # L'état actuel est d'abord gardé : restaurer ne fait rien perdre.
    g.base.creer_version(projet["id"], projet["texte"], projet["reglages"], "Avant la restauration", False,
                         statistiques([], projet["texte"])["mots"], formule["versions"])
    revision = g.base.enregistrer_projet(projet["id"], projet["revision"],
                                         {"texte": version["texte"], "reglages": version["reglages"]})
    if revision is None:
        raise ErreurHTTP(409, "Ce mémoire vient d'être modifié. Réessaie.")
    g.json(vue_projet(g.base, g.base.projet(projet["id"])))


# --- Bibliographie ---------------------------------------------------------------------------------------------------

@route("GET", r"/api/projets/(\d+)/references")
def references(g, projet_id):
    g.json({"references": g.base.references(g.projet(projet_id)["id"])})


@route("POST", r"/api/projets/(\d+)/references")
def ajouter_reference(g, projet_id):
    projet = g.projet(projet_id)
    if len(g.base.references(projet["id"])) >= 2000:
        raise ValueError("2 000 références au maximum par mémoire.")
    reference = bibliographie.nettoyer(g.donnees())
    identifiant = g.base.enregistrer_reference(projet["id"], reference)
    g.json(dict(reference, id=identifiant), 201)


@route("PUT", r"/api/projets/(\d+)/references/(\d+)")
def modifier_reference(g, projet_id, reference_id):
    projet = g.projet(projet_id)
    reference = bibliographie.nettoyer(g.donnees())
    g.base.enregistrer_reference(projet["id"], reference, int(reference_id))
    g.json(dict(reference, id=int(reference_id)))


@route("DELETE", r"/api/projets/(\d+)/references/(\d+)")
def supprimer_reference(g, projet_id, reference_id):
    g.base.supprimer_reference(g.projet(projet_id)["id"], int(reference_id))
    g.json({"ok": True})


@route("POST", r"/api/projets/(\d+)/references/bibtex")
def importer_bibtex(g, projet_id):
    projet = g.projet(projet_id)
    contenu = g.donnees().get("bibtex", "")
    if not isinstance(contenu, str) or len(contenu) > 5_000_000:
        raise ValueError("Fichier BibTeX invalide.")
    existantes = {r["cle"] for r in g.base.references(projet["id"])}
    ajoutees, ignorees = 0, []
    for reference in bibliographie.importer_bibtex(contenu)[:2000]:
        if reference["cle"] in existantes:
            ignorees.append(reference["cle"])
            continue
        g.base.enregistrer_reference(projet["id"], reference)
        existantes.add(reference["cle"])
        ajoutees += 1
    g.json({"ajoutees": ajoutees, "ignorees": ignorees})


# --- Partage avec le directeur et commentaires ----------------------------------------------------------------------------

@route("GET", r"/api/projets/(\d+)/partages")
def partages(g, projet_id):
    g.json({"partages": g.base.partages(g.projet(projet_id)["id"])})


@route("POST", r"/api/projets/(\d+)/partages")
def creer_partage(g, projet_id):
    projet = g.projet(projet_id)
    if len(g.base.partages(projet["id"])) >= 10:
        raise ValueError("10 liens de partage au maximum : supprimes-en un.")
    nom = texte(g.donnees(), "nom", 100) or "Direction du mémoire"
    jeton = g.base.creer_partage(projet["id"], nom)
    g.json({"jeton": jeton, "url": f"{g.config.url}/partage/{jeton}"}, 201)


@route("DELETE", r"/api/projets/(\d+)/partages/(\d+)")
def supprimer_partage(g, projet_id, partage_id):
    g.base.supprimer_partage(g.projet(projet_id)["id"], int(partage_id))
    g.json({"ok": True})


@route("GET", r"/api/projets/(\d+)/commentaires")
def commentaires(g, projet_id):
    projet = g.projet(projet_id)
    liste = g.base.commentaires(projet["id"])
    if g.parametres.get("lu") == ["1"]:
        g.base.marquer_commentaires_lus(projet["id"])
    g.json({"commentaires": liste})


@route("POST", r"/api/projets/(\d+)/commentaires")
def commenter(g, projet_id):
    projet = g.projet(projet_id)
    d = g.donnees()
    parent = d.get("parent_id")
    identifiant = g.base.ajouter_commentaire(projet["id"], g.utilisateur["nom"] or g.utilisateur["email"], "etudiant",
                                             texte(d, "texte", 5000, True), texte(d, "extrait", 500),
                                             int(parent) if parent else None)
    g.json({"id": identifiant}, 201)


@route("POST", r"/api/projets/(\d+)/commentaires/(\d+)/resolu")
def resoudre(g, projet_id, commentaire_id):
    g.base.resoudre_commentaire(g.projet(projet_id)["id"], int(commentaire_id), bool(g.donnees().get("resolu", True)))
    g.json({"ok": True})


# Côté directeur : pas de compte, le lien secret suffit.

@route("GET", r"/api/partage/([\w-]{20,})", connecte=False)
def voir_partage(g, jeton):
    partage = g.base.partage(jeton)
    projet = g.base.projet(partage["projet_id"])
    etudiant = g.base.utilisateur(projet["utilisateur_id"])
    g.json({"titre": projet["titre"], "etudiant": etudiant["nom"] or "l'étudiant", "destinataire": partage["nom"],
            "modifie_le": projet["modifie_le"], **rendu_apercu(g.base, projet),
            "commentaires": g.base.commentaires(projet["id"])})


@route("POST", r"/api/partage/([\w-]{20,})/commentaires", connecte=False)
def commenter_partage(g, jeton):
    partage = g.base.partage(jeton)
    g.limiter("commentaires", jeton)
    d = g.donnees()
    parent = d.get("parent_id")
    identifiant = g.base.ajouter_commentaire(partage["projet_id"], texte(d, "auteur", 100) or partage["nom"],
                                             "directeur", texte(d, "texte", 5000, True), texte(d, "extrait", 500),
                                             int(parent) if parent else None)
    g.json({"id": identifiant}, 201)


@route("POST", r"/api/partage/([\w-]{20,})/pdf", connecte=False)
def pdf_partage(g, jeton):
    partage = g.base.partage(jeton)
    g.limiter("exports", jeton)
    contenu, type_contenu, nom = exporter(g.base, g.base.projet(partage["projet_id"]), "pdf", "")
    g.fichier(contenu, type_contenu, nom)


# --- Mémoire d'exemple -----------------------------------------------------------------------------------------------------

EXEMPLE_REFERENCES = [
    {"cle": "holec1981", "type": "livre", "auteurs": "Holec, Henri", "annee": "1981",
     "titre": "Autonomy and Foreign Language Learning", "editeur": "Pergamon Press", "lieu": "Oxford"},
    {"cle": "dupont2019", "type": "livre", "auteurs": "Dupont, Marie", "annee": "2019",
     "titre": "Le numérique à l'université : pratiques et enjeux", "editeur": "Éditions Universitaires", "lieu": "Paris"},
    {"cle": "amadieu2014", "type": "livre", "auteurs": "Amadieu, Franck ; Tricot, André", "annee": "2014",
     "titre": "Apprendre avec le numérique : mythes et réalités", "editeur": "Retz", "lieu": "Paris"},
    {"cle": "karsenti2013", "type": "article", "auteurs": "Karsenti, Thierry", "annee": "2013",
     "titre": "Le numérique au service de l'apprentissage", "revue": "Revue internationale des technologies en pédagogie universitaire",
     "volume": "10", "numero": "1", "pages": "1-12"},
]


# --- Démarrage ---------------------------------------------------------------------------------------------------------------

def creer_serveur(config, hote="127.0.0.1", port=8060):
    base = Base(config.base)
    limiteurs = {
        "connexion": Limiteur(10, 15 * 60), "inscription": Limiteur(10, 3600), "oubli": Limiteur(5, 3600),
        "commentaires": Limiteur(60, 3600), "exports": Limiteur(30, 3600),
    }
    gestionnaire = type("GestionnaireRedigo", (Gestionnaire,), {"config": config, "base": base, "limiteurs": limiteurs})
    serveur = ThreadingHTTPServer((hote, port), gestionnaire)
    serveur.daemon_threads = True
    serveur.base = base
    return serveur


def servir(config, hote="127.0.0.1", port=8060):
    serveur = creer_serveur(config, hote, port)
    print(f"✍️  Rédigo est en ligne : {config.url}/")
    print(f"   Base de données : {config.base}")
    print(f"   Paiement : {config.paiement or 'désactivé'}"
          + (" (mode démonstration : le Pass s'active sans payer)" if config.paiement == "demo" else ""))
    print("   (Ctrl+C pour arrêter)")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nAu revoir !")
    finally:
        serveur.server_close()

