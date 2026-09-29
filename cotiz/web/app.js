"use strict";

// L'application Cotiz : connexion, tableau de bord et gestion d'une tontine.

let config = null;
let moi = null;
let tontine = null;          // la tontine ouverte (vue renvoyée par le serveur)
let ongletCourant = "tour";
let codeInvitation = null;

const STATUTS = { paye: "Payé", a_confirmer: "À confirmer", a_payer: "À payer", en_retard: "En retard" };
const STATUTS_TONTINE = { brouillon: "En préparation", en_cours: "En cours", termine: "Terminée" };

function dateCourte(iso) {
  return new Date(iso.slice(0, 10) + "T12:00:00").toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}

function pastille(statut, texte) {
  return el("span", { class: `pastille ${statut}` }, texte);
}

function afficherVue(nom) {
  for (const vue of $$(".vue")) vue.hidden = vue.id !== `vue-${nom}`;
  window.scrollTo(0, 0);
}

function message(zone, texte, type = "erreur") {
  zone.textContent = texte;
  zone.className = `message ${type}`;
}

// --- Navigation ---------------------------------------------------------------------------------------------

async function router() {
  const trouve = location.hash.match(/^#tontine\/(\d+)$/);
  if (!moi) {
    afficherAuth(location.hash === "#inscription" || codeInvitation ? "inscription" : "connexion");
    return;
  }
  if (trouve) await ouvrirTontine(Number(trouve[1]));
  else await afficherTableau();
}

// --- Invitation ---------------------------------------------------------------------------------------------

async function preparerInvitation() {
  const trouve = location.pathname.match(/^\/rejoindre\/([\w-]+)$/);
  if (!trouve) return;
  codeInvitation = trouve[1];
  try {
    const inv = await apiJson(`/api/invitation/${codeInvitation}`);
    $("#inv-nom").textContent = inv.nom;
    $("#inv-description").textContent = inv.description;
    $("#inv-montant").textContent = inv.montant;
    $("#inv-frequence").textContent = inv.frequence;
    $("#inv-debut").textContent = inv.debut;
    $("#inv-membres").textContent = inv.membres;
    $("#inv-organisateur").textContent = inv.organisateur;
    $("#carte-invitation").hidden = false;
    if (inv.statut !== "brouillon") {
      message($("#inv-message"), "Cette tontine a déjà commencé : seules les personnes ajoutées par l'organisateur peuvent y accéder.", "");
    }
  } catch (e) {
    codeInvitation = null;
    toast(e.message, true);
  }
}

function afficherBoutonRejoindre() {
  $("#inv-rejoindre").hidden = !(codeInvitation && moi);
}

async function rejoindre() {
  try {
    const { id } = await apiJson(`/api/invitation/${codeInvitation}/rejoindre`, { methode: "POST", corps: {} });
    codeInvitation = null;
    $("#carte-invitation").hidden = true;
    history.replaceState(null, "", `/app#tontine/${id}`);
    toast("Bienvenue dans la tontine !");
    await router();
  } catch (e) {
    message($("#inv-message"), e.message);
  }
}

// --- Connexion ----------------------------------------------------------------------------------------------------

function afficherAuth(formulaire) {
  afficherVue("auth");
  for (const f of $$("[data-formulaire]")) f.hidden = f.dataset.formulaire !== formulaire;
  for (const b of $$("[data-auth]")) b.setAttribute("aria-selected", String(b.dataset.auth === formulaire));
  message($("#message-auth"), "");
}

function brancherAuth() {
  for (const b of $$("[data-auth]")) b.addEventListener("click", () => afficherAuth(b.dataset.auth));
  for (const formulaire of $$("[data-formulaire]")) {
    formulaire.addEventListener("submit", async (e) => {
      e.preventDefault();
      const bouton = $("button[type=submit]", formulaire);
      bouton.disabled = true;
      try {
        moi = await apiJson(`/api/${formulaire.dataset.formulaire}`, { methode: "POST", corps: Object.fromEntries(new FormData(formulaire)) });
        formulaire.reset();
        afficherBoutonRejoindre();
        if (codeInvitation) {
          await rejoindre();
          return;
        }
        location.hash = "tontines";
        await router();
      } catch (erreur) {
        message($("#message-auth"), erreur.message);
      } finally {
        bouton.disabled = false;
      }
    });
  }
  $("#inv-rejoindre").addEventListener("click", rejoindre);
}

// --- Tableau de bord ------------------------------------------------------------------------------------------------

function afficherFormule() {
  const f = moi.formule;
  for (const b of $$(".badge-formule")) {
    b.textContent = f.code === "gratuit" ? "Gratuit" : "Organisateur";
    b.classList.toggle("pro", f.code !== "gratuit");
  }
  for (const b of $$(".compte")) b.textContent = moi.nom.trim()[0].toUpperCase();
}

async function afficherTableau() {
  tontine = null;
  afficherVue("tableau");
  document.title = "Mes tontines — Cotiz";
  afficherFormule();
  const { tontines, fiabilite } = await apiJson("/api/tableau");
  $("#salut").textContent = `Bonjour ${moi.nom.split(" ")[0]} 👋`;
  $("#fiabilite").textContent = fiabilite === null ? "Ton score de fiabilité apparaîtra après tes premières cotisations."
    : `Ton score de fiabilité : ${fiabilite} % de cotisations payées à temps.`;
  const liste = $("#liste-tontines");
  liste.replaceChildren();
  if (!tontines.length) {
    liste.append(el("div", { class: "vide" },
      el("b", {}, "Tu n'as pas encore de tontine."),
      el("span", {}, "Crée la tienne en 1 minute, ou demande le lien d'invitation à ton organisateur."),
      el("button", { class: "principal", onclick: ouvrirCreation }, "Créer ma première tontine")));
  }
  for (const t of tontines) {
    const details = [];
    if (t.statut === "en_cours") {
      details.push(el("div", { class: "ligne" },
        el("span", {}, `Tour ${t.tour} · ${t.cotisation} avant le ${dateCourte(t.echeance)}`),
        pastille(t.mon_statut, STATUTS[t.mon_statut])));
      details.push(el("div", { class: "barre-progression", title: `${t.progression} % collecté` },
        el("span", { style: `width:${t.progression}%` })));
      if (t.role === "organisateur" && t.a_confirmer) {
        details.push(el("span", { class: "petit" }, `⏳ ${t.a_confirmer} paiement${t.a_confirmer > 1 ? "s" : ""} à confirmer`));
      }
    } else if (t.statut === "brouillon") {
      details.push(el("span", { class: "petit" }, `${t.membres} membre${t.membres > 1 ? "s" : ""} pour l'instant · la tontine n'a pas encore commencé`));
    }
    if (t.je_recois) {
      details.push(el("div", { class: "a-recevoir" }, `💰 Tu reçois la cagnotte (${t.cagnotte}) au tour ${t.je_recois.tour}, le ${dateCourte(t.je_recois.date)}`));
    }
    liste.append(el("a", { class: "carte", href: `#tontine/${t.id}` },
      el("div", { class: "ligne" }, el("h3", {}, t.nom),
        el("span", {}, t.role === "organisateur" ? pastille("organisateur", "Organisateur") : null, " ",
          pastille(t.statut, STATUTS_TONTINE[t.statut]))),
      el("span", { class: "petit" }, `${t.cotisation} · ${t.frequence.toLowerCase()} · ${t.membres} membres`),
      ...details));
  }
}

// --- Création et réglages d'une tontine ------------------------------------------------------------------------------

function remplirListe(select, valeurs) {
  select.replaceChildren();
  for (const [valeur, libelle] of Object.entries(valeurs)) select.add(new Option(libelle, valeur));
}

let modeDialogueTontine = "creer";

function ouvrirCreation() {
  modeDialogueTontine = "creer";
  const f = $("#form-tontine");
  f.reset();
  $("#titre-dialogue-tontine").textContent = "Nouvelle tontine";
  $("#form-tontine button[value=valider]").textContent = "Créer";
  const demain = new Date(Date.now() + 7 * 86400000);
  f.elements.date_debut.value = demain.toISOString().slice(0, 10);
  f.elements.devise.value = "XOF";
  f.elements.frequence.value = "mensuelle";
  f.elements.mode_ordre.value = "tirage";
  message($("#message-tontine"), "");
  $("#dialogue-tontine").showModal();
}

function ouvrirReglages() {
  modeDialogueTontine = "modifier";
  const f = $("#form-tontine");
  $("#titre-dialogue-tontine").textContent = "Règles de la tontine";
  $("#form-tontine button[value=valider]").textContent = "Enregistrer";
  f.elements.nom.value = tontine.nom;
  f.elements.description.value = tontine.description;
  f.elements.devise.value = tontine.devise;
  f.elements.montant.value = tontine.montant.replace(/[^\d,]/g, "");
  f.elements.frequence.value = tontine.frequence_code;
  f.elements.date_debut.value = tontine.date_debut;
  f.elements.mode_ordre.value = tontine.mode_ordre_code;
  f.elements.penalite.value = tontine.penalite.replace(/[^\d,]/g, "");
  f.elements.jours_grace.value = tontine.jours_grace;
  message($("#message-tontine"), "");
  $("#dialogue-tontine").showModal();
}

async function validerTontine(e) {
  if (e.submitter && e.submitter.value === "annuler") return;
  e.preventDefault();
  const donnees = Object.fromEntries(new FormData($("#form-tontine")));
  try {
    if (modeDialogueTontine === "creer") {
      const { id } = await apiJson("/api/tontines", { methode: "POST", corps: donnees });
      $("#dialogue-tontine").close();
      location.hash = `tontine/${id}`;
      toast("Tontine créée ! Ajoute les membres ou partage le lien d'invitation.");
    } else {
      tontine = await apiJson(`/api/tontines/${tontine.id}`, { methode: "PUT", corps: donnees });
      $("#dialogue-tontine").close();
      afficherTontine();
      toast("Règles enregistrées.");
    }
  } catch (erreur) {
    if (erreur.statut === 402) {
      $("#dialogue-tontine").close();
      ouvrirFormule(erreur.message);
    } else {
      message($("#message-tontine"), erreur.message);
    }
  }
}

// --- Une tontine ------------------------------------------------------------------------------------------------------------

async function ouvrirTontine(id) {
  try {
    tontine = await apiJson(`/api/tontines/${id}`);
  } catch (e) {
    toast(e.message, true);
    location.hash = "tontines";
    return;
  }
  afficherVue("tontine");
  afficherTontine();
}

// Toute action de l'organisateur renvoie la tontine à jour.
async function action(chemin, options, succes) {
  try {
    tontine = await apiJson(chemin, options);
    afficherTontine();
    if (succes) toast(succes);
    return true;
  } catch (e) {
    if (e.statut === 402) ouvrirFormule(e.message);
    else toast(e.message, true);
    return false;
  }
}

function afficherTontine() {
  document.title = `${tontine.nom} — Cotiz`;
  $("#t-nom").textContent = tontine.nom;
  $("#t-sous-titre").textContent = `${tontine.montant} · ${tontine.frequence.toLowerCase()} · ${STATUTS_TONTINE[tontine.statut]}`;
  for (const b of $$("[data-organisateur]")) b.hidden = !tontine.organisateur;
  if (!tontine.organisateur && ongletCourant === "reglages") ongletCourant = "tour";
  choisirOnglet(ongletCourant);
}

function choisirOnglet(nom) {
  ongletCourant = nom;
  for (const b of $$(".onglets button")) b.setAttribute("aria-selected", String(b.dataset.onglet === nom));
  for (const o of $$(".onglet")) o.hidden = o.id !== `onglet-${nom}`;
  ({ tour: afficherTour, calendrier: afficherCalendrier, membres: afficherMembres, journal: afficherJournal,
    reglages: afficherOngletReglages })[nom]();
}

function blocInvitation() {
  const champ = el("input", { type: "text", value: tontine.invitation, readonly: true, "aria-label": "Lien d'invitation" });
  const texte = `Rejoins ma tontine « ${tontine.nom} » sur Cotiz (${tontine.montant}, ${tontine.frequence.toLowerCase()}) : ${tontine.invitation}`;
  return el("div", { class: "carte" },
    el("h3", {}, "Inviter des membres"),
    el("span", { class: "petit" }, "Envoie ce lien : chacun crée son compte avec son numéro et rejoint la tontine."),
    el("div", { class: "invitation-lien" }, champ,
      el("button", { onclick: async () => {
        try { await navigator.clipboard.writeText(tontine.invitation); toast("Lien copié."); }
        catch (e) { champ.select(); }
      } }, "Copier")),
    el("a", { class: "bouton", href: `https://wa.me/?text=${encodeURIComponent(texte)}`, target: "_blank", rel: "noopener" },
      "Partager sur WhatsApp"));
}

function afficherTour() {
  const zone = $("#onglet-tour");
  zone.replaceChildren();
  if (tontine.statut === "brouillon") {
    zone.append(el("div", { class: "carte" },
      el("h3", {}, "La tontine n'a pas encore commencé"),
      el("span", { class: "doux" }, `Premier tour le ${dateCourte(tontine.date_debut)}. ${tontine.membres.length} membre${tontine.membres.length > 1 ? "s" : ""}, `
        + `${tontine.nombre_tours} tour${tontine.nombre_tours > 1 ? "s" : ""}, cagnotte de ${tontine.cagnotte} à chaque tour.`),
      el("span", { class: "petit" }, `Ordre des bénéficiaires : ${tontine.mode_ordre.toLowerCase()}.`),
      tontine.organisateur ? el("button", { class: "principal large", onclick: demarrer }, "Démarrer la tontine") : null));
    if (tontine.organisateur) zone.append(blocInvitation());
    return;
  }
  if (tontine.statut === "termine") {
    zone.append(el("div", { class: "carte" }, el("h3", {}, "🎉 Tontine terminée"),
      el("span", { class: "doux" }, "Tous les tours ont été versés. L'historique complet reste disponible dans le calendrier et le journal.")));
    return;
  }
  const t = tontine.tour_courant;
  const moiLigne = t.lignes.find((l) => l.membre_id === tontine.moi.membre_id);
  zone.append(el("div", { class: "carte cagnotte" },
    el("div", { class: "beneficiaire" }, el("span", { class: "avatar" }, t.beneficiaire.trim()[0].toUpperCase()),
      el("div", {}, el("span", { class: "petit" }, `Tour ${t.tour} sur ${tontine.nombre_tours} · ${dateCourte(t.echeance)}`),
        el("h3", {}, `Pour ${t.beneficiaire}`))),
    el("div", {}, el("span", { class: "montant" }, t.collecte), el("span", { class: "sur" }, ` / ${t.attendu}`)),
    el("div", { class: "barre-progression" }, el("span", { style: `width:${t.progression}%` })),
    el("span", { class: "petit" }, `Paiement attendu avant le ${dateCourte(t.limite)}`
      + (tontine.penalite ? ` · pénalité de retard : ${tontine.penalite}` : ""))));

  if (moiLigne && moiLigne.statut !== "paye") {
    zone.append(el("div", { class: "carte" },
      el("div", { class: "ligne" }, el("b", {}, `Ta cotisation : ${moiLigne.du}`), pastille(moiLigne.statut, STATUTS[moiLigne.statut])),
      moiLigne.statut === "a_confirmer" ? el("span", { class: "petit" }, "Ton paiement est déclaré : l'organisateur doit le confirmer.")
        : el("button", { class: "principal large", onclick: () => ouvrirPaiement(tontine.moi.membre_id, tontine.moi.du_brut, !tontine.organisateur) },
          tontine.organisateur ? "Enregistrer mon paiement" : "J'ai payé")));
  }

  const lignes = el("div", { class: "lignes-membres" });
  for (const l of t.lignes) {
    const actions = [];
    if (tontine.organisateur) {
      if (l.statut === "a_payer" || l.statut === "en_retard") actions.push(el("button", { onclick: () => ouvrirPaiement(l.membre_id, l.du_brut, false, l.nom) }, "Encaisser"));
    }
    const declarations = l.cotisations.filter((c) => c.statut === "declaree").map((c) => el("div", { class: "declaration" },
      el("span", {}, `Déclare avoir payé ${c.montant} (${c.moyen}${c.reference ? ", réf. " + c.reference : ""})`),
      tontine.organisateur ? el("span", { class: "actions" },
        el("button", { class: "principal", onclick: () => decider(c.id, true) }, "Confirmer"),
        el("button", { onclick: () => decider(c.id, false) }, "Refuser")) : null));
    lignes.append(el("div", { class: "ligne-membre" },
      el("div", {}, el("div", { class: "nom" }, l.nom), el("span", { class: "petit" }, `${l.verse} / ${l.du}`)),
      pastille(l.statut, STATUTS[l.statut]),
      ...declarations,
      actions.length ? el("div", { class: "actions" }, ...actions) : null));
  }
  zone.append(el("div", { class: "carte" }, el("h3", {}, "Qui a payé ?"), lignes));

  if (tontine.organisateur) {
    const boutons = el("div", { class: "actions-principales" });
    boutons.append(el("button", { class: "principal large", onclick: () => verser(t.complet) },
      t.complet ? `Remettre la cagnotte à ${t.beneficiaire}` : "Remettre la cagnotte (tout n'est pas payé)"));
    boutons.append(el("button", { class: "large", onclick: afficherRappels }, "Relancer les retardataires"));
    zone.append(el("div", { class: "carte" }, boutons, el("div", { id: "zone-rappels" })));
  }
}

async function demarrer() {
  const tirage = tontine.mode_ordre_code === "tirage";
  if (!confirm(`Démarrer la tontine ? ${tirage ? "L'ordre des bénéficiaires sera tiré au sort maintenant" : "L'ordre des bénéficiaires sera figé"}, `
    + "et les membres ne pourront plus changer.")) return;
  await action(`/api/tontines/${tontine.id}/demarrer`, { methode: "POST", corps: {} },
    tirage ? "C'est parti ! L'ordre a été tiré au sort : il est visible dans le calendrier." : "C'est parti !");
}

async function decider(id, accepter) {
  await action(`/api/tontines/${tontine.id}/cotisations/${id}/decision`, { methode: "POST", corps: { accepter } },
    accepter ? "Paiement confirmé." : "Paiement refusé.");
}

async function verser(complet) {
  const t = tontine.tour_courant;
  if (!complet && !confirm(`Tout le monde n'a pas payé. Remettre quand même ${t.collecte} à ${t.beneficiaire} ? Les impayés resteront notés dans le journal.`)) return;
  if (complet && !confirm(`Confirmer que ${t.collecte} a été remis à ${t.beneficiaire} ?`)) return;
  await action(`/api/tontines/${tontine.id}/tours/${t.tour_id}/verser`, { methode: "POST", corps: { forcer: !complet } },
    `Cagnotte remise à ${t.beneficiaire}. Tour suivant !`);
}

async function afficherRappels() {
  const zone = $("#zone-rappels");
  const { rappels } = await apiJson(`/api/tontines/${tontine.id}/rappels`);
  zone.replaceChildren();
  if (!rappels.length) {
    zone.append(el("p", { class: "petit" }, "Personne à relancer : tout le monde a payé ou déclaré son paiement. 👏"));
    return;
  }
  for (const r of rappels) {
    zone.append(el("div", { class: "ligne-membre" },
      el("div", {}, el("div", { class: "nom" }, r.nom), el("span", { class: "petit" }, r.telephone)),
      pastille(r.statut, STATUTS[r.statut]),
      el("div", { class: "actions" },
        el("a", { class: "bouton", href: r.whatsapp, target: "_blank", rel: "noopener" }, "WhatsApp"),
        el("a", { class: "bouton", href: `sms:${r.telephone}?body=${encodeURIComponent(r.message)}` }, "SMS"))));
  }
}

let paiementEnCours = null;

function ouvrirPaiement(membreId, du, declaration, nom = null) {
  paiementEnCours = { membreId };
  const f = $("#form-paiement");
  f.reset();
  const decimales = ["EUR", "CAD", "USD", "MAD"].includes(tontine.devise) ? 2 : 0;
  f.elements.montant.value = decimales ? (du / 100).toFixed(2).replace(".", ",") : String(du);
  f.elements.moyen.value = "mobile_money";
  $("#titre-paiement").textContent = declaration ? "J'ai payé ma cotisation" : `Paiement reçu${nom ? " de " + nom : ""}`;
  $("#aide-paiement").textContent = declaration
    ? "L'organisateur recevra ta déclaration et la confirmera. Indique la référence Mobile Money pour aller plus vite."
    : "Ce paiement est enregistré comme reçu et apparaît tout de suite dans le journal.";
  message($("#message-paiement"), "");
  $("#dialogue-paiement").showModal();
}

async function validerPaiement(e) {
  if (e.submitter && e.submitter.value === "annuler") return;
  e.preventDefault();
  const donnees = Object.fromEntries(new FormData($("#form-paiement")));
  donnees.membre_id = paiementEnCours.membreId;
  try {
    tontine = await apiJson(`/api/tontines/${tontine.id}/tours/${tontine.tour_courant.tour_id}/cotisations`, { methode: "POST", corps: donnees });
    $("#dialogue-paiement").close();
    afficherTontine();
    toast(tontine.organisateur ? "Paiement enregistré." : "Merci ! Ton paiement est déclaré.");
  } catch (erreur) {
    message($("#message-paiement"), erreur.message);
  }
}

function afficherCalendrier() {
  const zone = $("#onglet-calendrier");
  zone.replaceChildren();
  if (!tontine.tours.length) {
    zone.append(el("div", { class: "vide" }, "Le calendrier sera créé au démarrage de la tontine."));
    return;
  }
  const courant = tontine.tour_courant ? tontine.tour_courant.tour_id : null;
  const liste = el("div", { class: "carte" });
  for (const t of tontine.tours) {
    const classes = ["tour-ligne", t.statut === "verse" ? "verse" : "", t.id === courant ? "courant" : "",
      t.beneficiaire_id === tontine.moi.membre_id ? "moi" : ""].join(" ");
    liste.append(el("div", { class: classes },
      el("span", { class: "numero" }, t.numero),
      el("div", {}, el("b", {}, t.beneficiaire + (t.beneficiaire_id === tontine.moi.membre_id ? " (toi)" : "")),
        el("div", { class: "petit" }, dateCourte(t.echeance))),
      t.statut === "verse" ? el("span", { class: "petit" }, `✓ ${t.montant_verse}`)
        : t.id === courant ? pastille("en_cours", "En cours") : el("span", { class: "petit" }, "À venir")));
  }
  zone.append(liste);
}

function afficherMembres() {
  const zone = $("#onglet-membres");
  zone.replaceChildren();
  const brouillon = tontine.statut === "brouillon";
  const liste = el("div", { class: "carte" }, el("h3", {}, `${tontine.membres.length} membres · ${tontine.nombre_tours} mains`));
  tontine.membres.forEach((m, i) => {
    const outils = [];
    if (tontine.organisateur && brouillon) {
      outils.push(el("label", { class: "petit" }, "Mains",
        el("select", { "aria-label": `Mains de ${m.nom}`, onchange: (e) => action(`/api/tontines/${tontine.id}/membres/${m.id}`,
          { methode: "PUT", corps: { mains: Number(e.target.value) } }) },
          ...Array.from({ length: config.mains_max }, (_, k) => el("option", { value: k + 1, selected: m.mains === k + 1 }, k + 1)))));
      if (tontine.mode_ordre_code === "manuel") {
        if (i > 0) outils.push(el("button", { "aria-label": "Monter", onclick: () => action(`/api/tontines/${tontine.id}/membres/${m.id}`,
          { methode: "PUT", corps: { rang: tontine.membres[i - 1].rang } }) }, "↑"));
        if (i < tontine.membres.length - 1) outils.push(el("button", { "aria-label": "Descendre", onclick: () => action(`/api/tontines/${tontine.id}/membres/${m.id}`,
          { methode: "PUT", corps: { rang: tontine.membres[i + 1].rang } }) }, "↓"));
      }
      if (m.role !== "organisateur") {
        outils.push(el("button", { class: "danger", "aria-label": `Retirer ${m.nom}`, onclick: () => {
          if (confirm(`Retirer ${m.nom} de la tontine ?`)) action(`/api/tontines/${tontine.id}/membres/${m.id}`, { methode: "DELETE" }, `${m.nom} a été retiré(e).`);
        } }, "✕"));
      }
    }
    const infos = [el("b", {}, `${tontine.mode_ordre_code === "manuel" && brouillon ? i + 1 + ". " : ""}${m.nom}`)];
    const details = [];
    if (m.role === "organisateur") details.push("organisateur");
    if (m.mains > 1) details.push(`${m.mains} mains`);
    if (m.telephone) details.push(m.telephone);
    if (tontine.organisateur && !m.compte) details.push("pas encore de compte");
    if (m.fiabilite !== undefined && m.fiabilite !== null) details.push(`fiabilité ${m.fiabilite} %`);
    infos.push(el("span", { class: "petit" }, details.join(" · ")));
    liste.append(el("div", { class: "membre-ligne" }, el("div", { class: "infos" }, ...infos),
      outils.length ? el("div", { class: "outils" }, ...outils) : null));
  });
  zone.append(liste);
  if (tontine.organisateur && brouillon) {
    const form = el("form", { class: "form-ajout" },
      el("label", {}, "Nom", el("input", { type: "text", name: "nom", required: true, maxlength: "80" })),
      el("label", {}, "Téléphone", el("input", { type: "tel", name: "telephone", required: true, placeholder: "+221…" })),
      el("label", {}, "Mains", el("select", { name: "mains" }, ...Array.from({ length: config.mains_max }, (_, k) => el("option", { value: k + 1 }, k + 1)))),
      el("button", { class: "principal", type: "submit" }, "Ajouter"));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(form));
      d.mains = Number(d.mains);
      if (await action(`/api/tontines/${tontine.id}/membres`, { methode: "POST", corps: d }, `${d.nom} a été ajouté(e).`)) form.reset();
    });
    zone.append(el("div", { class: "carte" }, el("h3", {}, "Ajouter un membre"),
      el("span", { class: "petit" }, "Même sans smartphone : l'organisateur enregistre ses paiements. S'il crée un compte plus tard avec ce numéro, il retrouvera la tontine."),
      form));
    zone.append(blocInvitation());
  }
}

