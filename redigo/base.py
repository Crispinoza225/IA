"""La base de données (SQLite) : comptes, mémoires, versions, références, commentaires, partages, licences."""

import datetime
import json
import os
import sqlite3
import threading

from .securite import empreinte_jeton, nouveau_jeton

SCHEMA = """
CREATE TABLE IF NOT EXISTS utilisateurs (
    id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, nom TEXT NOT NULL DEFAULT '', hash TEXT NOT NULL,
    pass_jusqua TEXT, cree_le TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
    empreinte TEXT PRIMARY KEY, utilisateur_id INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    expire_le TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reinitialisations (
    empreinte TEXT PRIMARY KEY, utilisateur_id INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    expire_le TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS projets (
    id INTEGER PRIMARY KEY, utilisateur_id INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    titre TEXT NOT NULL, texte TEXT NOT NULL DEFAULT '', reglages TEXT NOT NULL DEFAULT '{}',
    style_biblio TEXT NOT NULL DEFAULT 'apa', biblio_toutes INTEGER NOT NULL DEFAULT 0,
    revision INTEGER NOT NULL DEFAULT 1, cree_le TEXT NOT NULL, modifie_le TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS versions (
    id INTEGER PRIMARY KEY, projet_id INTEGER NOT NULL REFERENCES projets(id) ON DELETE CASCADE,
    texte TEXT NOT NULL, reglages TEXT NOT NULL, libelle TEXT NOT NULL DEFAULT '', auto INTEGER NOT NULL DEFAULT 1,
    mots INTEGER NOT NULL DEFAULT 0, cree_le TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS biblio (
    id INTEGER PRIMARY KEY, projet_id INTEGER NOT NULL REFERENCES projets(id) ON DELETE CASCADE,
    cle TEXT NOT NULL, donnees TEXT NOT NULL, UNIQUE (projet_id, cle));
CREATE TABLE IF NOT EXISTS partages (
    id INTEGER PRIMARY KEY, projet_id INTEGER NOT NULL REFERENCES projets(id) ON DELETE CASCADE,
    jeton TEXT NOT NULL UNIQUE, nom TEXT NOT NULL DEFAULT '', cree_le TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS commentaires (
    id INTEGER PRIMARY KEY, projet_id INTEGER NOT NULL REFERENCES projets(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES commentaires(id) ON DELETE CASCADE, auteur TEXT NOT NULL,
    role TEXT NOT NULL, extrait TEXT NOT NULL DEFAULT '', texte TEXT NOT NULL, resolu INTEGER NOT NULL DEFAULT 0,
    lu INTEGER NOT NULL DEFAULT 0, cree_le TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS licences (
    id INTEGER PRIMARY KEY, domaine TEXT NOT NULL UNIQUE, universite TEXT NOT NULL, expire_le TEXT NOT NULL,
    reglages TEXT);
CREATE TABLE IF NOT EXISTS modeles (
    id INTEGER PRIMARY KEY, utilisateur_id INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    nom TEXT NOT NULL, reglages TEXT NOT NULL, cree_le TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS paiements (
    id INTEGER PRIMARY KEY, utilisateur_id INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    fournisseur TEXT NOT NULL, reference TEXT NOT NULL UNIQUE, montant INTEGER NOT NULL, cree_le TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS projets_utilisateur ON projets(utilisateur_id);
CREATE INDEX IF NOT EXISTS versions_projet ON versions(projet_id);
CREATE INDEX IF NOT EXISTS commentaires_projet ON commentaires(projet_id);
"""

DUREE_SESSION = datetime.timedelta(days=30)
DUREE_REINITIALISATION = datetime.timedelta(hours=1)
DUREE_PASS = datetime.timedelta(days=365)

