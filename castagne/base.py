"""La base de données (SQLite) de Castagne : les brutes (qui sont aussi les comptes), les combats, les tournois."""

import datetime
import json
import os
import sqlite3
import threading

from redigo.securite import empreinte_jeton, nouveau_jeton

SCHEMA = """
CREATE TABLE IF NOT EXISTS brutes (
    id INTEGER PRIMARY KEY, nom TEXT NOT NULL, cle TEXT NOT NULL UNIQUE, hash TEXT, bot INTEGER NOT NULL DEFAULT 0,
    apparence TEXT NOT NULL, fiche TEXT NOT NULL, niveau INTEGER NOT NULL DEFAULT 1, xp INTEGER NOT NULL DEFAULT 0,
    victoires INTEGER NOT NULL DEFAULT 0, defaites INTEGER NOT NULL DEFAULT 0,
    maitre_id INTEGER REFERENCES brutes(id) ON DELETE SET NULL, choix TEXT, jour TEXT, combats_jour INTEGER NOT NULL DEFAULT 0,
    cree_le TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
    empreinte TEXT PRIMARY KEY, brute_id INTEGER NOT NULL REFERENCES brutes(id) ON DELETE CASCADE, expire_le TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS combats (
    id INTEGER PRIMARY KEY, attaquant_id INTEGER NOT NULL REFERENCES brutes(id) ON DELETE CASCADE,
    defenseur_id INTEGER NOT NULL REFERENCES brutes(id) ON DELETE CASCADE, gagnant_id INTEGER NOT NULL,
    tournoi_id INTEGER, date TEXT NOT NULL, donnees TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tournois (
    id INTEGER PRIMARY KEY, date TEXT NOT NULL, participants TEXT NOT NULL, tours TEXT NOT NULL, vainqueur_id INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS inscriptions (
    brute_id INTEGER NOT NULL REFERENCES brutes(id) ON DELETE CASCADE, date TEXT NOT NULL,
    tournoi_id INTEGER REFERENCES tournois(id), PRIMARY KEY (brute_id, date));
CREATE INDEX IF NOT EXISTS brutes_niveau ON brutes(niveau);
CREATE INDEX IF NOT EXISTS brutes_maitre ON brutes(maitre_id);
CREATE INDEX IF NOT EXISTS combats_attaquant ON combats(attaquant_id);
CREATE INDEX IF NOT EXISTS combats_defenseur ON combats(defenseur_id);
"""

DUREE_SESSION = datetime.timedelta(days=90)


def maintenant():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def iso(date):
    return date.isoformat()


class Introuvable(Exception):
    pass


def brute_depuis_ligne(ligne):
    if ligne is None:
        return None
    brute = dict(ligne)
    brute["apparence"] = json.loads(brute["apparence"])
    brute["fiche"] = json.loads(brute["fiche"])
    brute["choix"] = json.loads(brute["choix"]) if brute["choix"] else None
    return brute


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
            self.connexion.execute("BEGIN IMMEDIATE")  # une écriture à la fois : pas deux combats avec le même crédit
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

    # --- Brutes et sessions -----------------------------------------------------------------------------------------

    def brute(self, identifiant, c=None):
        if c is None:
            with self.transaction() as c:
                return self.brute(identifiant, c)
        return brute_depuis_ligne(c.execute("SELECT * FROM brutes WHERE id = ?", (identifiant,)).fetchone())

    def brute_par_nom(self, nom, c=None):
        if c is None:
            with self.transaction() as c:
                return self.brute_par_nom(nom, c)
        return brute_depuis_ligne(c.execute("SELECT * FROM brutes WHERE cle = ?", (nom.strip().lower(),)).fetchone())

    def ouvrir_session(self, brute_id):
        jeton = nouveau_jeton()
        with self.transaction() as c:
            c.execute("DELETE FROM sessions WHERE expire_le < ?", (iso(maintenant()),))
            c.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                      (empreinte_jeton(jeton), brute_id, iso(maintenant() + DUREE_SESSION)))
        return jeton

    def brute_de_session(self, jeton):
        if not jeton:
            return None
        with self.transaction() as c:
            ligne = c.execute("SELECT b.* FROM sessions s JOIN brutes b ON b.id = s.brute_id "
                              "WHERE s.empreinte = ? AND s.expire_le > ?", (empreinte_jeton(jeton), iso(maintenant()))).fetchone()
            return brute_depuis_ligne(ligne)

    def fermer_session(self, jeton):
        with self.transaction() as c:
            c.execute("DELETE FROM sessions WHERE empreinte = ?", (empreinte_jeton(jeton or ""),))
