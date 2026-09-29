/* Relecture animée d'un combat : le serveur a tout calculé, on rejoue ses événements un par un. */
'use strict';

const POSITIONS = { brute: 30, animaux: [15, 6, 22] }; // en % de la largeur, pour l'équipe de gauche

class Replay {
  /* options.fin(conteneur, donnees) : remplit le panneau de fin de combat (boutons). */
  constructor(conteneur, donnees, regles, options = {}) {
    this.donnees = donnees;
    this.regles = regles;
    this.options = options;
    this.vitesse = 1;
    this.passer = false;
    this.combattants = new Map();
    conteneur.innerHTML = `
      <div class="combat">
        <div class="arene"><div class="sol"></div><div class="hud"></div></div>
        <div class="controles">
          <button class="btn petit-btn actif" data-vitesse="1">▶ Normal</button>
          <button class="btn petit-btn" data-vitesse="2">⏩ Rapide</button>
          <button class="btn petit-btn" data-vitesse="4">⏭ Très rapide</button>
          <button class="btn petit-btn" data-passer>Voir le résultat</button>
        </div>
        <div class="cadre"><h3>📜 Le combat</h3><ol class="journal" role="log" aria-live="polite"></ol></div>
      </div>`;
    this.arene = $('.arene', conteneur);
    this.journalEl = $('.journal', conteneur);
    $$('[data-vitesse]', conteneur).forEach((b) => {
      b.onclick = () => {
        this.vitesse = Number(b.dataset.vitesse);
        $$('[data-vitesse]', conteneur).forEach((x) => x.classList.toggle('actif', x === b));
      };
    });
    $('[data-passer]', conteneur).onclick = (e) => { this.passer = true; e.target.disabled = true; };
  }

  /* --- Outils ------------------------------------------------------------------------------------------------------- */
  attendre(ms) {
    return this.passer ? Promise.resolve() : new Promise((r) => setTimeout(r, ms / this.vitesse));
  }

  async animer(el, images, ms, easing = 'ease-in-out') {
    if (this.passer) {
      const fin = images[images.length - 1];
      if (fin.transform !== undefined && el.classList.contains('mouvement')) el.style.transform = fin.transform;
      return;
    }
    const a = el.animate(images, { duration: ms / this.vitesse, easing, fill: 'forwards' });
    try { await a.finished; } catch { /* annulée */ }
    const fin = images[images.length - 1];
    if (fin.transform !== undefined && el.classList.contains('mouvement')) el.style.transform = fin.transform;
    a.cancel();
  }

  noter(html) {
    const li = document.createElement('li');
    li.innerHTML = html;
    this.journalEl.append(li);
    this.journalEl.scrollTop = this.journalEl.scrollHeight;
  }

  bulle(c, texte, ms = 700) {
    if (this.passer) return;
    const b = document.createElement('div');
    b.className = 'bulle';
    b.textContent = texte;
    $('.mouvement', c.el).append(b);
    setTimeout(() => b.remove(), ms / this.vitesse + 250);
  }

  chiffre(c, texte, soin = false) {
    if (this.passer) return;
    const d = document.createElement('div');
    d.className = `degats${soin ? ' soin' : ''}`;
    d.textContent = texte;
    $('.mouvement', c.el).append(d);
    d.animate([{ transform: 'translate(-50%, 0)', opacity: 1 }, { transform: 'translate(-50%, -60px)', opacity: 0 }],
      { duration: 900 / this.vitesse, easing: 'ease-out', fill: 'forwards' }).finished.then(() => d.remove(), () => d.remove());
  }

  nom(c) { return `<b>${echapper(c.nom)}</b>`; }
  nomArme(cle) { return this.regles?.armes?.[cle]?.nom || cle; }

  x(c) { return (c.pct / 100) * this.arene.clientWidth; }

  dessiner(c) {
    $('.dessin', c.el).innerHTML = c.animal ? dessinerAnimal(c.animal)
      : dessinerBrute(c.apparence || {}, { arme: c.arme, bouclier: c.bouclier, carrure: c.carrure });
  }

  majPv(c) {
    const pct = Math.max(0, (c.pv / c.pv_max) * 100);
    if (c.hud) {
      $('.jauge > i', c.hud).style.width = `${pct}%`;
      $('.pv-texte', c.hud).textContent = `${c.pv} / ${c.pv_max} PV`;
    }
    const mini = $('.mini-pv > i', c.el);
    if (mini) mini.style.width = `${pct}%`;
  }

