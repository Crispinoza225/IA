"""Point d'entrée.

  python3 -m cotiz                                     lance Cotiz sur http://127.0.0.1:8070/
  python3 -m cotiz lancer --hote 0.0.0.0 --port 8070   pour le rendre accessible (derrière un proxy HTTPS)
  python3 -m cotiz formule +221771234567 --jours 365   offre la formule Organisateur à un compte
"""

import argparse
import datetime
import os
import sys

from .serveur import Configuration


def main():
    parser = argparse.ArgumentParser(prog="python3 -m cotiz", description="Cotiz, la tontine en ligne.")
    actions = parser.add_subparsers(dest="action")
    p = actions.add_parser("lancer", help="lance le serveur (action par défaut)")
    p.add_argument("--hote", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8070)
    p.add_argument("--journal", action="store_true", help="affiche chaque requête et les erreurs détaillées")
    p = actions.add_parser("formule", help="offre la formule Organisateur à un compte")
    p.add_argument("telephone")
    p.add_argument("--jours", type=int, default=30)
    args = parser.parse_args()

    if args.action in (None, "lancer"):
        from .serveur import servir
        hote, port = getattr(args, "hote", "127.0.0.1"), getattr(args, "port", 8070)
        surcharges = {"options": {"journal": getattr(args, "journal", False)}}
        if "COTIZ_URL" not in os.environ:
            surcharges["url"] = f"http://{'127.0.0.1' if hote == '0.0.0.0' else hote}:{port}"
        servir(Configuration.depuis_environnement(**surcharges), hote, port)
        return

    from .base import Base
    from .tontine import telephone_normalise
    base = Base(Configuration.depuis_environnement().base)
    utilisateur = base.utilisateur_par_telephone(telephone_normalise(args.telephone))
    if not utilisateur:
        sys.exit("Aucun compte avec ce numéro.")
    base.activer_formule(utilisateur["id"], "offert", f"offert-{datetime.datetime.now().timestamp()}", 0, args.jours)
    print(f"✅ Formule Organisateur activée pour {utilisateur['nom']} ({args.jours} jours).")


if __name__ == "__main__":
    main()
