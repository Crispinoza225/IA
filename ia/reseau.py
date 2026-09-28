"""Un petit réseau de neurones écrit à la main, sans aucune bibliothèque.

Architecture : entrée -> couche cachée (tanh) -> sortie (softmax).
Apprentissage : descente de gradient avec rétropropagation et entropie croisée.
"""

import json
import math
import random


def softmax(valeurs):
    maximum = max(valeurs)
    exps = [math.exp(v - maximum) for v in valeurs]
    total = sum(exps)
    return [e / total for e in exps]


class ReseauNeurones:
    def __init__(self, nb_entrees, nb_caches, nb_sorties, graine=42):
        rng = random.Random(graine)
        self.nb_entrees = nb_entrees
        self.nb_caches = nb_caches
        self.nb_sorties = nb_sorties
        # Initialisation de Xavier : des poids aléatoires ni trop grands ni trop petits.
        l1 = math.sqrt(6 / (nb_entrees + nb_caches))
        l2 = math.sqrt(6 / (nb_caches + nb_sorties))
        self.w1 = [[rng.uniform(-l1, l1) for _ in range(nb_entrees)] for _ in range(nb_caches)]
        self.b1 = [0.0] * nb_caches
        self.w2 = [[rng.uniform(-l2, l2) for _ in range(nb_caches)] for _ in range(nb_sorties)]
        self.b2 = [0.0] * nb_sorties

    def propager(self, x):
        """Calcule la sortie du réseau et renvoie aussi l'activation cachée."""
        cache = [
            math.tanh(sum(w * xi for w, xi in zip(ligne, x) if xi) + b)
            for ligne, b in zip(self.w1, self.b1)
        ]
        sortie = softmax([sum(w * h for w, h in zip(ligne, cache)) + b for ligne, b in zip(self.w2, self.b2)])
        return cache, sortie

    def predire(self, x):
        return self.propager(x)[1]

    def entrainer(self, exemples, epoques=300, taux=0.1, graine=0, verbeux=False):
        """exemples : liste de (vecteur_entree, indice_classe). Renvoie la perte finale."""
        rng = random.Random(graine)
        exemples = list(exemples)
        perte_moyenne = 0.0
        for epoque in range(epoques):
            rng.shuffle(exemples)
            perte_totale = 0.0
            for x, cible in exemples:
                cache, sortie = self.propager(x)
                perte_totale -= math.log(sortie[cible] + 1e-12)

                # Gradient de l'entropie croisée + softmax : sortie - one_hot(cible).
                d_sortie = list(sortie)
                d_sortie[cible] -= 1.0

                # Gradient vers la couche cachée (dérivée de tanh : 1 - h²).
                d_cache = [
                    (1 - cache[j] ** 2) * sum(d_sortie[k] * self.w2[k][j] for k in range(self.nb_sorties))
                    for j in range(self.nb_caches)
                ]

                for k in range(self.nb_sorties):
                    ligne = self.w2[k]
                    for j in range(self.nb_caches):
                        ligne[j] -= taux * d_sortie[k] * cache[j]
                    self.b2[k] -= taux * d_sortie[k]

                actifs = [i for i, xi in enumerate(x) if xi]
                for j in range(self.nb_caches):
                    ligne = self.w1[j]
                    for i in actifs:
                        ligne[i] -= taux * d_cache[j] * x[i]
                    self.b1[j] -= taux * d_cache[j]

            perte_moyenne = perte_totale / len(exemples)
            if verbeux and (epoque % 50 == 0 or epoque == epoques - 1):
                print(f"  époque {epoque:4d}  perte = {perte_moyenne:.4f}")
        return perte_moyenne

    def vers_dict(self):
        return {
            "taille": [self.nb_entrees, self.nb_caches, self.nb_sorties],
            "w1": self.w1, "b1": self.b1, "w2": self.w2, "b2": self.b2,
        }

    @classmethod
    def depuis_dict(cls, d):
        reseau = cls(*d["taille"])
        reseau.w1, reseau.b1, reseau.w2, reseau.b2 = d["w1"], d["b1"], d["w2"], d["b2"]
        return reseau

    def sauvegarder(self, chemin):
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(self.vers_dict(), f)

    @classmethod
    def charger(cls, chemin):
        with open(chemin, encoding="utf-8") as f:
            return cls.depuis_dict(json.load(f))
