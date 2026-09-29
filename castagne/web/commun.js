/* Castagne : appels au serveur et dessins des brutes, des animaux et des armes (SVG). */
'use strict';

async function api(chemin, corps) {
  const options = corps === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Castagne': '1' }, body: JSON.stringify(corps),
  };
  const reponse = await fetch(chemin, { credentials: 'same-origin', ...options });
  const donnees = await reponse.json().catch(() => ({}));
  if (!reponse.ok) {
    const erreur = new Error(donnees.erreur || `Erreur ${reponse.status}`);
    erreur.statut = reponse.status;
    throw erreur;
  }
  return donnees;
}

const echapper = (texte) => String(texte ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const $ = (sel, racine = document) => racine.querySelector(sel);
const $$ = (sel, racine = document) => Array.from(racine.querySelectorAll(sel));

const ENCRE = '#3b2a1a';
const PEAUX = ['#f6d2b8', '#eab98f', '#d39a6a', '#b07448', '#8a5634', '#5e3a22'];
const CHEVEUX = ['#2b1d14', '#5a3a1e', '#8b5a2b', '#c98b3a', '#e8c66a', '#b33a1a', '#8f8f8f', '#f2efe6'];
const HAUTS = ['#c0392b', '#2f6690', '#3f8f3a', '#d9a441', '#7d3c98', '#e67e22', '#1d7874', '#f2efe6', '#34495e', '#e84a7a'];
const BAS = ['#4a3526', '#2c3e50', '#5d6d7e', '#6b4f2a', '#1b4332', '#7b2d26', '#3d3d3d', '#8d7b68'];

function assombrir(hex, facteur = 0.8) {
  const n = parseInt(hex.slice(1), 16);
  const c = [n >> 16, (n >> 8) & 255, n & 255].map((v) => Math.round(v * facteur));
  return `#${c.map((v) => v.toString(16).padStart(2, '0')).join('')}`;
}

/* --- Armes : dessinées la poignée à l'origine, la lame vers le haut -------------------------------------------------- */
const METAL = '#dfe6ea', BOIS = '#8b5a2b', BOIS_FONCE = '#6b4226';
const trait = `stroke="${ENCRE}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"`;
const manche = (bas, haut, couleur = BOIS, largeur = 4) =>
  `<rect x="${-largeur / 2}" y="${haut}" width="${largeur}" height="${bas - haut}" rx="${largeur / 2}" fill="${couleur}" ${trait}/>`;
const ARMES_SVG = {
  couteau: `${manche(8, -4, BOIS_FONCE)}<path d="M-2.5 -4 L2.8 -4 L1 -24 L-2.5 -17Z" fill="${METAL}" ${trait}/>`,
  epee: `${manche(9, -3, BOIS_FONCE)}<rect x="-8" y="-6" width="16" height="4" rx="2" fill="#d9a441" ${trait}/><path d="M-3 -6 L3 -6 L3 -44 L0 -50 L-3 -44Z" fill="${METAL}" ${trait}/>`,
  cimeterre: `${manche(9, -3, BOIS_FONCE)}<rect x="-7" y="-6" width="14" height="4" rx="2" fill="#d9a441" ${trait}/><path d="M-3 -6 L3 -6 C8 -22 10 -34 2 -48 C2 -34 -2 -22 -3 -6Z" fill="${METAL}" ${trait}/>`,
  hache: `${manche(10, -40)}<path d="M2 -38 C14 -44 20 -34 18 -24 C12 -28 6 -28 2 -26Z" fill="${METAL}" ${trait}/>`,
  marteau: `${manche(10, -40)}<rect x="-11" y="-50" width="22" height="13" rx="2" fill="#9aa4ab" ${trait}/>`,
  massue: `<path d="M-2.5 10 L2.5 10 L6 -34 C6 -44 -6 -44 -6 -34Z" fill="#a0692f" ${trait}/><circle cx="-2" cy="-30" r="1.5" fill="${ENCRE}"/><circle cx="2" cy="-22" r="1.5" fill="${ENCRE}"/><circle cx="-1" cy="-38" r="1.5" fill="${ENCRE}"/>`,
  lance: `${manche(22, -58, BOIS, 3.5)}<path d="M-4 -56 L0 -72 L4 -56Z" fill="${METAL}" ${trait}/>`,
  trident: `${manche(20, -50, BOIS, 3.5)}<path d="M-9 -64 L-9 -48 L9 -48 L9 -64 M0 -68 L0 -48" fill="none" stroke="${ENCRE}" stroke-width="5" stroke-linecap="round"/><path d="M-9 -64 L-9 -48 L9 -48 L9 -64 M0 -68 L0 -48" fill="none" stroke="${METAL}" stroke-width="2.6" stroke-linecap="round"/>`,
  baton: manche(26, -52, '#a0692f', 4.5),
  fleau: `${manche(10, -18, BOIS_FONCE)}<path d="M0 -18 Q6 -26 2 -32" fill="none" stroke="${ENCRE}" stroke-width="2" stroke-dasharray="2 2"/><circle cx="3" cy="-38" r="7" fill="#9aa4ab" ${trait}/><path d="M3 -47 L3 -45 M11 -38 L10 -38 M-5 -38 L-4 -38 M3 -29 L3 -31" ${trait}/>`,
  poele: `${manche(10, -14, '#2b2b2b')}<ellipse cx="0" cy="-26" rx="11" ry="13" fill="#3d3d3d" ${trait}/><ellipse cx="0" cy="-26" rx="7" ry="9" fill="#555"/>`,
  cle: `${manche(10, -24, '#9aa4ab', 5)}<path d="M-7 -24 L-7 -34 L-2 -34 L-2 -28 L2 -28 L2 -34 L7 -34 L7 -24Z" fill="#9aa4ab" ${trait}/>`,
  os: `<rect x="-3" y="-30" width="6" height="36" fill="#f2efe6" ${trait}/><circle cx="-3.5" cy="-31" r="4.5" fill="#f2efe6" ${trait}/><circle cx="3.5" cy="-31" r="4.5" fill="#f2efe6" ${trait}/><circle cx="-3.5" cy="7" r="4.5" fill="#f2efe6" ${trait}/><circle cx="3.5" cy="7" r="4.5" fill="#f2efe6" ${trait}/>`,
  fouet: `${manche(10, -8, BOIS_FONCE)}<path d="M0 -8 C10 -24 -14 -34 6 -52" fill="none" stroke="${ENCRE}" stroke-width="3.5" stroke-linecap="round"/><path d="M0 -8 C10 -24 -14 -34 6 -52" fill="none" stroke="#a0692f" stroke-width="1.8" stroke-linecap="round"/>`,
  nunchaku: `${manche(10, -12, '#2b2b2b')}<path d="M0 -12 Q4 -16 2 -20" fill="none" stroke="${ENCRE}" stroke-width="1.6"/><rect x="0" y="-42" width="4.5" height="22" rx="2" fill="#2b2b2b" ${trait} transform="rotate(20 2 -20)"/>`,
  eventail: `${manche(8, -4, '#2b2b2b', 3)}<path d="M0 -2 L-16 -26 A20 20 0 0 1 16 -26Z" fill="#c0392b" ${trait}/><path d="M0 -2 L-8 -29 M0 -2 L0 -30 M0 -2 L8 -29" stroke="${ENCRE}" stroke-width="1"/>`,
  masse: `${manche(10, -34, BOIS_FONCE)}<circle cx="0" cy="-40" r="8" fill="#9aa4ab" ${trait}/><path d="M0 -52 L0 -49 M-12 -40 L-9 -40 M12 -40 L9 -40 M-8.5 -48.5 L-6.5 -46.5 M8.5 -48.5 L6.5 -46.5" ${trait}/>`,
  balai: `${manche(12, -44, '#c98b3a', 3.5)}<path d="M-9 -44 L9 -44 L6 -58 L-6 -58Z" fill="#e8c66a" ${trait} transform="rotate(180 0 -44)"/>`,
  shuriken: `<path d="M0 -14 L3 -3 L14 0 L3 3 L0 14 L-3 3 L-14 0 L-3 -3Z" fill="${METAL}" ${trait}/><circle r="2.2" fill="${ENCRE}"/>`,
  javelot: `${manche(18, -54, '#c98b3a', 3)}<path d="M-3 -52 L0 -66 L3 -52Z" fill="${METAL}" ${trait}/>`,
};

function icone(contenu, vue = '-30 -75 60 105', classe = 'icone') {
  return `<svg class="${classe}" viewBox="${vue}" aria-hidden="true">${contenu}</svg>`;
}
const iconeArme = (cle) => icone(`<g transform="rotate(35)">${ARMES_SVG[cle] || ''}</g>`);

/* --- Brute : de profil, tournée vers la droite ----------------------------------------------------------------------- */
function coiffure(style, couleur, derriere) {
  const ombre = assombrir(couleur, 0.85);
  const t = `stroke="${ENCRE}" stroke-width="2.2" stroke-linejoin="round"`;
  if (derriere) {
    if (style === 3) return `<path d="M42 36 C38 56 40 70 48 76 L58 70 L56 40Z" fill="${ombre}" ${t}/>`;
    if (style === 4) return `<path d="M44 34 C30 38 28 58 34 66 C38 56 40 48 46 44Z" fill="${ombre}" ${t}/>`;
    if (style === 5) return `<circle cx="56" cy="38" r="24" fill="${couleur}" ${t}/>`;
    return '';
  }
  switch (style) {
    case 1: return `<path d="M41 40 C40 24 54 18 66 22 C72 24 76 30 75 36 C68 30 58 30 52 34 C48 36 46 42 45 46Z" fill="${couleur}" ${t}/>`;
    case 2: return `<path d="M46 30 L44 14 L52 24 L54 8 L60 22 L66 10 L66 25 L74 18 L70 30 C62 26 52 26 46 30Z" fill="${couleur}" ${t}/>`;
    case 3: case 4: return `<path d="M40 44 C38 24 54 16 67 22 C73 25 76 31 75 36 C66 30 56 30 50 36 C46 40 44 46 44 52Z" fill="${couleur}" ${t}/>`;
    case 5: return `<path d="M44 30 C50 24 62 24 70 28" fill="none" ${t}/>`;
    case 6: return `<circle cx="48" cy="22" r="8" fill="${couleur}" ${t}/><path d="M41 42 C40 25 54 19 66 23 C72 25 76 31 75 36 C68 31 58 31 52 35 C48 38 46 43 45 47Z" fill="${couleur}" ${t}/>`;
    default: return '';
  }
}

function yeux(style) {
  switch (style) {
    case 1: return `<path d="M62 40 L71 41" stroke="${ENCRE}" stroke-width="3" stroke-linecap="round"/><path d="M60 34 L72 37" stroke="${ENCRE}" stroke-width="2.6" stroke-linecap="round"/>`;
    case 2: return `<circle cx="67" cy="40" r="4.6" fill="#fff" stroke="${ENCRE}" stroke-width="1.6"/><circle cx="68.5" cy="40.5" r="2.2" fill="${ENCRE}"/><path d="M62 33 L72 34" stroke="${ENCRE}" stroke-width="2.4" stroke-linecap="round"/>`;
    case 3: return `<path d="M63 41 Q67 38 71 41" fill="none" stroke="${ENCRE}" stroke-width="2.4" stroke-linecap="round"/><path d="M61 35 L72 34" stroke="${ENCRE}" stroke-width="2.4" stroke-linecap="round"/>`;
    default: return `<circle cx="67" cy="40" r="2.6" fill="${ENCRE}"/><path d="M61 34 L72 36" stroke="${ENCRE}" stroke-width="2.6" stroke-linecap="round"/>`;
  }
}

function barbe(style, couleur) {
  const t = `stroke="${ENCRE}" stroke-width="2" stroke-linejoin="round"`;
  switch (style) {
    case 1: return `<path d="M60 49 Q68 46 75 49" fill="none" stroke="${couleur}" stroke-width="3.5" stroke-linecap="round"/>`;
    case 2: return `<path d="M50 46 C52 60 62 66 72 58 C74 54 74 52 74 50 C68 54 60 54 56 48Z" fill="${couleur}" ${t}/>`;
    case 3: return `<path d="M52 48 C54 70 64 78 70 72 C74 66 74 56 74 50 C68 55 60 54 56 48Z" fill="${couleur}" ${t}/>`;
    default: return '';
  }
}

/* options : arme (clé), bouclier (booléen), carrure (0,85 à 1,3) */
function dessinerBrute(a, options = {}) {
  const peau = PEAUX[a.peau] || PEAUX[1], ombrePeau = assombrir(peau, 0.82);
  const cheveux = CHEVEUX[a.cheveux] || CHEVEUX[0];
  const haut = HAUTS[a.haut] || HAUTS[0], bas = BAS[a.bas] || BAS[0];
  const k = Math.max(0.85, Math.min(1.3, options.carrure || 1)) * (a.genre === 'f' ? 0.92 : 1);
  const epaule = 17 * k, taille = 12 * k;
  const t = `stroke="${ENCRE}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"`;
  const jambe = (x1, x2, couleur) => `<path d="M${x1} 100 L${x2} 146" stroke="${ENCRE}" stroke-width="${13 * k}" stroke-linecap="round"/><path d="M${x1} 100 L${x2} 146" stroke="${couleur}" stroke-width="${13 * k - 4.8}" stroke-linecap="round"/><ellipse cx="${x2 + 4}" cy="149" rx="9" ry="5" fill="#3b2a1a"/>`;
  const bras = (x1, y1, x2, y2, couleur, epaisseur) => `<path d="M${x1} ${y1} L${x2} ${y2}" stroke="${ENCRE}" stroke-width="${epaisseur + 4.8}" stroke-linecap="round"/><path d="M${x1} ${y1} L${x2} ${y2}" stroke="${couleur}" stroke-width="${epaisseur}" stroke-linecap="round"/>`;
  const arme = options.arme && ARMES_SVG[options.arme]
    ? `<g transform="translate(84 90) rotate(${ARMES_SVG[options.arme] && options.arme === 'shuriken' ? 0 : 55})">${ARMES_SVG[options.arme]}</g>` : '';
  const bouclier = options.bouclier
    ? `<g transform="translate(36 86)"><circle r="15" fill="#a0692f" ${t}/><circle r="10" fill="none" stroke="${ENCRE}" stroke-width="1.6"/><circle r="3.5" fill="#d9a441" ${t}/></g>` : '';
  return `<svg class="brute" viewBox="-15 -25 150 185" aria-hidden="true">
    <ellipse cx="60" cy="152" rx="32" ry="5" fill="rgba(0,0,0,.18)"/>
    ${jambe(52, 46, assombrir(bas, 0.8))}
    ${bras(50, 68, 42, 94, ombrePeau, 8 * k)}
    ${bouclier}
    ${coiffure(a.coiffure, cheveux, true)}
    <path d="M${58 - epaule} 64 Q58 56 ${58 + epaule} 64 L${58 + taille} 104 L${58 - taille} 104Z" fill="${haut}" ${t}/>
    <rect x="${58 - taille - 1}" y="96" width="${2 * taille + 2}" height="7" rx="2" fill="#3b2a1a"/>
    <rect x="${56}" y="97" width="7" height="5" rx="1" fill="#d9a441"/>
    ${jambe(64, 70, bas)}
    <path d="M52 56 L52 64 L64 64 L64 56Z" fill="${ombrePeau}"/>
    <circle cx="58" cy="40" r="18" fill="${peau}" ${t}/>
    <circle cx="52" cy="43" r="4.5" fill="${ombrePeau}" ${t}/>
    <path d="M74 42 L80 47 L74 49" fill="${peau}" ${t}/>
    ${yeux(a.yeux)}
    <path d="M65 54 Q70 55 74 52" fill="none" stroke="${ENCRE}" stroke-width="2.2" stroke-linecap="round"/>
    ${barbe(a.genre === 'f' ? 0 : a.barbe, cheveux)}
    ${coiffure(a.coiffure, cheveux, false)}
    ${arme}
    ${bras(66, 68, 82, 88, peau, 8.5 * k)}
    <circle cx="84" cy="90" r="6" fill="${peau}" ${t}/>
  </svg>`;
}

/* La carrure dépend de la force et de l'endurance. */
const carrure = (caracs) => (caracs ? 0.85 + Math.min(0.45, ((caracs.force || 0) + (caracs.endurance || 0) - 10) * 0.02) : 1);

/* --- Animaux : de profil, tournés vers la droite --------------------------------------------------------------------- */
const ANIMAUX_STYLE = {
  chien: { corps: '#b07a45', ventre: '#e1b98a', taille: 0.62, oreille: 'tombante', queue: 'courte' },
  loup: { corps: '#8a8f99', ventre: '#d6d8dc', taille: 0.8, oreille: 'pointue', queue: 'touffue' },
  panthere: { corps: '#2d2a33', ventre: '#3c3844', taille: 0.85, oreille: 'ronde', queue: 'longue', yeux: '#f3c623' },
  ours: { corps: '#6b4428', ventre: '#8b5e3c', taille: 1.1, oreille: 'ronde', queue: 'aucune' },
};

function dessinerAnimal(cle) {
  const s = ANIMAUX_STYLE[cle] || ANIMAUX_STYLE.chien;
  const t = `stroke="${ENCRE}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"`;
  const patte = (x, fonce) => `<path d="M${x} 58 L${x} 80" stroke="${ENCRE}" stroke-width="10" stroke-linecap="round"/><path d="M${x} 58 L${x} 80" stroke="${fonce ? assombrir(s.corps, 0.8) : s.corps}" stroke-width="5.5" stroke-linecap="round"/>`;
  const oreilles = {
    tombante: `<path d="M82 22 C76 26 76 38 80 40 C84 34 86 28 86 24Z" fill="${assombrir(s.corps, 0.75)}" ${t}/>`,
    pointue: `<path d="M84 22 L86 6 L94 20Z" fill="${s.corps}" ${t}/>`,
    ronde: `<circle cx="86" cy="20" r="6" fill="${s.corps}" ${t}/>`,
  }[s.oreille];
  const queue = {
    courte: `<path d="M24 46 Q14 36 18 28" fill="none" stroke="${ENCRE}" stroke-width="7" stroke-linecap="round"/><path d="M24 46 Q14 36 18 28" fill="none" stroke="${s.corps}" stroke-width="3" stroke-linecap="round"/>`,
    touffue: `<path d="M26 46 C10 44 6 58 2 64 C14 62 22 56 28 52Z" fill="${s.corps}" ${t}/>`,
    longue: `<path d="M26 46 C8 50 6 70 16 74" fill="none" stroke="${ENCRE}" stroke-width="8" stroke-linecap="round"/><path d="M26 46 C8 50 6 70 16 74" fill="none" stroke="${s.corps}" stroke-width="3.6" stroke-linecap="round"/>`,
    aucune: '',
  }[s.queue];
  const museau = cle === 'ours' ? `<ellipse cx="104" cy="36" rx="9" ry="7" fill="${s.ventre}" ${t}/>`
    : `<path d="M96 28 L114 34 L112 42 L96 44Z" fill="${s.ventre}" ${t}/>`;
  return `<svg class="animal" viewBox="0 0 120 90" style="--taille:${s.taille}" aria-hidden="true">
    <ellipse cx="60" cy="84" rx="36" ry="4" fill="rgba(0,0,0,.18)"/>
    ${queue}${patte(36, true)}${patte(70, true)}
    <ellipse cx="54" cy="48" rx="34" ry="17" fill="${s.corps}" ${t}/>
    <path d="M34 58 Q54 66 76 58" fill="none" stroke="${s.ventre}" stroke-width="4" stroke-linecap="round"/>
    ${patte(44, false)}${patte(78, false)}
    <circle cx="92" cy="32" r="14" fill="${s.corps}" ${t}/>
    ${oreilles}${museau}
    <circle cx="${cle === 'ours' ? 111 : 115}" cy="${cle === 'ours' ? 33 : 34}" r="3" fill="${ENCRE}"/>
    <circle cx="95" cy="28" r="2.8" fill="${s.yeux || ENCRE}" stroke="${ENCRE}" stroke-width="1"/>
    <path d="M89 22 L99 25" stroke="${ENCRE}" stroke-width="2.2" stroke-linecap="round"/>
  </svg>`;
}

/* --- Apparence au hasard (création d'une brute) -------------------------------------------------------------------- */
function apparenceAleatoire(tailles, genre) {
  const a = {};
  for (const [cle, n] of Object.entries(tailles)) a[cle] = Math.floor(Math.random() * n);
  a.genre = genre || (Math.random() < 0.5 ? 'h' : 'f');
  if (a.genre === 'f') a.barbe = 0;
  return a;
}

/* La tête seule, pour les listes. */
const teteBrute = (a) => dessinerBrute(a).replace('viewBox="-15 -25 150 185"', 'viewBox="28 8 62 62"');
