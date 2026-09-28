"""Analyse du texte : transforme une phrase en liste de « termes » à indexer.

« Les Chats noirs » et « chat noir » doivent donner les mêmes termes, sinon on ne
retrouverait jamais une page qui parle de chats quand on cherche « chat ».
"""

import re
import unicodedata

MOTS_VIDES = set("""
a ai aie as au aux avec c ce ceci cela celle celles celui ces cet cette ceux d dans de des du elle elles en
est et etaient etait ete etre eu il ils j je l la le les leur leurs lui m ma mais me meme mes moi mon n ne
ni nos notre nous on ont ou par pas pour qu que quel quelle quels qui s sa sans se ses si son sont sur t ta
te tes toi ton tu un une vos votre vous y the of and to in is
""".split())

TERMINAISONS = ("issements", "issement", "ements", "ement", "ations", "ation", "euses", "euse", "ments",
                "ment", "ites", "ite", "ions", "eurs", "eur", "aux", "es", "er", "ez", "s", "e", "x")


def sans_accents(texte):
    texte = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in texte if unicodedata.category(c) != "Mn")


def mots(texte):
    """Découpe en mots (minuscules, sans accents), en gardant les nombres."""
    return re.findall(r"[a-z0-9]+", sans_accents(texte))


def raciner(mot):
    """Racinisation simplifiée : « planetes », « planete » → « planet »."""
    for fin in TERMINAISONS:
        if len(mot) - len(fin) >= 3 and mot.endswith(fin):
            return mot[: -len(fin)]
    return mot


def termes(texte):
    return [raciner(m) for m in mots(texte) if m not in MOTS_VIDES and len(m) > 1]


def distance_edition(a, b):
    """Distance de Levenshtein : nombre minimal de lettres à ajouter, retirer ou changer."""
    if len(a) < len(b):
        a, b = b, a
    precedente = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        courante = [i]
        for j, cb in enumerate(b, 1):
            courante.append(min(precedente[j] + 1, courante[j - 1] + 1, precedente[j - 1] + (ca != cb)))
        precedente = courante
    return precedente[-1]
