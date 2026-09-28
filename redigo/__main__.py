"""Point d'entrée.

  python3 -m redigo                                     lance la plateforme sur http://127.0.0.1:8060/
  python3 -m redigo lancer --hote 0.0.0.0 --port 8060   pour la rendre accessible (derrière un proxy HTTPS)
  python3 -m redigo licence ajouter univ-lyon.fr "Université de Lyon" 2027-08-31 --norme apa
  python3 -m redigo licence liste
  python3 -m redigo pass etudiant@exemple.fr            offre un Pass Mémoire (un an)
"""

import argparse
import datetime
import sys

from .serveur import Configuration


def main():
    parser = argparse.ArgumentParser(prog="python3 -m redigo", description="Rédigo, la mise en forme de mémoires en ligne.")
    actions = parser.add_subparsers(dest="action")
    p = actions.add_parser("lancer", help="lance le serveur (action par défaut)")
    p.add_argument("--hote", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8060)
    p.add_argument("--journal", action="store_true", help="affiche chaque requête et les erreurs détaillées")
    licence = actions.add_parser("licence", help="gère les licences des universités").add_subparsers(dest="sous_action")
    p = licence.add_parser("ajouter", help="ajoute ou prolonge une licence")
    p.add_argument("domaine", help="le domaine des adresses e-mail, par exemple univ-lyon.fr")
    p.add_argument("universite", help="le nom affiché")
    p.add_argument("fin", help="date de fin, AAAA-MM-JJ")
    p.add_argument("--norme", help="le modèle officiel : universite, apa, sobre ou plan_francais")
    licence.add_parser("liste", help="affiche les licences")
    p = actions.add_parser("pass", help="offre un Pass Mémoire à un compte")
    p.add_argument("email")
    args = parser.parse_args()

    if args.action in (None, "lancer"):
        from .serveur import servir
        hote, port = getattr(args, "hote", "127.0.0.1"), getattr(args, "port", 8060)
        surcharges = {"options": {"journal": getattr(args, "journal", False)}}
        import os
        if "REDIGO_URL" not in os.environ:
            surcharges["url"] = f"http://{'127.0.0.1' if hote == '0.0.0.0' else hote}:{port}"
        servir(Configuration.depuis_environnement(**surcharges), hote, port)
        return

    from .base import Base
    base = Base(Configuration.depuis_environnement().base)
    if args.action == "licence" and args.sous_action == "ajouter":
        datetime.date.fromisoformat(args.fin)
        reglages = None
        if args.norme:
            from memoire.reglages import NORMES
            if args.norme not in NORMES:
                sys.exit(f"Norme inconnue. Choix : {', '.join(NORMES)}")
            reglages = NORMES[args.norme][1]
        base.ajouter_licence(args.domaine, args.universite, args.fin, reglages)
        print(f"✅ Licence « {args.universite} » : toutes les adresses @{args.domaine} ont la formule université "
              f"jusqu'au {args.fin}.")
    elif args.action == "licence":
        for l in base.licences():
            print(f"{l['domaine']:<30} {l['universite']:<40} jusqu'au {l['expire_le']}")
    elif args.action == "pass":
        utilisateur = base.utilisateur_par_email(args.email.lower())
        if not utilisateur:
            sys.exit("Aucun compte avec cette adresse.")
        base.activer_pass(utilisateur["id"], "offert", f"offert-{datetime.datetime.now().timestamp()}", 0)
        print(f"✅ Pass Mémoire activé pour {args.email}.")


if __name__ == "__main__":
    main()
