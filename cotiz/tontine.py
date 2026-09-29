"""Les règles de la tontine : membres, ordre des tours, cotisations, versements, pénalités, journal et fiabilité.

Chaque tour, chaque membre verse `montant × mains` ; le bénéficiaire du tour reçoit la cagnotte. Un membre qui
a plusieurs « mains » cotise plusieurs fois et reçoit la cagnotte autant de fois.
"""

import datetime
import hashlib
import json
import re
import secrets
import urllib.parse

from .base import Interdit, Introuvable, iso, maintenant
from .calendrier import DEVISES, FREQUENCES, date_francaise, echeance, formater

MODES_ORDRE = {"tirage": "Tirage au sort au démarrage", "inscription": "Ordre d'inscription",
               "manuel": "Ordre choisi par l'organisateur"}
MOYENS = {"especes": "Espèces", "mobile_money": "Mobile Money", "virement": "Virement", "en_ligne": "Paiement en ligne"}
MAINS_MAX = 5
MEMBRES_MAX = 100


def telephone_normalise(texte):
    """« +221 77 123 45 67 » → « +221771234567 ». Lève ValueError si ce n'est pas un numéro plausible."""
    propre = re.sub(r"[\s.\-()]", "", str(texte or ""))
    if propre.startswith("00"):
        propre = "+" + propre[2:]
    if not re.fullmatch(r"\+?\d{8,15}", propre):
        raise ValueError("Ce numéro de téléphone n'est pas valide (8 à 15 chiffres).")
    return propre


def aujourdhui():
    return datetime.date.today()


# --- Journal infalsifiable ------------------------------------------------------------------------------------
# Chaque entrée contient l'empreinte de la précédente : modifier ou effacer une ligne après coup casse la chaîne,
# et tout le monde peut le vérifier.

