"""Point d'entrée : python3 -m minigpt {telecharger, entrainer, ecrire, discuter}"""

import argparse
import sys

import torch


def ecrire(modele, tokeniseur, debut, longueur, temperature, top_k):
    print(debut, end="", flush=True)
    idx = torch.tensor([tokeniseur.encoder(debut or "\n")])
    for i in modele.generer(idx, longueur, temperature=temperature, top_k=top_k):
        print(tokeniseur.decoder([i]), end="", flush=True)
    print()


def main():
    parser = argparse.ArgumentParser(prog="python3 -m minigpt", description="MiniGPT : un petit GPT fait maison.")
    actions = parser.add_subparsers(dest="action", required=True)

    actions.add_parser("telecharger", help="télécharge le corpus de textes en français")

    p = actions.add_parser("entrainer", help="entraîne le modèle sur les textes de minigpt/donnees/")
    p.add_argument("--taille", choices=["mini", "petit", "moyen"], default="petit")
    p.add_argument("--iterations", type=int, default=3000)
    p.add_argument("--taille-lot", type=int, default=32)

    for nom, aide in (("ecrire", "écrit la suite d'un début de texte"),
                      ("discuter", "mode interactif : tape un début, MiniGPT continue")):
        p = actions.add_parser(nom, help=aide)
        if nom == "ecrire":
            p.add_argument("debut", nargs="?", default="Le ")
        p.add_argument("--longueur", type=int, default=400)
        p.add_argument("--temperature", type=float, default=0.8)
        p.add_argument("--top-k", type=int, default=30)
        p.add_argument("--graine", type=int, default=None)

    args = parser.parse_args()

    if args.action == "telecharger":
        from .donnees import telecharger_europarl
        telecharger_europarl()
        return

    if args.action == "entrainer":
        from .entrainement import entrainer
        entrainer(taille=args.taille, iterations=args.iterations, taille_lot=args.taille_lot)
        return

    from .entrainement import charger
    modele, tokeniseur = charger()
    if args.graine is not None:
        torch.manual_seed(args.graine)
    options = dict(longueur=args.longueur, temperature=args.temperature, top_k=args.top_k)

    if args.action == "ecrire":
        ecrire(modele, tokeniseur, args.debut, **options)
        return

    print("🤖 MiniGPT — écris un début de phrase, je continue. (« quitter » pour partir)\n")
    while True:
        try:
            debut = input("Toi     > ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if debut.strip().lower() in {"quitter", "exit", "quit"}:
            break
        print("MiniGPT > ", end="")
        ecrire(modele, tokeniseur, debut, **options)
        print()


if __name__ == "__main__":
    sys.exit(main())
