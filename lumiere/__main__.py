"""Point d'entrée : python3 -m lumiere rendre <scène> [options]"""

import argparse
import os
import time
from multiprocessing import Pool

import numpy as np

from .image import ecrire_png, vers_pixels
from .moteur import ScenePreparee, rendre_echantillons
from .scenes import SCENES

DOSSIER_RENDUS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rendus")


def _travail(arguments):
    return rendre_echantillons(*arguments)


def rendre(scene, largeur, hauteur, echantillons, rebonds=10, processus=None, graine=0, afficher=print):
    """Rend l'image en répartissant les échantillons sur tous les cœurs du processeur."""
    sp = ScenePreparee(scene)
    par_tache = 2
    taches = [(sp, largeur, hauteur, min(par_tache, echantillons - i), graine * 100_003 + i, rebonds)
              for i in range(0, echantillons, par_tache)]
    image = np.zeros((hauteur, largeur, 3))
    debut = time.time()
    with Pool(processus or os.cpu_count()) as pool:
        for fait, somme in enumerate(pool.imap_unordered(_travail, taches), 1):
            image += somme
            ecoule = time.time() - debut
            reste = ecoule / fait * (len(taches) - fait)
            afficher(f"\r  {fait * 100 // len(taches):3d} %  ({ecoule:.0f} s, encore ~{reste:.0f} s)  ", end="")
    afficher()
    return image / echantillons


def main():
    parser = argparse.ArgumentParser(prog="python3 -m lumiere", description="Lumière : un moteur de rendu photoréaliste.")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("scenes", help="liste les scènes disponibles")
    p = actions.add_parser("rendre", help="calcule une image")
    p.add_argument("scene", choices=sorted(SCENES))
    p.add_argument("--largeur", type=int, default=480)
    p.add_argument("--hauteur", type=int, default=None, help="par défaut : format 16/9 (carré pour cornell)")
    p.add_argument("--echantillons", type=int, default=64, help="rayons par pixel : plus = moins de grain, plus lent")
    p.add_argument("--rebonds", type=int, default=10)
    p.add_argument("--sortie", default=None)
    args = parser.parse_args()

    if args.action == "scenes":
        for nom, fabrique in sorted(SCENES.items()):
            print(f"  {nom:10s} {fabrique.__doc__.strip().splitlines()[0]}")
        return

    hauteur = args.hauteur or (args.largeur if args.scene == "cornell" else args.largeur * 9 // 16)
    sortie = args.sortie or os.path.join(DOSSIER_RENDUS, f"{args.scene}.png")
    print(f"🎨 Rendu de « {args.scene} » : {args.largeur}×{hauteur}, {args.echantillons} rayons par pixel")
    image = rendre(SCENES[args.scene](), args.largeur, hauteur, args.echantillons, args.rebonds,
                   afficher=lambda *a, **k: print(*a, **k, flush=True))
    os.makedirs(os.path.dirname(os.path.abspath(sortie)), exist_ok=True)
    ecrire_png(sortie, vers_pixels(image))
    print(f"✅ Image enregistrée : {sortie}")


if __name__ == "__main__":
    main()
