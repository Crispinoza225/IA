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
  const c = [n >> 16, (n >> 8) & 255, n & 255].map((v) => Math.min(255, Math.round(v * facteur))); // > 1 éclaircit
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

/* --- Brute : style « chibi » de trois quarts, tournée vers la droite ------------------------------------------------ */
// Grosse tête, petit corps, gros contours et ombrages en aplats. Tout est dessiné ici, variante par variante.
const CHAUSSURES = ['#d63a2a', '#f4efe2', '#6b4226', '#2b2b2b'];
const T = (e = 3) => `stroke="${ENCRE}" stroke-width="${e}" stroke-linejoin="round" stroke-linecap="round"`;

function coiffure(style, couleur, derriere) {
  const ombre = assombrir(couleur, 0.78), reflet = assombrir(couleur, 1.25);
  if (derriere) {
    switch (style) {
      case 3: return `<path d="M34 30 C22 52 24 82 36 96 L50 90 C44 76 42 58 46 40Z" fill="${ombre}" ${T()}/>`;
      case 4: return `<path d="M36 28 C16 22 6 38 10 56 C14 48 20 44 26 46 C18 58 22 70 30 72 C30 60 34 50 42 42Z" fill="${couleur}" ${T()}/>
        <path d="M18 50 C16 56 20 64 26 68" fill="none" stroke="${ombre}" stroke-width="3" stroke-linecap="round"/>`;
      case 5: return `<path d="M58 -2 C72 -8 90 0 94 14 C104 20 104 38 96 46 C98 58 88 64 80 60 L40 62 C28 66 18 56 22 44 C12 34 18 16 30 12 C36 0 48 -4 58 -2Z" fill="${couleur}" ${T()}/>`;
      default: return '';
    }
  }
  switch (style) {
    case 0: return `<ellipse cx="66" cy="20" rx="9" ry="5" fill="#fff" opacity=".35" transform="rotate(-20 66 20)"/>`;
    case 1: return `<path d="M31 44 C28 22 44 8 62 9 C78 10 90 20 88 34 C82 30 78 30 74 33 L72 26 L66 32 L60 25 L54 32 L46 28 L42 38 C38 38 35 41 35 46Z" fill="${couleur}" ${T()}/>
      <path d="M40 18 C48 12 60 12 68 14" fill="none" stroke="${reflet}" stroke-width="3" stroke-linecap="round"/>`;
    case 2: return `<path d="M32 46 L20 30 L34 30 L26 12 L42 20 L44 2 L56 16 L64 -2 L70 16 L84 4 L82 22 L96 18 L88 32 C82 28 76 29 72 32 L68 26 L62 32 L56 25 L50 32 L44 28 L40 38 C37 39 34 42 35 46Z" fill="${couleur}" ${T()}/>
      <path d="M46 16 L50 22 M62 10 L63 18 M76 14 L73 21" stroke="${reflet}" stroke-width="2.5" stroke-linecap="round"/>`;
    case 3: case 4: return `<path d="M30 50 C24 22 42 6 62 8 C80 9 92 22 88 36 C80 28 70 26 62 28 C54 30 48 34 44 40 C40 44 38 50 38 58 C34 58 31 55 30 50Z" fill="${couleur}" ${T()}/>
      <path d="M44 16 C52 11 62 11 70 13" fill="none" stroke="${reflet}" stroke-width="3" stroke-linecap="round"/>`;
    case 5: return `<path d="M44 26 C52 22 60 26 66 22 C72 26 80 24 86 30" fill="none" stroke="${ombre}" stroke-width="4" stroke-linecap="round"/>`;
    case 6: return `<path d="M48 16 L44 -4 L56 8 L58 -10 L66 6 L74 -8 L74 10 L86 2 L80 20 C72 14 58 12 48 16Z" fill="${couleur}" ${T()}/>
      <path d="M56 6 L59 12 M70 2 L70 10" stroke="${reflet}" stroke-width="2.5" stroke-linecap="round"/>`;
    default: return '';
  }
}

