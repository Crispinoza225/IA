/* Le jeu : fiche de la brute, arène, combats, tournoi, classement. Navigation par l'ancre de l'adresse (#arene…). */
'use strict';

let REGLES = null;
let MOI = null;          // la brute connectée (null si visiteur)
let DERNIER = null;      // résultat du dernier combat lancé, pour l'écran de fin
const vue = $('#vue');

function toast(texte) {
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = texte;
  document.body.append(t);
  setTimeout(() => t.remove(), 3200);
}

async function rafraichirMoi() {
  try { MOI = await api('/api/moi'); } catch (e) { if (e.statut !== 401) throw e; MOI = null; }
  return MOI;
}

function majNav(actif) {
  const liens = MOI
    ? [['', 'Ma brute'], ['arene', 'Arène'], ['tournoi', 'Tournoi'], ['classement', 'Classement']]
    : [['classement', 'Classement']];
  $('#nav').innerHTML = liens.map(([h, t]) => `<a href="#${h}" class="${h === actif ? 'actif' : ''}">${t}</a>`).join('')
    + (MOI ? '<button id="deconnexion">Quitter</button>' : '<a href="/">Créer ma brute</a>');
  if (MOI) $('#deconnexion').onclick = async () => { await api('/api/deconnexion', {}); location.href = '/'; };
}

/* --- Fiche d'une brute ----------------------------------------------------------------------------------------------- */
function jaugeCarac(cle, valeur) {
  return `<div class="carac"><span>${REGLES.caracs[cle]}</span><span>${valeur}</span>
    <div class="jauge"><i style="width:${Math.min(100, (valeur / 30) * 100)}%"></i></div></div>`;
}

function ficheHTML(b) {
  const armes = b.armes.length ? b.armes.map((a) => `<li class="objet">${iconeArme(a)}${echapper(REGLES.armes[a].nom)}</li>`).join('')
    : '<li class="vide">Aucune : elle se bat à mains nues.</li>';
  const competences = b.competences.length ? b.competences.map((c) => `<li class="objet competence" title="${echapper(REGLES.competences[c].texte)}">${echapper(REGLES.competences[c].nom)}</li>`).join('')
    : '<li class="vide">Aucune pour l\'instant.</li>';
  const animaux = b.animaux.length ? b.animaux.map((a) => `<li class="objet">${dessinerAnimal(a)}${echapper(REGLES.animaux[a])}</li>`).join('')
    : '<li class="vide">Aucun.</li>';
  return `<section class="cadre fiche">
    <div class="portrait">
      ${dessinerBrute(b.apparence, { arme: b.armes[0], bouclier: b.competences.includes('bouclier'), carrure: carrure(b.caracs) })}
      <div class="animaux">${b.animaux.map(dessinerAnimal).join('')}</div>
    </div>
    <div>
      <h1 class="nom-brute">${echapper(b.nom)}</h1>
      <span class="niveau">NIVEAU ${b.niveau}</span>
      ${b.bot ? '<span class="petit"> · brute sauvage</span>' : ''}
      ${b.maitre ? `<span class="petit"> · élève de <a href="#brute/${encodeURIComponent(b.maitre)}">${echapper(b.maitre)}</a></span>` : ''}
      <div class="petit" style="margin-top:6px">Expérience : ${b.xp} / ${b.seuil}</div>
      <div class="jauge"><i style="width:${Math.min(100, (b.xp / b.seuil) * 100)}%"></i></div>
      <div class="petit" style="margin-top:8px">Points de vie : <b>${b.pv}</b></div>
      <div class="jauge pv"><i style="width:100%"></i></div>
      <div class="caracs">${Object.keys(REGLES.caracs).map((c) => jaugeCarac(c, b.caracs[c])).join('')}</div>
      <div class="bilan"><span class="v">${b.victoires} victoires</span><span class="d">${b.defaites} défaites</span></div>
      <h3 style="margin-top:16px">Armes</h3><ul class="liste-objets">${armes}</ul>
      <h3>Compétences</h3><ul class="liste-objets">${competences}</ul>
      <h3>Animaux</h3><ul class="liste-objets">${animaux}</ul>
    </div>
  </section>`;
}

