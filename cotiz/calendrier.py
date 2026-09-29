"""Les dates des tours et les montants d'argent."""

import calendar
import datetime

FREQUENCES = {"hebdomadaire": "Chaque semaine", "quinzaine": "Toutes les deux semaines", "mensuelle": "Chaque mois"}

# Nombre de décimales de chaque monnaie : les montants sont gardés en entiers dans la plus petite unité
# (des francs CFA, des centimes d'euro…), jamais en nombres à virgule.
DEVISES = {
    "XOF": ("Franc CFA (UEMOA)", "FCFA", 0),
    "XAF": ("Franc CFA (CEMAC)", "FCFA", 0),
    "GNF": ("Franc guinéen", "GNF", 0),
    "CDF": ("Franc congolais", "FC", 0),
    "MAD": ("Dirham marocain", "DH", 2),
    "EUR": ("Euro", "€", 2),
    "CAD": ("Dollar canadien", "$ CA", 2),
    "USD": ("Dollar américain", "$", 2),
}


def ajouter_mois(date, mois):
    """Le même jour, `mois` mois plus tard (le 31 janvier + 1 mois → le 28 ou 29 février)."""
    total = date.month - 1 + mois
    annee, mois_suivant = date.year + total // 12, total % 12 + 1
    jour = min(date.day, calendar.monthrange(annee, mois_suivant)[1])
    return datetime.date(annee, mois_suivant, jour)


def echeance(debut, frequence, rang):
    """La date du tour numéro `rang` (0 pour le premier)."""
    if frequence == "hebdomadaire":
        return debut + datetime.timedelta(weeks=rang)
    if frequence == "quinzaine":
        return debut + datetime.timedelta(weeks=2 * rang)
    return ajouter_mois(debut, rang)


def vers_unites(texte, devise):
    """« 10 000 » ou « 12,50 » → un entier dans la plus petite unité de la monnaie."""
    decimales = DEVISES[devise][2]
    propre = str(texte).replace(" ", "").replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        valeur = float(propre)
    except ValueError:
        raise ValueError("Ce montant n'est pas un nombre.")
    if valeur < 0 or valeur != valeur:
        raise ValueError("Le montant doit être positif.")
    return int(round(valeur * 10 ** decimales))


def formater(unites, devise):
    """10000, "XOF" → « 10 000 FCFA » ; 1250, "EUR" → « 12,50 € »."""
    _, symbole, decimales = DEVISES[devise]
    signe = "-" if unites < 0 else ""
    entier, reste = divmod(abs(unites), 10 ** decimales) if decimales else (abs(unites), 0)
    texte = f"{entier:,}".replace(",", " ")
    if decimales:
        texte += "," + str(reste).zfill(decimales)
    return f"{signe}{texte} {symbole}"


def date_francaise(date):
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
            "novembre", "décembre"]
    if isinstance(date, str):
        date = datetime.date.fromisoformat(date[:10])
    jour = "1er" if date.day == 1 else str(date.day)
    return f"{jour} {mois[date.month - 1]} {date.year}"
