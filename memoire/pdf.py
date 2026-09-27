"""Écrire le mémoire en PDF (avec reportlab), avec un sommaire aux vrais numéros de page et des signets.

Le sommaire est calculé en deux passes : on met une première fois le document en page pour savoir
sur quelle page tombe chaque titre, puis on recommence en remplissant le sommaire.
"""

import io
import os
from xml.sax.saxutils import escape

from .source import Citation, Liste, Paragraphe, Reference, SautDePage, Tableau, Titre

# Pour chaque police : fichiers possibles (la police elle-même, puis un équivalent libre aux mêmes dimensions).
FICHIERS = {
    "Times New Roman": [("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
                        ("Times New Roman.ttf", "Times New Roman Bold.ttf", "Times New Roman Italic.ttf", "Times New Roman Bold Italic.ttf"),
                        ("LiberationSerif-Regular.ttf", "LiberationSerif-Bold.ttf", "LiberationSerif-Italic.ttf", "LiberationSerif-BoldItalic.ttf")],
    "Arial": [("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
              ("Arial.ttf", "Arial Bold.ttf", "Arial Italic.ttf", "Arial Bold Italic.ttf"),
              ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf", "LiberationSans-Italic.ttf", "LiberationSans-BoldItalic.ttf")],
    "Calibri": [("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"),
                ("Carlito-Regular.ttf", "Carlito-Bold.ttf", "Carlito-Italic.ttf", "Carlito-BoldItalic.ttf")],
    "Garamond": [("GARA.TTF", "GARABD.TTF", "GARAIT.TTF", "GARABD.TTF"),
                 ("EBGaramond-Regular.ttf", "EBGaramond-Bold.ttf", "EBGaramond-Italic.ttf", "EBGaramond-BoldItalic.ttf")],
    "Georgia": [("georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf"),
                ("Gelasio-Regular.ttf", "Gelasio-Bold.ttf", "Gelasio-Italic.ttf", "Gelasio-BoldItalic.ttf")],
    "Cambria": [("cambria.ttc", "cambriab.ttf", "cambriai.ttf", "cambriaz.ttf"),
                ("Caladea-Regular.ttf", "Caladea-Bold.ttf", "Caladea-Italic.ttf", "Caladea-BoldItalic.ttf")],
}
SERIF = {"Times New Roman", "Garamond", "Georgia", "Cambria"}
DOSSIERS = ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"),
            "/Library/Fonts", "/System/Library/Fonts", "C:\\Windows\\Fonts"]
_fichiers_systeme = None
_polices_enregistrees = {}


def fichiers_systeme():
    global _fichiers_systeme
    if _fichiers_systeme is None:
        _fichiers_systeme = {}
        for dossier in DOSSIERS:
            for racine, _, noms in os.walk(dossier):
                for nom in noms:
                    _fichiers_systeme.setdefault(nom.lower(), os.path.join(racine, nom))
    return _fichiers_systeme


def enregistrer_police(nom):
    """Renvoie le nom de la famille reportlab à utiliser (une police TrueType trouvée, sinon Times ou Helvetica)."""
    if nom in _polices_enregistrees:
        return _polices_enregistrees[nom]
    from reportlab.lib.fonts import addMapping
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    trouves = fichiers_systeme()
    candidats = FICHIERS.get(nom, []) + (FICHIERS["Times New Roman"] if nom in SERIF else FICHIERS["Arial"])
    for variantes in candidats:
        chemins = [trouves.get(f.lower()) for f in variantes]
        if all(chemins) and not any(c.lower().endswith(".ttc") for c in chemins):
            famille = "M-" + nom.replace(" ", "")
            for suffixe, chemin in zip(("", "-Gras", "-Italique", "-GrasItalique"), chemins):
                pdfmetrics.registerFont(TTFont(famille + suffixe, chemin))
            for gras, italique, suffixe in ((0, 0, ""), (1, 0, "-Gras"), (0, 1, "-Italique"), (1, 1, "-GrasItalique")):
                addMapping(famille, gras, italique, famille + suffixe)
            _polices_enregistrees[nom] = famille
            return famille
    _polices_enregistrees[nom] = "Times-Roman" if nom in SERIF else "Helvetica"
    return _polices_enregistrees[nom]


def balisage(morceaux):
    """Morceaux → mini-HTML compris par reportlab (<b>, <i>)."""
    resultat = ""
    for m in morceaux:
        texte = escape(m.texte)
        if m.italique:
            texte = f"<i>{texte}</i>"
        if m.gras:
            texte = f"<b>{texte}</b>"
        resultat += texte
    return resultat


def ecrire_pdf(blocs, reglages, mention=""):
    """Renvoie (contenu du PDF en octets, liste des entrées du sommaire [(niveau, texte, page)]).

    mention : une petite ligne grise ajoutée en bas de chaque page (« réalisé avec… »), facultative.
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                    TableStyle)
    from reportlab.platypus.tableofcontents import TableOfContents

    r = reglages
    police = enregistrer_police(r.police)
    gras = police + "-Gras" if police.startswith("M-") else {"Times-Roman": "Times-Bold"}.get(police, "Helvetica-Bold")
    couleur = colors.HexColor(r.couleur_titres)
    interligne = r.taille * 1.15 * r.interligne  # « simple » ≈ 1,15 × la taille, comme dans Word

    corps = ParagraphStyle("corps", fontName=police, fontSize=r.taille, leading=interligne,
                           alignment=TA_JUSTIFY if r.alignement == "justifie" else TA_LEFT,
                           firstLineIndent=r.retrait * cm, spaceAfter=r.espace_apres)
    titres = []
    for niveau, (avant, apres) in enumerate([(24, 12), (18, 8), (12, 6)], start=1):
        taille = r.tailles_titres[niveau - 1]
        titres.append(ParagraphStyle(f"titre{niveau}", parent=corps, fontName=police, fontSize=taille,
                                     leading=taille * 1.2, alignment=TA_LEFT, firstLineIndent=0, spaceBefore=avant,
                                     spaceAfter=apres, textColor=couleur, keepWithNext=1))
    citation = ParagraphStyle("citation", parent=corps, fontSize=max(8, r.taille - 1), leading=max(8, r.taille - 1) * 1.2,
                              leftIndent=cm, rightIndent=cm, firstLineIndent=0, spaceBefore=6, spaceAfter=6)
    element_liste = ParagraphStyle("liste", parent=corps, firstLineIndent=0, leftIndent=1.27 * cm,
                                   bulletIndent=0.63 * cm, spaceAfter=2, bulletFontName=police, bulletFontSize=r.taille)
    reference = ParagraphStyle("reference", parent=corps, alignment=TA_LEFT, leftIndent=1.25 * cm,
                               firstLineIndent=-1.25 * cm)
    cellule = ParagraphStyle("cellule", parent=corps, alignment=TA_LEFT, firstLineIndent=0, spaceAfter=0,
                             leading=r.taille * 1.2)
    garde_style = ParagraphStyle("garde", parent=corps, alignment=TA_CENTER, firstLineIndent=0, spaceAfter=0)
    pied_style = ParagraphStyle("pied", fontName=police, fontSize=max(8, r.taille - 1),
                                alignment=TA_RIGHT if r.pagination == "droite" else TA_CENTER)

    class Document(BaseDocTemplate):
        def __init__(self, tampon):
            super().__init__(tampon, pagesize=A4, leftMargin=r.marge_gauche * cm, rightMargin=r.marge_droite * cm,
                             topMargin=r.marge_haut * cm, bottomMargin=r.marge_bas * cm,
                             title=r.garde.titre, author=r.garde.auteur, lang="fr-FR")
            cadre = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="cadre",
                          leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
            self.addPageTemplates([PageTemplate("page", [cadre], onPage=self.numero_de_page)])

        def beforeDocument(self):
            # Appelé au début de chaque passe : on recommence la liste des titres à zéro.
            self.entrees = []
            self.dernier_niveau = -1

        def numero_de_page(self, canevas, document):
            page = canevas.getPageNumber()
            if mention:
                canevas.saveState()
                canevas.setFont(police, 7)
                canevas.setFillColor(colors.HexColor("#808080"))
                canevas.drawCentredString(A4[0] / 2, 0.45 * cm, mention)
                canevas.restoreState()
            if r.pagination == "aucune" or (page == 1 and r.garde.afficher):
                return
            canevas.saveState()
            canevas.setFont(police, pied_style.fontSize)
            y = max(0.6 * cm, r.marge_bas * cm / 2)
            if r.pagination == "droite":
                canevas.drawRightString(A4[0] - r.marge_droite * cm, y, str(page))
            else:
                canevas.drawCentredString(r.marge_gauche * cm + self.width / 2, y, str(page))
            canevas.restoreState()

        def afterFlowable(self, flowable):
            niveau = getattr(flowable, "niveau_sommaire", None)
            if niveau is None:
                return
            texte, page = flowable.texte_sommaire, self.page
            cle = f"titre{len(self.entrees)}"
            self.canv.bookmarkPage(cle)
            # Les signets du PDF ne peuvent pas sauter de niveau (pas de niveau 3 directement sous un niveau 1).
            niveau_signet = min(niveau - 1, self.dernier_niveau + 1)
            self.dernier_niveau = niveau_signet
            self.canv.addOutlineEntry(texte, cle, level=niveau_signet, closed=niveau_signet > 0)
            self.entrees.append((niveau, texte, page))
            if niveau <= r.profondeur_sommaire:
                self.notify("TOCEntry", (niveau - 1, texte, page, cle))

    histoire = []

    if r.garde.afficher:
        g = r.garde

        def ligne(texte, taille, gras_=False, italique=False, avant=0):
            if texte:
                contenu = escape(texte)
                contenu = f"<i>{contenu}</i>" if italique else contenu
                contenu = f"<b>{contenu}</b>" if gras_ else contenu
                histoire.append(Spacer(1, avant))
                histoire.append(Paragraph(contenu, ParagraphStyle("g", parent=garde_style, fontSize=taille,
                                                                   leading=taille * 1.25)))

        ligne(g.universite, 14, gras_=True)
        ligne(g.faculte, 12, avant=2)
        ligne(g.type_document, 13, avant=4 * cm)
        ligne(g.titre, 22, gras_=True, avant=0.8 * cm)
        ligne(g.sous_titre, 14, italique=True, avant=0.3 * cm)
        if g.auteur:
            ligne("Présenté par", 12, avant=3 * cm)
            ligne(g.auteur, 14, gras_=True, avant=2)
        if g.directeur:
            ligne("Sous la direction de", 12, avant=0.8 * cm)
            ligne(g.directeur, 13, avant=2)
        ligne(g.annee, 12, avant=2 * cm)
        histoire.append(PageBreak())

    if r.sommaire:
        histoire.append(Paragraph(f"<b>{escape(r.titre_sommaire)}</b>",
                                  ParagraphStyle("titre_sommaire", parent=titres[0], spaceBefore=0, spaceAfter=18)))
        sommaire = TableOfContents(dotsMinLevel=0)
        sommaire.levelStyles = [
            ParagraphStyle(f"som{n}", fontName=gras if n == 0 else police, fontSize=r.taille, leading=r.taille * 1.5,
                           leftIndent=n * 0.7 * cm + 0.2 * cm, firstLineIndent=-0.2 * cm, rightIndent=0.8 * cm)
            for n in range(3)]
        histoire.append(sommaire)
        histoire.append(PageBreak())

    debut_de_page = True  # après la page de garde ou le sommaire, on est déjà en haut d'une page
    for bloc in blocs:
        if isinstance(bloc, Titre):
            if bloc.niveau == 1 and r.chapitre_nouvelle_page and not debut_de_page:
                histoire.append(PageBreak())
            texte = f"{r.prefixe_chapitre.strip()} {bloc.numero}".strip() if bloc.niveau == 1 and bloc.numero and r.prefixe_chapitre.strip() else bloc.numero
            texte = f"{texte} {bloc.texte}".strip()
            contenu = f"<b>{escape(texte)}</b>"
            if bloc.niveau == 3:
                contenu = f"<i>{contenu}</i>"
            paragraphe = Paragraph(contenu, titres[bloc.niveau - 1])
            paragraphe.niveau_sommaire, paragraphe.texte_sommaire = bloc.niveau, texte
            histoire.append(paragraphe)
        elif isinstance(bloc, Paragraphe):
            histoire.append(Paragraph(balisage(bloc.morceaux), corps))
        elif isinstance(bloc, Citation):
            histoire.append(Paragraph(f"<i>{balisage(bloc.morceaux)}</i>", citation))
        elif isinstance(bloc, Reference):
            histoire.append(Paragraph(balisage(bloc.morceaux), reference))
        elif isinstance(bloc, Liste):
            for numero, element in enumerate(bloc.elements, start=1):
                histoire.append(Paragraph(balisage(element), element_liste,
                                          bulletText=f"{numero}." if bloc.ordonnee else "•"))
            histoire.append(Spacer(1, r.espace_apres))
        elif isinstance(bloc, Tableau):
            donnees = [[Paragraph(f"<b>{balisage(c)}</b>" if rang == 0 else balisage(c), cellule) for c in ligne]
                       for rang, ligne in enumerate(bloc.lignes)]
            largeur = (A4[0] - (r.marge_gauche + r.marge_droite) * cm) / len(bloc.lignes[0])
            table = Table(donnees, colWidths=[largeur] * len(bloc.lignes[0]), repeatRows=1)
            table.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#808080")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E7E6E6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            histoire += [Spacer(1, 4), table, Spacer(1, 10)]
        elif isinstance(bloc, SautDePage):
            histoire.append(PageBreak())
        debut_de_page = isinstance(bloc, SautDePage)
    if not blocs:
        histoire.append(Paragraph("", corps))

    tampon = io.BytesIO()
    document = Document(tampon)
    document.multiBuild(histoire)
    return tampon.getvalue(), document.entrees
