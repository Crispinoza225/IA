/* Page d'accueil : créer une brute ou retrouver la sienne. */
'use strict';

(async () => {
  const parametres = new URLSearchParams(location.search);
  const maitre = parametres.get('maitre');
  let regles, apparence;

  // Déjà connecté ? Direction le jeu.
  try { await api('/api/moi'); location.replace('/jeu'); return; } catch { /* pas connecté */ }

  try { regles = await api('/api/regles'); } catch { regles = { apparence: { peau: 6, coiffure: 7, cheveux: 8, haut: 10, bas: 8, barbe: 4, yeux: 4 } }; }
  const dessiner = () => { $('#apercu').innerHTML = dessinerBrute(apparence, { carrure: 1 }); };
  apparence = apparenceAleatoire(regles.apparence);
  dessiner();
  $('#autreTete').onclick = () => { apparence = apparenceAleatoire(regles.apparence, apparence.genre); dessiner(); };
  $('#genre').onclick = () => { apparence = apparenceAleatoire(regles.apparence, apparence.genre === 'h' ? 'f' : 'h'); dessiner(); };

  if (maitre) {
    $('#maitreBandeau').hidden = false;
    $('#maitreBandeau').textContent = `🎓 Tu rejoins l'école de ${maitre} : ta brute sera son élève.`;
  }

  $$('.onglets button').forEach((b) => {
    b.onclick = () => {
      $$('.onglets button').forEach((x) => x.classList.toggle('actif', x === b));
      $('#formCreer').hidden = b.dataset.onglet !== 'creer';
      $('#formConnexion').hidden = b.dataset.onglet !== 'connexion';
    };
  });

  $('#formCreer').onsubmit = async (e) => {
    e.preventDefault();
    $('#erreurCreer').textContent = '';
    try {
      await api('/api/creer', { nom: $('#nom').value, mot_de_passe: $('#mdp').value, apparence, maitre: maitre || '' });
      location.href = '/jeu';
    } catch (erreur) { $('#erreurCreer').textContent = erreur.message; }
  };
  $('#formConnexion').onsubmit = async (e) => {
    e.preventDefault();
    $('#erreurConnexion').textContent = '';
    try {
      await api('/api/connexion', { nom: $('#nomConnexion').value, mot_de_passe: $('#mdpConnexion').value });
      location.href = '/jeu';
    } catch (erreur) { $('#erreurConnexion').textContent = erreur.message; }
  };

  try {
    const top = (await api('/api/classement')).slice(0, 10);
    $('#top tbody').innerHTML = top.length ? top.map((b, i) => `<tr>
        <td class="rang">${i + 1}</td><td class="tete">${teteBrute(b.apparence)}</td>
        <td><a href="/jeu#brute/${encodeURIComponent(b.nom)}">${echapper(b.nom)}</a></td>
        <td>Niveau ${b.niveau}</td><td>${b.victoires} victoires</td></tr>`).join('')
      : '<tr><td class="vide">Aucune brute pour l\'instant : sois la première !</td></tr>';
  } catch { $('#top tbody').innerHTML = ''; }
})();
