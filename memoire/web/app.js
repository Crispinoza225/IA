"use strict";

// L'état du projet : le texte et les réglages. Il est gardé dans le navigateur (localStorage)
// pour ne rien perdre en fermant la page, et peut être téléchargé en .json.
const CLE_STOCKAGE = "memoire-projet";
let config = null;
let projet = null;
let minuterie = null;
let requeteEnCours = 0;

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];
const texte = $("#texte");

function etat(message, erreur = false) {
  const zone = $("#etat");
  zone.textContent = message;
  zone.classList.toggle("erreur", erreur);
}

function lireStockage() {
  try {
    return JSON.parse(localStorage.getItem(CLE_STOCKAGE));
  } catch (e) {
    return null;
  }
}

function sauvegarder() {
  try {
    localStorage.setItem(CLE_STOCKAGE, JSON.stringify(projet));
  } catch (e) {
    /* stockage indisponible (navigation privée) : on continue sans */
  }
}

async function api(chemin, corps, brut = false) {
  const reponse = await fetch(chemin, {
    method: corps === undefined ? "GET" : "POST",
    headers: brut ? {} : { "Content-Type": "application/json" },
    body: corps === undefined ? undefined : brut ? corps : JSON.stringify(corps),
  });
  if (!reponse.ok) {
    let message = `Erreur ${reponse.status}`;
    try { message = (await reponse.json()).erreur || message; } catch (e) { /* réponse non JSON */ }
    throw new Error(message);
  }
  return reponse;
}

// --- Formulaire de réglages ---------------------------------------------------------------

function remplirListe(select, valeurs) {
  select.innerHTML = "";
  for (const [valeur, libelle] of Object.entries(valeurs)) {
    select.add(new Option(libelle, valeur));
  }
}

function afficherReglages() {
  const r = projet.reglages;
  for (const champ of $$("[data-cle]")) {
    const cle = champ.dataset.cle;
    let valeur = r[cle];
    if (champ.dataset.index !== undefined) valeur = valeur[Number(champ.dataset.index)];
    if (champ.type === "checkbox") champ.checked = Boolean(valeur);
    else champ.value = String(valeur);
  }
  for (const champ of $$("[data-garde]")) {
    const valeur = r.garde[champ.dataset.garde];
    if (champ.type === "checkbox") champ.checked = Boolean(valeur);
    else champ.value = valeur ?? "";
  }
  $("#norme").value = projet.norme || "universite";
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
      const cle = champ.dataset.cle;
      if (champ.dataset.index !== undefined) {
        const tailles = [...projet.reglages[cle]];
        tailles[Number(champ.dataset.index)] = lireChamp(champ, tailles[Number(champ.dataset.index)]);
        projet.reglages[cle] = tailles;
      } else {
        projet.reglages[cle] = lireChamp(champ, projet.reglages[cle]);
      }
      modifie();
    });
  }
  for (const champ of $$("[data-garde]")) {
    champ.addEventListener("input", () => {
      projet.reglages.garde[champ.dataset.garde] = lireChamp(champ, projet.reglages.garde[champ.dataset.garde]);
      modifie();
    });
  }
  $("#norme").addEventListener("change", (e) => {
    const garde = projet.reglages.garde;
    projet.reglages = structuredClone(config.normes[e.target.value].reglages);
    projet.reglages.garde = garde;  // changer de norme ne doit pas effacer la page de garde
    projet.norme = e.target.value;
    afficherReglages();
    modifie();
  });
}

// --- Aperçu -----------------------------------------------------------------------------------

function modifie() {
  sauvegarder();
  clearTimeout(minuterie);
  minuterie = setTimeout(mettreAJourApercu, 350);
}

async function mettreAJourApercu() {
  const numero = ++requeteEnCours;
  try {
    const reponse = await api("/api/apercu", { texte: projet.texte, reglages: projet.reglages });
    const donnees = await reponse.json();
    if (numero !== requeteEnCours) return;  // une réponse plus récente est déjà en route
    $("#pages").innerHTML = donnees.html;
    const mots = donnees.mots.toLocaleString("fr-FR");
    $("#infos").textContent = `${mots} mot${donnees.mots > 1 ? "s" : ""} · ${donnees.titres} titre${donnees.titres > 1 ? "s" : ""}`;
    etat("");
  } catch (e) {
    etat(e.message, true);
  }
}

