"""L'aperçu en direct : le mémoire en HTML, avec la même mise en forme que les exports."""

from html import escape

from .source import Citation, Liste, Paragraphe, SautDePage, Tableau, Titre

FAMILLES_CSS = {
    "Times New Roman": '"Times New Roman", "Liberation Serif", Times, serif',
    "Arial": 'Arial, "Liberation Sans", Helvetica, sans-serif',
    "Calibri": 'Calibri, Carlito, "Segoe UI", sans-serif',
    "Garamond": 'Garamond, "EB Garamond", "Times New Roman", serif',
    "Georgia": 'Georgia, Gelasio, serif',
    "Cambria": 'Cambria, Caladea, Georgia, serif',
}


def html_morceaux(morceaux):
    resultat = ""
    for m in morceaux:
        texte = escape(m.texte)
        if m.italique:
            texte = f"<em>{texte}</em>"
        if m.gras:
            texte = f"<strong>{texte}</strong>"
        resultat += texte
    return resultat


def feuille_de_style(r):
    return f"""
.feuille {{ font-family: {FAMILLES_CSS.get(r.police, "serif")}; font-size: {r.taille}pt;
  line-height: {1.15 * r.interligne:.3f}; padding: {r.marge_haut}cm {r.marge_droite}cm {r.marge_bas}cm {r.marge_gauche}cm; }}
.feuille p {{ text-align: {"justify" if r.alignement == "justifie" else "left"}; text-indent: {r.retrait}cm;
  margin: 0 0 {r.espace_apres}pt; hyphens: auto; }}
.feuille h1, .feuille h2, .feuille h3, .feuille .titre-sommaire {{ color: {r.couleur_titres}; line-height: 1.2; font-weight: bold; }}
.feuille h1, .feuille .titre-sommaire {{ font-size: {r.tailles_titres[0]}pt; margin: 24pt 0 12pt; }}
.feuille h2 {{ font-size: {r.tailles_titres[1]}pt; margin: 18pt 0 8pt; }}
.feuille h3 {{ font-size: {r.tailles_titres[2]}pt; margin: 12pt 0 6pt; font-style: italic; }}
.feuille > :first-child {{ margin-top: 0; }}
.feuille blockquote {{ margin: 6pt 1cm; font-style: italic; font-size: {max(8, r.taille - 1)}pt; line-height: 1.2; }}
.feuille ul, .feuille ol {{ margin: 0 0 {r.espace_apres}pt; padding-left: 1.27cm; }}
.feuille table {{ border-collapse: collapse; width: 100%; margin: 4pt 0 10pt; line-height: 1.2; }}
.feuille th, .feuille td {{ border: 0.5pt solid #808080; padding: 2pt 4pt; text-align: left; vertical-align: top; }}
.feuille th {{ background: #e7e6e6; }}
.sommaire .entree {{ display: flex; gap: 4pt; line-height: 1.5; }}
.sommaire .entree .points {{ flex: 1; border-bottom: 1.5pt dotted #777; margin-bottom: 0.35em; }}
.sommaire .niveau1 {{ font-weight: bold; }}
.sommaire .niveau2 {{ padding-left: 0.7cm; }}
.sommaire .niveau3 {{ padding-left: 1.4cm; }}
.garde {{ display: flex; flex-direction: column; align-items: center; text-align: center; line-height: 1.25; }}
"""


def apercu(blocs, reglages, entrees_sommaire=None):
    """Renvoie le HTML de l'aperçu : une « feuille » par partie (page de garde, sommaire, chapitres…).

    entrees_sommaire : [(niveau, texte, page)] calculées par l'export PDF, pour afficher les vrais numéros de page.
    """
    r = reglages
    feuilles = []

    if r.garde.afficher:
        g = r.garde
        lignes = [
            (g.universite, "font-size:14pt;font-weight:bold", 0), (g.faculte, "font-size:12pt", 0.1),
            (g.type_document, "font-size:13pt", 4), (g.titre, "font-size:22pt;font-weight:bold", 0.8),
            (g.sous_titre, "font-size:14pt;font-style:italic", 0.3),
            ("Présenté par" if g.auteur else "", "font-size:12pt", 3), (g.auteur, "font-size:14pt;font-weight:bold", 0.1),
            ("Sous la direction de" if g.directeur else "", "font-size:12pt", 0.8), (g.directeur, "font-size:13pt", 0.1),
            (g.annee, "font-size:12pt", 2),
        ]
        contenu = "".join(f'<div style="{style};margin-top:{avant}cm">{escape(texte)}</div>'
                          for texte, style, avant in lignes if texte)
        feuilles.append(("garde", contenu))

    if r.sommaire:
        if entrees_sommaire is None:
            entrees = [(b.niveau, f"{b.numero} {b.texte}".strip(), "") for b in blocs if isinstance(b, Titre)]
        else:
            entrees = list(entrees_sommaire)
        entrees = [e for e in entrees if e[0] <= r.profondeur_sommaire]
        lignes = "".join(f'<div class="entree niveau{n}"><span>{escape(t)}</span><span class="points"></span>'
                         f"<span>{p}</span></div>" for n, t, p in entrees)
        feuilles.append(("sommaire", f'<div class="titre-sommaire">{escape(r.titre_sommaire)}</div>{lignes}'))

    courante = []

    def nouvelle_feuille():
        if courante:
            feuilles.append(("", "".join(courante)))
            courante.clear()

    for bloc in blocs:
        if isinstance(bloc, Titre):
            if bloc.niveau == 1 and r.chapitre_nouvelle_page:
                nouvelle_feuille()
            numero = bloc.numero
            if bloc.niveau == 1 and numero and r.prefixe_chapitre.strip():
                numero = f"{r.prefixe_chapitre.strip()} {numero}"
            texte = f"{numero} {bloc.texte}".strip()
            courante.append(f"<h{bloc.niveau}>{escape(texte)}</h{bloc.niveau}>")
        elif isinstance(bloc, Paragraphe):
            courante.append(f"<p>{html_morceaux(bloc.morceaux)}</p>")
        elif isinstance(bloc, Citation):
            courante.append(f"<blockquote>{html_morceaux(bloc.morceaux)}</blockquote>")
        elif isinstance(bloc, Liste):
            balise = "ol" if bloc.ordonnee else "ul"
            elements = "".join(f"<li>{html_morceaux(e)}</li>" for e in bloc.elements)
            courante.append(f"<{balise}>{elements}</{balise}>")
        elif isinstance(bloc, Tableau):
            lignes = []
            for rang, ligne in enumerate(bloc.lignes):
                balise = "th" if rang == 0 else "td"
                lignes.append("<tr>" + "".join(f"<{balise}>{html_morceaux(c)}</{balise}>" for c in ligne) + "</tr>")
            courante.append(f"<table>{''.join(lignes)}</table>")
        elif isinstance(bloc, SautDePage):
            nouvelle_feuille()
    nouvelle_feuille()

    html = [f"<style>{feuille_de_style(r)}</style>"]
    for classe, contenu in feuilles:
        html.append(f'<section class="feuille {classe}">{contenu}</section>')
    return "".join(html)
