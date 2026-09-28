"use strict";

// Outils partagés par l'application et la page de partage.

const $ = (sel, racine = document) => racine.querySelector(sel);
const $$ = (sel, racine = document) => [...racine.querySelectorAll(sel)];

class ErreurApi extends Error {
  constructor(message, statut) {
    super(message);
    this.statut = statut;
  }
}

// Toutes les requêtes portent l'en-tête X-Redigo : le serveur refuse les autres (protection CSRF).
async function api(chemin, { methode = "GET", corps, brut = false } = {}) {
  const options = { method: methode, headers: { "X-Redigo": "1" }, credentials: "same-origin" };
  if (corps !== undefined) {
    options.body = brut ? corps : JSON.stringify(corps);
    if (!brut) options.headers["Content-Type"] = "application/json";
  }
  let reponse;
  try {
    reponse = await fetch(chemin, options);
  } catch (e) {
    throw new ErreurApi("Connexion au serveur impossible. Vérifie ta connexion internet.", 0);
  }
  if (!reponse.ok) {
    let message = `Erreur ${reponse.status}`;
    try { message = (await reponse.json()).erreur || message; } catch (e) { /* réponse non JSON */ }
    throw new ErreurApi(message, reponse.status);
  }
  return reponse;
}

async function apiJson(chemin, options) {
  return (await api(chemin, options)).json();
}

// Crée un élément : el("p", { class: "x" }, "texte", autreElement). Le texte n'est jamais interprété comme du HTML.
function el(balise, attributs = {}, ...enfants) {
  const element = document.createElement(balise);
  for (const [nom, valeur] of Object.entries(attributs)) {
    if (valeur === false || valeur === null || valeur === undefined) continue;
    if (nom.startsWith("on")) element.addEventListener(nom.slice(2), valeur);
    else if (nom === "class") element.className = valeur;
    else element.setAttribute(nom, valeur === true ? "" : valeur);
  }
  for (const enfant of enfants.flat()) {
    if (enfant === null || enfant === undefined || enfant === false) continue;
    element.append(enfant instanceof Node ? enfant : document.createTextNode(String(enfant)));
  }
  return element;
}

function telecharger(blob, nom) {
  const lien = el("a", { href: URL.createObjectURL(blob), download: nom });
  document.body.append(lien);
  lien.click();
  lien.remove();
  setTimeout(() => URL.revokeObjectURL(lien.href), 5000);
}

function nomDuFichier(reponse, defaut) {
  const trouve = (reponse.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/);
  return trouve ? trouve[1] : defaut;
}

function dateRelative(iso) {
  const date = new Date(iso);
  const secondes = (Date.now() - date.getTime()) / 1000;
  if (secondes < 60) return "à l'instant";
  if (secondes < 3600) return `il y a ${Math.floor(secondes / 60)} min`;
  if (secondes < 86400 && new Date().getDate() === date.getDate()) {
    return `aujourd'hui à ${date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}`;
  }
  return date.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })
    + ` à ${date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}`;
}

let minuterieToast = null;
function toast(message, erreur = false) {
  const zone = $("#toast");
  zone.textContent = message;
  zone.classList.toggle("erreur", erreur);
  zone.hidden = false;
  clearTimeout(minuterieToast);
  minuterieToast = setTimeout(() => { zone.hidden = true; }, erreur ? 6000 : 3500);
}
