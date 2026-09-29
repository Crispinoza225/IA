"""Point d'entrée.

  python3 -m castagne                                     lance Castagne sur http://127.0.0.1:8080/
  python3 -m castagne lancer --hote 0.0.0.0 --port 8080   pour le rendre accessible (derrière un proxy HTTPS)
"""

import argparse
import os

from .serveur import Configuration, servir


def main():
    parser = argparse.ArgumentParser(prog="python3 -m castagne", description="Castagne, le jeu de combat de brutes.")
    actions = parser.add_subparsers(dest="action")
    p = actions.add_parser("lancer", help="lance le serveur (action par défaut)")
    p.add_argument("--hote", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--journal", action="store_true", help="affiche chaque requête et les erreurs détaillées")
    args = parser.parse_args()
    hote, port = getattr(args, "hote", "127.0.0.1"), getattr(args, "port", 8080)
    surcharges = {"options": {"journal": getattr(args, "journal", False)}}
    if "CASTAGNE_URL" not in os.environ:
        surcharges["url"] = f"http://{'127.0.0.1' if hote == '0.0.0.0' else hote}:{port}"
    servir(Configuration.depuis_environnement(**surcharges), hote, port)


if __name__ == "__main__":
    main()
