"""La partie : créer une brute, l'entraîner au combat, monter de niveau, recruter des élèves, disputer des tournois."""

import json
import random

from . import regles as R
from .base import Introuvable, brute_depuis_ligne, iso, maintenant
from .combat import simuler


class Refus(Exception):
    """Une action interdite par les règles du jeu (plus de combats aujourd'hui, niveau à choisir…)."""


# --- Création ---------------------------------------------------------------------------------------------------------

def inserer_brute(c, nom, apparence, fiche, hash_mdp=None, bot=False, niveau=1, maitre_id=None):
    curseur = c.execute(
        "INSERT INTO brutes (nom, cle, hash, bot, apparence, fiche, niveau, maitre_id, cree_le) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (nom, nom.lower(), hash_mdp, int(bot), json.dumps(apparence), json.dumps(fiche), niveau, maitre_id, iso(maintenant())))
    return curseur.lastrowid


def creer_brute(base, nom, hash_mdp, apparence, maitre=None, rng=random):
    nom = R.nom_valide(nom.strip())
    apparence = R.apparence_valide(apparence)
    with base.transaction() as c:
        if c.execute("SELECT 1 FROM brutes WHERE cle = ?", (nom.lower(),)).fetchone():
            raise Refus(f"Le nom « {nom} » est déjà pris.")
        maitre_id = None
        if maitre:
            ligne = c.execute("SELECT id FROM brutes WHERE cle = ? AND bot = 0", (maitre.strip().lower(),)).fetchone()
            maitre_id = ligne["id"] if ligne else None
        return inserer_brute(c, nom, apparence, R.fiche_initiale(rng), hash_mdp, maitre_id=maitre_id)


def creer_bot(c, niveau, rng):
    nom = R.nom_aleatoire(rng)
    while c.execute("SELECT 1 FROM brutes WHERE cle = ?", (nom.lower(),)).fetchone():
        nom = R.nom_aleatoire(rng) + str(rng.randrange(10, 100))
    return inserer_brute(c, nom, R.apparence_aleatoire(rng), R.fiche_de_niveau(rng, niveau), bot=True, niveau=niveau)


# --- Progression --------------------------------------------------------------------------------------------------

def gagner_xp(c, brute_id, xp, rng):
    """Ajoute de l'expérience. Au passage de niveau, la brute doit choisir entre deux bonus (les brutes du jeu
    choisissent au hasard). Tant que le choix n'est pas fait, l'expérience continue de s'accumuler."""
    brute = brute_depuis_ligne(c.execute("SELECT * FROM brutes WHERE id = ?", (brute_id,)).fetchone())
    if not brute:
        return
    niveau, total, fiche, choix = brute["niveau"], brute["xp"] + xp, brute["fiche"], brute["choix"]
    while choix is None and total >= R.seuil_xp(niveau):
        total -= R.seuil_xp(niveau)
        niveau += 1
        options = R.options_niveau(rng, fiche)
        if brute["bot"]:
            R.appliquer(fiche, rng.choice(options))
        else:
            choix = options
    c.execute("UPDATE brutes SET niveau = ?, xp = ?, fiche = ?, choix = ? WHERE id = ?",
              (niveau, total, json.dumps(fiche), json.dumps(choix) if choix else None, brute_id))


def choisir(base, brute_id, index, rng=random):
    with base.transaction() as c:
        brute = brute_depuis_ligne(c.execute("SELECT * FROM brutes WHERE id = ?", (brute_id,)).fetchone())
        if not brute["choix"]:
            raise Refus("Aucun bonus à choisir.")
        if index not in range(len(brute["choix"])):
            raise ValueError("Choix invalide.")
        option = brute["choix"][index]
        fiche = R.appliquer(brute["fiche"], option)
        c.execute("UPDATE brutes SET fiche = ?, choix = NULL WHERE id = ?", (json.dumps(fiche), brute_id))
        gagner_xp(c, brute_id, 0, rng)  # assez d'expérience de côté pour un autre niveau ?
        return option


def combats_restants(brute, jour):
    return R.COMBATS_PAR_JOUR - (brute["combats_jour"] if brute["jour"] == jour else 0)


# --- Combats ------------------------------------------------------------------------------------------------------

def lancer_combat(c, a, b, rng, tournoi_id=None):
    """Simule et enregistre un combat entre deux brutes. Renvoie (identifiant du combat, brute gagnante)."""
    graine = rng.randrange(2 ** 31)
    gagnant, evenements = simuler(a, b, graine)
    vainqueur, vaincu = (a, b) if gagnant == 0 else (b, a)
    donnees = {"brutes": [{"id": x["id"], "nom": x["nom"], "niveau": x["niveau"]} for x in (a, b)],
               "gagnant": gagnant, "evenements": evenements}
    curseur = c.execute("INSERT INTO combats (attaquant_id, defenseur_id, gagnant_id, tournoi_id, date, donnees) "
                        "VALUES (?, ?, ?, ?, ?, ?)", (a["id"], b["id"], vainqueur["id"], tournoi_id, iso(maintenant()),
                                                      json.dumps(donnees, separators=(",", ":"))))
    c.execute("UPDATE brutes SET victoires = victoires + 1 WHERE id = ?", (vainqueur["id"],))
    c.execute("UPDATE brutes SET defaites = defaites + 1 WHERE id = ?", (vaincu["id"],))
    return curseur.lastrowid, vainqueur


def adversaires(base, brute, rng=random, nombre=6):
    """Des adversaires de niveau proche. S'il n'y a pas assez de joueurs, des brutes du jeu les complètent."""
    with base.transaction() as c:
        lignes = c.execute("SELECT * FROM brutes WHERE id != ? AND niveau BETWEEN ? AND ? ORDER BY RANDOM() LIMIT ?",
                           (brute["id"], brute["niveau"] - 1, brute["niveau"] + 1, nombre)).fetchall()
        choisies = [brute_depuis_ligne(l) for l in lignes]
        while len(choisies) < nombre:
            niveau = max(1, brute["niveau"] + rng.choice((-1, 0, 0, 1)))
            choisies.append(brute_depuis_ligne(c.execute("SELECT * FROM brutes WHERE id = ?", (creer_bot(c, niveau, rng),)).fetchone()))
        return choisies


def combattre(base, brute_id, nom_adversaire, jour, rng=random):
    with base.transaction() as c:
        brute = brute_depuis_ligne(c.execute("SELECT * FROM brutes WHERE id = ?", (brute_id,)).fetchone())
        adversaire = brute_depuis_ligne(c.execute("SELECT * FROM brutes WHERE cle = ?", (nom_adversaire.strip().lower(),)).fetchone())
        if not adversaire:
            raise Introuvable("Cette brute n'existe pas.")
        if adversaire["id"] == brute_id:
            raise Refus("Ta brute ne peut pas se battre contre elle-même.")
        if brute["choix"]:
            raise Refus("Choisis d'abord ton bonus de niveau.")
        if combats_restants(brute, jour) <= 0:
            raise Refus("Ta brute est épuisée : reviens demain pour de nouveaux combats.")
        deja = brute["combats_jour"] if brute["jour"] == jour else 0
        c.execute("UPDATE brutes SET jour = ?, combats_jour = ? WHERE id = ?", (jour, deja + 1, brute_id))
        combat_id, vainqueur = lancer_combat(c, brute, adversaire, rng)
        if vainqueur["id"] == brute_id:
            # Aucune gloire à battre une brute beaucoup plus faible : pas d'expérience.
            gain = R.XP_VICTOIRE if adversaire["niveau"] >= brute["niveau"] - 2 else 0
            if brute["maitre_id"]:
                gagner_xp(c, brute["maitre_id"], R.XP_MAITRE, rng)
        else:
            gain = R.XP_DEFAITE
        gagner_xp(c, brute_id, gain, rng)
        return combat_id, vainqueur["id"] == brute_id, gain


def combat(base, combat_id):
    ligne = base.un("SELECT * FROM combats WHERE id = ?", (combat_id,))
    if not ligne:
        raise Introuvable("Ce combat n'existe pas.")
    donnees = json.loads(ligne["donnees"])
    donnees.update(id=ligne["id"], date=ligne["date"], tournoi_id=ligne["tournoi_id"])
    return donnees


def historique(base, brute_id, limite=12):
    lignes = base.tous(
        "SELECT c.id, c.date, c.gagnant_id, c.tournoi_id, c.attaquant_id, a.nom AS attaquant, d.nom AS defenseur "
        "FROM combats c JOIN brutes a ON a.id = c.attaquant_id JOIN brutes d ON d.id = c.defenseur_id "
        "WHERE c.attaquant_id = ? OR c.defenseur_id = ? ORDER BY c.id DESC LIMIT ?", (brute_id, brute_id, limite))
    return [{"id": l["id"], "date": l["date"], "victoire": l["gagnant_id"] == brute_id, "tournoi": bool(l["tournoi_id"]),
             "adversaire": l["defenseur"] if l["attaquant_id"] == brute_id else l["attaquant"],
             "attaque": l["attaquant_id"] == brute_id} for l in lignes]


# --- Tournois -----------------------------------------------------------------------------------------------------

def inscrire(base, brute_id, jour):
    with base.transaction() as c:
        c.execute("INSERT OR IGNORE INTO inscriptions (brute_id, date) VALUES (?, ?)", (brute_id, jour))


def resoudre_tournois(base, jour, rng=random):
    """Dispute les tournois des jours passés : les inscrits, classés par niveau, forment des tableaux de huit,
    complétés par des brutes du jeu. Chaque victoire rapporte de l'expérience, le vainqueur en gagne beaucoup."""
    with base.transaction() as c:
        dates = [l["date"] for l in c.execute(
            "SELECT DISTINCT date FROM inscriptions WHERE tournoi_id IS NULL AND date < ? ORDER BY date", (jour,))]
        for date in dates:
            inscrits = [l["id"] for l in c.execute(
                "SELECT b.id FROM inscriptions i JOIN brutes b ON b.id = i.brute_id "
                "WHERE i.date = ? AND i.tournoi_id IS NULL ORDER BY b.niveau DESC, b.id", (date,))]
            for debut in range(0, len(inscrits), R.TAILLE_TOURNOI):
                groupe = inscrits[debut:debut + R.TAILLE_TOURNOI]
                niveaux = sorted(l["niveau"] for l in c.execute(
                    f"SELECT niveau FROM brutes WHERE id IN ({','.join('?' * len(groupe))})", groupe))
                niveau = niveaux[len(niveaux) // 2]  # les brutes du jeu qui complètent ont le niveau médian
                while len(groupe) < R.TAILLE_TOURNOI:
                    groupe.append(creer_bot(c, niveau, rng))
                rng.shuffle(groupe)
                tournoi_id = c.execute("INSERT INTO tournois (date, participants, tours, vainqueur_id) VALUES (?, ?, '[]', 0)",
                                       (date, json.dumps(groupe))).lastrowid
                tours, encore = [], groupe
                while len(encore) > 1:
                    manche, suivants = [], []
                    for i in range(0, len(encore), 2):
                        a, b = (brute_depuis_ligne(c.execute("SELECT * FROM brutes WHERE id = ?", (x,)).fetchone())
                                for x in encore[i:i + 2])
                        combat_id, vainqueur = lancer_combat(c, a, b, rng, tournoi_id)
                        gagner_xp(c, vainqueur["id"], R.XP_TOURNOI_TOUR, rng)
                        manche.append(combat_id)
                        suivants.append(vainqueur["id"])
                    tours.append(manche)
                    encore = suivants
                gagner_xp(c, encore[0], R.XP_TOURNOI_VAINQUEUR, rng)
                c.execute("UPDATE tournois SET tours = ?, vainqueur_id = ? WHERE id = ?", (json.dumps(tours), encore[0], tournoi_id))
                c.execute(f"UPDATE inscriptions SET tournoi_id = ? WHERE date = ? AND brute_id IN ({','.join('?' * len(groupe))})",
                          (tournoi_id, date, *groupe))


def tournoi(base, brute_id):
    """Le dernier tournoi disputé par la brute : le tableau, tour par tour."""
    ligne = base.un("SELECT t.* FROM inscriptions i JOIN tournois t ON t.id = i.tournoi_id WHERE i.brute_id = ? "
                    "ORDER BY t.id DESC LIMIT 1", (brute_id,))
    if not ligne:
        return None
    noms = {l["id"]: l["nom"] for l in base.tous(
        f"SELECT id, nom FROM brutes WHERE id IN ({','.join('?' * len(json.loads(ligne['participants'])))})",
        json.loads(ligne["participants"]))}
    tours = []
    for manche in json.loads(ligne["tours"]):
        combats = []
        for combat_id in manche:
            l = base.un("SELECT attaquant_id, defenseur_id, gagnant_id FROM combats WHERE id = ?", (combat_id,))
            combats.append({"id": combat_id, "a": noms.get(l["attaquant_id"]), "b": noms.get(l["defenseur_id"]),
                            "gagnant": noms.get(l["gagnant_id"])})
        tours.append(combats)
    return {"date": ligne["date"], "tours": tours, "vainqueur": noms.get(ligne["vainqueur_id"])}


# --- Présentation -------------------------------------------------------------------------------------------------

def resume(base, brute, public=True, jour=None):
    fiche = brute["fiche"]
    maitre = base.un("SELECT nom FROM brutes WHERE id = ?", (brute["maitre_id"],)) if brute["maitre_id"] else None
    eleves = base.tous("SELECT nom, niveau FROM brutes WHERE maitre_id = ? ORDER BY niveau DESC, nom LIMIT 50", (brute["id"],))
    donnees = {
        "nom": brute["nom"], "niveau": brute["niveau"], "xp": brute["xp"], "seuil": R.seuil_xp(brute["niveau"]),
        "victoires": brute["victoires"], "defaites": brute["defaites"], "apparence": brute["apparence"],
        "pv": R.pv_max(fiche), "caracs": {c: fiche[c] for c in R.CARACS}, "armes": fiche["armes"],
        "competences": fiche["competences"], "animaux": fiche["animaux"], "bot": bool(brute["bot"]),
        "maitre": maitre["nom"] if maitre else None, "eleves": eleves, "historique": historique(base, brute["id"]),
    }
    if not public:
        donnees["combats_restants"] = combats_restants(brute, jour)
        donnees["choix"] = [{"libelle": R.libelle(o), **o} for o in brute["choix"]] if brute["choix"] else None
        donnees["inscrit_tournoi"] = bool(base.un("SELECT 1 FROM inscriptions WHERE brute_id = ? AND date = ?", (brute["id"], jour)))
        donnees["tournoi"] = tournoi(base, brute["id"])
    return donnees


def classement(base, limite=50):
    return base.tous("SELECT nom, niveau, xp, victoires, defaites, apparence FROM brutes WHERE bot = 0 "
                     "ORDER BY niveau DESC, xp DESC, victoires DESC, id LIMIT ?", (limite,))
