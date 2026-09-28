"use strict";

// L'application Rédigo : connexion, tableau de bord et éditeur.

let config = null;       // polices, normes, formules… (envoyé par le serveur)
let moi = null;          // le compte connecté et sa formule
let projet = null;       // le mémoire ouvert
let references = [];
let commentaires = [];
let modeles = { licence: null, perso: [] };
let minuterieEnregistrement = null;
let enregistrementEnCours = null;
let modifie = false;
let numeroApercu = 0;
const texte = $("#texte");

// --- Navigation ----------------------------------------------------------------------------------

function afficherVue(nom) {
  for (const vue of $$(".vue")) vue.hidden = vue.id !== `vue-${nom}`;
}

async function router() {
  const ancre = location.hash.slice(1);
  if (ancre.startsWith("reinitialiser=")) {
    afficherAuth("reinitialiser");
    return;
  }
  if (!moi) {
    afficherAuth(ancre === "inscription" ? "inscription" : "connexion");
    return;
  }
  const trouve = ancre.match(/^projet\/(\d+)$/);
  if (trouve) {
    await ouvrirProjet(Number(trouve[1]));
  } else {
    await fermerProjet();
    await afficherTableau();
  }
}

// --- Connexion et inscription ---------------------------------------------------------------------

function afficherAuth(formulaire) {
  afficherVue("auth");
  document.title = "Rédigo — connexion";
  for (const f of $$("[data-formulaire]")) f.hidden = f.dataset.formulaire !== formulaire;
  for (const b of $$("[data-auth]")) b.setAttribute("aria-selected", String(b.dataset.auth === formulaire));
  $(".onglets-auth").hidden = !["connexion", "inscription"].includes(formulaire);
  messageAuth("");
  const premier = $(`[data-formulaire="${formulaire}"] input`);
  if (premier) premier.focus();
}

function messageAuth(message, type = "erreur") {
  const zone = $("#message-auth");
  zone.textContent = message;
  zone.className = `message ${type}`;
}

function brancherAuth() {
  for (const b of $$("[data-auth]")) b.addEventListener("click", () => { location.hash = b.dataset.auth; afficherAuth(b.dataset.auth); });
  for (const b of $$("[data-aller]")) b.addEventListener("click", () => afficherAuth(b.dataset.aller));
  for (const formulaire of $$("[data-formulaire]")) {
    formulaire.addEventListener("submit", async (e) => {
      e.preventDefault();
      const donnees = Object.fromEntries(new FormData(formulaire));
      const bouton = $("button[type=submit]", formulaire);
      bouton.disabled = true;
      try {
        const type = formulaire.dataset.formulaire;
        if (type === "oubli") {
          await api("/api/mot-de-passe/oubli", { methode: "POST", corps: donnees });
          messageAuth("Si un compte existe avec cette adresse, un e-mail vient d'être envoyé.", "ok");
          return;
        }
        if (type === "reinitialiser") donnees.jeton = location.hash.split("=")[1] || "";
        const chemin = { connexion: "/api/connexion", inscription: "/api/inscription",
          reinitialiser: "/api/mot-de-passe/reinitialiser" }[type];
        moi = await apiJson(chemin, { methode: "POST", corps: donnees });
        formulaire.reset();
        location.hash = "projets";
        if (type === "inscription") toast("Bienvenue sur Rédigo ! Crée ton premier mémoire.");
        await router();
      } catch (erreur) {
        messageAuth(erreur.message);
      } finally {
        bouton.disabled = false;
      }
    });
  }
}

// --- Tableau de bord -------------------------------------------------------------------------------------

function afficherFormule() {
  const f = moi.formule;
  for (const badge of $$(".badge-formule")) {
    badge.textContent = f.code === "gratuit" ? "Gratuit · passer au Pass" : f.nom;
    badge.classList.toggle("pass", f.code !== "gratuit");
  }
  for (const b of $$(".compte")) b.textContent = (moi.nom || moi.email).trim()[0].toUpperCase();
  $("#bandeau-gratuit").hidden = !f.mention;
}

async function afficherTableau() {
  afficherVue("tableau");
  document.title = "Mes mémoires — Rédigo";
  afficherFormule();
  const liste = $("#liste-projets");
  const { projets } = await apiJson("/api/projets");
  liste.replaceChildren();
  if (!projets.length) {
    liste.append(el("div", { class: "vide" },
      el("p", {}, "Tu n'as pas encore de mémoire."),
      el("button", { class: "principal", onclick: () => ouvrirDialogueNouveau() }, "Créer mon premier mémoire")));
  }
  for (const p of projets) {
    const carte = el("a", { class: "projet", href: `#projet/${p.id}` },
      el("div", { class: "miniature", "aria-hidden": "true" }),
      el("h3", {}, p.titre),
      el("div", { class: "meta" }, `Modifié ${dateRelative(p.modifie_le)}`,
        p.nouveaux_commentaires ? el("span", { class: "pastille" },
          `${p.nouveaux_commentaires} commentaire${p.nouveaux_commentaires > 1 ? "s" : ""}`) : null),
      el("button", { class: "supprimer", title: "Supprimer ce mémoire", "aria-label": `Supprimer ${p.titre}`,
        onclick: (e) => { e.preventDefault(); supprimerProjet(p); } }, "✕"));
    liste.append(carte);
  }
  const parametres = new URLSearchParams(location.search);
  const bandeau = $("#bandeau-paiement");
  bandeau.hidden = !parametres.get("paiement");
  if (parametres.get("paiement") === "reussi") {
    bandeau.textContent = moi.formule.code === "pass"
      ? "Merci ! Ton Pass Mémoire est activé."
      : "Merci ! Ton paiement est en cours de confirmation : le Pass sera activé dans quelques instants.";
  } else if (parametres.get("paiement") === "annule") {
    bandeau.textContent = "Paiement annulé : rien n'a été débité.";
  }
}