function historiqueHTML(b) {
  if (!b.historique.length) return '<p class="vide">Aucun combat pour l\'instant.</p>';
  return `<ul class="historique">${b.historique.map((h) => `<li>
      <span class="res ${h.victoire ? 'v' : 'd'}">${h.victoire ? 'Victoire' : 'Défaite'}</span>
      <span>${h.tournoi ? '🏆 ' : ''}${h.attaque ? 'contre' : 'attaquée par'} <a href="#brute/${encodeURIComponent(h.adversaire)}">${echapper(h.adversaire)}</a></span>
      <a class="revoir" href="#combat/${h.id}">Revoir</a></li>`).join('')}</ul>`;
}

/* --- Vues ------------------------------------------------------------------------------------------------------------- */
async function vueCellule() {
  await rafraichirMoi();
  if (!MOI) { location.href = '/'; return; }
  const b = MOI;
  const lien = `${location.origin}/?maitre=${encodeURIComponent(b.nom)}`;
  const choix = b.choix ? `<section class="cadre choix-niveau">
      <h2>⭐ Niveau ${b.niveau} !</h2><p>Choisis le bonus de ta brute :</p>
      <div class="options">${b.choix.map((o, i) => `<button class="btn option" data-choix="${i}">${illustrationOption(o)}${echapper(o.libelle)}${o.type === 'competence' ? `<small>${echapper(REGLES.competences[o.cle].texte)}</small>` : ''}</button>`).join('')}</div>
    </section>` : '';
  const tournoi = b.tournoi ? `<p>Dernier tournoi (${new Date(`${b.tournoi.date}T12:00`).toLocaleDateString('fr-FR')}) : vainqueur <b>${echapper(b.tournoi.vainqueur)}</b>. <a href="#tournoi">Voir le tableau</a></p>` : '';
  vue.innerHTML = `${choix}${ficheHTML(b)}
    <div class="grille-2">
      <section class="cadre">
        <h2>⚔️ Combats</h2>
        <p class="compteur"><b>${b.combats_restants}</b> / ${REGLES.combats_par_jour} combats aujourd'hui</p>
        <div class="actions">
          <a class="btn rouge" href="#arene" ${b.combats_restants && !b.choix ? '' : 'aria-disabled="true"'}>Aller à l'arène</a>
          ${b.inscrit_tournoi ? '<span class="petit">✅ Inscrite au tournoi de ce soir</span>' : '<button class="btn or" id="inscrire">S\'inscrire au tournoi</button>'}
        </div>
        ${b.combats_restants ? '' : '<p class="petit">Ta brute se repose : nouveaux combats demain.</p>'}
        ${tournoi}
      </section>
      <section class="cadre">
        <h2>🎓 Élèves</h2>
        <p class="petit">Chaque victoire d'un de tes élèves te rapporte 1 point d'expérience. Partage ce lien :</p>
        <div class="lien-eleve"><input type="text" readonly value="${echapper(lien)}" id="lienEleve"><button class="btn petit-btn" id="copier">Copier</button></div>
        ${b.eleves.length ? `<ul class="liste-objets" style="margin-top:12px">${b.eleves.map((e) => `<li class="objet" style="padding:4px 10px"><a href="#brute/${encodeURIComponent(e.nom)}">${echapper(e.nom)}</a>&nbsp;· niv. ${e.niveau}</li>`).join('')}</ul>` : '<p class="vide">Pas encore d\'élève.</p>'}
      </section>
    </div>
    <section class="cadre" style="margin-top:20px"><h2>📜 Derniers combats</h2>${historiqueHTML(b)}</section>`;
  $$('[data-choix]').forEach((bouton) => {
    bouton.onclick = async () => {
      try {
        const r = await api('/api/choisir', { choix: Number(bouton.dataset.choix) });
        toast(`${r.libelle} ✓`);
        vueCellule();
      } catch (e) { toast(e.message); }
    };
  });
  if ($('#inscrire')) $('#inscrire').onclick = async () => {
    try { await api('/api/tournoi', {}); toast('Inscrite ! Le tournoi se dispute cette nuit.'); vueCellule(); } catch (e) { toast(e.message); }
  };
  $('#copier').onclick = async () => {
    try { await navigator.clipboard.writeText(lien); toast('Lien copié !'); } catch { $('#lienEleve').select(); }
  };
  $$('a[aria-disabled]').forEach((a) => { a.onclick = (e) => { e.preventDefault(); toast(b.choix ? 'Choisis d\'abord ton bonus.' : 'Plus de combats aujourd\'hui.'); }; });
}

