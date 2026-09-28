"""Neurone : un chatbot français propulsé par un réseau de neurones fait maison."""

import ast
import datetime
import json
import operator
import os
import random
import re

from .reseau import ReseauNeurones
from .texte import construire_vocabulaire, jetons, vectoriser

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_INTENTIONS = os.path.join(DOSSIER, "intentions.json")
FICHIER_APPRIS = os.path.join(DOSSIER, "appris.json")

SEUIL_CONFIANCE = 0.55
# Part minimale des mots de la phrase que l'IA doit connaître pour oser répondre.
SEUIL_MOTS_CONNUS = 0.7
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]

OPERATEURS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def evaluer(noeud):
    """Évalue une expression arithmétique sans jamais exécuter de code arbitraire."""
    if isinstance(noeud, ast.Constant) and isinstance(noeud.value, (int, float)):
        return noeud.value
    if isinstance(noeud, ast.BinOp) and type(noeud.op) in OPERATEURS:
        gauche, droite = evaluer(noeud.left), evaluer(noeud.right)
        if isinstance(noeud.op, ast.Pow) and abs(droite) > 100:
            raise ValueError("exposant trop grand")
        return OPERATEURS[type(noeud.op)](gauche, droite)
    if isinstance(noeud, ast.UnaryOp) and type(noeud.op) in OPERATEURS:
        return OPERATEURS[type(noeud.op)](evaluer(noeud.operand))
    raise ValueError("expression non autorisée")


def calculer(phrase):
    expr = phrase.lower().replace(",", ".")
    for mot, symbole in (("divisé par", "/"), ("divise par", "/"), ("fois", "*"), ("x", "*"),
                         ("plus", "+"), ("moins", "-"), ("puissance", "**")):
        expr = re.sub(rf"\b{mot}\b", symbole, expr)
    morceaux = re.findall(r"[\d.]+|\*\*|[-+*/%()]", expr)
    if not any(re.fullmatch(r"[\d.]+", m) for m in morceaux):
        return "Donne-moi un calcul, par exemple : « calcule 12 * 7 »."
    texte = " ".join(morceaux)
    try:
        resultat = evaluer(ast.parse(texte, mode="eval").body)
    except ZeroDivisionError:
        return "Diviser par zéro ? Même mes neurones refusent ! 🤯"
    except (SyntaxError, ValueError):
        return "Je n'ai pas réussi à comprendre ce calcul 🤔"
    if isinstance(resultat, float) and resultat.is_integer():
        resultat = int(resultat)
    elif isinstance(resultat, float):
        resultat = round(resultat, 6)
    return f"{texte} = {resultat}"


class Chatbot:
    def __init__(self, fichier_intentions=FICHIER_INTENTIONS, fichier_appris=FICHIER_APPRIS, graine=None):
        self.fichier_appris = fichier_appris
        self.rng = random.Random(graine)
        with open(fichier_intentions, encoding="utf-8") as f:
            self.intentions = json.load(f)["intentions"]
        if fichier_appris and os.path.exists(fichier_appris):
            with open(fichier_appris, encoding="utf-8") as f:
                self.intentions += json.load(f)["intentions"]
        self.reseau = None

    # --- Apprentissage -------------------------------------------------
    def entrainer(self, epoques=300, verbeux=False):
        phrases = [ex for it in self.intentions for ex in it["exemples"]]
        self.vocabulaire = construire_vocabulaire(phrases)
        exemples = [
            (vectoriser(ex, self.vocabulaire), i)
            for i, it in enumerate(self.intentions)
            for ex in it["exemples"]
        ]
        nb_caches = max(16, len(self.intentions) * 2)
        self.reseau = ReseauNeurones(len(self.vocabulaire), nb_caches, len(self.intentions))
        return self.reseau.entrainer(exemples, epoques=epoques, verbeux=verbeux)

    def apprendre(self, question, reponse):
        """Ajoute une nouvelle connaissance, la sauvegarde et réentraîne le réseau."""
        self.intentions.append({"nom": f"appris_{len(self.intentions)}",
                                "exemples": [question], "reponses": [reponse]})
        if self.fichier_appris:
            appris = [it for it in self.intentions if it["nom"].startswith("appris_")]
            with open(self.fichier_appris, "w", encoding="utf-8") as f:
                json.dump({"intentions": appris}, f, ensure_ascii=False, indent=2)
        self.entrainer()

    # --- Réponse -------------------------------------------------------
    def classer(self, phrase):
        """Renvoie (nom_intention, confiance) ; nom vaut None si l'IA ne sait pas."""
        mots = jetons(phrase)
        connus = sum(m in self.vocabulaire for m in mots)
        if not mots or connus / len(mots) < SEUIL_MOTS_CONNUS:
            return None, 0.0
        vecteur = vectoriser(phrase, self.vocabulaire)
        probas = self.reseau.predire(vecteur)
        meilleur = max(range(len(probas)), key=probas.__getitem__)
        if probas[meilleur] < SEUIL_CONFIANCE:
            return None, probas[meilleur]
        return self.intentions[meilleur]["nom"], probas[meilleur]

    def repondre(self, phrase):
        nom, _ = self.classer(phrase)
        if nom is None:
            return None
        intention = next(it for it in self.intentions if it["nom"] == nom)
        reponse = self.rng.choice(intention["reponses"])
        maintenant = datetime.datetime.now()
        if "{heure}" in reponse:
            reponse = f"Il est {maintenant:%H:%M}. ⏰"
        elif "{date}" in reponse:
            reponse = (f"Nous sommes le {JOURS[maintenant.weekday()]} {maintenant.day} "
                       f"{MOIS[maintenant.month - 1]} {maintenant.year}. 📅")
        elif "{calcul}" in reponse:
            reponse = calculer(phrase)
        return reponse


def main():
    print("🧠 Entraînement du réseau de neurones…")
    bot = Chatbot()
    perte = bot.entrainer(verbeux=True)
    print(f"✅ Prêt ! (perte finale : {perte:.4f}, {len(bot.vocabulaire)} mots connus)")
    print("Écris « quitter » pour partir.\n")
    while True:
        try:
            phrase = input("Toi    > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nNeurone> Au revoir ! 👋")
            break
        if not phrase:
            continue
        if phrase.lower() in {"quitter", "exit", "quit"}:
            print("Neurone> Au revoir ! 👋")
            break
        reponse = bot.repondre(phrase)
        if reponse is None:
            print("Neurone> Je ne sais pas encore répondre à ça. Que devrais-je dire ? (Entrée pour passer)")
            nouvelle = input("Toi    > ").strip()
            if nouvelle:
                bot.apprendre(phrase, nouvelle)
                print("Neurone> Merci, j'ai appris quelque chose de nouveau ! 🎓")
            continue
        print(f"Neurone> {reponse}")


if __name__ == "__main__":
    main()
