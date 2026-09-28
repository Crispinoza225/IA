"""La bibliographie automatique : citations dans le texte et liste des références, en APA 7 ou ISO 690.

Dans le texte :
    [@dupont2020]              → (Dupont, 2020)
    [@dupont2020, p. 12]       → (Dupont, 2020, p. 12)
    [@dupont2020; @martin2019] → (Dupont, 2020 ; Martin, 2019)
    @dupont2020 montre que…    → Dupont (2020) montre que…

La liste des références est placée à la ligne « [bibliographie] », sinon sous le titre « Bibliographie »
(ou « Références »), sinon dans un nouveau chapitre « Bibliographie » avant les annexes.
"""

import re

from memoire.source import Citation, Liste, Morceau, Paragraphe, Reference, Tableau, Titre, sans_accents

STYLES = {"apa": "APA 7ᵉ édition", "iso690": "ISO 690"}
TYPES = {
    "livre": "Livre", "article": "Article de revue", "chapitre": "Chapitre d'ouvrage", "these": "Thèse ou mémoire",
    "rapport": "Rapport", "site": "Page web",
}
CHAMPS = ("cle", "type", "auteurs", "annee", "titre", "revue", "volume", "numero", "pages", "editeur", "lieu",
          "edition", "ouvrage", "directeurs", "universite", "url", "doi", "consulte")
TITRES_BIBLIOGRAPHIE = {"bibliographie", "references", "references bibliographiques", "bibliographie generale",
                        "sources", "sources et bibliographie"}
TITRES_ANNEXES = {"annexe", "annexes"}
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]


def nettoyer(reference):
    """Garde les champs connus, en texte, sans espaces superflus ; fabrique une clé si elle manque."""
    propre = {champ: re.sub(r"\s+", " ", str(reference.get(champ) or "")).strip()[:1000] for champ in CHAMPS}
    if propre["type"] not in TYPES:
        propre["type"] = "livre"
    propre["cle"] = re.sub(r"[^\w:-]", "", propre["cle"])[:60]
    if not propre["cle"]:
        premier = auteurs(propre["auteurs"])
        nom = sans_accents(premier[0][0]) if premier else "ref"
        propre["cle"] = re.sub(r"[^a-z0-9]", "", nom)[:20] + re.sub(r"\D", "", propre["annee"])[:4]
    return propre


# --- Les auteurs ------------------------------------------------------------------------------------

def auteurs(texte):
    """« Dupont, Jean ; Martin, Paul-Henri ; OMS » → [("Dupont", "Jean"), ("Martin", "Paul-Henri"), ("OMS", "")]."""
    resultat = []
    for morceau in re.split(r"\s*;\s*", texte or ""):
        if not morceau.strip():
            continue
        if "," in morceau:
            nom, prenom = morceau.split(",", 1)
            resultat.append((nom.strip(), prenom.strip()))
        else:
            resultat.append((morceau.strip(), ""))  # une organisation, ou un nom seul
    return resultat


def initiales(prenom):
    """« Jean-Pierre » → « J.-P. », « Marie Anne » → « M. A. »."""
    mots = []
    for mot in prenom.split():
        mots.append("-".join(p[0].upper() + "." for p in mot.split("-") if p))
    return " ".join(mots)


def enumerer(noms, conjonction="et"):
    if len(noms) <= 1:
        return "".join(noms)
    return ", ".join(noms[:-1]) + f" {conjonction} " + noms[-1]


def auteurs_apa(liste):
    noms = [f"{nom}, {initiales(prenom)}" if prenom else nom for nom, prenom in liste]
    if len(noms) > 20:
        return ", ".join(noms[:19]) + ", … " + noms[-1]
    return enumerer(noms)


def auteurs_iso(liste):
    noms = [f"{nom.upper()}, {prenom}" if prenom else nom.upper() for nom, prenom in liste]
    if len(noms) > 3:
        return noms[0] + " et al."
    return enumerer(noms)