function illustrationOption(o) {
  if (o.type === 'arme') return iconeArme(o.cle);
  if (o.type === 'animal') return dessinerAnimal(o.cle);
  if (o.type === 'competence') return '<span style="font-size:1.8rem">✨</span>';
  return '<span style="font-size:1.8rem">💪</span>';
}

async function vueArene() {
  await rafraichirMoi();
  if (!MOI) { location.href = '/'; return; }
  if (MOI.choix) { vue.innerHTML = '<section class="cadre"><h2>Niveau supérieur !</h2><p>Choisis d\'abord le bonus de ta brute.</p><a class="btn rouge" href="#">Choisir</a></section>'; return; }
  if (!MOI.combats_restants) { vue.innerHTML = '<section class="cadre"><h2>Ta brute est épuisée</h2><p>Elle a livré ses combats du jour. Reviens demain !</p><a class="btn" href="#">Retour</a></section>'; return; }
  vue.innerHTML = `<section class="cadre"><h2>🏟️ L'arène</h2>
    <p>Choisis ton adversaire. Encore <b>${MOI.combats_restants}</b> combat(s) aujourd'hui.</p>
    <div class="adversaires" id="adversaires"><p class="vide">Recherche d'adversaires…</p></div>
    <div class="actions"><button class="btn petit-btn" id="autres">🔄 D'autres adversaires</button></div></section>`;
  const remplir = async () => {
    const liste = await api('/api/adversaires');
    $('#adversaires').innerHTML = liste.map((a) => `<button class="cadre adversaire" data-nom="${echapper(a.nom)}">
        ${dessinerBrute(a.apparence)}<b>${echapper(a.nom)}</b><span class="niveau">NIV. ${a.niveau}</span>
        <div class="petit">${a.pv} PV · ${a.victoires} V / ${a.defaites} D</div></button>`).join('');
    $$('.adversaire').forEach((bouton) => { bouton.onclick = () => lancerCombat(bouton.dataset.nom); });
  };
  $('#autres').onclick = remplir;
  await remplir();
}

async function lancerCombat(nom) {
  try {
    DERNIER = await api('/api/combattre', { adversaire: nom });
    location.hash = `#combat/${DERNIER.combat}`;
  } catch (e) { toast(e.message); }
}