// --- Éditeur : barre d'outils ----------------------------------------------------------------

function remplacerSelection(avant, apres, exemple) {
  const debut = texte.selectionStart, fin = texte.selectionEnd;
  const choisi = texte.value.slice(debut, fin) || exemple;
  texte.setRangeText(avant + choisi + apres, debut, fin, "end");
  texte.setSelectionRange(debut + avant.length, debut + avant.length + choisi.length);
  texte.focus();
  texte.dispatchEvent(new Event("input"));
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
  texte.setRangeText(lignes.join("\n"), debut, fin, "end");
  texte.focus();
  texte.dispatchEvent(new Event("input"));
}

function inserer(bloc) {
  const debut = texte.selectionStart;
  const avant = texte.value.slice(0, debut);
  const separation = avant && !avant.endsWith("\n\n") ? (avant.endsWith("\n") ? "\n" : "\n\n") : "";
  texte.setRangeText(separation + bloc + "\n\n", debut, texte.selectionEnd, "end");
  texte.focus();
  texte.dispatchEvent(new Event("input"));
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
};

// --- Fichiers ------------------------------------------------------------------------------------

function telecharger(blob, nom) {
  const lien = document.createElement("a");
  lien.href = URL.createObjectURL(blob);
  lien.download = nom;
  document.body.append(lien);
  lien.click();
  lien.remove();
  setTimeout(() => URL.revokeObjectURL(lien.href), 5000);
}

function nomDuFichier(reponse, defaut) {
  const entete = reponse.headers.get("Content-Disposition") || "";
  const trouve = entete.match(/filename="([^"]+)"/);
  return trouve ? trouve[1] : defaut;
}

async function exporter(format) {
  etat(format === "pdf" ? "Création du PDF…" : "Création du fichier Word…");
  try {
    const reponse = await api(`/api/${format}`, { texte: projet.texte, reglages: projet.reglages });
    telecharger(await reponse.blob(), nomDuFichier(reponse, `memoire.${format}`));
    etat(format === "docx"
      ? "Fichier Word créé. À l'ouverture, accepte la mise à jour des champs pour remplir le sommaire."
      : "PDF créé.");
  } catch (e) {
    etat(e.message, true);
  }
}

function chargerProjet(nouveau) {
  projet = nouveau;
  texte.value = projet.texte;
  afficherReglages();
  modifie();
}

async function chargerExemple() {
  const donnees = await (await api("/api/exemple")).json();
  const reglages = structuredClone(config.defaut);
  Object.assign(reglages.garde, {
    universite: "Université de Lyon", faculte: "Faculté des Sciences de l'Éducation",
    titre: "Le numérique au service de l'autonomie des étudiants",
    sous_titre: "Enquête auprès de 214 étudiants de licence", auteur: "Camille Martin",
    directeur: "Mme Sophie Bernard", annee: "Année universitaire 2025-2026",
  });
  chargerProjet({ texte: donnees.texte, reglages, norme: "universite" });
}

