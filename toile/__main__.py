"""Point d'entrée : python3 -m toile [adresse] [--capture image.png]"""

import argparse


def main():
    parser = argparse.ArgumentParser(prog="python3 -m toile", description="Toile : un navigateur web fait maison.")
    parser.add_argument("adresse", nargs="?", default="about:accueil",
                        help="page à ouvrir (ex : https://example.com, about:demo, /chemin/vers/page.html)")
    parser.add_argument("--capture", metavar="IMAGE.png", help="au lieu d'ouvrir une fenêtre, enregistre une capture")
    parser.add_argument("--largeur", type=int, default=1000)
    parser.add_argument("--hauteur", type=int, default=None, help="hauteur de la capture (par défaut : toute la page)")
    parser.add_argument("--texte", action="store_true", help="affiche seulement le texte de la page dans le terminal")
    args = parser.parse_args()

    adresse = args.adresse
    if adresse.startswith(("/", "./", "../")):
        import os
        adresse = "file://" + os.path.abspath(adresse)

    if args.texte:
        from .page import charger
        page = charger(adresse)
        print(f"# {page.titre}\n\n{page.texte()}")
    elif args.capture:
        from .capture import capturer
        page = capturer(adresse, args.capture, args.largeur, args.hauteur)
        print(f"✅ Capture de « {page.titre or page.url} » enregistrée dans {args.capture}")
    else:
        from .fenetre import ouvrir
        ouvrir(adresse)


if __name__ == "__main__":
    main()
