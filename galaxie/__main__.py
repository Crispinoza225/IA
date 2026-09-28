"""Point d'entrée : python3 -m galaxie <scène> [options]"""

import argparse
import os
import time

from lumiere.image import ecrire_png

from .rendu import dessiner
from .scenes import SCENES

DOSSIER_SORTIES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sorties")


def main():
    parser = argparse.ArgumentParser(prog="python3 -m galaxie", description="Simulateur de galaxies.")
    parser.add_argument("scene", choices=sorted(SCENES), help="collision, spirale ou amas")
    parser.add_argument("--etoiles", type=int, default=None, help="nombre d'étoiles")
    parser.add_argument("--pas", type=int, default=None, help="nombre de pas de temps")
    parser.add_argument("--images", type=int, default=100, help="nombre d'images de l'animation")
    parser.add_argument("--largeur", type=int, default=640)
    parser.add_argument("--hauteur", type=int, default=480)
    parser.add_argument("--methode", choices=["directe", "barnes-hut"], default=None,
                        help="calcul de la gravité (par défaut : celui de la scène)")
    parser.add_argument("--sortie", default=None, help="fichier .gif (animation) ou .png (dernière image)")
    args = parser.parse_args()

    fabrique, reglages = SCENES[args.scene]
    univers = fabrique(**({"nb_etoiles": args.etoiles} if args.etoiles else {}))
    if args.methode:
        univers.methode = args.methode
    nb_pas = args.pas or reglages["pas"]
    sortie = args.sortie or os.path.join(DOSSIER_SORTIES, f"{args.scene}.gif")
    os.makedirs(os.path.dirname(os.path.abspath(sortie)), exist_ok=True)
    options_image = dict(largeur=args.largeur, hauteur=args.hauteur, champ=reglages["champ"], vue=reglages["vue"])

    print(f"🌌 {args.scene} : {len(univers.positions)} particules, {nb_pas} pas, gravité « {univers.methode} »")
    images = []
    tous_les = max(1, nb_pas // max(1, args.images))
    debut = time.time()
    for n in range(nb_pas + 1):
        if n % tous_les == 0:
            images.append(dessiner(univers, **options_image))
            ecoule = time.time() - debut
            reste = ecoule / max(n, 1) * (nb_pas - n)
            print(f"\r  pas {n:5d}/{nb_pas}  t = {univers.temps:6.2f}  ({ecoule:.0f} s, encore ~{reste:.0f} s)  ",
                  end="", flush=True)
        if n < nb_pas:
            univers.pas(reglages["dt"])
    print()

    if sortie.lower().endswith(".png"):
        ecrire_png(sortie, images[-1])
    else:
        from PIL import Image  # Pillow sert uniquement à assembler le GIF animé
        cadres = [Image.fromarray(i).quantize(colors=128, method=Image.Quantize.MEDIANCUT) for i in images]
        cadres[0].save(sortie, save_all=True, append_images=cadres[1:], duration=50, loop=0, optimize=True)
        ecrire_png(os.path.splitext(sortie)[0] + ".png", images[-1])
    print(f"✅ Enregistré : {sortie}")


if __name__ == "__main__":
    main()
