"""La simulation d'un combat : le serveur calcule tout, le navigateur rejoue la liste des événements.

Chaque combattant (une brute ou un animal) a une horloge : le prochain à agir est celui dont l'horloge est la plus
en retard, et chaque action la fait avancer selon sa rapidité et le poids de son arme. Le combat s'arrête dès qu'une
des deux brutes est au tapis. Le tirage est déterminé par une graine : le même combat se rejoue à l'identique.
"""

import random

from .regles import ANIMAUX, ARMES, DEGATS_MAINS_NUES, pv_max

ACTIONS_MAX = 600


def borner(valeur, bas, haut):
    return max(bas, min(haut, valeur))


class Combattant:
    def __init__(self, ident, equipe, nom, pv, force, agilite, rapidite, competences=(), armes=(), animal=None,
                 apparence=None, maitre=None):
        self.id, self.equipe, self.nom = ident, equipe, nom
        self.pv = self.pv_max = pv
        self.force, self.agilite, self.rapidite = force, agilite, rapidite
        self.competences = set(competences)
        self.reserve = list(armes)   # armes pas encore sorties
        self.arme = None             # arme en main
        self.animal = animal         # clé de ANIMAUX, ou None pour une brute
        self.apparence, self.maitre = apparence, maitre
        self.horloge = 0.0
        self.utilise = set()         # compétences à usage unique déjà utilisées

    @property
    def vivant(self):
        return self.pv > 0

    def a(self, competence):
        return competence in self.competences

    def stat_arme(self, cle):
        if self.animal:
            return ANIMAUX[self.animal].get(cle, 0)
        return ARMES[self.arme].get(cle, 0) if self.arme else 0

    def tempo(self):
        base = ARMES[self.arme]["tempo"] if self.arme else 1.0
        return base * 12 / (10 + self.rapidite)

    def public(self):
        return {"id": self.id, "equipe": self.equipe, "nom": self.nom, "pv": self.pv, "pv_max": self.pv_max,
                "animal": self.animal, "apparence": self.apparence, "maitre": self.maitre,
                "bouclier": self.a("bouclier")}


def equipe_depuis(fiche, nom, apparence, equipe, identifiants):
    """Une brute et ses animaux, prêts à combattre."""
    force, agilite, rapidite = fiche["force"], fiche["agilite"], fiche["rapidite"]
    competences = fiche["competences"]
    if "force_herculeenne" in competences:
        force *= 1.5
    if "agilite_feline" in competences:
        agilite *= 1.5
    if "vitesse_eclair" in competences:
        rapidite *= 1.5
    brute = Combattant(next(identifiants), equipe, nom, pv_max(fiche), force, agilite, rapidite, competences,
                       fiche["armes"], apparence=apparence)
    membres = [brute]
    for cle in fiche["animaux"]:
        a = ANIMAUX[cle]
        pv = int(a["pv"] * 1.5) if "ami_des_betes" in competences else a["pv"]
        membres.append(Combattant(next(identifiants), equipe, a["nom"], pv, a["degats"], a["agilite"], a["rapidite"],
                                  animal=cle, maitre=brute.id))
    return membres