def auteurs_courts(liste):
    """Pour les citations : « Dupont », « Dupont et Martin », « Dupont et al. »."""
    noms = [nom for nom, _ in liste]
    if not noms:
        return ""
    if len(noms) == 1:
        return noms[0]
    if len(noms) == 2:
        return f"{noms[0]} et {noms[1]}"
    return f"{noms[0]} et al."


# --- Les entrées de la bibliographie -------------------------------------------------------------------

def point(texte):
    """Termine par un point, sans en doubler un (« Titre ? » ou « J. » restent tels quels)."""
    texte = texte.rstrip()
    return texte if not texte or texte[-1] in ".?!…" else texte + "."


def pages_apa(pages):
    return pages.replace("--", "–").replace("-", "–")


def date_francaise(date):
    trouve = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", date or "")
    if not trouve:
        return date
    annee, mois, jour = trouve.groups()
    jour = "1er" if jour == "01" else str(int(jour))
    return f"{jour} {MOIS[int(mois) - 1]} {annee}"


def lien(ref):
    if ref["doi"]:
        doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", ref["doi"], flags=re.IGNORECASE)
        return f"https://doi.org/{doi}"
    return ref["url"]


class Entree:
    """Construit une entrée morceau par morceau : du texte normal et du texte en italique."""

    def __init__(self):
        self.morceaux = []

    def texte(self, texte):
        if texte:
            if self.morceaux and not self.morceaux[-1].italique:
                self.morceaux[-1].texte += texte
            else:
                self.morceaux.append(Morceau(texte))
        return self

    def italique(self, texte):
        if texte:
            self.morceaux.append(Morceau(texte, italique=True))
        return self


def entree_apa(ref, annee):
    e = Entree()
    liste = auteurs(ref["auteurs"])
    titre = ref["titre"] or "Sans titre"
    if liste:
        e.texte(point(auteurs_apa(liste)) + f" ({annee}). ")
    else:  # sans auteur, le titre prend sa place
        e.italique(titre) if ref["type"] != "article" else e.texte(titre)
        e.texte(f". ({annee}). ")
    type_ = ref["type"]
    if type_ == "article":
        if liste:
            e.texte(point(titre) + " ")
        if ref["revue"]:
            e.italique(ref["revue"])
            if ref["volume"]:
                e.texte(", ").italique(ref["volume"])
            if ref["numero"]:
                e.texte(f"({ref['numero']})")
            if ref["pages"]:
                e.texte(f", {pages_apa(ref['pages'])}")
            e.texte(".")
    elif type_ == "chapitre":
        if liste:
            e.texte(point(titre) + " ")
        e.texte("Dans ")
        directeurs = auteurs(ref["directeurs"])
        if directeurs:
            noms = [f"{initiales(p)} {n}".strip() for n, p in directeurs]
            e.texte(enumerer(noms) + " (dir.), ")
        e.italique(ref["ouvrage"] or "Ouvrage")
        details = [f"{ref['edition']}ᵉ éd." if ref["edition"].isdigit() else ref["edition"]]
        if ref["pages"]:
            details.append(f"p. {pages_apa(ref['pages'])}")
        details = [d for d in details if d]
        e.texte((f" ({', '.join(details)})" if details else "") + ".")
        if ref["editeur"]:
            e.texte(" " + point(ref["editeur"]))
    else:
        if liste:
            e.italique(titre)
        complement = ""
        if type_ == "livre" and ref["edition"]:
            complement = f" ({ref['edition']}ᵉ éd.)" if ref["edition"].isdigit() else f" ({ref['edition']})"
        elif type_ == "these":
            complement = f" [Thèse ou mémoire{', ' + ref['universite'] if ref['universite'] else ''}]"
        elif type_ == "rapport" and ref["numero"]:
            complement = f" (Rapport n° {ref['numero']})"
        e.texte(complement + ".")
        if ref["editeur"] and ref["editeur"] not in (ref["auteurs"],):
            e.texte(" " + point(ref["editeur"]))
    adresse = lien(ref)
    if adresse:
        e.texte(" " + adresse)
    return e.morceaux


