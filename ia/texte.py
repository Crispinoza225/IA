"""Transformation d'une phrase en vecteur de nombres compréhensible par le réseau."""

import re
import unicodedata

MOTS_VIDES = {"le", "la", "les", "un", "une", "des", "de", "du", "d", "l", "et", "a", "au", "aux"}


def normaliser(phrase):
    """Minuscules, sans accents, sans ponctuation."""
    phrase = unicodedata.normalize("NFD", phrase.lower())
    phrase = "".join(c for c in phrase if unicodedata.category(c) != "Mn")
    phrase = re.sub(r"[^a-z0-9 ]", " ", phrase)
    # Tous les nombres deviennent le même mot : seule leur présence compte.
    return re.sub(r"\d+", " nombre ", phrase)


def raciner(mot):
    """Racinisation très simple : on retire quelques terminaisons fréquentes."""
    for fin in ("ement", "ions", "ez", "es", "er", "s", "e", "x"):
        if len(mot) > len(fin) + 2 and mot.endswith(fin):
            return mot[: -len(fin)]
    return mot


def jetons(phrase):
    return [raciner(m) for m in normaliser(phrase).split() if m not in MOTS_VIDES]


def construire_vocabulaire(phrases):
    return sorted({j for p in phrases for j in jetons(p)})


def vectoriser(phrase, vocabulaire):
    """Sac de mots : 1 si le mot du vocabulaire est présent dans la phrase, sinon 0."""
    index = {m: i for i, m in enumerate(vocabulaire)}
    vecteur = [0.0] * len(vocabulaire)
    for j in jetons(phrase):
        if j in index:
            vecteur[index[j]] = 1.0
    return vecteur
