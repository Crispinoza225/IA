"""Les règles de Castagne : caractéristiques, armes, compétences, animaux, niveaux et apparence."""

import re

CARACS = ("force", "agilite", "rapidite", "endurance")
NOMS_CARACS = {"force": "Force", "agilite": "Agilité", "rapidite": "Rapidité", "endurance": "Endurance"}
COMBATS_PAR_JOUR = 6
XP_VICTOIRE, XP_DEFAITE, XP_MAITRE = 2, 1, 1
XP_TOURNOI_TOUR, XP_TOURNOI_VAINQUEUR = 1, 5
TAILLE_TOURNOI = 8

# degats : dégâts de base ; tempo : durée d'une attaque (plus c'est petit, plus on frappe souvent) ;
# precision, esquive, parade, contre, combo, desarme : bonus de probabilité ; jet : arme lancée puis perdue.
ARMES = {
    "couteau": {"nom": "Couteau", "degats": 5, "tempo": 0.7, "combo": 0.15, "esquive": 0.05},
    "epee": {"nom": "Épée", "degats": 8, "tempo": 1.0, "parade": 0.15, "contre": 0.1},
    "cimeterre": {"nom": "Cimeterre", "degats": 9, "tempo": 1.0, "combo": 0.1},
    "hache": {"nom": "Hache", "degats": 12, "tempo": 1.3, "precision": -0.05},
    "marteau": {"nom": "Marteau de guerre", "degats": 18, "tempo": 1.5, "precision": -0.1},
    "massue": {"nom": "Massue", "degats": 14, "tempo": 1.5},
    "lance": {"nom": "Lance", "degats": 8, "tempo": 1.1, "contre": 0.2},
    "trident": {"nom": "Trident", "degats": 8, "tempo": 1.2, "contre": 0.15, "parade": 0.1},
    "baton": {"nom": "Bâton", "degats": 5, "tempo": 0.9, "parade": 0.25, "contre": 0.15},
    "fleau": {"nom": "Fléau", "degats": 10, "tempo": 1.2, "combo": 0.1, "precision": 0.1},
    "poele": {"nom": "Poêle", "degats": 7, "tempo": 1.0, "parade": 0.2},
    "cle": {"nom": "Clé à molette", "degats": 7, "tempo": 0.9, "precision": 0.1, "desarme": 0.1},
    "os": {"nom": "Gros os", "degats": 9, "tempo": 1.0, "combo": 0.05},
    "fouet": {"nom": "Fouet", "degats": 7, "tempo": 0.8, "desarme": 0.25, "precision": 0.1},
    "nunchaku": {"nom": "Nunchaku", "degats": 3, "tempo": 0.6, "combo": 0.3},
    "eventail": {"nom": "Éventail de fer", "degats": 2, "tempo": 0.6, "esquive": 0.2, "combo": 0.2},
    "masse": {"nom": "Masse d'armes", "degats": 14, "tempo": 1.5, "parade": 0.05},
    "balai": {"nom": "Balai", "degats": 5, "tempo": 0.8, "parade": 0.1, "esquive": 0.1},
    "shuriken": {"nom": "Shuriken", "degats": 6, "tempo": 0.5, "jet": True, "precision": 0.1},
    "javelot": {"nom": "Javelot", "degats": 10, "tempo": 1.0, "jet": True},
}
DEGATS_MAINS_NUES = 5

COMPETENCES = {
    "force_herculeenne": ("Force herculéenne", "Force augmentée de moitié."),
    "agilite_feline": ("Agilité féline", "Agilité augmentée de moitié."),
    "vitesse_eclair": ("Vitesse éclair", "Rapidité augmentée de moitié."),
    "vitalite": ("Vitalité", "Points de vie augmentés de 30 %."),
    "cuir_epais": ("Cuir épais", "Encaisse 15 % de dégâts en moins."),
    "bouclier": ("Bouclier", "Pare souvent les attaques."),
    "riposte": ("Riposte", "Contre-attaque bien plus souvent."),
    "reflexes": ("Réflexes", "Esquive bien plus souvent."),
    "furie": ("Furie", "Enchaîne plus souvent plusieurs coups."),
    "coup_d_avance": ("Coup d'avance", "Frappe toujours en premier."),
    "desarmement": ("Désarmement", "Fait souvent tomber l'arme de l'adversaire."),
    "second_souffle": ("Second souffle", "Une fois par combat, récupère un tiers de sa vie quand elle est au plus bas."),
    "cri_de_guerre": ("Cri de guerre", "Son cri retarde tous ses adversaires au début du combat."),
    "increvable": ("Increvable", "Survit une fois à un coup fatal, avec 1 point de vie."),
    "maitre_d_armes": ("Maître d'armes", "Un quart de dégâts en plus avec une arme."),
    "poings_d_acier": ("Poings d'acier", "Dégâts à mains nues doublés."),
    "lanceur": ("Lanceur d'élite", "Peut lancer n'importe quelle arme sur l'adversaire."),
    "ami_des_betes": ("Ami des bêtes", "Ses animaux ont moitié plus de points de vie."),
}

ANIMAUX = {
    "chien": {"nom": "Chien", "pv": 8, "degats": 2, "agilite": 6, "rapidite": 3, "combo": 0.05, "max": 3},
    "loup": {"nom": "Loup", "pv": 12, "degats": 3, "agilite": 8, "rapidite": 4, "combo": 0.1, "max": 1},
    "panthere": {"nom": "Panthère", "pv": 14, "degats": 3, "agilite": 12, "rapidite": 6, "combo": 0.15, "max": 1},
    "ours": {"nom": "Ours", "pv": 25, "degats": 4, "agilite": 2, "rapidite": 1, "combo": 0.0, "max": 1},
}