const ICONES = { creation: "✨", ajout_membre: "👤", retrait_membre: "🚪", mains: "✋", demarrage: "🎲", paiement_declare: "📨",
  paiement_recu: "💵", paiement_confirme: "✅", paiement_refuse: "❌", versement: "💰", fin: "🎉", reglages: "⚙️" };

function phrase(e) {
  const d = e.details;
  switch (e.action) {
    case "creation": return `${e.auteur} a créé la tontine : ${d.cotisation}, ${d.frequence.toLowerCase()}, à partir du ${dateCourte(d.debut)}.`;
    case "ajout_membre": return e.auteur === d.membre ? `${d.membre} a rejoint la tontine avec le lien d'invitation.` : `${e.auteur} a ajouté ${d.membre}${d.mains > 1 ? ` (${d.mains} mains)` : ""}.`;
    case "retrait_membre": return `${e.auteur} a retiré ${d.membre}.`;
    case "mains": return `${d.membre} a maintenant ${d.mains} main${d.mains > 1 ? "s" : ""}.`;
    case "demarrage": return `${e.auteur} a démarré la tontine (${d.mode.toLowerCase()}). ${d.ordre.join(" · ")}`;
    case "paiement_declare": return `${d.membre} déclare avoir payé ${d.montant} pour le tour ${d.tour} (${d.moyen}${d.reference ? ", réf. " + d.reference : ""})${d.retard ? ", en retard" : ""}.`;
    case "paiement_recu": return `${e.auteur} a reçu ${d.montant} de ${d.membre} pour le tour ${d.tour} (${d.moyen})${d.penalite ? `, pénalité de retard ${d.penalite}` : ""}.`;
    case "paiement_confirme": return `${e.auteur} a confirmé le paiement de ${d.membre} (${d.montant}, tour ${d.tour})${d.penalite ? `, pénalité de retard ${d.penalite}` : ""}.`;
    case "paiement_refuse": return `${e.auteur} a refusé le paiement déclaré par ${d.membre} (${d.montant}, tour ${d.tour}).`;
    case "versement": return `${d.beneficiaire} a reçu la cagnotte du tour ${d.tour} : ${d.montant}.${d.impayes ? ` Impayés : ${d.impayes.join(", ")}.` : ""}`;
    case "fin": return d.message;
    case "reglages": return `${e.auteur} a modifié les règles : ${d.cotisation}, ${d.frequence.toLowerCase()}, ${d.ordre.toLowerCase()}.`;
    default: return e.action;
  }
}