async function supprimerProjet(p) {
  if (!confirm(`Supprimer définitivement « ${p.titre} » ? Ses versions, sources et commentaires seront aussi supprimés.`)) return;
  try {
    await api(`/api/projets/${p.id}`, { methode: "DELETE" });
    toast("Mémoire supprimé.");
    await afficherTableau();
  } catch (e) {
    toast(e.message, true);
  }
}

function listeDesModeles() {
  const choix = Object.entries(config.normes).map(([cle, n]) => ({ valeur: `norme:${cle}`, nom: n.nom, reglages: n.reglages }));
  if (modeles.licence) choix.unshift({ valeur: "licence", nom: modeles.licence.nom, reglages: modeles.licence.reglages });
  for (const m of modeles.perso) choix.push({ valeur: `perso:${m.id}`, nom: `Mon modèle : ${m.nom}`, reglages: m.reglages });
  return choix;
}

function remplirModeles(select, avecInvite) {
  select.replaceChildren();
  if (avecInvite) select.add(new Option("Choisir…", ""));
  for (const m of listeDesModeles()) select.add(new Option(m.nom, m.valeur));
}

async function chargerModeles() {
  modeles = await apiJson("/api/modeles");
}

async function ouvrirDialogueNouveau() {
  await chargerModeles();
  remplirModeles($("#modele-nouveau"), false);
  const dialogue = $("#dialogue-nouveau");
  $("#form-nouveau").reset();
  dialogue.showModal();
}

function brancherTableau() {
  $("#nouveau-projet").addEventListener("click", ouvrirDialogueNouveau);
  $("#dialogue-nouveau").addEventListener("close", async () => {
    const dialogue = $("#dialogue-nouveau");
    if (dialogue.returnValue !== "creer") return;
    const donnees = Object.fromEntries(new FormData($("#form-nouveau")));
    const modele = listeDesModeles().find((m) => m.valeur === donnees.modele);
    try {
      const cree = await apiJson("/api/projets", { methode: "POST", corps: {
        titre: donnees.titre, exemple: Boolean(donnees.exemple), reglages: modele ? modele.reglages : config.defaut } });
      location.hash = `projet/${cree.id}`;
    } catch (e) {
      if (e.statut === 402) ouvrirFormule(e.message);
      else toast(e.message, true);
    }
  });
}

// --- Formule, paiement et compte --------------------------------------------------------------------------

function ouvrirFormule(message = "") {
  const f = moi.formule;
  let texteFormule = `Tu es en formule ${f.nom}.`;
  if (f.code === "pass") texteFormule += ` Ton Pass est valable jusqu'au ${new Date(f.fin).toLocaleDateString("fr-FR")}.`;
  if (f.code === "universite") texteFormule = `Ton université (${f.universite}) t'offre toutes les fonctions jusqu'au ${new Date(f.fin).toLocaleDateString("fr-FR")}.`;
  $("#formule-actuelle").textContent = texteFormule;
  $("#offre-pass").hidden = f.code === "universite";
  $("#payer").textContent = f.code === "pass" ? "Prolonger d'un an" : "Obtenir le Pass";
  $("#prix-pass").textContent = `${(config.prix_pass / 100).toLocaleString("fr-FR", { minimumFractionDigits: 2 })} €`;
  $("#payer").disabled = !config.paiement;
  $("#note-paiement").textContent = {
    stripe: "Paiement sécurisé par carte bancaire avec Stripe. Rédigo ne voit jamais ton numéro de carte.",
    demo: "Mode démonstration : le Pass s'active sans paiement réel.",
  }[config.paiement] || "Le paiement en ligne n'est pas encore ouvert.";
  const zone = $("#message-formule");
  zone.textContent = message;
  zone.className = "message erreur";
  $("#dialogue-formule").showModal();
}

async function payer() {
  $("#payer").disabled = true;
  try {
    const reponse = await apiJson("/api/paiement/commande", { methode: "POST", corps: {} });
    if (reponse.url) {
      location.href = reponse.url;  // la page de paiement Stripe
      return;
    }
    moi = reponse;
    afficherFormule();
    $("#dialogue-formule").close();
    toast("Ton Pass Mémoire est activé. Merci !");
    if (!projet) await afficherTableau();
  } catch (e) {
    $("#message-formule").textContent = e.message;
  } finally {
    $("#payer").disabled = false;
  }
}

