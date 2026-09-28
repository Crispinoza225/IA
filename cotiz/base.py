"""La base de données (SQLite) de Cotiz et les comptes."""

import datetime
import os
import sqlite3
import threading

from redigo.securite import empreinte_jeton, nouveau_jeton

SCHEMA = """
CREATE TABLE IF NOT EXISTS utilisateurs (
    id INTEGER PRIMARY KEY, telephone TEXT NOT NULL UNIQUE, nom TEXT NOT NULL, hash TEXT NOT NULL,
    formule_jusqua TEXT, cree_le TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
    empreinte TEXT PRIMARY KEY, utilisateur_id INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    expire_le TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS groupes (
    id INTEGER PRIMARY KEY, nom TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', devise TEXT NOT NULL,
    montant INTEGER NOT NULL, frequence TEXT NOT NULL, date_debut TEXT NOT NULL, mode_ordre TEXT NOT NULL,
    penalite INTEGER NOT NULL DEFAULT 0, jours_grace INTEGER NOT NULL DEFAULT 0, statut TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE, createur_id INTEGER NOT NULL REFERENCES utilisateurs(id), cree_le TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS membres (
    id INTEGER PRIMARY KEY, groupe_id INTEGER NOT NULL REFERENCES groupes(id) ON DELETE CASCADE,
    utilisateur_id INTEGER REFERENCES utilisateurs(id) ON DELETE SET NULL, nom TEXT NOT NULL, telephone TEXT NOT NULL,
    role TEXT NOT NULL, mains INTEGER NOT NULL DEFAULT 1, rang INTEGER NOT NULL, rejoint_le TEXT NOT NULL,
    UNIQUE (groupe_id, telephone));
CREATE TABLE IF NOT EXISTS tours (
    id INTEGER PRIMARY KEY, groupe_id INTEGER NOT NULL REFERENCES groupes(id) ON DELETE CASCADE,
    numero INTEGER NOT NULL, echeance TEXT NOT NULL, beneficiaire_id INTEGER NOT NULL REFERENCES membres(id),
    statut TEXT NOT NULL DEFAULT 'a_venir', verse_le TEXT, montant_verse INTEGER, UNIQUE (groupe_id, numero));
CREATE TABLE IF NOT EXISTS cotisations (
    id INTEGER PRIMARY KEY, groupe_id INTEGER NOT NULL REFERENCES groupes(id) ON DELETE CASCADE,
    tour_id INTEGER NOT NULL REFERENCES tours(id) ON DELETE CASCADE,
    membre_id INTEGER NOT NULL REFERENCES membres(id) ON DELETE CASCADE, montant INTEGER NOT NULL,
    moyen TEXT NOT NULL, reference TEXT NOT NULL DEFAULT '', statut TEXT NOT NULL, penalite INTEGER NOT NULL DEFAULT 0,
    en_retard INTEGER NOT NULL DEFAULT 0, declare_le TEXT NOT NULL, confirme_le TEXT, confirme_par TEXT);
CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY, groupe_id INTEGER NOT NULL REFERENCES groupes(id) ON DELETE CASCADE,
    date TEXT NOT NULL, auteur TEXT NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL,
    precedente TEXT NOT NULL, empreinte TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS paiements (
    id INTEGER PRIMARY KEY, utilisateur_id INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    fournisseur TEXT NOT NULL, reference TEXT NOT NULL UNIQUE, montant INTEGER NOT NULL, cree_le TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS membres_utilisateur ON membres(utilisateur_id);
CREATE INDEX IF NOT EXISTS membres_telephone ON membres(telephone);
CREATE INDEX IF NOT EXISTS cotisations_tour ON cotisations(tour_id);
CREATE INDEX IF NOT EXISTS journal_groupe ON journal(groupe_id);
"""

DUREE_SESSION = datetime.timedelta(days=60)


def maintenant():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def iso(date):
    return date.isoformat()


class Introuvable(Exception):
    pass


class Interdit(Exception):
    pass