def _empreinte(precedente, date, auteur, action, details):
    contenu = json.dumps([precedente, date, auteur, action, details], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(contenu.encode("utf-8")).hexdigest()


def journaliser(c, groupe_id, auteur, action, details):
    ligne = c.execute("SELECT empreinte FROM journal WHERE groupe_id = ? ORDER BY id DESC LIMIT 1", (groupe_id,)).fetchone()
    precedente = ligne["empreinte"] if ligne else "0" * 64
    date = iso(maintenant())
    details = json.dumps(details, ensure_ascii=False, sort_keys=True)
    c.execute("INSERT INTO journal (groupe_id, date, auteur, action, details, precedente, empreinte) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (groupe_id, date, auteur, action, details, precedente, _empreinte(precedente, date, auteur, action, details)))


def verifier_journal(base, groupe_id):
    """Renvoie (True, nombre d'entrées) si la chaîne est intacte, sinon (False, numéro de la première entrée abîmée)."""
    precedente = "0" * 64
    lignes = base.tous("SELECT * FROM journal WHERE groupe_id = ? ORDER BY id", (groupe_id,))
    for rang, l in enumerate(lignes, start=1):
        if l["precedente"] != precedente or l["empreinte"] != _empreinte(precedente, l["date"], l["auteur"], l["action"], l["details"]):
            return False, rang
        precedente = l["empreinte"]
    return True, len(lignes)


# --- Groupes et membres ---------------------------------------------------------------------------------------

def creer_groupe(base, utilisateur, nom, devise, montant, frequence, date_debut, mode_ordre, penalite=0, jours_grace=0,
                 description=""):
    if devise not in DEVISES:
        raise ValueError("Monnaie inconnue.")
    if frequence not in FREQUENCES:
        raise ValueError("Fréquence inconnue.")
    if mode_ordre not in MODES_ORDRE:
        raise ValueError("Mode d'ordre inconnu.")
    if montant <= 0:
        raise ValueError("La cotisation doit être supérieure à zéro.")
    if penalite < 0 or not 0 <= jours_grace <= 30:
        raise ValueError("Pénalité ou délai de grâce invalide.")
    datetime.date.fromisoformat(date_debut)
    with base.transaction() as c:
        curseur = c.execute(
            "INSERT INTO groupes (nom, description, devise, montant, frequence, date_debut, mode_ordre, penalite, jours_grace, "
            "statut, code, createur_id, cree_le) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'brouillon', ?, ?, ?)",
            (nom, description, devise, montant, frequence, date_debut, mode_ordre, penalite, jours_grace,
             secrets.token_urlsafe(9), utilisateur["id"], iso(maintenant())))
        groupe_id = curseur.lastrowid
        c.execute("INSERT INTO membres (groupe_id, utilisateur_id, nom, telephone, role, mains, rang, rejoint_le) "
                  "VALUES (?, ?, ?, ?, 'organisateur', 1, 1, ?)",
                  (groupe_id, utilisateur["id"], utilisateur["nom"], utilisateur["telephone"], iso(maintenant())))
        journaliser(c, groupe_id, utilisateur["nom"], "creation", {
            "nom": nom, "cotisation": formater(montant, devise), "frequence": FREQUENCES[frequence],
            "debut": date_debut, "ordre": MODES_ORDRE[mode_ordre]})
    return groupe_id


def groupe(base, groupe_id):
    g = base.un("SELECT * FROM groupes WHERE id = ?", (groupe_id,))
    if not g:
        raise Introuvable("Cette tontine n'existe pas.")
    return g


def membre_de(base, groupe_id, utilisateur):
    """La place de l'utilisateur dans la tontine (ou Introuvable : on ne révèle pas qu'elle existe)."""
    m = base.un("SELECT * FROM membres WHERE groupe_id = ? AND utilisateur_id = ?", (groupe_id, utilisateur["id"]))
    if not m:
        raise Introuvable("Cette tontine n'existe pas.")
    return m


def exiger_organisateur(base, groupe_id, utilisateur):
    m = membre_de(base, groupe_id, utilisateur)
    if m["role"] != "organisateur":
        raise Interdit("Seul l'organisateur peut faire cela.")
    return m


def ajouter_membre(base, groupe_id, auteur, nom, telephone, mains=1, utilisateur_id=None):
    g = groupe(base, groupe_id)
    if g["statut"] != "brouillon":
        raise ValueError("La tontine a déjà commencé : on ne peut plus ajouter de membre.")
    if not 1 <= mains <= MAINS_MAX:
        raise ValueError(f"Un membre peut avoir de 1 à {MAINS_MAX} mains.")
    telephone = telephone_normalise(telephone)
    nom = nom.strip()[:80]
    if not nom:
        raise ValueError("Le nom est obligatoire.")
    with base.transaction() as c:
        nombre = c.execute("SELECT count(*) AS n FROM membres WHERE groupe_id = ?", (groupe_id,)).fetchone()["n"]
        if nombre >= MEMBRES_MAX:
            raise ValueError(f"{MEMBRES_MAX} membres au maximum par tontine.")
        if c.execute("SELECT 1 FROM membres WHERE groupe_id = ? AND telephone = ?", (groupe_id, telephone)).fetchone():
            raise ValueError("Ce numéro fait déjà partie de la tontine.")
        if utilisateur_id is None:
            compte = c.execute("SELECT id FROM utilisateurs WHERE telephone = ?", (telephone,)).fetchone()
            utilisateur_id = compte["id"] if compte else None
        rang = c.execute("SELECT coalesce(max(rang), 0) + 1 AS r FROM membres WHERE groupe_id = ?", (groupe_id,)).fetchone()["r"]
        curseur = c.execute("INSERT INTO membres (groupe_id, utilisateur_id, nom, telephone, role, mains, rang, rejoint_le) "
                            "VALUES (?, ?, ?, ?, 'membre', ?, ?, ?)",
                            (groupe_id, utilisateur_id, nom, telephone, mains, rang, iso(maintenant())))
        journaliser(c, groupe_id, auteur, "ajout_membre", {"membre": nom, "mains": mains})
        return curseur.lastrowid


def modifier_membre(base, groupe_id, membre_id, auteur, mains=None, rang=None):
    g = groupe(base, groupe_id)
    if g["statut"] != "brouillon":
        raise ValueError("La tontine a déjà commencé : les membres ne peuvent plus changer.")
    m = base.un("SELECT * FROM membres WHERE id = ? AND groupe_id = ?", (membre_id, groupe_id))
    if not m:
        raise Introuvable("Ce membre n'existe pas.")
    with base.transaction() as c:
        if mains is not None:
            if not 1 <= mains <= MAINS_MAX:
                raise ValueError(f"Un membre peut avoir de 1 à {MAINS_MAX} mains.")
            c.execute("UPDATE membres SET mains = ? WHERE id = ?", (mains, membre_id))
            journaliser(c, groupe_id, auteur, "mains", {"membre": m["nom"], "mains": mains})
        if rang is not None:  # échange de place avec le membre qui occupe ce rang
            autre = c.execute("SELECT id FROM membres WHERE groupe_id = ? AND rang = ?", (groupe_id, rang)).fetchone()
            if autre:
                c.execute("UPDATE membres SET rang = ? WHERE id = ?", (m["rang"], autre["id"]))
                c.execute("UPDATE membres SET rang = ? WHERE id = ?", (rang, membre_id))


def retirer_membre(base, groupe_id, membre_id, auteur):
    g = groupe(base, groupe_id)
    if g["statut"] != "brouillon":
        raise ValueError("La tontine a déjà commencé : un membre ne peut plus être retiré.")
    m = base.un("SELECT * FROM membres WHERE id = ? AND groupe_id = ?", (membre_id, groupe_id))
    if not m:
        raise Introuvable("Ce membre n'existe pas.")
    if m["role"] == "organisateur":
        raise ValueError("L'organisateur ne peut pas être retiré.")
    with base.transaction() as c:
        c.execute("DELETE FROM membres WHERE id = ?", (membre_id,))
        journaliser(c, groupe_id, auteur, "retrait_membre", {"membre": m["nom"]})


def rejoindre(base, code, utilisateur):
    """Rejoindre avec le lien d'invitation, ou retrouver la place que l'organisateur a créée pour ce numéro."""
    g = base.un("SELECT * FROM groupes WHERE code = ?", (code,))
    if not g:
        raise Introuvable("Ce lien d'invitation n'est pas valable.")
    deja = base.un("SELECT * FROM membres WHERE groupe_id = ? AND (utilisateur_id = ? OR telephone = ?)",
                   (g["id"], utilisateur["id"], utilisateur["telephone"]))
    if deja:
        if deja["utilisateur_id"] is None:
            base.modifier("UPDATE membres SET utilisateur_id = ? WHERE id = ?", (utilisateur["id"], deja["id"]))
        return g["id"]
    ajouter_membre(base, g["id"], utilisateur["nom"], utilisateur["nom"], utilisateur["telephone"], 1, utilisateur["id"])
    return g["id"]


# --- Démarrage et tours ---------------------------------------------------------------------------------------------

def demarrer(base, groupe_id, auteur):
    """Fixe l'ordre des bénéficiaires et crée le calendrier de tous les tours."""
    g = groupe(base, groupe_id)
    if g["statut"] != "brouillon":
        raise ValueError("Cette tontine a déjà commencé.")
    membres = base.tous("SELECT * FROM membres WHERE groupe_id = ? ORDER BY rang, id", (groupe_id,))
    places = [m for m in membres for _ in range(m["mains"])]  # une place par main
    if len(places) < 2:
        raise ValueError("Il faut au moins deux mains pour démarrer une tontine.")
    if g["mode_ordre"] == "tirage":
        secrets.SystemRandom().shuffle(places)
    debut = datetime.date.fromisoformat(g["date_debut"])
    with base.transaction() as c:
        for rang, m in enumerate(places):
            c.execute("INSERT INTO tours (groupe_id, numero, echeance, beneficiaire_id) VALUES (?, ?, ?, ?)",
                      (groupe_id, rang + 1, echeance(debut, g["frequence"], rang).isoformat(), m["id"]))
        c.execute("UPDATE groupes SET statut = 'en_cours' WHERE id = ?", (groupe_id,))
        journaliser(c, groupe_id, auteur, "demarrage", {
            "ordre": [f"Tour {i + 1} : {m['nom']}" for i, m in enumerate(places)],
            "mode": MODES_ORDRE[g["mode_ordre"]]})


def du_par_tour(g, membre):
    return g["montant"] * membre["mains"]


def limite_paiement(g, tour):
    return datetime.date.fromisoformat(tour["echeance"]) + datetime.timedelta(days=g["jours_grace"])


def etat_tour(base, g, tour, jour=None):
    """Pour chaque membre : ce qu'il doit, ce qu'il a versé et son statut (payé, à confirmer, à payer, en retard)."""
    jour = jour or aujourdhui()
    membres = base.tous("SELECT * FROM membres WHERE groupe_id = ? ORDER BY rang, id", (g["id"],))
    cotisations = base.tous("SELECT * FROM cotisations WHERE tour_id = ? ORDER BY id", (tour["id"],))
    lignes, collecte, attendu = [], 0, 0
    for m in membres:
        du = du_par_tour(g, m)
        attendu += du
        siennes = [c for c in cotisations if c["membre_id"] == m["id"]]
        confirme = sum(c["montant"] for c in siennes if c["statut"] == "confirmee")
        en_attente = [c for c in siennes if c["statut"] == "declaree"]
        collecte += min(confirme, du)
        if confirme >= du:
            statut = "paye"
        elif en_attente:
            statut = "a_confirmer"
        elif jour > limite_paiement(g, tour):
            statut = "en_retard"
        else:
            statut = "a_payer"
        lignes.append({"membre_id": m["id"], "nom": m["nom"], "telephone": m["telephone"], "du": du,
                       "verse": confirme, "statut": statut, "cotisations": siennes,
                       "penalites": sum(c["penalite"] for c in siennes if c["statut"] == "confirmee")})
    return {"lignes": lignes, "collecte": collecte, "attendu": attendu, "complet": collecte >= attendu}


def tour_courant(base, groupe_id):
    return base.un("SELECT * FROM tours WHERE groupe_id = ? AND statut = 'a_venir' ORDER BY numero LIMIT 1", (groupe_id,))


def tour(base, groupe_id, tour_id):
    t = base.un("SELECT * FROM tours WHERE id = ? AND groupe_id = ?", (tour_id, groupe_id))
    if not t:
        raise Introuvable("Ce tour n'existe pas.")
    return t


# --- Cotisations ----------------------------------------------------------------------------------------------------

def enregistrer_cotisation(base, groupe_id, tour_id, membre_id, auteur, montant, moyen, reference="", confirmee=False,
                           jour=None):
    """Un membre déclare avoir payé (à confirmer par l'organisateur), ou l'organisateur enregistre un paiement reçu."""
    g = groupe(base, groupe_id)
    t = tour(base, groupe_id, tour_id)
    if t["statut"] != "a_venir":
        raise ValueError("La cagnotte de ce tour a déjà été versée.")
    if moyen not in MOYENS:
        raise ValueError("Moyen de paiement inconnu.")
    if montant <= 0:
        raise ValueError("Le montant doit être supérieur à zéro.")
    m = base.un("SELECT * FROM membres WHERE id = ? AND groupe_id = ?", (membre_id, groupe_id))
    if not m:
        raise Introuvable("Ce membre n'existe pas.")
    jour = jour or aujourdhui()
    en_retard = jour > limite_paiement(g, t)
    penalite = g["penalite"] if (confirmee and en_retard) else 0
    with base.transaction() as c:
        curseur = c.execute(
            "INSERT INTO cotisations (groupe_id, tour_id, membre_id, montant, moyen, reference, statut, penalite, en_retard, "
            "declare_le, confirme_le, confirme_par) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (groupe_id, tour_id, membre_id, montant, moyen, reference[:100], "confirmee" if confirmee else "declaree",
             penalite, int(en_retard), jour.isoformat(), jour.isoformat() if confirmee else None,
             auteur if confirmee else None))
        journaliser(c, groupe_id, auteur, "paiement_recu" if confirmee else "paiement_declare", {
            "membre": m["nom"], "tour": t["numero"], "montant": formater(montant, g["devise"]), "moyen": MOYENS[moyen],
            "reference": reference[:100], "retard": en_retard,
            **({"penalite": formater(penalite, g["devise"])} if penalite else {})})
        return curseur.lastrowid


def decider_cotisation(base, groupe_id, cotisation_id, auteur, accepter, jour=None):
    """L'organisateur confirme (ou refuse) un paiement déclaré par un membre."""
    g = groupe(base, groupe_id)
    c_ = base.un("SELECT c.*, m.nom, t.numero, t.echeance, t.statut AS statut_tour FROM cotisations c "
                 "JOIN membres m ON m.id = c.membre_id JOIN tours t ON t.id = c.tour_id "
                 "WHERE c.id = ? AND c.groupe_id = ?", (cotisation_id, groupe_id))
    if not c_:
        raise Introuvable("Ce paiement n'existe pas.")
    if c_["statut"] != "declaree":
        raise ValueError("Ce paiement a déjà été traité.")
    jour = jour or aujourdhui()
    # Le retard se juge à la date de la déclaration : confirmer tard ne pénalise pas le membre.
    penalite = g["penalite"] if (accepter and c_["en_retard"]) else 0
    with base.transaction() as c:
        c.execute("UPDATE cotisations SET statut = ?, penalite = ?, confirme_le = ?, confirme_par = ? WHERE id = ?",
                  ("confirmee" if accepter else "refusee", penalite, jour.isoformat(), auteur, cotisation_id))
        journaliser(c, groupe_id, auteur, "paiement_confirme" if accepter else "paiement_refuse", {
            "membre": c_["nom"], "tour": c_["numero"], "montant": formater(c_["montant"], g["devise"]),
            **({"penalite": formater(penalite, g["devise"])} if penalite else {})})


def verser(base, groupe_id, tour_id, auteur, forcer=False, jour=None):
    """La cagnotte est remise au bénéficiaire : le tour est clos."""
    g = groupe(base, groupe_id)
    t = tour(base, groupe_id, tour_id)
    if t["statut"] != "a_venir":
        raise ValueError("Cette cagnotte a déjà été versée.")
    courant = tour_courant(base, groupe_id)
    if courant["id"] != t["id"]:
        raise ValueError("Les tours se versent dans l'ordre.")
    etat = etat_tour(base, g, t, jour)
    manquants = [l["nom"] for l in etat["lignes"] if l["statut"] != "paye"]
    if manquants and not forcer:
        raise ValueError("Tout le monde n'a pas encore payé : " + ", ".join(manquants) + ".")
    beneficiaire = base.un("SELECT nom FROM membres WHERE id = ?", (t["beneficiaire_id"],))
    jour = jour or aujourdhui()
    with base.transaction() as c:
        c.execute("UPDATE tours SET statut = 'verse', verse_le = ?, montant_verse = ? WHERE id = ?",
                  (jour.isoformat(), etat["collecte"], tour_id))
        reste = c.execute("SELECT count(*) AS n FROM tours WHERE groupe_id = ? AND statut = 'a_venir'", (groupe_id,)).fetchone()["n"]
        if not reste:
            c.execute("UPDATE groupes SET statut = 'termine' WHERE id = ?", (groupe_id,))
        journaliser(c, groupe_id, auteur, "versement", {
            "tour": t["numero"], "beneficiaire": beneficiaire["nom"], "montant": formater(etat["collecte"], g["devise"]),
            **({"impayes": manquants} if manquants else {})})
        if not reste:
            journaliser(c, groupe_id, auteur, "fin", {"message": "Tous les tours ont été versés."})


# --- Fiabilité, rappels, résumés ----------------------------------------------------------------------------------------

def fiabilite(base, telephone, jour=None):
    """Part des cotisations payées à temps par ce numéro, dans toutes ses tontines (None sans historique)."""
    jour = jour or aujourdhui()
    lignes = base.tous(
        "SELECT t.id AS tour_id, t.echeance, g.jours_grace, g.montant * m.mains AS du, m.id AS membre_id, "
        "(SELECT coalesce(sum(c.montant), 0) FROM cotisations c WHERE c.tour_id = t.id AND c.membre_id = m.id "
        " AND c.statut = 'confirmee' AND c.en_retard = 0) AS a_temps "
        "FROM membres m JOIN groupes g ON g.id = m.groupe_id JOIN tours t ON t.groupe_id = g.id "
        "WHERE m.telephone = ?", (telephone,))
    dus = [l for l in lignes if datetime.date.fromisoformat(l["echeance"]) + datetime.timedelta(days=l["jours_grace"]) < jour
           or l["a_temps"] >= l["du"]]
    if not dus:
        return None
    return round(100 * sum(l["a_temps"] >= l["du"] for l in dus) / len(dus))


def lien_whatsapp(telephone, message):
    numero = telephone.lstrip("+")
    return f"https://wa.me/{numero}?text={urllib.parse.quote(message)}"


def rappels(base, groupe_id, jour=None):
    """Les membres à relancer pour le tour en cours, avec un message prêt à envoyer par WhatsApp ou SMS."""
    g = groupe(base, groupe_id)
    t = tour_courant(base, groupe_id)
    if not t:
        return []
    etat = etat_tour(base, g, t, jour)
    beneficiaire = base.un("SELECT nom FROM membres WHERE id = ?", (t["beneficiaire_id"],))["nom"]
    resultat = []
    for l in etat["lignes"]:
        if l["statut"] not in ("a_payer", "en_retard"):
            continue
        reste = formater(l["du"] - l["verse"], g["devise"])
        if l["statut"] == "en_retard":
            message = (f"Bonjour {l['nom']}, ta cotisation de {reste} pour la tontine « {g['nom']} » (tour {t['numero']}) "
                       f"était attendue le {date_francaise(t['echeance'])}. Merci de régulariser rapidement : "
                       f"{beneficiaire} attend sa cagnotte.")
        else:
            message = (f"Bonjour {l['nom']}, petit rappel : ta cotisation de {reste} pour la tontine « {g['nom']} » "
                       f"(tour {t['numero']}, pour {beneficiaire}) est attendue le {date_francaise(t['echeance'])}. Merci !")
        resultat.append({**{k: l[k] for k in ("membre_id", "nom", "telephone", "statut")}, "message": message,
                         "whatsapp": lien_whatsapp(l["telephone"], message)})
    return resultat


def resume_pour(base, utilisateur, jour=None):
    """Le tableau de bord d'un utilisateur : ses tontines, ce qu'il doit bientôt, quand il reçoit."""
    jour = jour or aujourdhui()
    groupes = base.tous("SELECT g.*, m.id AS membre_id, m.role, m.mains FROM groupes g JOIN membres m ON m.groupe_id = g.id "
                        "WHERE m.utilisateur_id = ? ORDER BY g.statut = 'termine', g.cree_le DESC", (utilisateur["id"],))
    resultat = []
    for g in groupes:
        nombre = base.un("SELECT count(*) AS n, sum(mains) AS mains FROM membres WHERE groupe_id = ?", (g["id"],))
        entree = {"id": g["id"], "nom": g["nom"], "statut": g["statut"], "role": g["role"], "devise": g["devise"],
                  "cotisation": formater(g["montant"] * g["mains"], g["devise"]), "membres": nombre["n"],
                  "cagnotte": formater(g["montant"] * (nombre["mains"] or 0), g["devise"]),
                  "frequence": FREQUENCES[g["frequence"]]}
        t = tour_courant(base, g["id"]) if g["statut"] == "en_cours" else None
        if t:
            etat = etat_tour(base, g, t, jour)
            ma_ligne = next(l for l in etat["lignes"] if l["membre_id"] == g["membre_id"])
            entree.update(tour=t["numero"], echeance=t["echeance"], mon_statut=ma_ligne["statut"],
                          progression=round(100 * etat["collecte"] / etat["attendu"]) if etat["attendu"] else 0,
                          a_confirmer=sum(l["statut"] == "a_confirmer" for l in etat["lignes"]))
        mes_tours = base.tous("SELECT numero, echeance, statut FROM tours WHERE groupe_id = ? AND beneficiaire_id = ? "
                              "ORDER BY numero", (g["id"], g["membre_id"]))
        prochain = next((x for x in mes_tours if x["statut"] == "a_venir"), None)
        if prochain:
            entree["je_recois"] = {"tour": prochain["numero"], "date": prochain["echeance"]}
        resultat.append(entree)
    return resultat