async function afficherJournal() {
  const zone = $("#onglet-journal");
  const { intact, verification, entrees } = await apiJson(`/api/tontines/${tontine.id}/journal`);
  zone.replaceChildren(
    el("div", { class: `sceau ${intact ? "intact" : "casse"}` }, intact ? "🔒" : "⚠️",
      intact ? `Journal vérifié : ses ${verification} entrées sont intactes. Chacune est scellée avec la précédente, rien ne peut être modifié en cachette.`
        : `Attention : l'entrée n° ${verification} du journal a été modifiée après coup.`));
  const liste = el("div", { class: "carte" });
  for (const e of entrees) {
    liste.append(el("div", { class: "journal-entree" }, el("span", { class: "icone" }, ICONES[e.action] || "•"),
      el("div", {}, el("div", {}, phrase(e)),
        el("span", { class: "quand" }, new Date(e.date).toLocaleString("fr-FR", { dateStyle: "long", timeStyle: "short" })))));
  }
  zone.append(liste);
}

function afficherOngletReglages() {
  const zone = $("#onglet-reglages");
  zone.replaceChildren();
  const brouillon = tontine.statut === "brouillon";
  zone.append(el("div", { class: "carte" },
    el("h3", {}, "Règles de la tontine"),
    el("span", { class: "doux" }, `${tontine.montant} par main, ${tontine.frequence.toLowerCase()}, à partir du ${dateCourte(tontine.date_debut)}. `
      + `${tontine.mode_ordre}. ${tontine.penalite ? `Pénalité de retard : ${tontine.penalite}` : "Pas de pénalité de retard"}`
      + `${tontine.jours_grace ? `, ${tontine.jours_grace} jour${tontine.jours_grace > 1 ? "s" : ""} de grâce` : ""}.`),
    brouillon ? el("button", { onclick: ouvrirReglages }, "Modifier les règles")
      : el("span", { class: "petit" }, "La tontine a commencé : ses règles sont figées pour tout le monde.")));
  zone.append(el("div", { class: "carte" },
    el("h3", {}, "Export Excel"),
    el("span", { class: "petit" }, "Toutes les cotisations, tour par tour, dans un fichier que tu peux ouvrir avec Excel."),
    el("button", { onclick: exporter }, "Télécharger le fichier")));
  if (tontine.statut !== "en_cours") {
    zone.append(el("div", { class: "carte" },
      el("h3", {}, "Supprimer la tontine"),
      el("button", { class: "danger", onclick: async () => {
        if (!confirm(`Supprimer définitivement « ${tontine.nom} » et son historique ?`)) return;
        try {
          await api(`/api/tontines/${tontine.id}`, { methode: "DELETE" });
          location.hash = "tontines";
          toast("Tontine supprimée.");
        } catch (e) { toast(e.message, true); }
      } }, "Supprimer")));
  }
}