function messageCompte(message, type = "erreur") {
  const zone = $("#message-compte");
  zone.textContent = message;
  zone.className = `message ${type}`;
}

function brancherCompte() {
  for (const b of $$("[data-ouvrir]")) {
    b.addEventListener("click", () => {
      const cible = b.dataset.ouvrir;
      if (cible === "dialogue-formule") return ouvrirFormule();
      if (cible === "dialogue-partage") return ouvrirPartage();
      if (cible === "dialogue-compte") {
        $("#compte-email").textContent = `${moi.nom ? moi.nom + " · " : ""}${moi.email}`;
        messageCompte("");
      }
      $(`#${cible}`).showModal();
    });
  }
  $("#payer").addEventListener("click", payer);
  $("#deconnexion").addEventListener("click", async () => {
    await enregistrerMaintenant();
    await api("/api/deconnexion", { methode: "POST", corps: {} });
    moi = null;
    $("#dialogue-compte").close();
    location.hash = "connexion";
    await router();
  });
  $("#changer-mdp").addEventListener("click", async () => {
    try {
      await api("/api/compte/mot-de-passe", { methode: "POST", corps: { actuel: $("#mdp-actuel").value, nouveau: $("#mdp-nouveau").value } });
      $("#mdp-actuel").value = $("#mdp-nouveau").value = "";
      messageCompte("Mot de passe changé. Tes autres appareils ont été déconnectés.", "ok");
    } catch (e) {
      messageCompte(e.message);
    }
  });
  $("#exporter-donnees").addEventListener("click", async () => {
    try {
      const reponse = await api("/api/compte/export");
      telecharger(await reponse.blob(), "redigo-export.json");
    } catch (e) {
      messageCompte(e.message);
    }
  });
  $("#supprimer-compte").addEventListener("click", async () => {
    if (!confirm("Supprimer définitivement ton compte et tous tes mémoires ? Cette action est irréversible.")) return;
    try {
      await api("/api/compte/supprimer", { methode: "POST", corps: { mot_de_passe: $("#mdp-suppression").value } });
      location.href = "/";
    } catch (e) {
      messageCompte(e.message);
    }
  });
}

// --- Ouvrir et enregistrer un mémoire ---------------------------------------------------------------------------

async function ouvrirProjet(id) {
  if (projet && projet.id === id) return;
  await fermerProjet();
  try {
    projet = await apiJson(`/api/projets/${id}`);
  } catch (e) {
    toast(e.message, true);
    location.hash = "projets";
    return;
  }
  afficherVue("editeur");
  afficherFormule();
  document.title = `${projet.titre} — Rédigo`;
  $("#titre-projet").value = projet.titre;
  texte.value = projet.texte;
  $("#style-biblio").value = projet.style_biblio;
  $("#biblio-toutes").checked = projet.biblio_toutes;
  afficherReglages();
  etat("Enregistré");
  await Promise.all([chargerModeles().then(() => remplirModeles($("#choix-modele"), true)),
    chargerReferences(), chargerCommentaires(), chargerVersions()]);
  mettreAJourApercu();
}

async function fermerProjet() {
  if (!projet) return;
  await enregistrerMaintenant();
  projet = null;
  references = [];
  commentaires = [];
  $("#pages").replaceChildren();
}

function etat(message, erreur = false) {
  const zone = $("#etat");
  zone.textContent = message;
  zone.classList.toggle("erreur", erreur);
}

// Chaque modification est enregistrée automatiquement, un court instant après la dernière frappe.
function changement(champs) {
  Object.assign(projet, champs);
  projet.enAttente = { ...(projet.enAttente || {}), ...champs };
  modifie = true;
  etat("Modifications…");
  clearTimeout(minuterieEnregistrement);
  minuterieEnregistrement = setTimeout(enregistrerMaintenant, 700);
}

async function enregistrerMaintenant() {
  clearTimeout(minuterieEnregistrement);
  if (enregistrementEnCours) await enregistrementEnCours;
  if (!projet || !projet.enAttente) return;
  const champs = projet.enAttente;
  delete projet.enAttente;
  const id = projet.id;
  etat("Enregistrement…");
  enregistrementEnCours = (async () => {
    try {
      const { revision } = await apiJson(`/api/projets/${id}`, { methode: "PUT", corps: { ...champs, revision: projet.revision } });
      if (projet && projet.id === id) {
        projet.revision = revision;
        if (!projet.enAttente) { modifie = false; etat("Enregistré"); }
        mettreAJourApercu();
      }
    } catch (e) {
      if (projet && projet.id === id) projet.enAttente = { ...champs, ...(projet.enAttente || {}) };
      etat(e.statut === 409 ? "Modifié dans un autre onglet : recharge la page." : `Non enregistré : ${e.message}`, true);
      if (e.statut !== 409) minuterieEnregistrement = setTimeout(enregistrerMaintenant, 5000);
    } finally {
      enregistrementEnCours = null;
    }
  })();
  await enregistrementEnCours;
}

window.addEventListener("beforeunload", (e) => {
  if (modifie) {
    enregistrerMaintenant();
    e.preventDefault();
  }
});

