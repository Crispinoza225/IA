"""Écrire un vrai fichier Word (.docx) à la main.

Un .docx est une archive ZIP qui contient des fichiers XML : le texte (document.xml), les styles
(styles.xml), la numérotation des titres et des listes (numbering.xml), le pied de page avec le
numéro de page, etc. En l'écrivant nous-mêmes, on obtient un document « propre » : de vrais styles
Titre 1, Titre 2, Titre 3, une numérotation automatique que Word tient à jour, et un vrai sommaire
que Word sait actualiser.
"""

import datetime
import io
import zipfile
from xml.sax.saxutils import escape

from .source import Citation, Liste, Paragraphe, SautDePage, Tableau, Titre

CM = 567  # un centimètre en « twips » (vingtièmes de point), l'unité de Word

ESPACES = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
           'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


def attribut(texte):
    return escape(str(texte), {'"': "&quot;"})


# --- Morceaux de texte ----------------------------------------------------------------------

def run(texte, gras=False, italique=False):
    proprietes = ("<w:b/>" if gras else "") + ("<w:i/>" if italique else "")
    proprietes = f"<w:rPr>{proprietes}</w:rPr>" if proprietes else ""
    return f'<w:r>{proprietes}<w:t xml:space="preserve">{escape(texte)}</w:t></w:r>'


def runs(morceaux):
    return "".join(run(m.texte, m.gras, m.italique) for m in morceaux if m.texte)


def paragraphe(contenu, style=None, proprietes=""):
    style = f'<w:pStyle w:val="{style}"/>' if style else ""
    ppr = f"<w:pPr>{style}{proprietes}</w:pPr>" if style or proprietes else ""
    return f"<w:p>{ppr}{contenu}</w:p>"


# Pour changer de page, on marque le paragraphe suivant « saut de page avant » plutôt que d'insérer un
# paragraphe contenant un saut : sinon Word laisse une ligne vide en haut de la page suivante, et un
# chapitre qui commence lui-même sur une nouvelle page créerait une page blanche.
SAUT_AVANT = "<w:pageBreakBefore/>"


# --- Les différentes parties ----------------------------------------------------------------------

def page_de_garde(garde):
    def ligne(texte, taille=None, gras=False, italique=False, avant=0):
        if not texte:
            return ""
        rpr = ("<w:b/>" if gras else "") + ("<w:i/>" if italique else "") + (f'<w:sz w:val="{int(taille * 2)}"/>' if taille else "")
        contenu = f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{escape(texte)}</w:t></w:r>'
        return paragraphe(contenu, "PageDeGarde", f'<w:spacing w:before="{int(avant * 20)}"/>')

    parties = [
        ligne(garde.universite, 14, gras=True),
        ligne(garde.faculte, 12),
        ligne(garde.type_document, 13, avant=100),
        ligne(garde.titre, 22, gras=True, avant=30),
        ligne(garde.sous_titre, 14, italique=True, avant=6),
        ligne("Présenté par", 12, avant=90) if garde.auteur else "",
        ligne(garde.auteur, 14, gras=True),
        ligne("Sous la direction de", 12, avant=24) if garde.directeur else "",
        ligne(garde.directeur, 13),
        ligne(garde.annee, 12, avant=60),
    ]
    return "".join(parties)


def sommaire(blocs, reglages, saut_avant):
    """Un vrai champ « table des matières » : Word le met à jour et calcule les numéros de page à l'ouverture."""
    entrees = [b for b in blocs if isinstance(b, Titre) and b.niveau <= reglages.profondeur_sommaire]
    debut = (f'<w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>'
             f'<w:r><w:instrText xml:space="preserve"> TOC \\o "1-{reglages.profondeur_sommaire}" \\h \\z \\u </w:instrText></w:r>'
             '<w:r><w:fldChar w:fldCharType="separate"/></w:r>')
    fin = '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    lignes = []
    for position, titre in enumerate(entrees):
        texte = f"{titre.numero} {titre.texte}".strip()
        contenu = (debut if position == 0 else "") + run(texte) + (fin if position == len(entrees) - 1 else "")
        lignes.append(paragraphe(contenu, f"TM{titre.niveau}"))
    if not lignes:
        lignes.append(paragraphe(debut + run("(Aucun titre)") + fin, "TM1"))
    titre = paragraphe(run(reglages.titre_sommaire), "TitreSommaire", SAUT_AVANT if saut_avant else "")
    return titre + "".join(lignes)


