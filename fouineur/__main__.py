"""Point d'entrée : python3 -m fouineur {demo, explorer, chercher, serveur}"""

import argparse
import os
import re
import sys

from .index import Index

CHEMIN_INDEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "donnees", "index.json.gz")


def charger_index():
    if not os.path.exists(CHEMIN_INDEX):
        raise SystemExit("Aucun index. Lance d'abord : python3 -m fouineur explorer <url>  (ou : python3 -m fouineur demo)")
    return Index.charger(CHEMIN_INDEX)


def explorer_et_indexer(departs, max_pages, delai, meme_domaine):
    from .explorateur import Explorateur

    print(f"🕷️  Exploration à partir de : {', '.join(departs)}")
    pages = Explorateur(delai=delai, meme_domaine=meme_domaine).explorer(departs, max_pages=max_pages)
    print(f"📇 Construction de l'index et calcul du PageRank pour {len(pages)} pages…")
    index = Index.construire(pages)
    print(f"   {len(index.postings)} termes différents indexés")
    return index


def afficher_resultats(index, requete):
    reponse = index.chercher(requete)
    print(f"\n{reponse['total']} résultat(s) en {reponse['duree'] * 1000:.1f} ms")
    if reponse["suggestion"]:
        print(f"Vouliez-vous dire : {reponse['suggestion']} ?")
    gras, bleu, normal = ("\033[1m", "\033[94m", "\033[0m") if sys.stdout.isatty() else ("", "", "")
    for numero, r in enumerate(reponse["resultats"], 1):
        extrait = re.sub(r"\[\[(.*?)\]\]", rf"{gras}\1{normal}", r["extrait"])  # mots trouvés en gras
        print(f"\n{numero}. {bleu}{r['titre']}{normal}  (score {r['score']})\n   {r['url']}\n   {extrait}")


def main():
    parser = argparse.ArgumentParser(prog="python3 -m fouineur", description="Fouineur : un moteur de recherche fait maison.")
    actions = parser.add_subparsers(dest="action", required=True)

    p = actions.add_parser("demo", help="explore le mini-web de démonstration et ouvre l'interface web")
    p.add_argument("--port", type=int, default=8000)

    p = actions.add_parser("explorer", help="explore le web à partir d'une ou plusieurs adresses et construit l'index")
    p.add_argument("departs", nargs="+", help="adresses de départ, ex : https://fr.wikipedia.org/wiki/Volcan")
    p.add_argument("--pages", type=int, default=100, help="nombre maximal de pages à visiter")
    p.add_argument("--delai", type=float, default=1.0, help="secondes d'attente entre deux pages (politesse)")
    p.add_argument("--tous-domaines", action="store_true", help="suivre aussi les liens vers d'autres sites")

    p = actions.add_parser("chercher", help="cherche dans l'index depuis le terminal")
    p.add_argument("requete", nargs="+")

    p = actions.add_parser("serveur", help="lance l'interface web")
    p.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    from .serveur import servir

    if args.action == "demo":
        from .demo import demarrer_serveur_demo
        _, adresse = demarrer_serveur_demo()
        index = explorer_et_indexer([adresse], max_pages=100, delai=0, meme_domaine=True)
        servir(index, args.port)
    elif args.action == "explorer":
        index = explorer_et_indexer(args.departs, args.pages, args.delai, not args.tous_domaines)
        os.makedirs(os.path.dirname(CHEMIN_INDEX), exist_ok=True)
        index.sauvegarder(CHEMIN_INDEX)
        print(f"✅ Index sauvegardé dans {CHEMIN_INDEX}")
        print("   Cherche avec : python3 -m fouineur chercher <mots>   ou   python3 -m fouineur serveur")
    elif args.action == "chercher":
        afficher_resultats(charger_index(), " ".join(args.requete))
    elif args.action == "serveur":
        servir(charger_index(), args.port)


if __name__ == "__main__":
    main()