  /* --- Mise en place ------------------------------------------------------------------------------------------------ */
  installer(evenement) {
    const hud = $('.hud', this.arene);
    const animaux = [0, 0];
    for (const info of evenement.combattants) {
      const c = { ...info, arme: null, dx: 0 };
      const cote = info.equipe === 0 ? 1 : -1;
      c.dir = cote;
      const base = info.animal ? POSITIONS.animaux[animaux[info.equipe]++ % 3] : POSITIONS.brute;
      c.pct = info.equipe === 0 ? base : 100 - base;
      const brute = this.donnees.brutes?.[info.equipe];
      c.carrure = 1 + Math.min(0.3, ((brute?.niveau || 1) - 1) * 0.015);
      c.el = document.createElement('div');
      c.el.className = `combattant equipe-${info.equipe}${info.animal ? ' animal' : ''}`;
      c.el.style.left = `${c.pct}%`;
      c.el.innerHTML = `<div class="mouvement">${info.animal ? '<div class="jauge pv mini-pv"><i style="width:100%"></i></div>' : ''}
        <div class="impact"><div class="dessin"></div></div></div>`;
      this.arene.append(c.el);
      this.dessiner(c);
      if (!info.animal) {
        c.hud = document.createElement('div');
        c.hud.className = `hud-brute ${info.equipe === 0 ? 'gauche' : 'droite'}`;
        c.hud.innerHTML = `<div class="tete">${teteBrute(info.apparence || {})}</div><b></b><div class="jauge pv"><i style="width:100%"></i></div><span class="pv-texte"></span>`;
        $('b', c.hud).textContent = `${info.nom}${brute ? ` · niv. ${brute.niveau}` : ''}`;
        hud.append(c.hud);
      }
      this.majPv(c);
      this.combattants.set(info.id, c);
    }
    const [a, b] = evenement.combattants.filter((c) => !c.animal);
    this.noter(`🔔 ${this.nom(a)} affronte ${this.nom(b)} !`);
  }

  async deplacer(c, dx, ms) {
    c.dx = dx;
    await this.animer($('.mouvement', c.el), [{ transform: $('.mouvement', c.el).style.transform || 'translateX(0px)' }, { transform: `translateX(${dx}px)` }], ms);
  }

  async secouer(c, force = 8) {
    await this.animer($('.impact', c.el), [
      { transform: 'translateX(0)', filter: 'brightness(1)' }, { transform: `translateX(${-force * c.dir}px)`, filter: 'brightness(1.8) saturate(.4)' },
      { transform: `translateX(${force * c.dir * 0.5}px)` }, { transform: 'translateX(0)', filter: 'brightness(1)' }], 260);
  }

  async lancerProjectile(de, vers, arme) {
    if (this.passer) return;
    const p = document.createElement('div');
    p.className = 'projectile';
    p.innerHTML = iconeArme(arme);
    const depart = this.x(de) + de.dx, arrivee = this.x(vers) + vers.dx;
    p.style.left = `${depart}px`;
    p.style.bottom = '140px';
    this.arene.append(p);
    await p.animate([{ transform: 'translateX(0) rotate(0)' }, { transform: `translate(${arrivee - depart}px, 30px) rotate(${de.dir * 720}deg)` }],
      { duration: 420 / this.vitesse, easing: 'linear', fill: 'forwards' }).finished.catch(() => {});
    p.remove();
  }

