"""L'interface web de Fouineur : une page d'accueil avec une barre de recherche, et une page de résultats."""

import re
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote_plus, urlparse

PAR_PAGE = 10

STYLE = """
:root { --fond:#fff; --texte:#202124; --doux:#5f6368; --lien:#1a0dab; --vert:#188038; --bord:#dfe1e5; --surligne:#fff3b0; }
@media (prefers-color-scheme: dark) {
  :root { --fond:#202124; --texte:#e8eaed; --doux:#9aa0a6; --lien:#8ab4f8; --vert:#81c995; --bord:#5f6368; --surligne:#5c4d00; }
}
* { box-sizing:border-box; }
body { margin:0; font-family:system-ui,-apple-system,"Segoe UI",sans-serif; background:var(--fond); color:var(--texte); }
a { color:var(--lien); text-decoration:none; } a:hover { text-decoration:underline; }
.logo { font-weight:700; letter-spacing:-1px; color:var(--texte); }
.logo span:nth-child(1){color:#4285f4} .logo span:nth-child(2){color:#ea4335} .logo span:nth-child(3){color:#fbbc05}
.logo span:nth-child(4){color:#4285f4} .logo span:nth-child(5){color:#34a853} .logo span:nth-child(6){color:#ea4335}
form { display:flex; gap:8px; }
input[type=search] { flex:1; font-size:16px; padding:12px 20px; border:1px solid var(--bord); border-radius:24px;
  background:var(--fond); color:var(--texte); outline:none; min-width:0; }
input[type=search]:focus { box-shadow:0 1px 6px rgba(32,33,36,.28); }
button { font-size:15px; padding:0 18px; border:1px solid var(--bord); border-radius:24px; background:var(--fond);
  color:var(--texte); cursor:pointer; }
.accueil { display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:80vh; padding:16px; }
.accueil .logo { font-size:64px; margin-bottom:24px; }
.accueil form { width:100%; max-width:580px; }
.accueil p { color:var(--doux); }
header { display:flex; align-items:center; gap:24px; padding:16px; border-bottom:1px solid var(--bord); flex-wrap:wrap; }
header .logo { font-size:28px; } header form { flex:1; max-width:640px; min-width:240px; }
main { max-width:680px; padding:8px 16px 40px; margin-left:clamp(0px, 10vw, 150px); }
.infos { color:var(--doux); font-size:14px; margin:8px 0 16px; }
.suggestion { font-size:18px; margin:12px 0; } .suggestion a { font-weight:600; font-style:italic; }
.resultat { margin-bottom:26px; }
.resultat .url { color:var(--vert); font-size:14px; overflow-wrap:anywhere; }
.resultat h3 { margin:4px 0; font-size:20px; font-weight:400; }
.resultat p { margin:0; color:var(--doux); line-height:1.5; font-size:14px; }
mark { background:var(--surligne); color:inherit; font-weight:600; padding:0 1px; }
.pages { display:flex; gap:14px; font-size:16px; margin-top:24px; }
.pages b { color:var(--texte); }
main p, .suggestion { overflow-wrap:anywhere; }
@media (max-width: 600px) {
  header { gap:12px; padding:12px 16px; } header form { flex-basis:100%; min-width:0; }
  main { margin-left:0; } .accueil .logo { font-size:44px; }
}
"""


def logo():
    return '<span class="logo">' + "".join(f"<span>{c}</span>" for c in "Fouine") + "ur 🔎</span>"


def gabarit(titre, corps):
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(titre)}</title>
<style>{STYLE}</style></head><body>{corps}</body></html>"""


def formulaire(requete=""):
    return f"""<form action="/recherche" method="get">
<input type="search" name="q" value="{escape(requete)}" placeholder="Rechercher…" autofocus aria-label="Recherche">
<button type="submit">Fouiner</button></form>"""


def surligner(extrait):
    """Transforme les [[mots]] marqués par l'index en <mark>mots</mark>, en échappant tout le reste."""
    morceaux = re.split(r"\[\[(.*?)\]\]", extrait)
    return "".join(f"<mark>{escape(m)}</mark>" if i % 2 else escape(m) for i, m in enumerate(morceaux))


def page_accueil(index):
    return gabarit("Fouineur", f"""<div class="accueil"><a href="/">{logo()}</a>{formulaire()}
<p>{len(index.documents)} pages indexées</p></div>""")


def page_resultats(index, requete, numero_page):
    reponse = index.chercher(requete, nb_resultats=PAR_PAGE, debut=(numero_page - 1) * PAR_PAGE)
    html = [f'<header><a href="/">{logo()}</a>{formulaire(requete)}</header><main>']
    html.append(f'<div class="infos">Environ {reponse["total"]} résultat{"s" if reponse["total"] > 1 else ""} '
                f'({reponse["duree"] * 1000:.1f} ms)</div>')
    if reponse["suggestion"]:
        html.append(f'<div class="suggestion">Vouliez-vous dire : '
                    f'<a href="/recherche?q={quote_plus(reponse["suggestion"])}">{escape(reponse["suggestion"])}</a> ?</div>')
    for r in reponse["resultats"]:
        html.append(f"""<div class="resultat"><div class="url">{escape(r["url"])}</div>
<h3><a href="{escape(r["url"])}">{escape(r["titre"])}</a></h3><p>{surligner(r["extrait"])}</p></div>""")
    if not reponse["resultats"]:
        html.append(f"<p>Aucun document ne correspond à <b>{escape(requete)}</b>.</p>")

    nb_pages = (reponse["total"] + PAR_PAGE - 1) // PAR_PAGE
    if nb_pages > 1:
        liens = [f"<b>{n}</b>" if n == numero_page else f'<a href="/recherche?q={quote_plus(requete)}&page={n}">{n}</a>'
                 for n in range(1, min(nb_pages, 10) + 1)]
        html.append('<nav class="pages">' + "".join(liens) + "</nav>")
    html.append("</main>")
    return gabarit(f"{requete} - Fouineur", "".join(html))


def creer_gestionnaire(index):
    class Gestionnaire(BaseHTTPRequestHandler):
        def do_GET(self):
            adresse = urlparse(self.path)
            parametres = parse_qs(adresse.query)
            requete = parametres.get("q", [""])[0].strip()
            if adresse.path == "/recherche" and requete:
                try:
                    numero = max(1, int(parametres.get("page", ["1"])[0]))
                except ValueError:
                    numero = 1
                self._envoyer(200, page_resultats(index, requete, numero))
            elif adresse.path in ("/", "/recherche"):
                self._envoyer(200, page_accueil(index))
            else:
                self._envoyer(404, gabarit("Introuvable", "<main><h1>Page introuvable</h1></main>"))

        def _envoyer(self, code, html):
            donnees = html.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(donnees)))
            self.end_headers()
            self.wfile.write(donnees)

        def log_message(self, format, *args):
            pass

    return Gestionnaire


def servir(index, port=8000):
    serveur = ThreadingHTTPServer(("127.0.0.1", port), creer_gestionnaire(index))
    print(f"🔎 Fouineur est prêt : ouvre http://127.0.0.1:{serveur.server_address[1]}/ dans ton navigateur")
    print("   (Ctrl+C pour arrêter)")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nAu revoir !")
    return serveur