async function mettreAJourApercu() {
  if (!projet) return;
  const numero = ++numeroApercu;
  const id = projet.id;
  try {
    const donnees = await apiJson(`/api/projets/${id}/apercu`, { methode: "POST", corps: {} });
    if (numero !== numeroApercu || !projet || projet.id !== id) return;  // une réponse plus récente arrive
    $("#pages").innerHTML = donnees.html;  // HTML produit par le serveur, dont tout le texte est échappé
    const mots = donnees.mots.toLocaleString("fr-FR");
    $("#infos").textContent = `${mots} mot${donnees.mots > 1 ? "s" : ""} · ${donnees.titres} titre${donnees.titres > 1 ? "s" : ""}`
      + ` · ${donnees.citees.length} source${donnees.citees.length > 1 ? "s" : ""} citée${donnees.citees.length > 1 ? "s" : ""}`;
    $("#alerte-citations").textContent = donnees.inconnues.length
      ? `Sources introuvables dans ta bibliographie : ${donnees.inconnues.map((c) => "@" + c).join(", ")}` : "";
  } catch (e) {
    if (numero === numeroApercu) etat(e.message, true);
  }
}

// --- Réglages ------------------------------------------------------------------------------------------------------

function remplirListe(select, valeurs) {
  select.replaceChildren();
  for (const [valeur, libelle] of Object.entries(valeurs)) select.add(new Option(libelle, valeur));
}

function afficherReglages() {
  const r = projet.reglages;
  for (const champ of $$("[data-cle]")) {
    let valeur = r[champ.dataset.cle];
    if (champ.dataset.index !== undefined) valeur = valeur[Number(champ.dataset.index)];
    if (champ.type === "checkbox") champ.checked = Boolean(valeur);
    else champ.value = String(valeur);
  }
  for (const champ of $$("[data-garde]")) {
    const valeur = r.garde[champ.dataset.garde];
    if (champ.type === "checkbox") champ.checked = Boolean(valeur);
    else champ.value = valeur ?? "";
  }
}

function lireChamp(champ, ancien) {
  if (champ.type === "checkbox") return champ.checked;
  if (champ.type === "number" || typeof ancien === "number") {
    const nombre = parseFloat(champ.value);
    return Number.isFinite(nombre) ? nombre : ancien;
  }
  return champ.value;
}

function brancherReglages() {
  for (const champ of $$("[data-cle]")) {
    champ.addEventListener("input", () => {
      const reglages = structuredClone(projet.reglages);
      const cle = champ.dataset.cle;
      if (champ.dataset.index !== undefined) {
        const i = Number(champ.dataset.index);
        reglages[cle] = [...reglages[cle]];
        reglages[cle][i] = lireChamp(champ, reglages[cle][i]);
      } else {
        reglages[cle] = lireChamp(champ, reglages[cle]);
      }
      changement({ reglages });
    });
  }
  for (const champ of $$("[data-garde]")) {
    champ.addEventListener("input", () => {
      const reglages = structuredClone(projet.reglages);
      reglages.garde[champ.dataset.garde] = lireChamp(champ, reglages.garde[champ.dataset.garde]);
      changement({ reglages });
    });
  }
  $("#choix-modele").addEventListener("change", (e) => {
    const modele = listeDesModeles().find((m) => m.valeur === e.target.value);
    e.target.value = "";
    if (!modele) return;
    const reglages = { ...structuredClone(config.defaut), ...structuredClone(modele.reglages), garde: projet.reglages.garde };
    changement({ reglages });
    afficherReglages();
    toast(`Modèle « ${modele.nom} » appliqué.`);
  });
  $("#enregistrer-modele").addEventListener("click", async () => {
    const nom = prompt("Nom de ce modèle (ex. : Consignes Master MEEF) :");
    if (!nom || !nom.trim()) return;
    try {
      await api("/api/modeles", { methode: "POST", corps: { nom: nom.trim(), reglages: projet.reglages } });
      await chargerModeles();
      remplirModeles($("#choix-modele"), true);
      toast("Modèle enregistré : tu le retrouveras en créant un mémoire.");
    } catch (e) {
      toast(e.message, true);
    }
  });
  $("#titre-projet").addEventListener("input", (e) => {
    document.title = `${e.target.value || "Sans titre"} — Rédigo`;
    changement({ titre: e.target.value });
  });
}

// --- Éditeur de texte ---------------------------------------------------------------------------------------------

function saisie() {
  texte.dispatchEvent(new Event("input"));
}

function remplacerSelection(avant, apres, exemple) {
  const debut = texte.selectionStart, fin = texte.selectionEnd;
  const choisi = texte.value.slice(debut, fin) || exemple;
  texte.focus();
  texte.setRangeText(avant + choisi + apres, debut, fin, "end");
  texte.setSelectionRange(debut + avant.length, debut + avant.length + choisi.length);
  saisie();
}

