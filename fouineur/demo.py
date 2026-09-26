"""Un mini-web de démonstration, servi en local, pour essayer Fouineur sans internet.

C'est une petite encyclopédie : les pages se citent entre elles, ce qui donne un vrai graphe
de liens pour PageRank. Le robots.txt interdit la section /prive/, pour vérifier que le robot le respecte.
"""

import re
import threading
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# nom de la page : (titre, texte, pages liées). Les liens sont aussi insérés dans le texte avec [[nom]].
PAGES = {
    "index": ("Encyclopédie Fouineur — Accueil",
              "Bienvenue dans la petite encyclopédie de démonstration. Explore l'[[espace]], les [[animaux]], "
              "l'[[informatique]] et l'[[histoire]]. Tu peux aussi lire notre page sur la [[terre]].",
              []),
    "espace": ("L'espace et le système solaire",
               "Le système solaire est composé du [[soleil]] et des huit planètes qui tournent autour de lui : "
               "Mercure, Vénus, la [[terre]], [[mars]], [[jupiter]], Saturne, Uranus et Neptune. "
               "Les humains explorent l'espace avec des fusées et des sondes depuis 1957.",
               ["index"]),
    "soleil": ("Le Soleil, notre étoile",
               "Le Soleil est une étoile naine jaune âgée d'environ 4,6 milliards d'années. Sa surface atteint "
               "5 500 degrés. Il produit son énergie par fusion nucléaire de l'hydrogène en hélium. "
               "Sans lui, aucune vie ne serait possible sur la [[terre]].",
               ["espace"]),
    "terre": ("La Terre, planète bleue",
              "La Terre est la troisième planète du [[espace|système solaire]] et la seule connue à abriter la vie. "
              "Les océans recouvrent 71 % de sa surface. Elle possède un satellite naturel, la Lune. "
              "Ses [[volcans]] et ses séismes montrent que son intérieur est encore très chaud.",
              ["espace", "soleil", "animaux"]),
    "mars": ("Mars, la planète rouge",
             "Mars doit sa couleur rouge à l'oxyde de fer, c'est-à-dire la rouille, présent dans son sol. "
             "On y trouve Olympus Mons, le plus grand volcan du système solaire, haut de 22 kilomètres. "
             "Des robots comme Curiosity et Perseverance explorent sa surface à la recherche de traces de vie.",
             ["espace", "volcans"]),
    "jupiter": ("Jupiter, la géante gazeuse",
                "Jupiter est la plus grande planète du système solaire : on pourrait y ranger plus de 1 300 Terres. "
                "Sa Grande Tache rouge est une tempête plus large que notre planète, qui dure depuis des siècles.",
                ["espace"]),
    "volcans": ("Les volcans",
                "Un volcan est une ouverture dans la croûte terrestre par laquelle s'échappe le magma, "
                "qu'on appelle lave une fois à la surface. Le Piton de la Fournaise, à La Réunion, est l'un "
                "des volcans les plus actifs du monde. Le plus grand volcan connu se trouve sur [[mars]].",
                ["terre"]),
    "animaux": ("Les animaux",
                "Le règne animal compte plus d'un million d'espèces connues. Découvre le [[chat]], le "
                "[[dauphin]] et la [[fourmi]], trois animaux étonnants.",
                ["index"]),
    "chat": ("Le chat domestique",
             "Le chat est un petit félin carnivore domestiqué depuis près de 10 000 ans. Il dort jusqu'à "
             "16 heures par jour et ronronne quand il est content. Ses moustaches l'aident à se repérer dans le noir.",
             ["animaux"]),
    "dauphin": ("Le dauphin",
                "Le dauphin est un mammifère marin très intelligent. Il communique avec des sifflements et "
                "se repère grâce à l'écholocation, une sorte de sonar naturel. Il vit en groupes appelés pods.",
                ["animaux"]),
    "fourmi": ("La fourmi",
               "La fourmi est un insecte social qui vit en colonies pouvant compter des millions d'individus. "
               "Elle peut porter jusqu'à 50 fois son propre poids. Les colonies s'organisent sans chef, un "
               "exemple d'intelligence collective qui inspire l'[[intelligence-artificielle|intelligence artificielle]].",
               ["animaux"]),
    "informatique": ("L'informatique",
                     "L'informatique est la science du traitement automatique de l'information par des "
                     "ordinateurs. Elle regroupe la [[programmation]], les réseaux comme [[internet]], et "
                     "l'[[intelligence-artificielle|intelligence artificielle]].",
                     ["index"]),
    "programmation": ("La programmation",
                      "Programmer, c'est écrire des instructions qu'un ordinateur sait exécuter. Python est un "
                      "langage de programmation apprécié des débutants pour sa syntaxe claire. Ada Lovelace est "
                      "considérée comme la première programmeuse de l'histoire.",
                      ["informatique"]),
    "internet": ("Internet et le Web",
                 "Internet est un réseau mondial qui relie des milliards d'appareils. Le Web, inventé par Tim "
                 "Berners-Lee en 1989, est un ensemble de pages reliées par des liens. Les [[moteurs-de-recherche|"
                 "moteurs de recherche]] parcourent ces liens pour indexer les pages.",
                 ["informatique"]),
    "moteurs-de-recherche": ("Les moteurs de recherche",
                             "Un moteur de recherche parcourt le web avec un robot d'exploration, construit un "
                             "index inversé puis classe les pages. Google a popularisé l'algorithme PageRank, qui "
                             "juge une page importante si d'autres pages importantes pointent vers elle.",
                             ["internet", "informatique"]),
    "intelligence-artificielle": ("L'intelligence artificielle",
                                  "L'intelligence artificielle cherche à faire réaliser par des machines des tâches "
                                  "qui demandent de l'intelligence. Les [[reseaux-de-neurones|réseaux de neurones]] "
                                  "apprennent à partir d'exemples. Les grands modèles de langage écrivent du texte.",
                                  ["informatique"]),
    "reseaux-de-neurones": ("Les réseaux de neurones",
                            "Un réseau de neurones artificiels est composé de couches de neurones reliés par des "
                            "poids. Pendant l'apprentissage, la rétropropagation ajuste ces poids pour réduire les "
                            "erreurs. Le Transformer, inventé en 2017, est à la base des modèles comme GPT.",
                            ["intelligence-artificielle"]),
    "histoire": ("L'histoire",
                 "L'histoire étudie le passé de l'humanité. Découvre les [[pyramides]] d'Égypte et "
                 "l'invention de l'[[imprimerie]].",
                 ["index"]),
    "pyramides": ("Les pyramides d'Égypte",
                  "La grande pyramide de Gizeh a été construite vers 2560 avant notre ère pour le pharaon Khéops. "
                  "Haute de 146 mètres à l'origine, elle est restée le plus haut monument construit par l'homme "
                  "pendant près de 4 000 ans.",
                  ["histoire"]),
    "imprimerie": ("L'imprimerie",
                   "Vers 1450, Gutenberg met au point l'imprimerie à caractères mobiles. Les livres deviennent "
                   "beaucoup moins chers, et le savoir se diffuse comme jamais. On compare souvent cette révolution "
                   "à celle d'[[internet]].",
                   ["histoire"]),
    "prive/secret": ("Page secrète",
                     "Cette page est interdite aux robots par le fichier robots.txt : elle ne doit jamais "
                     "apparaître dans les résultats. Mot de passe : licorne.",
                     ["index"]),
}