function visage(style, genre) {
  const cils = genre === 'f' ? `<path d="M59 36 L56 33 M82 36 L85 33" stroke="${ENCRE}" stroke-width="2.2" stroke-linecap="round"/>` : '';
  const oeil = (x, rx, ry, px) => `<ellipse cx="${x}" cy="41" rx="${rx}" ry="${ry}" fill="#fff" ${T(2.4)}/>
    <circle cx="${x + px}" cy="42" r="${ry * 0.52}" fill="${ENCRE}"/><circle cx="${x + px + 1}" cy="40" r="1.3" fill="#fff"/>`;
  let yeux;
  switch (style) {
    case 1: // paupières lourdes, l'air blasé
      yeux = `${oeil(64, 5.5, 6, 1.5)}${oeil(79, 4.5, 5.5, 1.2)}<path d="M58 39 L70 39 M74 39 L84 39" stroke="${ENCRE}" stroke-width="3.2" stroke-linecap="round"/>`;
      break;
    case 2: // grands yeux fous
      yeux = `${oeil(64, 7, 8, 0)}${oeil(80, 5.5, 7, 0)}<path d="M57 29 L70 31 M75 30 L85 27" stroke="${ENCRE}" stroke-width="3.2" stroke-linecap="round"/>`;
      break;
    case 3: // plissés
      yeux = `<path d="M59 42 Q64 38 69 42 M75 42 Q79 38 84 42" fill="none" stroke="${ENCRE}" stroke-width="3" stroke-linecap="round"/>
        <path d="M57 33 L70 37 M74 36 L85 32" stroke="${ENCRE}" stroke-width="3.4" stroke-linecap="round"/>`;
      break;
    default: // colère
      yeux = `${oeil(64, 5.5, 6.5, 1.8)}${oeil(79, 4.5, 5.8, 1.4)}<path d="M57 31 L71 37 M74 36 L86 30" stroke="${ENCRE}" stroke-width="3.6" stroke-linecap="round"/>`;
  }
  const bouches = [
    `<path d="M66 56 Q74 61 83 54 L82 58 Q74 65 67 60Z" fill="#fff" ${T(2.2)}/><path d="M72 58 L72 61 M77 57 L77 60" stroke="${ENCRE}" stroke-width="1.3"/>`,
    `<path d="M67 58 Q75 55 83 57" fill="none" ${T(2.6)}/>`,
    `<path d="M66 54 Q75 52 84 53 Q80 64 70 62Z" fill="#7a2a1f" ${T(2.2)}/><path d="M68 55 L82 54" stroke="#fff" stroke-width="2.4"/>`,
    `<path d="M67 57 Q72 54 76 57 Q80 60 84 56" fill="none" ${T(2.6)}/>`,
  ];
  return `${yeux}${cils}<path d="M84 45 Q91 48 86 52" fill="none" ${T(2.4)}/>${bouches[style] || bouches[0]}`;
}

function barbe(style, couleur) {
  const t = T(2.4);
  switch (style) {
    case 1: return `<path d="M64 53 Q74 47 86 51 Q80 54 75 52 Q70 55 64 53Z" fill="${couleur}" ${t}/>`;
    case 2: return `<path d="M68 61 Q75 66 82 60 L80 72 Q75 76 71 70Z" fill="${couleur}" ${t}/>`;
    case 3: return `<path d="M36 50 C38 68 50 78 64 76 C76 76 86 68 88 56 C82 62 76 64 70 62 C62 62 58 58 54 54 C48 58 42 56 36 50Z" fill="${couleur}" ${t}/>`;
    default: return '';
  }
}