  /* --- Les événements ---------------------------------------------------------------------------------------------- */
  async jouer() {
    for (const e of this.donnees.evenements) {
      const c = this.combattants.get(e.id), cible = this.combattants.get(e.cible);
      switch (e.t) {
        case 'debut':
          this.installer(e);
          await this.attendre(700);
          break;
        case 'arme':
          c.arme = e.arme;
          this.dessiner(c);
          this.bulle(c, this.nomArme(e.arme));
          this.noter(`🗡️ ${this.nom(c)} sort : ${echapper(this.nomArme(e.arme))}.`);
          await this.attendre(550);
          break;
        case 'attaque': { // l'attaquant court se placer devant sa cible
          const dx = this.x(cible) + cible.dx - this.x(c) - c.dir * (c.animal || cible.animal ? 62 : 72);
          await this.deplacer(c, dx, 300);
          break;
        }
        case 'coup':
          this.chiffre(cible, `-${e.degats}`);
          cible.pv = e.pv;
          this.majPv(cible);
          this.noter(`💥 ${this.nom(c)} frappe ${this.nom(cible)} : <b>-${e.degats}</b>`);
          await this.secouer(cible);
          await this.attendre(120);
          break;
        case 'esquive':
          this.bulle(c, 'Esquive !');
          this.noter(`💨 ${this.nom(c)} esquive.`);
          await this.animer($('.impact', c.el), [{ transform: 'translate(0,0)' }, { transform: `translate(${-c.dir * 34}px,-18px)` }, { transform: 'translate(0,0)' }], 360);
          break;
        case 'parade':
          this.bulle(c, 'Parade !');
          this.noter(`🛡️ ${this.nom(c)} pare le coup.`);
          await this.secouer(c, 3);
          await this.attendre(150);
          break;
        case 'contre':
          this.bulle(c, 'Contre !');
          this.noter(`↩️ ${this.nom(c)} contre-attaque !`);
          await this.animer($('.impact', c.el), [{ transform: 'translateX(0)' }, { transform: `translateX(${c.dir * 22}px)` }, { transform: 'translateX(0)' }], 260);
          break;
        case 'retour':
          await this.deplacer(c, 0, 280);
          break;
        case 'lancer':
          this.noter(`🎯 ${this.nom(c)} lance : ${echapper(this.nomArme(e.arme))} sur ${this.nom(cible)}${e.touche ? '' : '… raté !'}`);
          c.arme = null;
          this.dessiner(c);
          await this.lancerProjectile(c, cible, e.arme);
          if (!e.touche) this.bulle(cible, 'Raté !');
          break;
        case 'desarme':
          c.arme = null;
          this.dessiner(c);
          this.bulle(c, 'Désarmé !');
          this.noter(`🫳 ${this.nom(c)} perd son arme : ${echapper(this.nomArme(e.arme))}.`);
          await this.attendre(450);
          break;
        case 'soin':
          this.chiffre(c, `+${e.pv - c.pv}`, true);
          c.pv = e.pv;
          this.majPv(c);
          this.bulle(c, 'Second souffle !');
          this.noter(`💚 ${this.nom(c)} reprend son souffle.`);
          await this.attendre(700);
          break;
        case 'cri':
          this.bulle(c, 'RAAAAH !', 900);
          this.noter(`📢 ${this.nom(c)} pousse un cri de guerre ! Ses adversaires sont pétrifiés.`);
          await Promise.all([...this.combattants.values()].filter((x) => x.equipe !== c.equipe && x.pv > 0).map((x) => this.secouer(x, 4)));
          await this.attendre(300);
          break;
        case 'increvable':
          this.bulle(c, 'Increvable !', 900);
          this.noter(`🦴 ${this.nom(c)} refuse de tomber !`);
          await this.attendre(600);
          break;
        case 'ko':
          c.el.classList.add('ko');
          this.noter(`💀 ${this.nom(c)} est au tapis !`);
          await this.animer($('.impact', c.el), [{ transform: 'rotate(0deg)' }, { transform: `rotate(${-c.dir * 80}deg) translate(${-c.dir * 20}px, 30px)` }], 450, 'ease-in');
          $('.impact', c.el).style.transform = `rotate(${-c.dir * 80}deg) translate(${-c.dir * 20}px, 30px)`; // reste à terre
          if (c.animal) c.el.style.opacity = '.5';
          break;
        case 'fin':
          this.terminer(e.gagnant);
          break;
        default:
          break;
      }
    }
  }

  terminer(gagnant) {
    const brute = this.donnees.brutes[gagnant];
    this.noter(`🏆 <b>${echapper(brute.nom)}</b> remporte le combat !`);
    const fin = document.createElement('div');
    fin.className = 'fin-combat';
    fin.innerHTML = `<div><h2>${echapper(brute.nom)} gagne !</h2><div class="actions" style="justify-content:center"></div></div>`;
    this.arene.append(fin);
    if (this.options.fin) this.options.fin($('.actions', fin), this.donnees);
  }
}