function prefixerLignes(prefixe, numeroter = false) {
  const valeur = texte.value;
  const debut = valeur.lastIndexOf("\n", texte.selectionStart - 1) + 1;
  let fin = valeur.indexOf("\n", texte.selectionEnd);
  if (fin === -1) fin = valeur.length;
  const lignes = valeur.slice(debut, fin).split("\n").map((ligne, i) => {
    const propre = ligne.replace(/^(#{1,3}\s+|[-*•]\s+|\d+[.)]\s+|>\s*)/, "");
    return (numeroter ? `${i + 1}. ` : prefixe) + propre;
  });
  texte.focus();
  texte.setRangeText(lignes.join("\n"), debut, fin, "end");
  saisie();
}

function inserer(bloc) {
  const debut = texte.selectionStart;
  const avant = texte.value.slice(0, debut);
  const separation = avant && !avant.endsWith("\n\n") ? (avant.endsWith("\n") ? "\n" : "\n\n") : "";
  texte.focus();
  texte.setRangeText(separation + bloc + "\n\n", debut, texte.selectionEnd, "end");
  saisie();
}

function insererCitation(cle, precision = "") {
  const debut = texte.selectionStart;
  const avant = texte.value.slice(Math.max(0, debut - 1), debut);
  const espace = avant && !/[\s(]/.test(avant) ? " " : "";
  texte.focus();
  texte.setRangeText(`${espace}[@${cle}${precision ? ", " + precision : ""}]`, debut, texte.selectionEnd, "end");
  saisie();
}

const actions = {
  titre1: () => prefixerLignes("# "),
  titre2: () => prefixerLignes("## "),
  titre3: () => prefixerLignes("### "),
  gras: () => remplacerSelection("**", "**", "texte en gras"),
  italique: () => remplacerSelection("*", "*", "texte en italique"),
  puces: () => prefixerLignes("- "),
  numeros: () => prefixerLignes("", true),
  citation: () => prefixerLignes("> "),
  tableau: () => inserer("| Colonne 1 | Colonne 2 | Colonne 3 |\n|---|---|---|\n| … | … | … |\n| … | … | … |"),
  saut: () => inserer("---saut de page---"),
  citer: () => ouvrirCiter(),
};

function brancherEditeur() {
  for (const bouton of $$(".onglets button")) {
    bouton.addEventListener("click", () => {
      const groupe = bouton.closest(".onglets");
      for (const autre of $$("button", groupe)) autre.setAttribute("aria-selected", String(autre === bouton));
      for (const autre of $$("button", groupe)) $(`#onglet-${autre.dataset.onglet}`).hidden = autre !== bouton;
      if (bouton.dataset.onglet === "commentaires") chargerCommentaires(true);
      if (bouton.dataset.onglet === "versions") chargerVersions();
    });
  }
  for (const bouton of $$("[data-action]")) bouton.addEventListener("click", () => actions[bouton.dataset.action]());
  texte.addEventListener("input", () => changement({ texte: texte.value }));
  texte.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") { e.preventDefault(); actions.gras(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "i") { e.preventDefault(); actions.italique(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); enregistrerMaintenant(); }
  });
  // Sur un petit écran, la page entière tient dans la largeur.
  let zoom = innerWidth <= 900 ? Math.max(0.3, Math.min(0.6, (innerWidth - 40) / 794)) : 0.6;
  const appliquerZoom = () => {
    $("#pages").style.setProperty("--zoom", zoom);
    $("#zoom-valeur").textContent = `${Math.round(zoom * 100)} %`;
  };
  $("#zoom-moins").addEventListener("click", () => { zoom = Math.max(0.3, zoom - 0.1); appliquerZoom(); });
  $("#zoom-plus").addEventListener("click", () => { zoom = Math.min(1.5, zoom + 0.1); appliquerZoom(); });
  appliquerZoom();

  $("#export-docx").addEventListener("click", () => exporter("docx"));
  $("#export-pdf").addEventListener("click", () => exporter("pdf"));
  $("#importer-docx").addEventListener("change", async (e) => {
    const fichier = e.target.files[0];
    e.target.value = "";
    if (!fichier) return;
    try {
      const { texte: importe } = await apiJson("/api/importer-docx", { methode: "POST", corps: await fichier.arrayBuffer(), brut: true });
      if (texte.value.trim() && !confirm("Remplacer le texte actuel par celui du document Word ? (Une version de l'actuel est gardée.)")) return;
      await api(`/api/projets/${projet.id}/versions`, { methode: "POST", corps: { libelle: "Avant l'import Word" } });
      texte.value = importe;
      saisie();
      toast("Document Word importé : vérifie les titres (# ## ###) repérés automatiquement.");
    } catch (erreur) {
      toast(erreur.message, true);
    }
  });
}

async function exporter(format) {
  await enregistrerMaintenant();
  const bouton = $(`#export-${format}`);
  bouton.disabled = true;
  etat(format === "pdf" ? "Création du PDF…" : "Création du fichier Word…");
  try {
    const reponse = await api(`/api/projets/${projet.id}/export/${format}`, { methode: "POST", corps: {} });
    telecharger(await reponse.blob(), nomDuFichier(reponse, `memoire.${format}`));
    etat("Enregistré");
    toast(format === "docx"
      ? "Fichier Word créé. À l'ouverture, accepte la mise à jour des champs pour remplir le sommaire."
      : "PDF créé.");
  } catch (e) {
    etat(e.message, true);
  } finally {
    bouton.disabled = false;
  }
}

// --- Bibliographie -------------------------------------------------------------------------------------------------

function resumeReference(r) {
  const auteurs = r.auteurs.split(";").map((a) => a.split(",")[0].trim()).filter(Boolean);
  const qui = auteurs.length > 2 ? `${auteurs[0]} et al.` : auteurs.join(" et ") || "Sans auteur";
  return `${qui} (${r.annee || "s.d."}) — ${r.titre || "Sans titre"}`;
}

async function chargerReferences() {
  references = (await apiJson(`/api/projets/${projet.id}/references`)).references;
  afficherReferences();
}

function correspond(r, filtre) {
  const f = filtre.trim().toLowerCase();
  return !f || [r.cle, r.auteurs, r.titre, r.annee].join(" ").toLowerCase().includes(f);
}

function afficherReferences() {
  const liste = $("#liste-references");
  const filtre = $("#filtre-references").value;
  liste.replaceChildren();
  if (!references.length) {
    liste.append(el("li", { class: "petit" }, "Aucune source pour l'instant. Ajoute-en une, ou importe un fichier BibTeX depuis Zotero."));
  }
  for (const r of references.filter((x) => correspond(x, filtre))) {
    liste.append(el("li", {},
      el("div", { class: "entete-ref" },
        el("span", { class: "cle" }, `@${r.cle}`),
        el("span", { class: "actions" },
          el("button", { title: "Insérer la citation à l'endroit du curseur", onclick: () => insererCitation(r.cle) }, "Citer"),
          el("button", { onclick: () => ouvrirReference(r) }, "Modifier"),
          el("button", { class: "danger", "aria-label": `Supprimer ${r.cle}`, onclick: () => supprimerReference(r) }, "✕"))),
      el("span", { class: "resume" }, `${config.types_references[r.type] || ""} · ${resumeReference(r)}`)));
  }
}

function afficherChampsReference() {
  const type = $("#type-reference").value;
  for (const bloc of $$("#form-reference [data-types]")) bloc.hidden = !bloc.dataset.types.split(" ").includes(type);
}

let referenceEnCours = null;

function ouvrirReference(reference = null) {
  referenceEnCours = reference;
  const formulaire = $("#form-reference");
  formulaire.reset();
  $("#titre-reference").textContent = reference ? "Modifier la source" : "Nouvelle source";
  $("#message-reference").textContent = "";
  if (reference) {
    for (const [cle, valeur] of Object.entries(reference)) {
      if (formulaire.elements[cle]) formulaire.elements[cle].value = valeur;
    }
  }
  afficherChampsReference();
  $("#dialogue-reference").showModal();
}

async function enregistrerReference(e) {
  if (e.submitter && e.submitter.value === "annuler") return;
  e.preventDefault();
  const donnees = Object.fromEntries(new FormData($("#form-reference")));
  try {
    const chemin = `/api/projets/${projet.id}/references` + (referenceEnCours ? `/${referenceEnCours.id}` : "");
    await api(chemin, { methode: referenceEnCours ? "PUT" : "POST", corps: donnees });
    $("#dialogue-reference").close();
    await chargerReferences();
    mettreAJourApercu();
  } catch (erreur) {
    const zone = $("#message-reference");
    zone.textContent = erreur.message;
    zone.className = "message erreur";
  }
}

async function supprimerReference(r) {
  if (!confirm(`Supprimer la source « ${resumeReference(r)} » ?`)) return;
  await api(`/api/projets/${projet.id}/references/${r.id}`, { methode: "DELETE" });
  await chargerReferences();
  mettreAJourApercu();
}

function ouvrirCiter() {
  if (!references.length) {
    toast("Ajoute d'abord des sources dans l'onglet Bibliographie.");
    $('[data-onglet="biblio"]').click();
    return;
  }
  const debut = texte.selectionStart, fin = texte.selectionEnd;
  const liste = $("#liste-citer");
  const afficher = () => {
    liste.replaceChildren();
    for (const r of references.filter((x) => correspond(x, $("#filtre-citer").value))) {
      liste.append(el("li", { tabindex: "0", onclick: () => choisir(r), onkeydown: (e) => { if (e.key === "Enter") { e.preventDefault(); choisir(r); } } },
        el("span", { class: "cle" }, `@${r.cle}`), el("span", { class: "resume" }, resumeReference(r))));
    }
  };
  const choisir = (r) => {
    $("#dialogue-citer").close();
    texte.setSelectionRange(debut, fin);
    insererCitation(r.cle, $("#precision-citer").value.trim());
  };
  $("#filtre-citer").value = "";
  $("#precision-citer").value = "";
  $("#filtre-citer").oninput = afficher;
  afficher();
  $("#dialogue-citer").showModal();
}

function brancherBibliographie() {
  remplirListe($("#style-biblio"), config.styles_biblio);
  remplirListe($("#type-reference"), config.types_references);
  $("#style-biblio").addEventListener("change", (e) => changement({ style_biblio: e.target.value }));
  $("#biblio-toutes").addEventListener("change", (e) => changement({ biblio_toutes: e.target.checked }));
  $("#ajouter-reference").addEventListener("click", () => ouvrirReference());
  $("#type-reference").addEventListener("change", afficherChampsReference);
  $("#form-reference").addEventListener("submit", enregistrerReference);
  $("#filtre-references").addEventListener("input", afficherReferences);
  $("#importer-bibtex").addEventListener("change", async (e) => {
    const fichier = e.target.files[0];
    e.target.value = "";
    if (!fichier) return;
    try {
      const resultat = await apiJson(`/api/projets/${projet.id}/references/bibtex`, { methode: "POST", corps: { bibtex: await fichier.text() } });
      await chargerReferences();
      mettreAJourApercu();
      toast(`${resultat.ajoutees} source${resultat.ajoutees > 1 ? "s" : ""} importée${resultat.ajoutees > 1 ? "s" : ""}`
        + (resultat.ignorees.length ? ` (${resultat.ignorees.length} déjà présente${resultat.ignorees.length > 1 ? "s" : ""})` : "") + ".");
    } catch (erreur) {
      toast(erreur.message, true);
    }
  });
}

// --- Commentaires ----------------------------------------------------------------------------------------------------

async function chargerCommentaires(marquerLus = false) {
  if (!projet) return;
  commentaires = (await apiJson(`/api/projets/${projet.id}/commentaires${marquerLus ? "?lu=1" : ""}`)).commentaires;
  if (marquerLus) commentaires.forEach((c) => { c.lu = 1; });
  afficherCommentaires();
}

function retrouverExtrait(extrait) {
  const position = texte.value.indexOf(extrait);
  if (position === -1) {
    toast("Ce passage a été modifié depuis le commentaire.");
    return;
  }
  $('[data-onglet="texte"]').click();
  texte.focus();
  texte.setSelectionRange(position, position + extrait.length);
  // Fait défiler la zone de texte jusqu'au passage.
  const ligne = texte.value.slice(0, position).split("\n").length;
  texte.scrollTop = Math.max(0, (ligne - 3) * parseFloat(getComputedStyle(texte).lineHeight));
}

function messageDuFil(c) {
  return el("div", { class: `message-fil ${c.role}` },
    el("span", { class: "auteur" }, c.auteur, " ", el("small", {}, `${c.role === "directeur" ? "direction" : "toi"} · ${dateRelative(c.cree_le)}`)),
    el("p", {}, c.texte));
}

function afficherCommentaires() {
  const zone = $("#liste-commentaires");
  const voirResolus = $("#voir-resolus").checked;
  const racines = commentaires.filter((c) => !c.parent_id);
  const nonLus = commentaires.filter((c) => !c.lu && c.role === "directeur").length;
  const pastille = $("#compteur-commentaires");
  pastille.hidden = !nonLus;
  pastille.textContent = nonLus;
  zone.replaceChildren();
  const visibles = racines.filter((c) => voirResolus || !c.resolu).reverse();
  if (!visibles.length) {
    zone.append(el("p", { class: "petit" }, racines.length ? "Tous les commentaires sont résolus. 🎉"
      : "Aucun commentaire pour l'instant. Partage ton mémoire avec ta direction pour en recevoir."));
  }
  for (const racine of visibles) {
    const reponses = commentaires.filter((c) => c.parent_id === racine.id);
    const champ = el("input", { type: "text", placeholder: "Répondre…", "aria-label": "Répondre", maxlength: "5000" });
    const repondre = async () => {
      if (!champ.value.trim()) return;
      await api(`/api/projets/${projet.id}/commentaires`, { methode: "POST", corps: { texte: champ.value, parent_id: racine.id } });
      await chargerCommentaires();
    };
    champ.addEventListener("keydown", (e) => { if (e.key === "Enter") repondre(); });
    zone.append(el("div", { class: `fil${racine.resolu ? " resolu" : ""}` },
      racine.extrait ? el("button", { class: "extrait", title: "Retrouver ce passage dans le texte", onclick: () => retrouverExtrait(racine.extrait) },
        `« ${racine.extrait} »`) : null,
      messageDuFil(racine), ...reponses.map(messageDuFil),
      el("div", { class: "reponse-fil" }, champ, el("button", { onclick: repondre }, "Envoyer"),
        el("button", { onclick: async () => {
          await api(`/api/projets/${projet.id}/commentaires/${racine.id}/resolu`, { methode: "POST", corps: { resolu: !racine.resolu } });
          await chargerCommentaires();
        } }, racine.resolu ? "Rouvrir" : "✓ Résolu"))));
  }
}

// --- Versions ---------------------------------------------------------------------------------------------------------

let versionEnCours = null;

async function chargerVersions() {
  if (!projet) return;
  const { versions } = await apiJson(`/api/projets/${projet.id}/versions`);
  const liste = $("#liste-versions");
  liste.replaceChildren();
  if (!versions.length) liste.append(el("li", { class: "petit" }, "Aucune version pour l'instant."));
  for (const v of versions) {
    liste.append(el("li", {},
      el("span", { class: "quand" }, v.auto ? "Automatique" : el("span", { class: "nommee" }, v.libelle), " · ", dateRelative(v.cree_le)),
      el("span", { class: "petit" }, `${v.mots.toLocaleString("fr-FR")} mots`),
      el("button", { onclick: () => voirVersion(v) }, "Voir")));
  }
  if (moi.formule.code === "gratuit") {
    liste.append(el("li", { class: "petit" }, `La formule gratuite garde les ${moi.formule.versions} dernières versions automatiques. `,
      el("button", { class: "lien", onclick: () => ouvrirFormule() }, "Historique complet avec le Pass")));
  }
}

async function voirVersion(v) {
  versionEnCours = await apiJson(`/api/projets/${projet.id}/versions/${v.id}`);
  $("#titre-version").textContent = `${v.auto ? "Version automatique" : v.libelle} — ${dateRelative(v.cree_le)}`;
  $("#texte-version").textContent = versionEnCours.texte;
  $("#dialogue-version").showModal();
}

function brancherVersions() {
  $("#form-version").addEventListener("submit", async (e) => {
    e.preventDefault();
    await enregistrerMaintenant();
    const champ = e.target.elements.libelle;
    await api(`/api/projets/${projet.id}/versions`, { methode: "POST", corps: { libelle: champ.value } });
    champ.value = "";
    toast("Version enregistrée.");
    await chargerVersions();
  });
  $("#restaurer-version").addEventListener("click", async () => {
    await enregistrerMaintenant();
    try {
      const restaure = await apiJson(`/api/projets/${projet.id}/versions/${versionEnCours.id}/restaurer`, { methode: "POST", corps: {} });
      Object.assign(projet, restaure);
      texte.value = projet.texte;
      afficherReglages();
      $("#dialogue-version").close();
      toast("Version restaurée. L'état précédent a été gardé dans l'historique.");
      await chargerVersions();
      mettreAJourApercu();
    } catch (e) {
      toast(e.message, true);
    }
  });
}

// --- Partage ------------------------------------------------------------------------------------------------------------

async function ouvrirPartage() {
  await afficherPartages();
  $("#dialogue-partage").showModal();
}

async function afficherPartages() {
  const { partages } = await apiJson(`/api/projets/${projet.id}/partages`);
  const liste = $("#liste-partages");
  liste.replaceChildren();
  for (const p of partages) {
    const url = `${location.origin}/partage/${p.jeton}`;
    liste.append(el("li", {},
      el("span", { class: "nom" }, p.nom),
      el("button", { onclick: async () => {
        try { await navigator.clipboard.writeText(url); toast("Lien copié : envoie-le par e-mail."); }
        catch (e) { prompt("Copie ce lien :", url); }
      } }, "Copier le lien"),
      el("button", { class: "danger", onclick: async () => {
        if (!confirm(`Désactiver le lien de ${p.nom} ? Il ne fonctionnera plus.`)) return;
        await api(`/api/projets/${projet.id}/partages/${p.id}`, { methode: "DELETE" });
        await afficherPartages();
      } }, "Désactiver")));
  }
}

function brancherPartage() {
  $("#creer-partage").addEventListener("click", async () => {
    try {
      const { url } = await apiJson(`/api/projets/${projet.id}/partages`, { methode: "POST", corps: { nom: $("#nom-partage").value } });
      $("#nom-partage").value = "";
      await afficherPartages();
      try { await navigator.clipboard.writeText(url); toast("Lien créé et copié : envoie-le par e-mail."); }
      catch (e) { toast("Lien créé : clique sur « Copier le lien »."); }
    } catch (e) {
      toast(e.message, true);
    }
  });
}

// --- Démarrage --------------------------------------------------------------------------------------------------------------

async function demarrer() {
  config = await apiJson("/api/configuration");
  remplirListe($("#choix-police"), Object.fromEntries(config.polices.map((p) => [p, p])));
  remplirListe($("#choix-alignement"), config.alignements);
  remplirListe($("#choix-numerotation"), config.numerotations);
  remplirListe($("#choix-pagination"), config.paginations);
  if (!config.pdf) {
    $("#export-pdf").disabled = true;
    $("#export-pdf").title = "L'export PDF n'est pas disponible sur ce serveur.";
  }
  brancherAuth();
  brancherTableau();
  brancherCompte();
  brancherReglages();
  brancherEditeur();
  brancherBibliographie();
  brancherVersions();
  brancherPartage();
  $("#voir-resolus").addEventListener("change", afficherCommentaires);
  try {
    moi = await apiJson("/api/moi");
  } catch (e) {
    if (e.statut !== 401) throw e;
  }
  window.addEventListener("hashchange", () => router().catch((e) => toast(e.message, true)));
  await router();
  // Les nouveaux commentaires arrivent sans recharger la page.
  setInterval(() => { if (projet && !document.hidden) chargerCommentaires().catch(() => {}); }, 60000);
}

demarrer().catch((e) => toast(`Impossible de démarrer : ${e.message}`, true));