/* options : arme (clé), bouclier (booléen), carrure (0,85 à 1,3) */
function dessinerBrute(a, options = {}) {
  const peau = PEAUX[a.peau] || PEAUX[1], ombrePeau = assombrir(peau, 0.8), refletPeau = assombrir(peau, 1.08);
  const cheveux = CHEVEUX[a.cheveux] || CHEVEUX[0];
  const haut = HAUTS[a.haut] || HAUTS[0], bas = BAS[a.bas] || BAS[0];
  const chaussure = CHAUSSURES[((a.haut || 0) + (a.bas || 0)) % CHAUSSURES.length];
  const k = Math.max(0.85, Math.min(1.3, options.carrure || 1)) * (a.genre === 'f' ? 0.9 : 1);
  const X = (x) => 60 + (x - 60) * k; // élargit le buste et les épaules selon la carrure
  const membre = (d, couleur, epaisseur) => `<path d="${d}" fill="none" stroke="${ENCRE}" stroke-width="${epaisseur + 5}" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="${d}" fill="none" stroke="${couleur}" stroke-width="${epaisseur}" stroke-linecap="round" stroke-linejoin="round"/>`;
  const basket = (x, couleur) => `<path d="M${x - 10} 140 C${x - 11} 130 ${x - 4} 126 ${x + 2} 127 C${x + 8} 128 ${x + 13} 132 ${x + 14} 138 C${x + 14} 142 ${x - 10} 143 ${x - 10} 140Z" fill="${couleur}" ${T(2.8)}/>
    <path d="M${x - 10} 138 L${x + 14} 137" stroke="#fff" stroke-width="2.4" opacity=".8"/>`;
  const arme = options.arme && ARMES_SVG[options.arme]
    ? `<g transform="translate(92 96) scale(1.25) rotate(${options.arme === 'shuriken' ? 0 : 50})">${ARMES_SVG[options.arme]}</g>` : '';
  const bouclier = options.bouclier
    ? `<g transform="translate(${X(34)} 94)"><circle r="17" fill="#a0692f" ${T()}/><path d="M-12 -8 A14 14 0 0 1 8 -13" fill="none" stroke="#c98b4f" stroke-width="3" stroke-linecap="round"/>
       <circle r="11" fill="none" stroke="${ENCRE}" stroke-width="1.8"/><circle r="4.5" fill="#d9a441" ${T(2.4)}/></g>` : '';
  return `<svg class="brute" viewBox="-22 -20 184 172" aria-hidden="true">
    <ellipse cx="60" cy="142" rx="34" ry="6" fill="rgba(0,0,0,.2)"/>
    ${coiffure(a.coiffure, cheveux, true)}
    ${membre('M53 104 L50 128', ombrePeau, 11 * k)}${basket(49, assombrir(chaussure, 0.85))}
    ${membre(`M${X(46)} 74 L${X(38)} 90 L${X(36)} 98`, ombrePeau, 10 * k)}
    <circle cx="${X(35)}" cy="100" r="7.5" fill="${ombrePeau}" ${T(2.8)}/>
    ${bouclier}
    ${membre('M67 104 L70 128', peau, 11 * k)}${basket(71, chaussure)}
    <path d="M${X(41)} 92 L${X(79)} 92 L${X(81)} 110 L66 112 L60 104 L54 112 L${X(39)} 110Z" fill="${bas}" ${T()}/>
    <path d="M${X(41)} 94 L${X(49)} 94 L${X(47)} 110 L${X(39)} 110Z" fill="${assombrir(bas, 0.78)}"/>
    <path d="M${X(40)} 68 Q60 60 ${X(80)} 68 L${X(79)} 94 Q60 98 ${X(41)} 94Z" fill="${haut}" ${T()}/>
    <path d="M${X(42)} 70 Q${X(46)} 82 ${X(43)} 93 L${X(50)} 95 Q${X(50)} 80 ${X(48)} 66Z" fill="${assombrir(haut, 0.78)}"/>
    <path d="M${X(66)} 70 Q${X(72)} 74 ${X(74)} 84" fill="none" stroke="${assombrir(haut, 1.2)}" stroke-width="3" stroke-linecap="round"/>
    <rect x="${X(40)}" y="89" width="${X(80) - X(40)}" height="7" rx="3" fill="#6b4226" ${T(2.4)}/>
    <rect x="56" y="88.5" width="9" height="8" rx="2" fill="#d9a441" ${T(2)}/>
    <path d="M52 58 L52 68 Q60 72 68 68 L68 58Z" fill="${ombrePeau}" ${T(2.4)}/>
    <circle cx="60" cy="40" r="28" fill="${peau}" ${T(3.2)}/>
    <path d="M36 26 C30 40 34 58 48 66 C40 56 38 42 42 30Z" fill="${ombrePeau}" opacity=".9"/>
    <ellipse cx="72" cy="22" rx="8" ry="5" fill="${refletPeau}" opacity=".7" transform="rotate(-25 72 22)"/>
    <ellipse cx="39" cy="46" rx="6.5" ry="8" fill="${peau}" ${T(2.8)}/><path d="M38 43 Q41 46 38 50" fill="none" stroke="${ombrePeau}" stroke-width="2.4" stroke-linecap="round"/>
    ${a.genre === 'f' ? `<ellipse cx="80" cy="52" rx="4.5" ry="3" fill="#e8746a" opacity=".45"/>` : ''}
    ${visage(a.yeux, a.genre)}
    ${barbe(a.genre === 'f' ? 0 : a.barbe, cheveux)}
    ${coiffure(a.coiffure, cheveux, false)}
    ${arme}
    ${membre(`M${X(76)} 74 L${X(84)} 86 L92 94`, peau, 10.5 * k)}
    <rect x="${X(82) - 5}" y="84" width="11" height="8" rx="2" fill="${haut}" ${T(2.2)} transform="rotate(40 ${X(82)} 88)"/>
    <circle cx="92" cy="96" r="8.5" fill="${peau}" ${T(3)}/><path d="M88 94 Q91 91 95 93" fill="none" stroke="${ombrePeau}" stroke-width="2" stroke-linecap="round"/>
  </svg>`;
}

/* La carrure dépend de la force et de l'endurance. */
const carrure = (caracs) => (caracs ? 0.85 + Math.min(0.45, ((caracs.force || 0) + (caracs.endurance || 0) - 10) * 0.02) : 1);

/* --- Animaux : même style que les brutes, tournés vers la droite ---------------------------------------------------- */
const ANIMAUX_STYLE = {
  chien: { corps: '#c8874a', ventre: '#f1d3a8', taille: 0.62, oreille: 'tombante', queue: 'courte', tache: true },
  loup: { corps: '#8d95a3', ventre: '#e3e6eb', taille: 0.8, oreille: 'pointue', queue: 'touffue' },
  panthere: { corps: '#35303d', ventre: '#4a4455', taille: 0.85, oreille: 'ronde', queue: 'longue', yeux: '#f3c623' },
  ours: { corps: '#7a4d2c', ventre: '#b07a4c', taille: 1.1, oreille: 'ronde', queue: 'aucune' },
};