function brancherFichiers() {
  $("#export-docx").addEventListener("click", () => exporter("docx"));
  $("#export-pdf").addEventListener("click", () => exporter("pdf"));
  $("#exemple").addEventListener("click", () => {
    if (!projet.texte.trim() || confirm("Remplacer ton texte par le mémoire d'exemple ?")) chargerExemple();
  });
  $("#nouveau").addEventListener("click", () => {
    if (!projet.texte.trim() || confirm("Commencer un nouveau document ? Pense à enregistrer le projet actuel.")) {
      chargerProjet({ texte: "# Introduction\n\n", reglages: structuredClone(config.defaut), norme: "universite" });
    }
  });
  $("#enregistrer").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(projet, null, 2)], { type: "application/json" });
    telecharger(blob, "projet-memoire.json");
    etat("Projet enregistré.");
  });
  $("#ouvrir").addEventListener("change", async (e) => {
    const fichier = e.target.files[0];
    e.target.value = "";
    if (!fichier) return;
    try {
      const donnees = JSON.parse(await fichier.text());
      if (typeof donnees.texte !== "string" || typeof donnees.reglages !== "object") throw new Error();
      donnees.reglages = { ...structuredClone(config.defaut), ...donnees.reglages,
        garde: { ...config.defaut.garde, ...(donnees.reglages.garde || {}) } };
      chargerProjet(donnees);
      etat("Projet ouvert.");
    } catch (erreur) {
      etat("Ce fichier n'est pas un projet de mémoire valide.", true);
    }
  });
  $("#importer").addEventListener("change", async (e) => {
    const fichier = e.target.files[0];
    e.target.value = "";
    if (!fichier) return;
    etat("Import du document Word…");
    try {
      const donnees = await (await api("/api/importer-docx", await fichier.arrayBuffer(), true)).json();
      if (projet.texte.trim() && !confirm("Remplacer le texte actuel par celui du document Word ?")) {
        etat("");
        return;
      }
      projet.texte = donnees.texte;
      texte.value = donnees.texte;
      modifie();
      etat("Document Word importé : vérifie les titres (# ## ###) repérés automatiquement.");
    } catch (erreur) {
      etat(erreur.message, true);
    }
  });
}

// --- Démarrage -----------------------------------------------------------------------------------

function brancherInterface() {
  for (const bouton of $$(".onglets button")) {
    bouton.addEventListener("click", () => {
      for (const autre of $$(".onglets button")) autre.setAttribute("aria-selected", String(autre === bouton));
      for (const onglet of $$(".onglet")) onglet.hidden = onglet.id !== `onglet-${bouton.dataset.onglet}`;
    });
  }
  for (const bouton of $$("[data-action]")) bouton.addEventListener("click", () => actions[bouton.dataset.action]());
  texte.addEventListener("input", () => {
    projet.texte = texte.value;
    modifie();
  });
  texte.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") { e.preventDefault(); actions.gras(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "i") { e.preventDefault(); actions.italique(); }
  });
  let zoom = 0.6;
  const appliquerZoom = () => {
    $("#pages").style.setProperty("--zoom", zoom);
    $("#zoom-valeur").textContent = `${Math.round(zoom * 100)} %`;
  };
  $("#zoom-moins").addEventListener("click", () => { zoom = Math.max(0.3, zoom - 0.1); appliquerZoom(); });
  $("#zoom-plus").addEventListener("click", () => { zoom = Math.min(1.5, zoom + 0.1); appliquerZoom(); });
  appliquerZoom();
}

async function demarrer() {
  config = await (await api("/api/configuration")).json();
  remplirListe($("#choix-police"), Object.fromEntries(config.polices.map((p) => [p, p])));
  remplirListe($("#choix-alignement"), config.alignements);
  remplirListe($("#choix-numerotation"), config.numerotations);
  remplirListe($("#choix-pagination"), config.paginations);
  remplirListe($("#norme"), Object.fromEntries(Object.entries(config.normes).map(([cle, n]) => [cle, n.nom])));
  if (!config.pdf) {
    $("#export-pdf").disabled = true;
    $("#export-pdf").title = "Installe reportlab pour l'export PDF : pip install reportlab";
  }
  brancherInterface();
  brancherReglages();
  brancherFichiers();
  const enregistre = lireStockage();
  if (enregistre && typeof enregistre.texte === "string" && enregistre.reglages) {
    enregistre.reglages = { ...structuredClone(config.defaut), ...enregistre.reglages,
      garde: { ...config.defaut.garde, ...(enregistre.reglages.garde || {}) } };
    chargerProjet(enregistre);
  } else {
    await chargerExemple();  // première visite : un exemple complet pour découvrir la plateforme
  }
}

demarrer().catch((e) => etat(`Impossible de démarrer : ${e.message}`, true));
