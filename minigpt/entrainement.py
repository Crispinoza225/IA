"""Entraînement de MiniGPT : on lui montre du texte et il apprend à deviner le caractère suivant."""

import math
import os
import time

import torch

from .donnees import Tokeniseur, charger_corpus
from .modele import Config, MiniGPT

DOSSIER_MODELES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modeles")
CHEMIN_MODELE = os.path.join(DOSSIER_MODELES, "minigpt.pt")

TAILLES = {
    # nom : (nb_couches, nb_tetes, dim, taille_contexte) — plus c'est grand, plus c'est lent.
    "mini": (2, 2, 64, 64),
    "petit": (4, 4, 192, 128),
    "moyen": (6, 6, 384, 256),
}


def choisir_appareil():
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def sauvegarder(modele, tokeniseur, chemin=CHEMIN_MODELE, **infos):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    torch.save({
        "config": modele.cfg.vers_dict(),
        "poids": modele.state_dict(),
        "tokeniseur": tokeniseur.vers_json(),
        **infos,
    }, chemin)


def charger(chemin=CHEMIN_MODELE, appareil="cpu"):
    if not os.path.exists(chemin):
        raise SystemExit("Aucun modèle trouvé. Lance d'abord : python3 -m minigpt entrainer")
    sauvegarde = torch.load(chemin, map_location=appareil)
    modele = MiniGPT(Config(**sauvegarde["config"])).to(appareil)
    modele.load_state_dict(sauvegarde["poids"])
    modele.eval()
    return modele, Tokeniseur.depuis_json(sauvegarde["tokeniseur"])


def taux_apprentissage(etape, total, maximum, echauffement=100):
    """Échauffement progressif, puis décroissance en cosinus jusqu'à 10 % du maximum."""
    if etape < echauffement:
        return maximum * (etape + 1) / echauffement
    progression = (etape - echauffement) / max(1, total - echauffement)
    return maximum * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * progression)))


def entrainer(taille="petit", iterations=3000, taille_lot=32, taux_max=2e-3,
              evaluer_tous_les=250, graine=1337, chemin=CHEMIN_MODELE):
    torch.manual_seed(graine)
    appareil = choisir_appareil()

    print("📚 Lecture du corpus :")
    texte = charger_corpus()
    tokeniseur = Tokeniseur.depuis_texte(texte)
    donnees = torch.tensor(tokeniseur.encoder(texte), dtype=torch.long)
    coupure = int(0.9 * len(donnees))
    # 90 % pour apprendre, 10 % gardés de côté pour vérifier qu'il ne fait pas qu'apprendre par cœur.
    jeux = {"entrainement": donnees[:coupure], "validation": donnees[coupure:]}

    nb_couches, nb_tetes, dim, contexte = TAILLES[taille]
    cfg = Config(taille_vocab=tokeniseur.taille, taille_contexte=contexte,
                 nb_couches=nb_couches, nb_tetes=nb_tetes, dim=dim)
    modele = MiniGPT(cfg).to(appareil)
    optimiseur = torch.optim.AdamW(modele.parameters(), lr=taux_max, weight_decay=0.1, betas=(0.9, 0.99))

    nb_caracteres = f"{len(texte):,}".replace(",", " ")
    nb_parametres = f"{modele.nb_parametres():,}".replace(",", " ")
    print(f"🧠 {nb_caracteres} caractères, vocabulaire de {tokeniseur.taille} caractères")
    print(f"🧠 Modèle « {taille} » : {nb_parametres} paramètres, appareil : {appareil}")

    def lot(jeu):
        d = jeux[jeu]
        debuts = torch.randint(len(d) - contexte - 1, (taille_lot,))
        x = torch.stack([d[i:i + contexte] for i in debuts])
        y = torch.stack([d[i + 1:i + contexte + 1] for i in debuts])  # la cible = le texte décalé d'un cran
        return x.to(appareil), y.to(appareil)

    @torch.no_grad()
    def estimer_pertes(nb_lots=20):
        modele.eval()
        resultats = {jeu: sum(modele(*lot(jeu))[1].item() for _ in range(nb_lots)) / nb_lots for jeu in jeux}
        modele.train()
        return resultats

    debut = time.time()
    meilleure = float("inf")
    for etape in range(iterations + 1):
        if etape % evaluer_tous_les == 0 or etape == iterations:
            pertes = estimer_pertes()
            duree = time.time() - debut
            print(f"étape {etape:5d} | perte entraînement {pertes['entrainement']:.3f} "
                  f"| validation {pertes['validation']:.3f} | {duree:5.0f} s")
            if pertes["validation"] < meilleure:
                meilleure = pertes["validation"]
                sauvegarder(modele, tokeniseur, chemin, etape=etape, perte_validation=meilleure)
            if etape > 0:
                modele.eval()
                depart = torch.tensor([tokeniseur.encoder("Le ")], device=appareil)
                apercu = tokeniseur.decoder(list(modele.generer(depart, 80, top_k=20)))
                modele.train()
                print("   ✍️  Le " + apercu.replace("\n", " "))
        if etape == iterations:
            break

        for groupe in optimiseur.param_groups:
            groupe["lr"] = taux_apprentissage(etape, iterations, taux_max)
        _, perte = modele(*lot("entrainement"))
        optimiseur.zero_grad(set_to_none=True)
        perte.backward()  # rétropropagation : calcul de la direction pour s'améliorer
        torch.nn.utils.clip_grad_norm_(modele.parameters(), 1.0)
        optimiseur.step()

    print(f"✅ Modèle sauvegardé dans {chemin} (meilleure perte de validation : {meilleure:.3f})")
