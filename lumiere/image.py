"""Conversion des valeurs de lumière en pixels, et écriture d'un fichier PNG sans aucune bibliothèque."""

import struct
import zlib

import numpy as np


def vers_pixels(image, gamma=2.2):
    """Lumière (0 → ∞) → pixels (0 → 255).

    Nos yeux ne perçoivent pas la lumière de façon linéaire : la correction gamma éclaircit
    les zones sombres pour que l'image paraisse naturelle à l'écran.
    """
    # Une lumière trop intense est ramenée à la luminosité maximale en gardant sa teinte
    # (sinon une lampe orange très forte deviendrait blanche).
    maximum = np.max(image, axis=-1, keepdims=True)
    image = np.maximum(image, 0.0) / np.maximum(maximum, 1.0)
    image = image ** (1.0 / gamma)
    return (image * 255 + 0.5).astype(np.uint8)


def ecrire_png(chemin, pixels):
    """Écrit un tableau (hauteur, largeur, 3) d'octets au format PNG."""
    hauteur, largeur, _ = pixels.shape
    # Chaque ligne commence par un octet de « filtre » (0 = aucun), puis les pixels RVB.
    brut = b"".join(b"\x00" + pixels[y].tobytes() for y in range(hauteur))

    def morceau(type_, donnees):
        crc = zlib.crc32(type_ + donnees) & 0xFFFFFFFF
        return struct.pack(">I", len(donnees)) + type_ + donnees + struct.pack(">I", crc)

    entete = struct.pack(">IIBBBBB", largeur, hauteur, 8, 2, 0, 0, 0)  # 8 bits, couleurs RVB
    with open(chemin, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(morceau(b"IHDR", entete))
        f.write(morceau(b"IDAT", zlib.compress(brut, 9)))
        f.write(morceau(b"IEND", b""))
