"""La fenêtre du navigateur (Tkinter) : barre d'adresse, historique, défilement et liens cliquables."""

import tkinter as tk

from .mise_en_page import DessinLigne, DessinRect, DessinTexte, Disposition
from .page import charger
from .polices import PolicesTk
from .reseau import ErreurReseau

PAS_DEFILEMENT = 60
GRIS = "#eceff3"


class Navigateur:
    def __init__(self, adresse="about:accueil", largeur=1024, hauteur=720):
        self.racine = tk.Tk()
        self.racine.title("Toile")
        self.racine.geometry(f"{largeur}x{hauteur}")
        self.polices = PolicesTk()
        self.historique = []
        self.position = -1
        self.page = None
        self.disposition = None
        self.defilement = 0.0
        self.largeur_disposee = None
        self._redimension_prevue = None
        self.construire_interface()
        self.aller(adresse)

    # --- Interface ------------------------------------------------------------------------
    def construire_interface(self):
        barre = tk.Frame(self.racine, bg=GRIS, padx=6, pady=6)
        barre.pack(side="top", fill="x")
        style_bouton = dict(relief="flat", bg=GRIS, activebackground="#dfe3e8", font=("Helvetica", 14), width=2,
                            borderwidth=0, cursor="hand2")
        self.bouton_retour = tk.Button(barre, text="◀", command=self.precedente, **style_bouton)
        self.bouton_avance = tk.Button(barre, text="▶", command=self.suivante, **style_bouton)
        for bouton in (self.bouton_retour, self.bouton_avance,
                       tk.Button(barre, text="⟳", command=self.recharger, **style_bouton),
                       tk.Button(barre, text="⌂", command=lambda: self.aller("about:accueil"), **style_bouton)):
            bouton.pack(side="left", padx=1)
        self.saisie = tk.Entry(barre, font=("Helvetica", 13), relief="flat", highlightthickness=1,
                               highlightcolor="#1a73e8", highlightbackground="#c9ced6")
        self.saisie.pack(side="left", fill="x", expand=True, padx=(8, 2), ipady=4)
        self.saisie.bind("<Return>", lambda _e: self.aller(self.saisie.get()))

        self.statut = tk.Label(self.racine, anchor="w", bg=GRIS, fg="#555555", font=("Helvetica", 10), padx=8)
        self.statut.pack(side="bottom", fill="x")

        zone = tk.Frame(self.racine)
        zone.pack(side="top", fill="both", expand=True)
        self.ascenseur = tk.Scrollbar(zone, orient="vertical", command=self.ascenseur_bouge)
        self.ascenseur.pack(side="right", fill="y")
        self.toile = tk.Canvas(zone, bg="white", highlightthickness=0)
        self.toile.pack(side="left", fill="both", expand=True)

        self.toile.bind("<Configure>", self.redimensionner)
        self.toile.bind("<Button-1>", self.clic)
        self.toile.bind("<Motion>", self.survol)
        self.toile.bind("<MouseWheel>", lambda e: self.defiler(-e.delta / (120 if abs(e.delta) >= 120 else 1) * PAS_DEFILEMENT / 3))
        self.toile.bind("<Button-4>", lambda _e: self.defiler(-PAS_DEFILEMENT))
        self.toile.bind("<Button-5>", lambda _e: self.defiler(PAS_DEFILEMENT))
        for touche, pas in (("<Down>", PAS_DEFILEMENT), ("<Up>", -PAS_DEFILEMENT), ("<Next>", "page"),
                            ("<Prior>", "-page"), ("<space>", "page")):
            self.racine.bind(touche, lambda e, pas=pas: self.touche_defilement(e, pas))
        self.racine.bind("<Home>", lambda e: self.hors_saisie(e) and self.defiler_a(0))
        self.racine.bind("<End>", lambda e: self.hors_saisie(e) and self.defiler_a(float("inf")))
        self.racine.bind("<Alt-Left>", lambda _e: self.precedente())
        self.racine.bind("<Alt-Right>", lambda _e: self.suivante())
        self.racine.bind("<F5>", lambda _e: self.recharger())
        self.racine.bind("<Control-l>", lambda _e: (self.saisie.focus_set(), self.saisie.select_range(0, "end")))

    def hors_saisie(self, evenement):
        return evenement.widget is not self.saisie

    def touche_defilement(self, evenement, pas):
        if not self.hors_saisie(evenement):
            return
        hauteur = self.toile.winfo_height()
        self.defiler({"page": hauteur * 0.9, "-page": -hauteur * 0.9}.get(pas, pas))

    # --- Navigation -----------------------------------------------------------------------
    def aller(self, adresse, ajouter=True):
        self.statut.config(text=f"Chargement de {adresse}…")
        self.racine.config(cursor="watch")
        self.racine.update_idletasks()
        page = charger(adresse)
        self.racine.config(cursor="")
        if ajouter:
            del self.historique[self.position + 1:]
            self.historique.append(adresse if isinstance(adresse, str) else str(adresse))
            self.position = len(self.historique) - 1
        self.page = page
        self.racine.title(f"{page.titre or page.url} — Toile")
        self.saisie.delete(0, "end")
        self.saisie.insert(0, str(page.url))
        self.bouton_retour.config(state="normal" if self.position > 0 else "disabled")
        self.bouton_avance.config(state="normal" if self.position < len(self.historique) - 1 else "disabled")
        self.defilement = 0.0
        self.disposer()
        ancre = getattr(page.url, "ancre", "")
        if ancre and ancre in self.disposition.ancres:
            self.defiler_a(self.disposition.ancres[ancre])
        self.statut.config(text="")

    def precedente(self):
        if self.position > 0:
            self.position -= 1
            self.aller(self.historique[self.position], ajouter=False)

    def suivante(self):
        if self.position < len(self.historique) - 1:
            self.position += 1
            self.aller(self.historique[self.position], ajouter=False)

    def recharger(self):
        if self.historique:
            position = self.defilement
            self.aller(self.historique[self.position], ajouter=False)
            self.defiler_a(position)

    # --- Mise en page et dessin -----------------------------------------------------------
    def disposer(self):
        largeur = max(200, self.toile.winfo_width())
        self.largeur_disposee = largeur
        self.disposition = Disposition(self.page.arbre, self.polices, largeur)
        self.dessiner()

    def redimensionner(self, evenement):
        if self.page is None or evenement.width == self.largeur_disposee:
            self.dessiner()
            return
        # On attend que l'utilisateur ait fini de redimensionner avant de tout recalculer.
        if self._redimension_prevue:
            self.racine.after_cancel(self._redimension_prevue)
        self._redimension_prevue = self.racine.after(80, self.disposer)

    def dessiner(self):
        if self.disposition is None:
            return
        t = self.toile
        t.delete("all")
        t.config(bg=self.disposition.fond)
        haut, hauteur = self.defilement, t.winfo_height()
        bas = haut + hauteur
        for ordre in self.disposition.dessins:
            if isinstance(ordre, DessinRect):
                if ordre.y2 < haut or ordre.y1 > bas:
                    continue
                t.create_rectangle(ordre.x1, ordre.y1 - haut, ordre.x2, ordre.y2 - haut, fill=ordre.couleur, width=0)
            elif isinstance(ordre, DessinTexte):
                if ordre.y > bas or ordre.y + ordre.police[1] * 2 < haut:
                    continue
                t.create_text(ordre.x, ordre.y - haut, text=ordre.texte, anchor="nw", fill=ordre.couleur,
                              font=self.polices.police(ordre.police))
            elif isinstance(ordre, DessinLigne):
                if max(ordre.y1, ordre.y2) < haut or min(ordre.y1, ordre.y2) > bas:
                    continue
                t.create_line(ordre.x1, ordre.y1 - haut, ordre.x2, ordre.y2 - haut, fill=ordre.couleur,
                              width=ordre.epaisseur)
        total = max(self.disposition.hauteur, 1)
        self.ascenseur.set(haut / total, min(1.0, bas / total))

    # --- Défilement -------------------------------------------------------------------------
    def defiler_a(self, position):
        if self.disposition is None:
            return
        maximum = max(0.0, self.disposition.hauteur - self.toile.winfo_height())
        self.defilement = min(max(0.0, position), maximum)
        self.dessiner()

    def defiler(self, pas):
        self.defiler_a(self.defilement + pas)

    def ascenseur_bouge(self, action, valeur, unite=None):
        if action == "moveto":
            self.defiler_a(float(valeur) * self.disposition.hauteur)
        elif action == "scroll":
            pas = self.toile.winfo_height() * 0.9 if unite == "pages" else PAS_DEFILEMENT
            self.defiler(int(valeur) * pas)

    # --- Souris ---------------------------------------------------------------------------------
    def clic(self, evenement):
        self.toile.focus_set()
        href = self.disposition.lien_a(evenement.x, evenement.y + self.defilement) if self.disposition else None
        if not href:
            return
        if href.startswith("#"):
            if href[1:] in self.disposition.ancres:
                self.defiler_a(self.disposition.ancres[href[1:]])
            return
        if href.lower().startswith(("javascript:", "mailto:", "tel:")):
            self.statut.config(text=f"Toile ne sait pas ouvrir ce genre de lien : {href}")
            return
        try:
            self.aller(self.page.url.resoudre(href))
        except (ErreurReseau, ValueError) as erreur:
            self.statut.config(text=str(erreur))

    def survol(self, evenement):
        href = self.disposition.lien_a(evenement.x, evenement.y + self.defilement) if self.disposition else None
        self.toile.config(cursor="hand2" if href else "")
        if href:
            try:
                self.statut.config(text=str(self.page.url.resoudre(href)) if not href.startswith("#") else href)
            except (ErreurReseau, ValueError):
                self.statut.config(text=href)
        elif not self.statut.cget("text").startswith("Chargement"):
            self.statut.config(text="")

    def lancer(self):
        self.racine.mainloop()


def ouvrir(adresse="about:accueil"):
    Navigateur(adresse).lancer()