# Les formules : ce que chacune permet.
FORMULES = {
    "gratuit": {"nom": "Gratuit", "projets": 1, "versions": 5, "mention": True},
    "pass": {"nom": "Pass Mémoire", "projets": 20, "versions": 200, "mention": False},
    "universite": {"nom": "Licence université", "projets": 20, "versions": 200, "mention": False},
}
PRIX_PASS = 990  # en centimes d'euro, payé une fois pour un an
MENTION = "Mis en forme avec Rédigo — version gratuite"


def maintenant():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def iso(date):
    return date.isoformat()


class Introuvable(Exception):
    pass


class Base:
    def __init__(self, chemin):
        self.chemin = chemin
        if chemin != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(chemin)), exist_ok=True)
        self.local = threading.local()
        self.partagee = None
        if chemin == ":memory:":  # une base en mémoire n'existe que dans sa connexion : on la partage
            self.partagee = sqlite3.connect(chemin, check_same_thread=False)
            self.verrou = threading.RLock()
        self.executer_script(SCHEMA)

    # --- Connexion ---------------------------------------------------------------------------------

    def connexion(self):
        if self.partagee is not None:
            connexion = self.partagee
        else:
            connexion = getattr(self.local, "connexion", None)
            if connexion is None:
                connexion = sqlite3.connect(self.chemin, timeout=10)
                connexion.execute("PRAGMA journal_mode=WAL")
                self.local.connexion = connexion
        connexion.row_factory = sqlite3.Row
        connexion.execute("PRAGMA foreign_keys=ON")
        return connexion

    def executer_script(self, script):
        with self.transaction() as c:
            c.executescript(script)

    class _Transaction:
        def __init__(self, base):
            self.base = base

        def __enter__(self):
            if self.base.partagee is not None:
                self.base.verrou.acquire()
            self.connexion = self.base.connexion()
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
            return [dict(ligne) for ligne in c.execute(requete, parametres).fetchall()]

    def modifier(self, requete, parametres=()):
        with self.transaction() as c:
            curseur = c.execute(requete, parametres)
            return curseur.lastrowid, curseur.rowcount

    # --- Comptes ---------------------------------------------------------------------------------------

    def creer_utilisateur(self, email, nom, empreinte_mot_de_passe):
        identifiant, _ = self.modifier("INSERT INTO utilisateurs (email, nom, hash, cree_le) VALUES (?, ?, ?, ?)",
                                       (email, nom, empreinte_mot_de_passe, iso(maintenant())))
        return identifiant

    def utilisateur_par_email(self, email):
        return self.un("SELECT * FROM utilisateurs WHERE email = ?", (email,))

    def utilisateur(self, identifiant):
        return self.un("SELECT * FROM utilisateurs WHERE id = ?", (identifiant,))

    def changer_mot_de_passe(self, identifiant, empreinte_mot_de_passe):
        self.modifier("UPDATE utilisateurs SET hash = ? WHERE id = ?", (empreinte_mot_de_passe, identifiant))
        self.modifier("DELETE FROM sessions WHERE utilisateur_id = ?", (identifiant,))  # déconnecte partout

    def supprimer_utilisateur(self, identifiant):
        self.modifier("DELETE FROM utilisateurs WHERE id = ?", (identifiant,))

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

    def demander_reinitialisation(self, utilisateur_id):
        jeton = nouveau_jeton()
        self.modifier("DELETE FROM reinitialisations WHERE utilisateur_id = ? OR expire_le < ?",
                      (utilisateur_id, iso(maintenant())))
        self.modifier("INSERT INTO reinitialisations VALUES (?, ?, ?)",
                      (empreinte_jeton(jeton), utilisateur_id, iso(maintenant() + DUREE_REINITIALISATION)))
        return jeton

    def utiliser_reinitialisation(self, jeton):
        """Renvoie l'identifiant de l'utilisateur si le jeton est valable, et l'efface (usage unique)."""
        ligne = self.un("SELECT * FROM reinitialisations WHERE empreinte = ? AND expire_le > ?",
                        (empreinte_jeton(jeton or ""), iso(maintenant())))
        if ligne:
            self.modifier("DELETE FROM reinitialisations WHERE empreinte = ?", (ligne["empreinte"],))
            return ligne["utilisateur_id"]
        return None

    # --- Formules et licences -------------------------------------------------------------------------------

    def licence_pour(self, email):
        """La licence de l'université dont l'e-mail fait partie (etu.univ-lyon.fr → univ-lyon.fr aussi)."""
        domaine = email.rsplit("@", 1)[-1].lower()
        parties = domaine.split(".")
        candidats = [".".join(parties[i:]) for i in range(len(parties) - 1)]
        if not candidats:
            return None
        marques = ",".join("?" * len(candidats))
        return self.un(f"SELECT * FROM licences WHERE domaine IN ({marques}) AND expire_le >= ? "
                       "ORDER BY length(domaine) DESC", (*candidats, maintenant().date().isoformat()))

    def formule(self, utilisateur):
        """(code de la formule, date de fin ou None, licence ou None)."""
        licence = self.licence_pour(utilisateur["email"])
        if licence:
            return "universite", licence["expire_le"], licence
        fin = utilisateur.get("pass_jusqua")
        if fin and fin >= iso(maintenant()):
            return "pass", fin, None
        return "gratuit", None, None

    def activer_pass(self, utilisateur_id, fournisseur, reference, montant):
        """Active (ou prolonge) le Pass Mémoire. Sans effet si ce paiement a déjà été compté."""
        with self.transaction() as c:
            if c.execute("SELECT 1 FROM paiements WHERE reference = ?", (reference,)).fetchone():
                return False
            ligne = c.execute("SELECT pass_jusqua FROM utilisateurs WHERE id = ?", (utilisateur_id,)).fetchone()
            if not ligne:
                return False
            depart = maintenant()
            if ligne["pass_jusqua"] and ligne["pass_jusqua"] > iso(depart):
                depart = datetime.datetime.fromisoformat(ligne["pass_jusqua"])
            c.execute("UPDATE utilisateurs SET pass_jusqua = ? WHERE id = ?", (iso(depart + DUREE_PASS), utilisateur_id))
            c.execute("INSERT INTO paiements (utilisateur_id, fournisseur, reference, montant, cree_le) "
                      "VALUES (?, ?, ?, ?, ?)", (utilisateur_id, fournisseur, reference, montant, iso(maintenant())))
            return True

    def ajouter_licence(self, domaine, universite, expire_le, reglages=None):
        self.modifier("INSERT INTO licences (domaine, universite, expire_le, reglages) VALUES (?, ?, ?, ?) "
                      "ON CONFLICT(domaine) DO UPDATE SET universite = excluded.universite, "
                      "expire_le = excluded.expire_le, reglages = COALESCE(excluded.reglages, licences.reglages)",
                      (domaine.lower().lstrip("@"), universite, expire_le,
                       json.dumps(reglages, ensure_ascii=False) if reglages else None))

    def licences(self):
        return self.tous("SELECT * FROM licences ORDER BY universite")

    # --- Mémoires ------------------------------------------------------------------------------------------

    def projets(self, utilisateur_id):
        return self.tous("SELECT p.id, p.titre, p.modifie_le, p.cree_le, length(p.texte) AS taille, "
                         "(SELECT count(*) FROM commentaires c WHERE c.projet_id = p.id AND c.lu = 0 "
                         " AND c.role = 'directeur') AS nouveaux_commentaires "
                         "FROM projets p WHERE utilisateur_id = ? ORDER BY modifie_le DESC", (utilisateur_id,))

    def nombre_de_projets(self, utilisateur_id):
        return self.un("SELECT count(*) AS n FROM projets WHERE utilisateur_id = ?", (utilisateur_id,))["n"]

    def creer_projet(self, utilisateur_id, titre, texte, reglages):
        date = iso(maintenant())
        identifiant, _ = self.modifier(
            "INSERT INTO projets (utilisateur_id, titre, texte, reglages, cree_le, modifie_le) VALUES (?, ?, ?, ?, ?, ?)",
            (utilisateur_id, titre, texte, json.dumps(reglages, ensure_ascii=False), date, date))
        return identifiant

    def projet(self, projet_id, utilisateur_id=None):
        """Le mémoire, seulement s'il appartient à cet utilisateur (quand il est précisé)."""
        projet = self.un("SELECT * FROM projets WHERE id = ?", (projet_id,))
        if not projet or (utilisateur_id is not None and projet["utilisateur_id"] != utilisateur_id):
            raise Introuvable("Ce mémoire n'existe pas.")
        projet["reglages"] = json.loads(projet["reglages"])
        return projet

    def enregistrer_projet(self, projet_id, revision, champs):
        """Enregistre si personne n'a modifié le mémoire entre-temps (sinon renvoie None : conflit)."""
        champs = dict(champs)
        if "reglages" in champs:
            champs["reglages"] = json.dumps(champs["reglages"], ensure_ascii=False)
        colonnes = ", ".join(f"{nom} = ?" for nom in champs)
        with self.transaction() as c:
            curseur = c.execute(f"UPDATE projets SET {colonnes}, revision = revision + 1, modifie_le = ? "
                                "WHERE id = ? AND revision = ?",
                                (*champs.values(), iso(maintenant()), projet_id, revision))
            return revision + 1 if curseur.rowcount else None

    def supprimer_projet(self, projet_id):
        self.modifier("DELETE FROM projets WHERE id = ?", (projet_id,))

    # --- Versions -------------------------------------------------------------------------------------------

    def versions(self, projet_id):
        return self.tous("SELECT id, libelle, auto, mots, cree_le FROM versions WHERE projet_id = ? "
                         "ORDER BY id DESC", (projet_id,))

    def derniere_version(self, projet_id):
        return self.un("SELECT * FROM versions WHERE projet_id = ? ORDER BY id DESC LIMIT 1", (projet_id,))

    def creer_version(self, projet_id, texte, reglages, libelle, auto, mots, garder):
        identifiant, _ = self.modifier(
            "INSERT INTO versions (projet_id, texte, reglages, libelle, auto, mots, cree_le) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (projet_id, texte, json.dumps(reglages, ensure_ascii=False), libelle, int(auto), mots, iso(maintenant())))
        # On ne garde que les `garder` versions automatiques les plus récentes ; les versions nommées restent.
        self.modifier("DELETE FROM versions WHERE projet_id = ? AND auto = 1 AND id NOT IN "
                      "(SELECT id FROM versions WHERE projet_id = ? AND auto = 1 ORDER BY id DESC LIMIT ?)",
                      (projet_id, projet_id, garder))
        return identifiant

    def version(self, projet_id, version_id):
        version = self.un("SELECT * FROM versions WHERE id = ? AND projet_id = ?", (version_id, projet_id))
        if not version:
            raise Introuvable("Cette version n'existe pas.")
        version["reglages"] = json.loads(version["reglages"])
        return version

    # --- Bibliographie ----------------------------------------------------------------------------------

    def references(self, projet_id):
        return [dict(json.loads(l["donnees"]), id=l["id"])
                for l in self.tous("SELECT * FROM biblio WHERE projet_id = ? ORDER BY cle", (projet_id,))]

    def enregistrer_reference(self, projet_id, reference, reference_id=None):
        donnees = json.dumps({k: v for k, v in reference.items() if k != "id"}, ensure_ascii=False)
        try:
            if reference_id:
                _, n = self.modifier("UPDATE biblio SET cle = ?, donnees = ? WHERE id = ? AND projet_id = ?",
                                     (reference["cle"], donnees, reference_id, projet_id))
                if not n:
                    raise Introuvable("Cette référence n'existe pas.")
                return reference_id
            identifiant, _ = self.modifier("INSERT INTO biblio (projet_id, cle, donnees) VALUES (?, ?, ?)",
                                           (projet_id, reference["cle"], donnees))
            return identifiant
        except sqlite3.IntegrityError:
            raise ValueError(f"La clé « {reference['cle']} » est déjà utilisée par une autre référence.")

    def supprimer_reference(self, projet_id, reference_id):
        self.modifier("DELETE FROM biblio WHERE id = ? AND projet_id = ?", (reference_id, projet_id))

    # --- Partages et commentaires -------------------------------------------------------------------------

    def partages(self, projet_id):
        return self.tous("SELECT id, jeton, nom, cree_le FROM partages WHERE projet_id = ? ORDER BY id", (projet_id,))

    def creer_partage(self, projet_id, nom):
        jeton = nouveau_jeton()
        self.modifier("INSERT INTO partages (projet_id, jeton, nom, cree_le) VALUES (?, ?, ?, ?)",
                      (projet_id, jeton, nom, iso(maintenant())))
        return jeton

    def supprimer_partage(self, projet_id, partage_id):
        self.modifier("DELETE FROM partages WHERE id = ? AND projet_id = ?", (partage_id, projet_id))

    def partage(self, jeton):
        partage = self.un("SELECT * FROM partages WHERE jeton = ?", (jeton or "",))
        if not partage:
            raise Introuvable("Ce lien de partage n'existe pas ou a été désactivé.")
        return partage

    def commentaires(self, projet_id):
        return self.tous("SELECT * FROM commentaires WHERE projet_id = ? ORDER BY id", (projet_id,))

    def ajouter_commentaire(self, projet_id, auteur, role, texte, extrait="", parent_id=None):
        if parent_id is not None and not self.un("SELECT 1 FROM commentaires WHERE id = ? AND projet_id = ?",
                                                 (parent_id, projet_id)):
            raise Introuvable("Ce commentaire n'existe pas.")
        identifiant, _ = self.modifier(
            "INSERT INTO commentaires (projet_id, parent_id, auteur, role, extrait, texte, lu, cree_le) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (projet_id, parent_id, auteur, role, extrait, texte, int(role == "etudiant"), iso(maintenant())))
        if parent_id is not None:  # une nouvelle réponse rouvre la discussion
            self.modifier("UPDATE commentaires SET resolu = 0 WHERE id = ?", (parent_id,))
        return identifiant

    def marquer_commentaires_lus(self, projet_id):
        self.modifier("UPDATE commentaires SET lu = 1 WHERE projet_id = ?", (projet_id,))

    def resoudre_commentaire(self, projet_id, commentaire_id, resolu):
        _, n = self.modifier("UPDATE commentaires SET resolu = ? WHERE id = ? AND projet_id = ? AND parent_id IS NULL",
                             (int(resolu), commentaire_id, projet_id))
        if not n:
            raise Introuvable("Ce commentaire n'existe pas.")

    # --- Modèles personnels ---------------------------------------------------------------------------------

    def modeles(self, utilisateur_id):
        return [dict(m, reglages=json.loads(m["reglages"]))
                for m in self.tous("SELECT id, nom, reglages FROM modeles WHERE utilisateur_id = ? ORDER BY nom",
                                   (utilisateur_id,))]

    def creer_modele(self, utilisateur_id, nom, reglages):
        identifiant, _ = self.modifier("INSERT INTO modeles (utilisateur_id, nom, reglages, cree_le) VALUES (?, ?, ?, ?)",
                                       (utilisateur_id, nom, json.dumps(reglages, ensure_ascii=False), iso(maintenant())))
        return identifiant

    def supprimer_modele(self, utilisateur_id, modele_id):
        self.modifier("DELETE FROM modeles WHERE id = ? AND utilisateur_id = ?", (modele_id, utilisateur_id))