def entree_iso(ref, annee):
    e = Entree()
    liste = auteurs(ref["auteurs"])
    titre = ref["titre"] or "Sans titre"
    type_ = ref["type"]
    if liste:
        e.texte(point(auteurs_iso(liste)) + " ")
    lieu_editeur = " : ".join(x for x in (ref["lieu"], ref["editeur"]) if x)
    if type_ == "article":
        e.texte(point(titre) + " ")
        if ref["revue"]:
            e.italique(ref["revue"]).texte(". ")
        details = [annee]
        if ref["volume"]:
            details.append(f"vol. {ref['volume']}")
        if ref["numero"]:
            details.append(f"n° {ref['numero']}")
        if ref["pages"]:
            details.append(f"p. {ref['pages'].replace('--', '-')}")
        e.texte(", ".join(details) + ".")
    elif type_ == "chapitre":
        e.texte(point(titre) + " In : ")
        directeurs = auteurs(ref["directeurs"])
        if directeurs:
            e.texte(auteurs_iso(directeurs) + " (dir.). ")
        e.italique(ref["ouvrage"] or "Ouvrage").texte(". ")
        if ref["edition"]:
            e.texte(f"{ref['edition']}ᵉ éd. " if ref["edition"].isdigit() else point(ref["edition"]) + " ")
        e.texte(", ".join(x for x in (lieu_editeur, annee) if x))
        if ref["pages"]:
            e.texte(f", p. {ref['pages'].replace('--', '-')}")
        e.texte(".")
    else:
        e.italique(titre)
        e.texte(" [en ligne]. " if type_ == "site" else ". ")
        if type_ == "livre" and ref["edition"]:
            e.texte(f"{ref['edition']}ᵉ éd. " if ref["edition"].isdigit() else point(ref["edition"]) + " ")
        if type_ == "these":
            e.texte("Thèse ou mémoire. ")
            lieu_editeur = " : ".join(x for x in (ref["lieu"], ref["universite"] or ref["editeur"]) if x)
        if type_ == "rapport" and ref["numero"]:
            e.texte(f"Rapport n° {ref['numero']}. ")
        e.texte(", ".join(x for x in (lieu_editeur, annee) if x) + ".")
    if ref["consulte"] and (ref["url"] or type_ == "site"):
        e.texte(f" [Consulté le {date_francaise(ref['consulte'])}].")
    if ref["doi"]:
        e.texte(" DOI " + re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", ref["doi"], flags=re.IGNORECASE) + ".")
    elif ref["url"]:
        e.texte(f" Disponible à l'adresse : {ref['url']}")
    return e.morceaux


def cle_de_tri(ref):
    liste = auteurs(ref["auteurs"])
    premier = sans_accents(liste[0][0] + " " + liste[0][1]) if liste else sans_accents(ref["titre"])
    return premier, ref["annee"] or "9999", sans_accents(ref["titre"])


def annees(references):
    """L'année affichée de chaque référence, avec « 2020a », « 2020b » quand un même auteur publie deux fois la même année."""
    groupes = {}
    for ref in sorted(references, key=cle_de_tri):
        annee = ref["annee"] or "s.d."
        groupes.setdefault((auteurs_courts(auteurs(ref["auteurs"])) or ref["titre"], annee), []).append(ref["cle"])
    resultat = {}
    for (_, annee), cles in groupes.items():
        for rang, cle in enumerate(cles):
            resultat[cle] = annee + (chr(ord("a") + rang) if len(cles) > 1 and rang < 26 else "")
    return resultat


def entrees(references, style):
    """Les entrées de la bibliographie (listes de morceaux), triées par auteur puis par année."""
    affichees = annees(references)
    fabrique = entree_iso if style == "iso690" else entree_apa
    return [fabrique(ref, affichees[ref["cle"]]) for ref in sorted(references, key=cle_de_tri)]


# --- Les citations dans le texte -------------------------------------------------------------------------

CITATION_ENTRE_CROCHETS = re.compile(r"\[((?:\s*@[\w:-]+[^;\]]*;?)+)\]")
CITATION_DANS_LA_PHRASE = re.compile(r"(?<![\w@.\[])@([\w:-]+)")


def appliquer(blocs, references, style="apa", toutes=False):
    """Remplace les citations dans les blocs et insère la bibliographie.

    Renvoie (nouveaux blocs, clés citées, clés inconnues).
    """
    par_cle = {ref["cle"]: ref for ref in references}
    affichees = annees(references)
    citees, inconnues = [], []

    def auteur_de(ref):
        return auteurs_courts(auteurs(ref["auteurs"])) or f"« {ref['titre'] or 'Sans titre'} »"

    def citer(cle):
        if cle not in citees:
            citees.append(cle)

    def entre_crochets(trouve):
        parties = []
        for element in trouve.group(1).split(";"):
            element = element.strip()
            cle, _, precision = element[1:].partition(",")
            cle = cle.strip()
            if cle not in par_cle:
                if cle not in inconnues:
                    inconnues.append(cle)
                return trouve.group(0)
            citer(cle)
            ref = par_cle[cle]
            partie = f"{auteur_de(ref)}, {affichees[cle]}"
            if precision.strip():
                partie += f", {precision.strip()}"
            parties.append(partie)
        return "(" + " ; ".join(parties) + ")"

    def dans_la_phrase(trouve):
        cle = trouve.group(1).rstrip(":-")
        reste = trouve.group(1)[len(cle):]
        if cle not in par_cle:
            return trouve.group(0)  # peut-être une adresse ou un @pseudo : on n'y touche pas
        citer(cle)
        return f"{auteur_de(par_cle[cle])} ({affichees[cle]})" + reste

    def transformer(morceaux):
        for m in morceaux:
            if "@" in m.texte:
                m.texte = CITATION_DANS_LA_PHRASE.sub(dans_la_phrase, CITATION_ENTRE_CROCHETS.sub(entre_crochets, m.texte))

    for bloc in blocs:
        if isinstance(bloc, (Paragraphe, Citation)):
            transformer(bloc.morceaux)
        elif isinstance(bloc, Liste):
            for element in bloc.elements:
                transformer(element)
        elif isinstance(bloc, Tableau):
            for ligne in bloc.lignes:
                for cellule in ligne:
                    transformer(cellule)

    a_lister = references if toutes else [par_cle[cle] for cle in citees]
    liste = [Reference(morceaux) for morceaux in entrees(a_lister, style)] if a_lister else []

    def texte_du_bloc(bloc):
        return "".join(m.texte for m in bloc.morceaux).strip().lower() if isinstance(bloc, Paragraphe) else None

    # 1. à l'endroit choisi par l'auteur
    for position, bloc in enumerate(blocs):
        if texte_du_bloc(bloc) == "[bibliographie]":
            return blocs[:position] + liste + blocs[position + 1:], citees, inconnues
    if not liste:
        return blocs, citees, inconnues
    # 2. sous un titre « Bibliographie » déjà présent
    for position, bloc in enumerate(blocs):
        if isinstance(bloc, Titre) and sans_accents(bloc.texte).strip(" .:") in TITRES_BIBLIOGRAPHIE:
            return blocs[:position + 1] + liste + blocs[position + 1:], citees, inconnues
    # 3. dans un nouveau chapitre, avant les annexes
    position = next((i for i, b in enumerate(blocs) if isinstance(b, Titre) and b.niveau == 1
                     and sans_accents(b.texte).strip(" .:") in TITRES_ANNEXES), len(blocs))
    chapitre = [Titre(1, "Bibliographie", numerote=False)] + liste
    return blocs[:position] + chapitre + blocs[position:], citees, inconnues


# --- Import BibTeX (Zotero, Mendeley, Google Scholar…) -----------------------------------------------------

TYPES_BIBTEX = {
    "book": "livre", "article": "article", "incollection": "chapitre", "inbook": "chapitre",
    "inproceedings": "chapitre", "phdthesis": "these", "mastersthesis": "these", "thesis": "these",
    "techreport": "rapport", "report": "rapport", "online": "site", "misc": "site", "webpage": "site",
}
ACCENTS_LATEX = {
    "'": {"e": "é", "a": "á", "i": "í", "o": "ó", "u": "ú", "E": "É", "c": "ć"},
    "`": {"e": "è", "a": "à", "u": "ù", "E": "È", "A": "À"},
    "^": {"e": "ê", "a": "â", "i": "î", "o": "ô", "u": "û", "E": "Ê"},
    '"': {"e": "ë", "i": "ï", "u": "ü", "o": "ö", "a": "ä"},
    "c": {"c": "ç", "C": "Ç"},
}


def delatex(texte):
    def accent(trouve):
        commande, lettre = trouve.group(1), trouve.group(2)
        return ACCENTS_LATEX.get(commande, {}).get(lettre, lettre)

    texte = re.sub(r"\\([`'^\"c])\s*\{?\\?([A-Za-z])\}?", accent, texte)
    texte = texte.replace("\\&", "&").replace("--", "–").replace("~", " ")
    texte = re.sub(r"\\[a-zA-Z]+\s*", "", texte)
    return re.sub(r"\s+", " ", texte.replace("{", "").replace("}", "")).strip()


def lire_valeur(texte, i):
    """Lit une valeur BibTeX à partir de la position i : {…}, "…" ou un nombre. Renvoie (valeur, fin)."""
    if texte[i] == "{":
        profondeur, debut = 0, i
        while i < len(texte):
            profondeur += {"{": 1, "}": -1}.get(texte[i], 0)
            i += 1
            if profondeur == 0:
                return texte[debut + 1:i - 1], i
        return texte[debut + 1:], i
    if texte[i] == '"':
        fin = texte.find('"', i + 1)
        fin = len(texte) if fin == -1 else fin
        return texte[i + 1:fin], fin + 1
    trouve = re.match(r"[\w.-]+", texte[i:])
    return (trouve.group(0), i + trouve.end()) if trouve else ("", i + 1)


def auteurs_bibtex(texte):
    noms = []
    for nom in re.split(r"\s+and\s+", delatex(texte)):
        nom = nom.strip()
        if not nom:
            continue
        if "," not in nom and " " in nom:  # « Jean Dupont » → « Dupont, Jean »
            prenom, _, famille = nom.rpartition(" ")
            nom = f"{famille}, {prenom}"
        noms.append(nom)
    return " ; ".join(noms)


def importer_bibtex(texte):
    """Lit un fichier BibTeX et renvoie la liste des références (dictionnaires nettoyés)."""
    references = []
    for trouve in re.finditer(r"@(\w+)\s*\{\s*([^,\s]*)\s*,", texte):
        type_bibtex = trouve.group(1).lower()
        if type_bibtex in ("comment", "string", "preamble"):
            continue
        champs, i = {}, trouve.end()
        while i < len(texte):
            nom = re.match(r"\s*,?\s*([A-Za-z_-]+)\s*=\s*", texte[i:])
            if not nom:
                break
            i += nom.end()
            valeur, i = lire_valeur(texte, i)
            champs[nom.group(1).lower()] = valeur
        date = champs.get("year") or champs.get("date", "")[:4]
        type_ = TYPES_BIBTEX.get(type_bibtex, "livre")
        references.append(nettoyer({
            "cle": trouve.group(2), "type": type_,
            "auteurs": auteurs_bibtex(champs.get("author", "")),
            "annee": delatex(date), "titre": delatex(champs.get("title", "")),
            "revue": delatex(champs.get("journal") or champs.get("journaltitle", "")),
            "volume": champs.get("volume", ""), "numero": champs.get("number", ""),
            "pages": delatex(champs.get("pages", "")).replace("–", "-"),
            "editeur": delatex(champs.get("publisher") or champs.get("institution", "")),
            "lieu": delatex(champs.get("address") or champs.get("location", "")),
            "edition": delatex(champs.get("edition", "")), "ouvrage": delatex(champs.get("booktitle", "")),
            "directeurs": auteurs_bibtex(champs.get("editor", "")),
            "universite": delatex(champs.get("school", "")), "url": champs.get("url", ""),
            "doi": champs.get("doi", ""), "consulte": champs.get("urldate", ""),
        }))
    return references