class Combat:
    def __init__(self, equipe_a, equipe_b, graine):
        self.rng = random.Random(graine)
        self.combattants = equipe_a + equipe_b
        self.brutes = [equipe_a[0], equipe_b[0]]
        self.evenements = [{"t": "debut", "combattants": [c.public() for c in self.combattants]}]
        for c in self.combattants:
            c.horloge = 0.0 if c.a("coup_d_avance") else self.rng.uniform(0.1, 1.0) * c.tempo()

    def noter(self, **evenement):
        self.evenements.append(evenement)

    def fini(self):
        return not all(b.vivant for b in self.brutes)

    def ennemis(self, c):
        return [e for e in self.combattants if e.equipe != c.equipe and e.vivant]

    def cible(self, c):
        ennemis = self.ennemis(c)
        return self.rng.choices(ennemis, weights=[1 if e.animal else 3 for e in ennemis])[0]

    # --- Le déroulé -----------------------------------------------------------------------------------------------

    def jouer(self):
        for _ in range(ACTIONS_MAX):
            actif = min((c for c in self.combattants if c.vivant), key=lambda c: (c.horloge, c.id))
            duree = self.agir(actif)
            if self.fini():
                break
            actif.horloge += duree * self.rng.uniform(0.9, 1.1)
        if self.fini():
            gagnant = 0 if self.brutes[0].vivant else 1
        else:  # combat interminable : on départage aux points de vie restants
            gagnant = 0 if self.brutes[0].pv / self.brutes[0].pv_max >= self.brutes[1].pv / self.brutes[1].pv_max else 1
        self.noter(t="fin", gagnant=gagnant)
        return gagnant

    def agir(self, c):
        if not c.animal:
            if c.a("second_souffle") and "second_souffle" not in c.utilise and c.pv < c.pv_max * 0.25:
                c.utilise.add("second_souffle")
                c.pv = min(c.pv_max, c.pv + c.pv_max // 3)
                self.noter(t="soin", id=c.id, pv=c.pv)
                return 0.6 * c.tempo()
            if c.a("cri_de_guerre") and "cri_de_guerre" not in c.utilise:
                c.utilise.add("cri_de_guerre")
                self.noter(t="cri", id=c.id)
                for e in self.ennemis(c):
                    e.horloge += 0.6
            if c.arme is None and c.reserve and self.rng.random() < 0.6:
                c.arme = c.reserve.pop(self.rng.randrange(len(c.reserve)))
                self.noter(t="arme", id=c.id, arme=c.arme)
                return 0.5 * c.tempo()
            if c.arme and (ARMES[c.arme].get("jet") or (c.a("lanceur") and c.reserve and self.rng.random() < 0.3)):
                return self.lancer(c)
        return self.attaquer(c)

    def lancer(self, c):
        cible, arme = self.cible(c), c.arme
        c.arme = None
        if self.rng.random() < self.chance_esquive(c, cible, bonus=ARMES[arme].get("precision", 0)):
            self.noter(t="lancer", id=c.id, cible=cible.id, arme=arme, touche=False)
        else:
            degats = round(self.degats(c, cible, arme) * 2)  # un lancer frappe fort, mais l'arme est perdue
            self.noter(t="lancer", id=c.id, cible=cible.id, arme=arme, touche=True)
            self.blesser(c, cible, degats)
        return ARMES[arme]["tempo"] * 12 / (10 + c.rapidite)

    def attaquer(self, c):
        tempo = c.tempo()
        cible = self.cible(c)
        self.noter(t="attaque", id=c.id, cible=cible.id)
        combo = borner(0.08 + c.rapidite * 0.01 + c.stat_arme("combo") + (0.2 if c.a("furie") else 0), 0, 0.6)
        for coup in range(5):
            touche = self.frapper(c, cible)
            if not c.vivant or not cible.vivant or self.fini():
                break
            chance_contre = cible.stat_arme("contre") + (0.2 if cible.a("riposte") else 0) + 0.03
            if touche is not None and not cible.animal and self.rng.random() < chance_contre:
                self.noter(t="contre", id=cible.id, cible=c.id)
                self.frapper(cible, c)
                break
            if coup == 4 or self.rng.random() >= combo:
                break
        if c.vivant:
            self.noter(t="retour", id=c.id)
        return tempo

    def chance_esquive(self, attaquant, cible, bonus=0.0):
        esquive = 0.06 + (cible.agilite - attaquant.agilite) * 0.015
        esquive += cible.stat_arme("esquive") + (0.2 if cible.a("reflexes") else 0) - bonus
        return borner(esquive, 0.02, 0.6)

    def frapper(self, c, cible):
        """Un coup : esquivé (None), paré (False) ou reçu (True)."""
        if self.rng.random() < self.chance_esquive(c, cible, c.stat_arme("precision")):
            self.noter(t="esquive", id=cible.id)
            return None
        if not cible.animal:
            parade = borner(cible.stat_arme("parade") + (0.2 if cible.a("bouclier") else 0), 0, 0.6)
            if self.rng.random() < parade:
                self.noter(t="parade", id=cible.id)
                return False
        self.blesser(c, cible, self.degats(c, cible, c.arme))
        if (c.a("desarmement") or c.stat_arme("desarme")) and cible.arme and cible.vivant:
            if self.rng.random() < 0.25 + c.stat_arme("desarme"):
                self.noter(t="desarme", id=cible.id, arme=cible.arme)
                cible.arme = None
        return True

    def degats(self, c, cible, arme):
        if c.animal:
            base = c.force
        elif arme:
            base = (ARMES[arme]["degats"] + c.force * 0.7) * (1.25 if c.a("maitre_d_armes") else 1)
        else:
            base = (DEGATS_MAINS_NUES + c.force * 0.7) * (2 if c.a("poings_d_acier") else 1)
        base *= self.rng.uniform(0.8, 1.2)
        if cible.a("cuir_epais"):
            base *= 0.85
        return max(1, round(base))

    def blesser(self, c, cible, degats):
        cible.pv -= degats
        if cible.pv <= 0 and cible.a("increvable") and "increvable" not in cible.utilise:
            cible.utilise.add("increvable")
            cible.pv = 1
            self.noter(t="coup", id=c.id, cible=cible.id, degats=degats, pv=cible.pv)
            self.noter(t="increvable", id=cible.id)
            return
        cible.pv = max(0, cible.pv)
        self.noter(t="coup", id=c.id, cible=cible.id, degats=degats, pv=cible.pv)
        if not cible.vivant:
            self.noter(t="ko", id=cible.id)


def simuler(brute_a, brute_b, graine):
    """brute_x : {"nom", "apparence", "fiche"}. Renvoie (gagnant 0 ou 1, liste des événements)."""
    identifiants = iter(range(1, 100))
    equipe_a = equipe_depuis(brute_a["fiche"], brute_a["nom"], brute_a["apparence"], 0, identifiants)
    equipe_b = equipe_depuis(brute_b["fiche"], brute_b["nom"], brute_b["apparence"], 1, identifiants)
    combat = Combat(equipe_a, equipe_b, graine)
    gagnant = combat.jouer()
    return gagnant, combat.evenements
