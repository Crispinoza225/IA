"""Le réseau : télécharger une page en parlant HTTP directement sur une connexion (socket).

Aucune bibliothèque HTTP : on écrit la requête à la main (« GET /page HTTP/1.1 … »),
puis on lit et on décode la réponse du serveur ligne par ligne.
"""

import base64
import gzip
import os
import socket
import ssl
import urllib.parse
from dataclasses import dataclass
from urllib.request import proxy_bypass  # respecte la variable no_proxy

AGENT = "Toile/1.0 (navigateur educatif)"
DOSSIER_PAGES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pages")


class ErreurReseau(Exception):
    pass


@dataclass
class Reponse:
    url: "URL"
    statut: int
    entetes: dict
    corps: bytes

    @property
    def texte(self):
        """Décode le corps avec le bon encodage (celui annoncé par le serveur, sinon UTF-8)."""
        type_contenu = self.entetes.get("content-type", "")
        encodage = "utf-8"
        if "charset=" in type_contenu:
            encodage = type_contenu.split("charset=")[-1].split(";")[0].strip().strip('"')
        try:
            return self.corps.decode(encodage, errors="replace")
        except LookupError:
            return self.corps.decode("utf-8", errors="replace")


class URL:
    """Une adresse web découpée en morceaux : schéma, hôte, port, chemin."""

    def __init__(self, texte):
        texte = texte.strip()
        if "://" not in texte and not texte.startswith(("about:", "data:")):
            texte = "https://" + texte  # comme les vrais navigateurs quand on tape « exemple.fr »
        self.texte = texte
        if texte.startswith(("about:", "data:")):
            self.schema, self.hote, self.port, self.chemin = texte.split(":", 1)[0], "", 0, texte.split(":", 1)[1]
            return
        parties = urllib.parse.urlsplit(texte)
        self.schema = parties.scheme.lower()
        if self.schema not in ("http", "https", "file"):
            raise ErreurReseau(f"Schéma non pris en charge : {self.schema}")
        self.hote = (parties.hostname or "").lower()
        self.port = parties.port or {"http": 80, "https": 443}.get(self.schema, 0)
        self.chemin = (parties.path or "/") + (f"?{parties.query}" if parties.query else "")
        self.ancre = parties.fragment

    def __str__(self):
        if self.schema in ("about", "data"):
            return self.texte
        if self.schema == "file":
            return "file://" + self.chemin
        port = "" if self.port == {"http": 80, "https": 443}[self.schema] else f":{self.port}"
        return f"{self.schema}://{self.hote}{port}{self.chemin}"

    def __eq__(self, autre):
        return isinstance(autre, URL) and str(self) == str(autre)

    def resoudre(self, lien):
        """Transforme un lien relatif (« ../photo.html ») en adresse complète."""
        if lien.startswith(("about:", "data:")):
            return URL(lien)
        if self.schema in ("about", "data"):
            return URL(lien)
        return URL(urllib.parse.urljoin(str(self), lien))

    # --- Téléchargement ------------------------------------------------------
    def telecharger(self, redirections=5, delai=10):
        if self.schema == "about":
            return self._about()
        if self.schema == "data":
            return self._data()
        if self.schema == "file":
            try:
                with open(urllib.parse.unquote(self.chemin), "rb") as f:
                    return Reponse(self, 200, {"content-type": "text/html; charset=utf-8"}, f.read())
            except OSError as erreur:
                raise ErreurReseau(str(erreur)) from erreur

        reponse = self._requete_http(delai)
        if 300 <= reponse.statut < 400 and "location" in reponse.entetes:
            if redirections == 0:
                raise ErreurReseau("Trop de redirections")
            return self.resoudre(reponse.entetes["location"]).telecharger(redirections - 1, delai)
        return reponse

    def _about(self):
        nom = self.chemin or "accueil"
        chemin = os.path.join(DOSSIER_PAGES, f"{nom}.html")
        if not os.path.exists(chemin):
            chemin = os.path.join(DOSSIER_PAGES, "accueil.html")
        with open(chemin, "rb") as f:
            return Reponse(self, 200, {"content-type": "text/html; charset=utf-8"}, f.read())

    def _data(self):
        """data:text/html,<h1>Bonjour</h1>  — la page est directement dans l'adresse."""
        entete, _, contenu = self.chemin.partition(",")
        corps = base64.b64decode(contenu) if entete.endswith(";base64") else urllib.parse.unquote(contenu).encode()
        return Reponse(self, 200, {"content-type": entete.replace(";base64", "") or "text/html"}, corps)

    def _connexion(self, delai):
        """Ouvre la connexion TCP, éventuellement à travers un proxy, puis la chiffre si c'est du HTTPS."""
        proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
        if proxy and not proxy_bypass(self.hote):
            proxy_url = urllib.parse.urlsplit(proxy)
            connexion = socket.create_connection((proxy_url.hostname, proxy_url.port or 80), timeout=delai)
            # Le proxy ouvre un « tunnel » vers le vrai serveur ; ensuite tout passe au travers.
            connexion.sendall(f"CONNECT {self.hote}:{self.port} HTTP/1.1\r\nHost: {self.hote}:{self.port}\r\n\r\n".encode())
            reponse = b""
            while b"\r\n\r\n" not in reponse:
                morceau = connexion.recv(4096)
                if not morceau:
                    break
                reponse += morceau
            if b" 200" not in reponse.split(b"\r\n", 1)[0]:
                connexion.close()
                raise ErreurReseau(f"Le proxy refuse l'accès à {self.hote}")
        else:
            connexion = socket.create_connection((self.hote, self.port), timeout=delai)
        if self.schema == "https":
            contexte = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE"))
            connexion = contexte.wrap_socket(connexion, server_hostname=self.hote)
        return connexion

    def _requete_http(self, delai):
        try:
            connexion = self._connexion(delai)
        except (OSError, ssl.SSLError) as erreur:
            raise ErreurReseau(f"Connexion impossible à {self.hote} : {erreur}") from erreur
        requete = (
            f"GET {self.chemin} HTTP/1.1\r\n"
            f"Host: {self.hote}\r\n"
            f"User-Agent: {AGENT}\r\n"
            "Accept: text/html,*/*\r\n"
            "Accept-Encoding: gzip\r\n"
            "Connection: close\r\n\r\n"
        )
        with connexion:
            connexion.sendall(requete.encode())
            fichier = connexion.makefile("rb")
            ligne_statut = fichier.readline().decode("latin-1")
            try:
                _, statut, _ = (ligne_statut.split(" ", 2) + [""])[:3]
                statut = int(statut)
            except ValueError as erreur:
                raise ErreurReseau(f"Réponse incompréhensible : {ligne_statut!r}") from erreur
            entetes = {}
            while True:
                ligne = fichier.readline().decode("latin-1")
                if ligne in ("\r\n", "\n", ""):
                    break
                nom, _, valeur = ligne.partition(":")
                entetes[nom.strip().lower()] = valeur.strip()
            corps = lire_corps(fichier, entetes)
        if entetes.get("content-encoding") == "gzip":
            corps = gzip.decompress(corps)
        return Reponse(self, statut, entetes, corps)


def lire_corps(fichier, entetes):
    """Lit le corps de la réponse, qu'il soit envoyé d'un bloc ou « par morceaux » (chunked)."""
    if entetes.get("transfer-encoding", "").lower() == "chunked":
        corps = b""
        while True:
            taille = int(fichier.readline().split(b";")[0].strip() or b"0", 16)
            if taille == 0:
                break
            corps += fichier.read(taille)
            fichier.readline()  # le \r\n qui termine chaque morceau
        return corps
    if "content-length" in entetes:
        return fichier.read(int(entetes["content-length"]))
    return fichier.read()