# L'apparence : des numéros de variantes, dessinées par le navigateur (web/commun.js).
APPARENCE = {"peau": 6, "coiffure": 7, "cheveux": 8, "haut": 10, "bas": 8, "barbe": 4, "yeux": 4}
GENRES = ("h", "f")

NOM_VALIDE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ0-9][A-Za-zÀ-ÖØ-öø-ÿ0-9_-]{2,19}$")
SYLLABES = ["gro", "bul", "mor", "dak", "zog", "ra", "tor", "kel", "bru", "mi", "no", "fa", "gar", "lok", "tu", "ba",
            "rok", "zi", "pa", "kra", "vu", "dor", "ma", "gni", "tar", "po", "ju", "sko", "rin", "bo"]


def seuil_xp(niveau):
    """Expérience nécessaire pour passer du niveau `niveau` au suivant."""
    return 4 + 2 * niveau


def pv_max(fiche):
    pv = 50 + fiche["endurance"] * 6
    return int(pv * 1.3) if "vitalite" in fiche["competences"] else pv


def nom_valide(nom):
    if not NOM_VALIDE.match(nom or ""):
        raise ValueError("Le nom doit faire 3 à 20 caractères : lettres, chiffres, tirets.")
    return nom


def nom_aleatoire(rng):
    return "".join(rng.choice(SYLLABES) for _ in range(rng.choice((2, 2, 3)))).capitalize()


def apparence_aleatoire(rng, genre=None):
    apparence = {cle: rng.randrange(n) for cle, n in APPARENCE.items()}
    apparence["genre"] = genre or rng.choice(GENRES)
    if apparence["genre"] == "f":
        apparence["barbe"] = 0
    return apparence


def apparence_valide(apparence):
    if not isinstance(apparence, dict) or apparence.get("genre") not in GENRES:
        raise ValueError("Apparence invalide.")
    propre = {"genre": apparence["genre"]}
    for cle, n in APPARENCE.items():
        valeur = apparence.get(cle)
        if not isinstance(valeur, int) or isinstance(valeur, bool) or not 0 <= valeur < n:
            raise ValueError("Apparence invalide.")
        propre[cle] = valeur
    if propre["genre"] == "f":
        propre["barbe"] = 0
    return propre


# --- Progression --------------------------------------------------------------------------------------------------

def animaux_possibles(fiche):
    return [cle for cle, a in ANIMAUX.items() if fiche["animaux"].count(cle) < a["max"]]


def options_niveau(rng, fiche):
    """Deux bonus différents parmi lesquels choisir au passage de niveau."""
    options = []
    while len(options) < 2:
        genre = rng.choices(["carac", "partage", "arme", "competence", "animal"], weights=[5, 3, 3, 3, 1])[0]
        option = None
        if genre == "carac":
            option = {"type": "carac", "gains": {rng.choice(CARACS): 3}}
        elif genre == "partage":
            a, b = rng.sample(CARACS, 2)
            option = {"type": "carac", "gains": {a: 2, b: 1}}
        elif genre == "arme":
            libres = [a for a in ARMES if a not in fiche["armes"]]
            option = libres and {"type": "arme", "cle": rng.choice(libres)}
        elif genre == "competence":
            libres = [c for c in COMPETENCES if c not in fiche["competences"]]
            option = libres and {"type": "competence", "cle": rng.choice(libres)}
        else:
            libres = animaux_possibles(fiche)
            option = libres and {"type": "animal", "cle": rng.choice(libres)}
        if option and option not in options:
            options.append(option)
    return options


def appliquer(fiche, option):
    if option["type"] == "carac":
        for carac, gain in option["gains"].items():
            fiche[carac] += gain
    elif option["type"] == "arme":
        fiche["armes"].append(option["cle"])
    elif option["type"] == "competence":
        fiche["competences"].append(option["cle"])
    elif option["type"] == "animal":
        fiche["animaux"].append(option["cle"])
    return fiche


def libelle(option):
    if option["type"] == "carac":
        return " et ".join(f"{NOMS_CARACS[c]} +{g}" for c, g in option["gains"].items())
    if option["type"] == "arme":
        return f"Nouvelle arme : {ARMES[option['cle']]['nom']}"
    if option["type"] == "competence":
        return f"Nouvelle compétence : {COMPETENCES[option['cle']][0]}"
    return f"Nouvel animal : {ANIMAUX[option['cle']]['nom']}"


def fiche_initiale(rng):
    """Une brute toute neuve : 20 points répartis au hasard, et un premier bonus."""
    fiche = {c: 2 for c in CARACS}
    for _ in range(12):
        fiche[rng.choice(CARACS)] += 1
    fiche.update(armes=[], competences=[], animaux=[])
    bonus = rng.choices(["arme", "competence", "animal"], weights=[5, 4, 1])[0]
    if bonus == "arme":
        appliquer(fiche, {"type": "arme", "cle": rng.choice(list(ARMES))})
    elif bonus == "competence":
        appliquer(fiche, {"type": "competence", "cle": rng.choice(list(COMPETENCES))})
    else:
        appliquer(fiche, {"type": "animal", "cle": rng.choice(list(ANIMAUX))})
    return fiche


def fiche_de_niveau(rng, niveau):
    """Une brute adverse générée : elle a fait des choix au hasard à chaque niveau."""
    fiche = fiche_initiale(rng)
    for _ in range(niveau - 1):
        appliquer(fiche, rng.choice(options_niveau(rng, fiche)))
    return fiche
