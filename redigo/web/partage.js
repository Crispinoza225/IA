"use strict";

// La page que reçoit la direction du mémoire : lecture de la dernière version et commentaires, sans compte.

const jeton = location.pathname.split("/").pop();
let extrait = "";

function messageDuFil(c) {
  return el("div", { class: `message-fil ${c.role}` },
    el("span", { class: "auteur" }, c.auteur, " ", el("small", {}, `${c.role === "directeur" ? "direction" : "étudiant"} · ${dateRelative(c.cree_le)}`)),
    el("p", {}, c.texte));
}

function afficherCommentaires(commentaires) {
  const zone = $("#liste-commentaires");
  zone.replaceChildren();
  const racines = commentaires.filter((c) => !c.parent_id).reverse();
  if (!racines.length) zone.append(el("p", { class: "petit" }, "Aucun commentaire pour l'instant."));
  for (const racine of racines) {
    const champ = el("input", { type: "text", placeholder: "Répondre…", "aria-label": "Répondre", maxlength: "5000" });
    const repondre = async () => {
      if (!champ.value.trim()) return;
      await envoyer({ texte: champ.value, parent_id: racine.id });
    };
    champ.addEventListener("keydown", (e) => { if (e.key === "Enter") repondre(); });
    zone.append(el("div", { class: `fil${racine.resolu ? " resolu" : ""}` },
      racine.extrait ? el("span", { class: "extrait" }, `« ${racine.extrait} »`) : null,
      racine.resolu ? el("span", { class: "petit" }, "✓ Marqué comme résolu par l'étudiant") : null,
      messageDuFil(racine), ...commentaires.filter((c) => c.parent_id === racine.id).map(messageDuFil),
      el("div", { class: "reponse-fil" }, champ, el("button", { onclick: repondre }, "Répondre"))));
  }
}

async function charger() {
  const donnees = await apiJson(`/api/partage/${jeton}`);
  document.title = `${donnees.titre} — Rédigo`;
  $("#titre").textContent = donnees.titre;
  $("#sous-titre").textContent = `par ${donnees.etudiant} · dernière modification ${dateRelative(donnees.modifie_le)}`;
  $("#pages").innerHTML = donnees.html;  // HTML produit par le serveur, dont tout le texte est échappé
  afficherCommentaires(donnees.commentaires);
  if (!$("#auteur").value) $("#auteur").value = localStorageLire() || donnees.destinataire;
}

function localStorageLire() {
  try { return localStorage.getItem("redigo-nom"); } catch (e) { return null; }
}

function localStorageEcrire(nom) {
  try { localStorage.setItem("redigo-nom", nom); } catch (e) { /* stockage indisponible */ }
}

async function envoyer(corps) {
  const auteur = $("#auteur").value.trim();
  if (!auteur) {
    toast("Indique ton nom avant de commenter.", true);
    $("#auteur").focus();
    return;
  }
  localStorageEcrire(auteur);
  try {
    await api(`/api/partage/${jeton}/commentaires`, { methode: "POST", corps: { auteur, ...corps } });
    await charger();
    toast("Commentaire envoyé.");
  } catch (e) {
    toast(e.message, true);
  }
}

function choisirExtrait(texte) {
  extrait = texte.replace(/\s+/g, " ").trim().slice(0, 500);
  $("#extrait-choisi").hidden = !extrait;
  $("#extrait-texte").textContent = `« ${extrait} »`;
}

function brancher() {
  // Sélectionner un passage dans l'aperçu le rattache au prochain commentaire.
  document.addEventListener("selectionchange", () => {
    const selection = document.getSelection();
    if (!selection || selection.isCollapsed || !$("#pages").contains(selection.anchorNode)) return;
    const texte = selection.toString();
    if (texte.trim().length > 2) choisirExtrait(texte);
  });
  $("#retirer-extrait").addEventListener("click", () => choisirExtrait(""));
  $("#form-commentaire").addEventListener("submit", async (e) => {
    e.preventDefault();
    await envoyer({ texte: $("#commentaire").value, extrait });
    $("#commentaire").value = "";
    choisirExtrait("");
  });
  $("#telecharger-pdf").addEventListener("click", async () => {
    try {
      const reponse = await api(`/api/partage/${jeton}/pdf`, { methode: "POST", corps: {} });
      telecharger(await reponse.blob(), nomDuFichier(reponse, "memoire.pdf"));
    } catch (e) {
      toast(e.message, true);
    }
  });
  let zoom = innerWidth <= 900 ? Math.max(0.3, Math.min(0.7, (innerWidth - 40) / 794)) : 0.7;
  const appliquerZoom = () => {
    $("#pages").style.setProperty("--zoom", zoom);
    $("#zoom-valeur").textContent = `${Math.round(zoom * 100)} %`;
  };
  $("#zoom-moins").addEventListener("click", () => { zoom = Math.max(0.3, zoom - 0.1); appliquerZoom(); });
  $("#zoom-plus").addEventListener("click", () => { zoom = Math.min(1.5, zoom + 0.1); appliquerZoom(); });
  appliquerZoom();
}

brancher();
charger().catch((e) => {
  $("#titre").textContent = "Lien indisponible";
  $("#sous-titre").textContent = e.message;
  $("#form-commentaire").hidden = true;
  $("#telecharger-pdf").hidden = true;
});