function dessinerAnimal(cle) {
  const s = ANIMAUX_STYLE[cle] || ANIMAUX_STYLE.chien;
  const ombre = assombrir(s.corps, 0.75), reflet = assombrir(s.corps, 1.2);
  const patte = (x, arriere) => `<path d="M${x} 62 L${x} 80" stroke="${ENCRE}" stroke-width="14" stroke-linecap="round"/>
    <path d="M${x} 62 L${x} 80" stroke="${arriere ? ombre : s.corps}" stroke-width="8.5" stroke-linecap="round"/>`;
  const oreilles = {
    tombante: `<path d="M76 14 C68 16 66 32 72 36 C78 30 82 22 82 16Z" fill="${ombre}" ${T(2.8)}/>`,
    pointue: `<path d="M78 16 L80 -2 L92 12Z" fill="${s.corps}" ${T(2.8)}/><path d="M81 6 L83 12 L87 11Z" fill="#e8a0a0"/>`,
    ronde: `<circle cx="80" cy="12" r="8" fill="${s.corps}" ${T(2.8)}/><circle cx="80" cy="12" r="3.5" fill="${ombre}"/>`,
  }[s.oreille];
  const queue = {
    courte: `<path d="M24 46 Q12 36 16 24" fill="none" stroke="${ENCRE}" stroke-width="10" stroke-linecap="round"/><path d="M24 46 Q12 36 16 24" fill="none" stroke="${s.corps}" stroke-width="5" stroke-linecap="round"/>`,
    touffue: `<path d="M26 44 C8 40 2 56 0 66 C14 64 24 56 30 50Z" fill="${s.corps}" ${T(2.8)}/><path d="M6 60 C12 58 18 54 22 50" fill="none" stroke="${reflet}" stroke-width="2.5" stroke-linecap="round"/>`,
    longue: `<path d="M26 46 C6 50 6 74 18 76" fill="none" stroke="${ENCRE}" stroke-width="11" stroke-linecap="round"/><path d="M26 46 C6 50 6 74 18 76" fill="none" stroke="${s.corps}" stroke-width="5.5" stroke-linecap="round"/>`,
    aucune: '',
  }[s.queue];
  const museau = cle === 'ours'
    ? `<ellipse cx="104" cy="34" rx="12" ry="9" fill="${s.ventre}" ${T(2.8)}/><ellipse cx="112" cy="30" rx="4" ry="3" fill="${ENCRE}"/>`
    : `<path d="M94 24 Q112 24 116 32 Q116 40 106 42 L94 42Z" fill="${s.ventre}" ${T(2.8)}/><ellipse cx="114" cy="30" rx="3.5" ry="3" fill="${ENCRE}"/>
       <path d="M100 40 Q106 44 111 40" fill="none" stroke="${ENCRE}" stroke-width="2" stroke-linecap="round"/>`;
  return `<svg class="animal" viewBox="-4 -8 128 98" style="--taille:${s.taille}" aria-hidden="true">
    <ellipse cx="58" cy="86" rx="40" ry="5" fill="rgba(0,0,0,.2)"/>
    ${queue}${patte(34, true)}${patte(66, true)}
    <ellipse cx="52" cy="50" rx="34" ry="21" fill="${s.corps}" ${T(3)}/>
    <path d="M24 56 Q50 74 80 58 Q76 68 52 71 Q30 70 24 56Z" fill="${s.ventre}"/>
    <path d="M34 36 Q50 30 66 34" fill="none" stroke="${reflet}" stroke-width="3" stroke-linecap="round"/>
    ${s.tache ? `<ellipse cx="40" cy="46" rx="9" ry="7" fill="${ombre}"/>` : ''}
    ${patte(42, false)}${patte(74, false)}
    <circle cx="88" cy="30" r="21" fill="${s.corps}" ${T(3)}/>
    <path d="M70 38 C72 48 82 52 92 50 C84 48 76 44 70 38Z" fill="${ombre}"/>
    ${oreilles}${museau}
    <ellipse cx="94" cy="24" rx="5.5" ry="6.5" fill="${s.yeux || '#fff'}" ${T(2.2)}/>
    <circle cx="96" cy="25" r="3" fill="${ENCRE}"/><circle cx="97" cy="23.5" r="1.1" fill="#fff"/>
    <path d="M86 14 L100 18" stroke="${ENCRE}" stroke-width="3.2" stroke-linecap="round"/>
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
const teteBrute = (a) => dessinerBrute(a).replace('viewBox="-22 -20 184 172"', 'viewBox="22 -4 76 76"');