class Base:
    """Une connexion SQLite par fil d'exécution (ou une seule, partagée, pour une base en mémoire)."""

    def __init__(self, chemin):
        self.chemin = chemin
        self.local = threading.local()
        self.partagee = None
        self.verrou = threading.RLock()
        if chemin == ":memory:":
            self.partagee = sqlite3.connect(chemin, check_same_thread=False)
        else:
            os.makedirs(os.path.dirname(os.path.abspath(chemin)), exist_ok=True)
        with self.transaction() as c:
            c.executescript(SCHEMA)

    def connexion(self):
        connexion = self.partagee or getattr(self.local, "connexion", None)
        if connexion is None:
            connexion = sqlite3.connect(self.chemin, timeout=10)
            connexion.execute("PRAGMA journal_mode=WAL")
            self.local.connexion = connexion
        connexion.row_factory = sqlite3.Row
        connexion.execute("PRAGMA foreign_keys=ON")
        return connexion

    class _Transaction:
        def __init__(self, base):
            self.base = base

        def __enter__(self):
            if self.base.partagee is not None:
                self.base.verrou.acquire()
            self.connexion = self.base.connexion()
            self.connexion.execute("BEGIN IMMEDIATE")  # une écriture à la fois : le journal reste une chaîne
            return self.connexion

        def __exit__(self, type_erreur, *args):
            try:
                if type_erreur is None:
                    self.connexion.commit()
                else:
                    self.connexion.rollback()
            finally:
                if self.base.partagee is not None:
                    self.base.verrou.release()

    def transaction(self):
        return Base._Transaction(self)

    def un(self, requete, parametres=()):
        with self.transaction() as c:
            ligne = c.execute(requete, parametres).fetchone()
            return dict(ligne) if ligne else None

    def tous(self, requete, parametres=()):
        with self.transaction() as c:
            return [dict(l) for l in c.execute(requete, parametres).fetchall()]

    def modifier(self, requete, parametres=()):
        with self.transaction() as c:
            curseur = c.execute(requete, parametres)
            return curseur.lastrowid, curseur.rowcount

    # --- Comptes ----------------------------------------------------------------------------------------

    def creer_utilisateur(self, telephone, nom, empreinte_mot_de_passe):
        identifiant, _ = self.modifier("INSERT INTO utilisateurs (telephone, nom, hash, cree_le) VALUES (?, ?, ?, ?)",
                                       (telephone, nom, empreinte_mot_de_passe, iso(maintenant())))
        # Si des organisateurs l'avaient déjà ajouté à leurs tontines avec ce numéro, on relie ces places au compte.
        self.modifier("UPDATE membres SET utilisateur_id = ? WHERE telephone = ? AND utilisateur_id IS NULL",
                      (identifiant, telephone))
        return identifiant

    def utilisateur(self, identifiant):
        return self.un("SELECT * FROM utilisateurs WHERE id = ?", (identifiant,))

    def utilisateur_par_telephone(self, telephone):
        return self.un("SELECT * FROM utilisateurs WHERE telephone = ?", (telephone,))

    def changer_mot_de_passe(self, identifiant, empreinte_mot_de_passe):
        self.modifier("UPDATE utilisateurs SET hash = ? WHERE id = ?", (empreinte_mot_de_passe, identifiant))
        self.modifier("DELETE FROM sessions WHERE utilisateur_id = ?", (identifiant,))

    def ouvrir_session(self, utilisateur_id):
        jeton = nouveau_jeton()
        self.modifier("DELETE FROM sessions WHERE expire_le < ?", (iso(maintenant()),))
        self.modifier("INSERT INTO sessions VALUES (?, ?, ?)",
                      (empreinte_jeton(jeton), utilisateur_id, iso(maintenant() + DUREE_SESSION)))
        return jeton

    def utilisateur_de_session(self, jeton):
        if not jeton:
            return None
        return self.un("SELECT u.* FROM sessions s JOIN utilisateurs u ON u.id = s.utilisateur_id "
                       "WHERE s.empreinte = ? AND s.expire_le > ?", (empreinte_jeton(jeton), iso(maintenant())))

    def fermer_session(self, jeton):
        self.modifier("DELETE FROM sessions WHERE empreinte = ?", (empreinte_jeton(jeton or ""),))

    def activer_formule(self, utilisateur_id, fournisseur, reference, montant, jours):
        """Ajoute `jours` jours de formule Organisateur. Sans effet si ce paiement a déjà été compté."""
        with self.transaction() as c:
            if c.execute("SELECT 1 FROM paiements WHERE reference = ?", (reference,)).fetchone():
                return False
            ligne = c.execute("SELECT formule_jusqua FROM utilisateurs WHERE id = ?", (utilisateur_id,)).fetchone()
            if not ligne:
                return False
            depart = maintenant()
            if ligne["formule_jusqua"] and ligne["formule_jusqua"] > iso(depart):
                depart = datetime.datetime.fromisoformat(ligne["formule_jusqua"])
            c.execute("UPDATE utilisateurs SET formule_jusqua = ? WHERE id = ?",
                      (iso(depart + datetime.timedelta(days=jours)), utilisateur_id))
            c.execute("INSERT INTO paiements (utilisateur_id, fournisseur, reference, montant, cree_le) VALUES (?, ?, ?, ?, ?)",
                      (utilisateur_id, fournisseur, reference, montant, iso(maintenant())))
            return True