async function vueCombat(id) {
  const donnees = await api(`/api/combats/${id}`);
  const replay = new Replay(vue, donnees, REGLES, {
    fin: (actions) => {
      const moiDedans = MOI && donnees.brutes.some((b) => b.nom === MOI.nom);
      if (DERNIER && DERNIER.combat === donnees.id) {
        actions.insertAdjacentHTML('beforebegin', `<p style="font-weight:800">${DERNIER.xp ? `+${DERNIER.xp} point${DERNIER.xp > 1 ? 's' : ''} d'expérience` : 'Pas d\'expérience : adversaire trop faible.'}</p>`);
        DERNIER = null;
      }
      actions.innerHTML = moiDedans
        ? '<a class="btn rouge" href="#arene">Combat suivant</a><a class="btn" href="#">Ma brute</a>'
        : `<a class="btn" href="#brute/${encodeURIComponent(donnees.brutes[0].nom)}">${echapper(donnees.brutes[0].nom)}</a><a class="btn" href="#brute/${encodeURIComponent(donnees.brutes[1].nom)}">${echapper(donnees.brutes[1].nom)}</a>`;
    },
  });
  await replay.jouer();
}

async function vueBrute(nom) {
  const b = await api(`/api/brutes/${encodeURIComponent(nom)}`);
  const defi = MOI && MOI.nom !== b.nom;
  vue.innerHTML = `${ficheHTML(b)}
    ${defi ? `<div class="actions"><button class="btn rouge" id="defier">⚔️ Défier ${echapper(b.nom)}</button>
      <span class="petit">Utilise un de tes combats du jour (${MOI.combats_restants} restant${MOI.combats_restants > 1 ? 's' : ''}).</span></div>` : ''}
    ${b.eleves.length ? `<section class="cadre" style="margin-top:20px"><h2>🎓 Élèves</h2><ul class="liste-objets">${b.eleves.map((e) => `<li class="objet" style="padding:4px 10px"><a href="#brute/${encodeURIComponent(e.nom)}">${echapper(e.nom)}</a>&nbsp;· niv. ${e.niveau}</li>`).join('')}</ul></section>` : ''}
    <section class="cadre" style="margin-top:20px"><h2>📜 Derniers combats</h2>${historiqueHTML(b)}</section>`;
  if (defi) $('#defier').onclick = () => lancerCombat(b.nom);
}

async function vueTournoi() {
  await rafraichirMoi();
  if (!MOI) { location.href = '/'; return; }
  const t = MOI.tournoi;
  const inscription = MOI.inscrit_tournoi
    ? '<p>✅ Ta brute est inscrite au tournoi de ce soir. Résultats demain !</p>'
    : '<p>Inscris ta brute : le tournoi se dispute à minuit entre huit brutes de niveau proche. Chaque victoire rapporte 1 point d\'expérience, le vainqueur en gagne 5 de plus.</p><button class="btn or" id="inscrire">S\'inscrire au tournoi de ce soir</button>';
  const nomsTours = ['Quarts de finale', 'Demi-finales', 'Finale'];
  const tableau = t ? `<section class="cadre" style="margin-top:20px">
      <h2>🏆 Tournoi du ${new Date(`${t.date}T12:00`).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long' })}</h2>
      <div class="tableau">${t.tours.map((manche, i) => `<div class="manche"><h3>${nomsTours[i] || `Tour ${i + 1}`}</h3>${manche.map((m) => `<div class="match">
          <div><span class="${m.gagnant === m.a ? 'gagne' : ''}">${echapper(m.a)}</span></div>
          <div><span class="${m.gagnant === m.b ? 'gagne' : ''}">${echapper(m.b)}</span><a href="#combat/${m.id}">Revoir</a></div></div>`).join('')}</div>`).join('')}</div>
      <p class="champion">👑 ${echapper(t.vainqueur)}</p></section>` : '';
  vue.innerHTML = `<section class="cadre"><h2>🏆 Le tournoi</h2>${inscription}</section>${tableau}`;
  if ($('#inscrire')) $('#inscrire').onclick = async () => {
    try { await api('/api/tournoi', {}); toast('Inscrite !'); vueTournoi(); } catch (e) { toast(e.message); }
  };
}

async function vueClassement() {
  const liste = await api('/api/classement');
  vue.innerHTML = `<section class="cadre"><h2>🏆 Classement</h2>
    ${liste.length ? `<table class="classement"><thead><tr><th>#</th><th></th><th>Brute</th><th>Niveau</th><th>Victoires</th><th>Défaites</th></tr></thead>
    <tbody>${liste.map((b, i) => `<tr><td class="rang">${i + 1}</td><td class="tete">${teteBrute(b.apparence)}</td>
      <td><a href="#brute/${encodeURIComponent(b.nom)}">${echapper(b.nom)}</a></td><td>${b.niveau}</td><td>${b.victoires}</td><td>${b.defaites}</td></tr>`).join('')}</tbody></table>`
    : '<p class="vide">Aucune brute pour l\'instant.</p>'}</section>`;
}

/* --- Navigation ------------------------------------------------------------------------------------------------------ */
async function router() {
  const [nom, ...reste] = decodeURIComponent(location.hash.slice(1)).split('/');
  const arg = reste.join('/');
  majNav(nom);
  window.scrollTo(0, 0);
  try {
    if (nom === 'arene') await vueArene();
    else if (nom === 'combat') await vueCombat(Number(arg));
    else if (nom === 'brute') await vueBrute(arg);
    else if (nom === 'tournoi') await vueTournoi();
    else if (nom === 'classement') await vueClassement();
    else await vueCellule();
  } catch (e) {
    vue.innerHTML = `<section class="cadre"><h2>Oups</h2><p>${echapper(e.message)}</p><a class="btn" href="#">Retour</a></section>`;
  }
}

(async () => {
  REGLES = await api('/api/regles');
  await rafraichirMoi();
  window.addEventListener('hashchange', router);
  router();
})();