ROBOTS_TXT = "User-agent: *\nDisallow: /prive/\n"


def lien_html(cible, texte=None):
    adresse = "/" if cible == "index" else f"/{cible}"
    return f'<a href="{adresse}">{escape(texte or PAGES[cible][0])}</a>'


def texte_brut(texte):
    """« l'[[espace|système solaire]] » → « l'système solaire » (sans la syntaxe des liens)."""
    return re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", texte)


def rendre_page(nom):
    titre, texte, liens = PAGES[nom]

    def remplacer(morceau):
        cible, _, libelle = morceau.partition("|")
        return lien_html(cible, libelle or cible)

    morceaux = texte.split("[[")
    corps = escape(morceaux[0])
    for morceau in morceaux[1:]:
        dedans, _, apres = morceau.partition("]]")
        corps += remplacer(dedans) + escape(apres)
    voir_aussi = "".join(f"<li>{lien_html(c)}</li>" for c in liens)
    lien_secret = '<p><a href="/prive/secret">.</a></p>' if nom == "index" else ""
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>{escape(titre)}</title>
<meta name="description" content="{escape(texte_brut(texte).split('. ')[0])}.">
<style>body{{font-family:sans-serif;max-width:40em;margin:2em auto}}</style>
<script>console.log("ce texte ne doit pas être indexé");</script></head>
<body><nav><a href="/">Accueil</a></nav><h1>{escape(titre)}</h1><p>{corps}</p>
<h2>Voir aussi</h2><ul>{voir_aussi}</ul>{lien_secret}</body></html>"""


class GestionnaireDemo(BaseHTTPRequestHandler):
    def do_GET(self):
        chemin = self.path.strip("/") or "index"
        if chemin == "robots.txt":
            self._repondre(200, "text/plain", ROBOTS_TXT)
        elif chemin in PAGES:
            self._repondre(200, "text/html; charset=utf-8", rendre_page(chemin))
        else:
            self._repondre(404, "text/html; charset=utf-8", "<h1>Page introuvable</h1>")

    def _repondre(self, code, type_contenu, contenu):
        donnees = contenu.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(donnees)))
        self.end_headers()
        self.wfile.write(donnees)

    def log_message(self, *args):
        pass  # pas de journal dans le terminal


def demarrer_serveur_demo(port=0):
    """Lance le mini-web dans un fil d'exécution séparé. Renvoie (serveur, adresse)."""
    serveur = ThreadingHTTPServer(("127.0.0.1", port), GestionnaireDemo)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    return serveur, f"http://127.0.0.1:{serveur.server_address[1]}/"