async function exporter() {
  try {
    const reponse = await api(`/api/tontines/${tontine.id}/export.csv`);
    telecharger(await reponse.blob(), nomDuFichier(reponse, "tontine.csv"));
  } catch (e) {
    if (e.statut === 402) ouvrirFormule(e.message);
    else toast(e.message, true);
  }
}

// --- Formule et compte -------------------------------------------------------------------------------------------------------

function ouvrirFormule(texte = "") {
  const f = moi.formule;
  $("#formule-actuelle").textContent = f.code === "gratuit"
    ? `Tu es en formule gratuite : ${f.tontines} tontine organisée à la fois, jusqu'à ${f.membres} membres. Participer aux tontines des autres est toujours gratuit.`
    : `Tu es en formule Organisateur jusqu'au ${dateCourte(f.fin)}.`;
  $("#prix-formule").textContent = `${config.prix.XOF} (${config.prix.EUR})`;
  $("#payer").textContent = f.code === "gratuit" ? "Passer à la formule Organisateur" : "Prolonger d'un mois";
  $("#payer").disabled = !config.paiement;
  $("#note-paiement").textContent = config.paiement === "demo" ? "Mode démonstration : la formule s'active sans paiement réel."
    : "Le paiement en ligne arrive bientôt : contacte-nous pour activer la formule.";
  message($("#message-formule"), texte);
  $("#dialogue-formule").showModal();
}