def corps(blocs, reglages, listes_numerotees, saut_avant):
    xml = []
    saut = saut_avant  # le prochain paragraphe doit-il commencer sur une nouvelle page ?

    def debut_de_page():
        nonlocal saut
        resultat, saut = (SAUT_AVANT if saut else ""), False
        return resultat

    for bloc in blocs:
        if isinstance(bloc, Titre):
            # Un titre non numéroté garde son style (pour le sommaire), mais sans numéro.
            sans_numero = '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="0"/></w:numPr>' \
                if not bloc.numerote and reglages.numerotation != "aucune" else ""
            xml.append(paragraphe(run(bloc.texte), f"Heading{bloc.niveau}", debut_de_page() + sans_numero))
        elif isinstance(bloc, Paragraphe):
            xml.append(paragraphe(runs(bloc.morceaux), None, debut_de_page()))
        elif isinstance(bloc, Citation):
            xml.append(paragraphe(runs(bloc.morceaux), "Quote", debut_de_page()))
        elif isinstance(bloc, Liste):
            if bloc.ordonnee:
                listes_numerotees.append(len(listes_numerotees) + 3)  # chaque liste recommence à 1
                numero = listes_numerotees[-1]
            else:
                numero = 2
            for element in bloc.elements:
                xml.append(paragraphe(runs(element), "ListParagraph", debut_de_page() +
                                      f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{numero}"/></w:numPr>'))
        elif isinstance(bloc, Tableau):
            if saut:  # un tableau ne peut pas porter de saut de page : un paragraphe vide le fait pour lui
                xml.append(paragraphe("", None, debut_de_page()))
            xml.append(tableau(bloc))
        elif isinstance(bloc, SautDePage):
            saut = True
    return "".join(xml)


def tableau(bloc):
    bordure = '<w:{0} w:val="single" w:sz="6" w:space="0" w:color="808080"/>'
    bordures = "".join(bordure.format(c) for c in ("top", "left", "bottom", "right", "insideH", "insideV"))
    colonnes = len(bloc.lignes[0])
    lignes = []
    for rang, ligne in enumerate(bloc.lignes):
        cellules = []
        for cellule in ligne:
            texte = "".join(run(m.texte, m.gras or rang == 0, m.italique) for m in cellule if m.texte)
            ombre = '<w:shd w:val="clear" w:color="auto" w:fill="E7E6E6"/>' if rang == 0 else ""
            cellules.append(f'<w:tc><w:tcPr><w:tcW w:w="{5000 // colonnes}" w:type="pct"/>{ombre}</w:tcPr>'
                            f'{paragraphe(texte, "Tableau")}</w:tc>')
        entete = "<w:trPr><w:tblHeader/></w:trPr>" if rang == 0 else ""
        lignes.append(f"<w:tr>{entete}{''.join(cellules)}</w:tr>")
    grille = "".join(f'<w:gridCol w:w="{9000 // colonnes}"/>' for _ in range(colonnes))
    return (f'<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:jc w:val="center"/><w:tblBorders>{bordures}</w:tblBorders>'
            f'<w:tblCellMar><w:left w:w="100" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr>'
            f"<w:tblGrid>{grille}</w:tblGrid>{''.join(lignes)}</w:tbl>" + paragraphe(""))


# --- Fichiers de l'archive ----------------------------------------------------------------------------

def styles(reglages):
    r = reglages
    police = attribut(r.police)
    taille = int(round(r.taille * 2))  # Word compte en demi-points
    interligne = int(round(240 * r.interligne))
    alignement = "both" if r.alignement == "justifie" else "left"
    couleur = r.couleur_titres.lstrip("#").upper()

    def titre(niveau):
        taille_titre = int(round(r.tailles_titres[niveau - 1] * 2))
        numerotation = f'<w:numPr><w:ilvl w:val="{niveau - 1}"/><w:numId w:val="1"/></w:numPr>' \
            if r.numerotation != "aucune" else ""
        saut = "<w:pageBreakBefore/>" if niveau == 1 and r.chapitre_nouvelle_page else ""
        avant, apres = [(24, 12), (18, 8), (12, 6)][niveau - 1]
        return f'''<w:style w:type="paragraph" w:styleId="Heading{niveau}"><w:name w:val="heading {niveau}"/>
<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:uiPriority w:val="9"/><w:qFormat/>
<w:pPr><w:keepNext/><w:keepLines/>{saut}{numerotation}<w:spacing w:before="{avant * 20}" w:after="{apres * 20}" w:line="240" w:lineRule="auto"/>
<w:jc w:val="left"/><w:ind w:firstLine="0"/><w:outlineLvl w:val="{niveau - 1}"/></w:pPr>
<w:rPr><w:b/>{"<w:i/>" if niveau == 3 else ""}<w:color w:val="{couleur}"/><w:sz w:val="{taille_titre}"/><w:szCs w:val="{taille_titre}"/></w:rPr></w:style>'''

    def entree_sommaire(niveau):
        return f'''<w:style w:type="paragraph" w:styleId="TM{niveau}"><w:name w:val="toc {niveau}"/>
<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:uiPriority w:val="39"/>
<w:pPr><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="{int((21 - r.marge_gauche - r.marge_droite) * CM) - 10}"/></w:tabs>
<w:spacing w:after="60" w:line="240" w:lineRule="auto"/><w:jc w:val="left"/><w:ind w:left="{(niveau - 1) * 400}" w:firstLine="0"/></w:pPr>
{"<w:rPr><w:b/></w:rPr>" if niveau == 1 else ""}</w:style>'''

    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {ESPACES}>
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="{police}" w:hAnsi="{police}" w:eastAsia="{police}" w:cs="{police}"/>
<w:sz w:val="{taille}"/><w:szCs w:val="{taille}"/><w:lang w:val="fr-FR"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="{int(r.espace_apres * 20)}" w:line="{interligne}" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/>
<w:pPr><w:jc w:val="{alignement}"/><w:ind w:firstLine="{int(r.retrait * CM)}"/></w:pPr></w:style>
{titre(1)}{titre(2)}{titre(3)}
<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:spacing w:before="120" w:after="120" w:line="240" w:lineRule="auto"/><w:ind w:left="{CM}" w:right="{CM}" w:firstLine="0"/></w:pPr>
<w:rPr><w:i/><w:sz w:val="{max(16, taille - 2)}"/><w:szCs w:val="{max(16, taille - 2)}"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:qFormat/>
<w:pPr><w:spacing w:after="60"/><w:ind w:left="720" w:hanging="360"/><w:contextualSpacing/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="PageDeGarde"><w:name w:val="Page de garde"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:after="0" w:line="276" w:lineRule="auto"/><w:jc w:val="center"/><w:ind w:firstLine="0"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="TitreSommaire"><w:name w:val="TOC Heading"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
<w:pPr><w:spacing w:before="0" w:after="240" w:line="240" w:lineRule="auto"/><w:jc w:val="left"/><w:ind w:firstLine="0"/></w:pPr>
<w:rPr><w:b/><w:color w:val="{couleur}"/><w:sz w:val="{int(r.tailles_titres[0] * 2)}"/></w:rPr></w:style>
{entree_sommaire(1)}{entree_sommaire(2)}{entree_sommaire(3)}
<w:style w:type="paragraph" w:styleId="Tableau"><w:name w:val="Texte de tableau"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:before="40" w:after="40" w:line="240" w:lineRule="auto"/><w:jc w:val="left"/><w:ind w:firstLine="0"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Footer"><w:name w:val="footer"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/><w:ind w:firstLine="0"/></w:pPr></w:style>
</w:styles>'''


def numerotation(reglages, listes_numerotees):
    formats = {
        "decimale": [("decimal", "%1."), ("decimal", "%1.%2."), ("decimal", "%1.%2.%3.")],
        "romaine": [("upperRoman", "%1."), ("upperLetter", "%2."), ("decimal", "%3.")],
    }.get(reglages.numerotation, [("decimal", "%1.")] * 3)
    prefixe = attribut(reglages.prefixe_chapitre.strip() + " ") if reglages.prefixe_chapitre.strip() else ""
    niveaux = "".join(
        f'<w:lvl w:ilvl="{i}"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/><w:pStyle w:val="Heading{i + 1}"/>'
        f'<w:lvlText w:val="{prefixe if i == 0 else ""}{texte}"/><w:lvlJc w:val="left"/><w:suff w:val="space"/>'
        f'<w:pPr><w:ind w:left="0" w:firstLine="0"/></w:pPr></w:lvl>'
        for i, (fmt, texte) in enumerate(formats))
    instances = "".join(
        f'<w:num w:numId="{n}"><w:abstractNumId w:val="2"/><w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>'
        for n in listes_numerotees)
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering {ESPACES}>
<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="multilevel"/>{niveaux}</w:abstractNum>
<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="hybridMultilevel"/>
<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/><w:lvlJc w:val="left"/>
<w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl></w:abstractNum>
<w:abstractNum w:abstractNumId="2"><w:multiLevelType w:val="hybridMultilevel"/>
<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/><w:lvlJc w:val="left"/>
<w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl></w:abstractNum>
<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>
{instances}
</w:numbering>'''


def pied_de_page(reglages):
    alignement = "right" if reglages.pagination == "droite" else "center"
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr {ESPACES}><w:p><w:pPr><w:pStyle w:val="Footer"/><w:jc w:val="{alignement}"/></w:pPr>
<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>
<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>'''


def ecrire_docx(blocs, reglages):
    """Renvoie le contenu du fichier .docx (en octets)."""
    r = reglages
    listes_numerotees = []
    contenu = ""
    if r.garde.afficher:
        contenu += page_de_garde(r.garde)
    if r.sommaire:
        contenu += sommaire(blocs, r, saut_avant=r.garde.afficher)
    contenu += corps(blocs, r, listes_numerotees, saut_avant=r.garde.afficher or r.sommaire)
    avec_pied = r.pagination != "aucune"
    reference_pied = '<w:footerReference w:type="default" r:id="rIdPied"/>' if avec_pied else ""
    section = (f'<w:sectPr>{reference_pied}<w:pgSz w:w="11906" w:h="16838"/>'
               f'<w:pgMar w:top="{int(r.marge_haut * CM)}" w:right="{int(r.marge_droite * CM)}" '
               f'w:bottom="{int(r.marge_bas * CM)}" w:left="{int(r.marge_gauche * CM)}" '
               f'w:header="708" w:footer="{int(min(r.marge_bas, 1.25) * CM)}" w:gutter="0"/>'
               f'{"<w:titlePg/>" if r.garde.afficher else ""}</w:sectPr>')  # titlePg : pas de numéro sur la 1re page
    document = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document {ESPACES}><w:body>{contenu}{section}</w:body></w:document>'

    relations_document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                          '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                          '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                          '<Relationship Id="rIdNum" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
                          '<Relationship Id="rIdSettings" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>'
                          + ('<Relationship Id="rIdPied" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>' if avec_pied else "")
                          + "</Relationships>")
    types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
             '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
             '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
             '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
             '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
             '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
             "</Types>")
    relations = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                 '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                 "</Relationships>")
    # updateFields : à l'ouverture, Word propose de mettre à jour le sommaire (et calcule les numéros de page).
    reglages_word = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:settings {ESPACES}>'
                     '<w:updateFields w:val="true"/><w:defaultTabStop w:val="708"/>'
                     '<w:characterSpacingControl w:val="doNotCompress"/><w:compat><w:compatSetting w:name="compatibilityMode" '
                     'w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat></w:settings>')
    maintenant = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    proprietes = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                  '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                  'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
                  'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                  f"<dc:title>{escape(r.garde.titre)}</dc:title><dc:creator>{escape(r.garde.auteur)}</dc:creator>"
                  f'<dc:language>fr-FR</dc:language><dcterms:created xsi:type="dcterms:W3CDTF">{maintenant}</dcterms:created>'
                  "</cp:coreProperties>")

    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", types)
        archive.writestr("_rels/.rels", relations)
        archive.writestr("docProps/core.xml", proprietes)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", styles(r))
        archive.writestr("word/numbering.xml", numerotation(r, listes_numerotees))
        archive.writestr("word/settings.xml", reglages_word)
        archive.writestr("word/_rels/document.xml.rels", relations_document)
        if avec_pied:
            archive.writestr("word/footer1.xml", pied_de_page(r))
    return tampon.getvalue()

