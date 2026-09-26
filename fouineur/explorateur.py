"""Le robot d'exploration (« crawler ») : il visite des pages web et suit leurs liens.

Comme les robots de Google, il est poli : il respecte le fichier robots.txt de chaque
site, attend entre deux requêtes et s'identifie avec un nom clair.
"""

import time
import urllib.error
import urllib.request
import urllib.robotparser
from collections import deque
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse

AGENT = "FouineurBot/1.0 (moteur de recherche éducatif)"
TAILLE_MAX = 2_000_000  # on ignore les pages de plus de 2 Mo


class ExtracteurHTML(HTMLParser):
    """Lit le HTML et récupère le titre, la description, le texte visible et les liens."""

    IGNORES = {"script", "style", "noscript", "svg", "template", "nav", "footer"}  # pas du vrai contenu
    BLOCS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article"}

    def __init__(self, url):
        super().__init__(convert_charrefs=True)
        self.url = url
        self.titre = ""
        self.description = ""
        self.morceaux = []
        self.liens = []
        self._dans_titre = False
        self._profondeur_ignoree = 0

    def handle_starttag(self, balise, attributs):
        attributs = dict(attributs)
        if balise in self.IGNORES:
            self._profondeur_ignoree += 1
        elif balise == "title":
            self._dans_titre = True
        elif balise == "a" and attributs.get("href"):
            lien = normaliser_url(urljoin(self.url, attributs["href"]))
            if lien:
                self.liens.append(lien)
        elif balise == "meta" and attributs.get("name", "").lower() == "description":
            self.description = attributs.get("content", "").strip()
        if balise in self.BLOCS:
            self.morceaux.append("\n")

    def handle_endtag(self, balise):
        if balise in self.IGNORES and self._profondeur_ignoree:
            self._profondeur_ignoree -= 1
        elif balise == "title":
            self._dans_titre = False

    def handle_data(self, donnees):
        if self._dans_titre:
            self.titre += donnees
        elif not self._profondeur_ignoree:
            self.morceaux.append(donnees)

    @property
    def texte(self):
        lignes = (" ".join(ligne.split()) for ligne in "".join(self.morceaux).splitlines())
        return "\n".join(ligne for ligne in lignes if ligne)


def normaliser_url(url):
    """Retire l'ancre (#...) et refuse tout ce qui n'est pas http(s)."""
    url, _ = urldefrag(url)
    parties = urlparse(url)
    if parties.scheme not in ("http", "https") or not parties.netloc:
        return None
    return parties._replace(netloc=parties.netloc.lower(), path=parties.path or "/").geturl()


def analyser_page(url, html):
    extracteur = ExtracteurHTML(url)
    extracteur.feed(html)
    return {
        "url": url,
        "titre": " ".join(extracteur.titre.split()) or url,
        "description": extracteur.description,
        "texte": extracteur.texte,
        "liens": list(dict.fromkeys(extracteur.liens)),  # sans doublons, dans l'ordre
    }


class Explorateur:
    def __init__(self, delai=1.0, meme_domaine=True, delai_expiration=10, afficher=print):
        self.delai = delai
        self.meme_domaine = meme_domaine
        self.delai_expiration = delai_expiration
        self.afficher = afficher
        self._robots = {}

    def autorise(self, url):
        """Consulte (une seule fois par site) le fichier robots.txt."""
        parties = urlparse(url)
        site = f"{parties.scheme}://{parties.netloc}"
        if site not in self._robots:
            robots = urllib.robotparser.RobotFileParser()
            try:
                requete = urllib.request.Request(site + "/robots.txt", headers={"User-Agent": AGENT})
                with urllib.request.urlopen(requete, timeout=self.delai_expiration) as reponse:
                    robots.parse(reponse.read().decode("utf-8", errors="ignore").splitlines())
            except urllib.error.HTTPError as erreur:
                # Accès au robots.txt refusé (401/403) : rien n'est permis. Absent (404…) : tout l'est.
                robots.parse(["User-agent: *", "Disallow: /"] if erreur.code in (401, 403) else [])
            except (urllib.error.URLError, OSError, ValueError):
                robots.parse([])
            self._robots[site] = robots
        return self._robots[site].can_fetch(AGENT, url)

    def telecharger(self, url):
        """Renvoie (url_finale, html) ou None si ce n'est pas une page HTML lisible."""
        requete = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "text/html"})
        with urllib.request.urlopen(requete, timeout=self.delai_expiration) as reponse:
            if "html" not in reponse.headers.get("Content-Type", ""):
                return None
            contenu = reponse.read(TAILLE_MAX + 1)
            if len(contenu) > TAILLE_MAX:
                return None
            encodage = reponse.headers.get_content_charset() or "utf-8"
            return normaliser_url(reponse.geturl()) or url, contenu.decode(encodage, errors="replace")

    def explorer(self, departs, max_pages=100):
        """Parcours en largeur : on visite d'abord les pages proches du départ."""
        departs = [u for u in (normaliser_url(d) for d in departs) if u]
        domaines = {urlparse(u).netloc for u in departs}
        file_attente = deque(departs)
        vues = set(departs)
        pages = []
        while file_attente and len(pages) < max_pages:
            url = file_attente.popleft()
            if not self.autorise(url):
                self.afficher(f"  🚫 interdit par robots.txt : {url}")
                continue
            try:
                resultat = self.telecharger(url)
            except (urllib.error.URLError, OSError, ValueError) as erreur:
                self.afficher(f"  ⚠️  {url} : {erreur}")
                continue
            finally:
                time.sleep(self.delai)
            if resultat is None:
                continue
            url_finale, html = resultat
            page = analyser_page(url_finale, html)
            if url_finale != url:
                if url_finale in vues:
                    continue  # une redirection vers une page déjà vue
                vues.add(url_finale)
            pages.append(page)
            self.afficher(f"  [{len(pages):4d}/{max_pages}] {page['titre'][:70]}")
            for lien in page["liens"]:
                if lien not in vues and (not self.meme_domaine or urlparse(lien).netloc in domaines):
                    vues.add(lien)
                    file_attente.append(lien)
        return pages
