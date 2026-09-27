"""Le serveur de la plateforme : il sert l'interface web et fabrique l'aperçu, le Word et le PDF.

Tout reste sur ton ordinateur : le serveur n'écoute que l'adresse locale 127.0.0.1.
"""

import json
import os
import re
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .apercu import apercu
from .docx import ecrire_docx
from .reglages import ALIGNEMENTS, NORMES, NUMEROTATIONS, POLICES, POSITIONS_PAGINATION, Reglages
from .source import Titre, importer_docx, lire, numeroter

DOSSIER = os.path.dirname(os.path.abspath(__file__))
TAILLE_MAX = 20 * 1024 * 1024  # 20 Mo
FICHIERS_WEB = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                "/style.css": ("style.css", "text/css")}


def preparer(donnees):
    reglages = Reglages.depuis_dict(donnees.get("reglages"))
    texte = str(donnees.get("texte", ""))
    return numeroter(lire(texte), reglages.numerotation), reglages, texte


def pdf_disponible():
    try:
        import reportlab  # noqa: F401
        return True
    except ImportError:
        return False


def nom_de_fichier(reglages, extension):
    base = unicodedata.normalize("NFKD", reglages.garde.titre or "memoire").encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-")[:60] or "memoire"
    return f"{base}.{extension}"


def statistiques(blocs, texte):
    mots = len(re.findall(r"\w+", re.sub(r"[#*>|]", " ", texte)))
    return {"mots": mots, "titres": sum(isinstance(b, Titre) for b in blocs)}


class Gestionnaire(BaseHTTPRequestHandler):
    server_version = "Memoire/1.0"

    def log_message(self, *args):
        pass

    def envoyer(self, code, contenu, type_contenu, nom_fichier=None):
        if isinstance(contenu, str):
            contenu = contenu.encode("utf-8")
            type_contenu += "; charset=utf-8"
        self.send_response(code)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(contenu)))
        self.send_header("Cache-Control", "no-store")
        if nom_fichier:
            self.send_header("Content-Disposition", f'attachment; filename="{nom_fichier}"')
        self.end_headers()
        self.wfile.write(contenu)

    def envoyer_json(self, objet, code=200):
        self.envoyer(code, json.dumps(objet, ensure_ascii=False), "application/json")

    def do_GET(self):
        if self.path in FICHIERS_WEB:
            nom, type_contenu = FICHIERS_WEB[self.path]
            with open(os.path.join(DOSSIER, "web", nom), "rb") as f:
                self.envoyer(200, f.read(), type_contenu + "; charset=utf-8")
        elif self.path == "/api/configuration":
            self.envoyer_json({
                "polices": POLICES, "alignements": ALIGNEMENTS, "numerotations": NUMEROTATIONS,
                "paginations": POSITIONS_PAGINATION, "pdf": pdf_disponible(),
                "normes": {cle: {"nom": nom, "reglages": Reglages.depuis_dict(valeurs).vers_dict()}
                           for cle, (nom, valeurs) in NORMES.items()},
                "defaut": Reglages().vers_dict(),
            })
        elif self.path == "/api/exemple":
            with open(os.path.join(DOSSIER, "exemple.md"), encoding="utf-8") as f:
                self.envoyer_json({"texte": f.read()})
        else:
            self.envoyer(404, "Introuvable", "text/plain")

    def do_POST(self):
        longueur = int(self.headers.get("Content-Length", 0))
        if longueur > TAILLE_MAX:
            self.envoyer_json({"erreur": "Fichier trop volumineux (20 Mo au maximum)."}, 413)
            return
        corps = self.rfile.read(longueur)
        try:
            if self.path == "/api/importer-docx":
                self.envoyer_json({"texte": importer_docx(corps)})
                return
            blocs, reglages, texte = preparer(json.loads(corps or b"{}"))
            if self.path == "/api/apercu":
                entrees = None
                if reglages.sommaire and pdf_disponible():
                    from .pdf import ecrire_pdf
                    _, entrees = ecrire_pdf(blocs, reglages)  # pour afficher les vrais numéros de page
                self.envoyer_json({"html": apercu(blocs, reglages, entrees), **statistiques(blocs, texte)})
            elif self.path == "/api/docx":
                self.envoyer(200, ecrire_docx(blocs, reglages),
                             "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                             nom_de_fichier(reglages, "docx"))
            elif self.path == "/api/pdf":
                if not pdf_disponible():
                    self.envoyer_json({"erreur": "Installe reportlab pour l'export PDF : pip install reportlab"}, 501)
                    return
                from .pdf import ecrire_pdf
                pdf, _ = ecrire_pdf(blocs, reglages)
                self.envoyer(200, pdf, "application/pdf", nom_de_fichier(reglages, "pdf"))
            else:
                self.envoyer(404, "Introuvable", "text/plain")
        except (ValueError, KeyError, OSError) as erreur:
            self.envoyer_json({"erreur": f"Impossible de traiter la demande : {erreur}"}, 400)
        except Exception as erreur:  # le fichier importé peut être abîmé de mille façons
            self.envoyer_json({"erreur": f"Erreur inattendue : {erreur}"}, 500)


def servir(port=8050, ouvrir_navigateur=True):
    serveur = ThreadingHTTPServer(("127.0.0.1", port), Gestionnaire)
    adresse = f"http://127.0.0.1:{serveur.server_address[1]}/"
    print(f"📝 La plateforme de mise en forme est prête : {adresse}")
    print("   (Ctrl+C pour arrêter)")
    if ouvrir_navigateur:
        import webbrowser
        webbrowser.open(adresse)
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nAu revoir !")
