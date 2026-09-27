"""Mots de passe, jetons et limitation des tentatives."""

import hashlib
import hmac
import secrets
import threading
import time

# scrypt : une fonction de hachage volontairement lente et gourmande en mémoire, pour qu'un mot de passe
# volé sous forme hachée coûte très cher à retrouver par essais successifs.
N, R, P = 2 ** 14, 8, 1


def hacher_mot_de_passe(mot_de_passe):
    sel = secrets.token_bytes(16)
    empreinte = hashlib.scrypt(mot_de_passe.encode("utf-8"), salt=sel, n=N, r=R, p=P, dklen=32)
    return f"scrypt${N}${R}${P}${sel.hex()}${empreinte.hex()}"


def verifier_mot_de_passe(mot_de_passe, stocke):
    try:
        _, n, r, p, sel, empreinte = stocke.split("$")
        calcule = hashlib.scrypt(mot_de_passe.encode("utf-8"), salt=bytes.fromhex(sel), n=int(n), r=int(r),
                                 p=int(p), dklen=32)
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(calcule.hex(), empreinte)


def nouveau_jeton():
    return secrets.token_urlsafe(32)


def empreinte_jeton(jeton):
    """Les jetons de session sont gardés hachés : une fuite de la base ne permet pas de se connecter."""
    return hashlib.sha256(jeton.encode("utf-8")).hexdigest()


def mot_de_passe_acceptable(mot_de_passe):
    if len(mot_de_passe) < 8:
        return "Le mot de passe doit contenir au moins 8 caractères."
    if len(mot_de_passe) > 200:
        return "Le mot de passe est trop long."
    return None


class Limiteur:
    """Au plus `maximum` tentatives par `fenetre` secondes pour une même clé (adresse IP, e-mail…)."""

    def __init__(self, maximum, fenetre):
        self.maximum, self.fenetre = maximum, fenetre
        self.tentatives = {}
        self.verrou = threading.Lock()

    def autorise(self, cle, maintenant=None):
        maintenant = time.monotonic() if maintenant is None else maintenant
        with self.verrou:
            recentes = [t for t in self.tentatives.get(cle, []) if maintenant - t < self.fenetre]
            if len(recentes) >= self.maximum:
                self.tentatives[cle] = recentes
                return False
            recentes.append(maintenant)
            self.tentatives[cle] = recentes
            if len(self.tentatives) > 10000:  # ménage : on oublie les clés sans tentative récente
                self.tentatives = {c: t for c, t in self.tentatives.items() if t and maintenant - t[-1] < self.fenetre}
            return True