function brancherCompte() {
  for (const b of $$("[data-ouvrir]")) {
    b.addEventListener("click", () => {
      if (b.dataset.ouvrir === "formule") return ouvrirFormule();
      $("#compte-infos").textContent = `${moi.nom} · ${moi.telephone}`;
      message($("#message-compte"), "");
      $("#dialogue-compte").showModal();
    });
  }
  $("#payer").addEventListener("click", async () => {
    try {
      moi = await apiJson("/api/formule/commande", { methode: "POST", corps: {} });
      afficherFormule();
      $("#dialogue-formule").close();
      toast("Formule Organisateur activée. Merci !");
    } catch (e) {
      message($("#message-formule"), e.message);
    }
  });
  $("#deconnexion").addEventListener("click", async () => {
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
      message($("#message-compte"), "Mot de passe changé.", "ok");
    } catch (e) {
      message($("#message-compte"), e.message);
    }
  });
}

// --- Démarrage ---------------------------------------------------------------------------------------------------------------

async function demarrerApplication() {
  config = await apiJson("/api/configuration");
  remplirListe($("#choix-devise"), config.devises);
  remplirListe($("#choix-frequence"), config.frequences);
  remplirListe($("#choix-ordre"), config.modes_ordre);
  remplirListe($("#choix-moyen"), config.moyens);
  const moyens = $("#choix-moyen");
  moyens.remove([...moyens.options].findIndex((o) => o.value === "en_ligne"));  // réservé aux paiements automatiques
  brancherAuth();
  brancherCompte();
  $("#nouvelle-tontine").addEventListener("click", ouvrirCreation);
  $("#form-tontine").addEventListener("submit", validerTontine);
  $("#form-paiement").addEventListener("submit", validerPaiement);
  for (const b of $$(".onglets button")) b.addEventListener("click", () => choisirOnglet(b.dataset.onglet));
  await preparerInvitation();
  try {
    moi = await apiJson("/api/moi");
  } catch (e) {
    if (e.statut !== 401) throw e;
  }
  afficherBoutonRejoindre();
  window.addEventListener("hashchange", () => router().catch((e) => toast(e.message, true)));
  if (codeInvitation && moi) {
    afficherVue("aucune");  // seule la carte d'invitation reste visible, avec son bouton « Rejoindre »
    return;
  }
  await router();
}

demarrerApplication().catch((e) => toast(`Impossible de démarrer : ${e.message}`, true));
