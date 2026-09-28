"""Le cœur de MiniGPT : un Transformer « décodeur », la même architecture que GPT.

Chaque pièce est écrite explicitement pour pouvoir être lue et comprise :
  plongements -> N blocs [attention + réseau feed-forward] -> probabilités du prochain caractère.
"""

import math
from dataclasses import asdict, dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass
class Config:
    taille_vocab: int = 100
    taille_contexte: int = 128   # combien de caractères le modèle peut « voir » en arrière
    nb_couches: int = 4          # nombre de blocs Transformer empilés
    nb_tetes: int = 4            # nombre de têtes d'attention par bloc
    dim: int = 192               # taille des vecteurs qui représentent chaque caractère
    dropout: float = 0.1

    def vers_dict(self):
        return asdict(self)


class AttentionCausale(nn.Module):
    """Auto-attention multi-têtes : chaque position regarde les positions précédentes.

    « Causale » signifie qu'un caractère ne peut jamais regarder le futur :
    sinon le modèle tricherait en lisant la réponse qu'il doit prédire.
    """

    def __init__(self, cfg):
        super().__init__()
        assert cfg.dim % cfg.nb_tetes == 0
        self.nb_tetes = cfg.nb_tetes
        self.dim_tete = cfg.dim // cfg.nb_tetes
        # Une seule couche calcule d'un coup les requêtes (Q), clés (K) et valeurs (V).
        self.qkv = nn.Linear(cfg.dim, 3 * cfg.dim)
        self.projection = nn.Linear(cfg.dim, cfg.dim)
        self.dropout = nn.Dropout(cfg.dropout)
        # Masque triangulaire : 1 là où l'on a le droit de regarder, 0 pour le futur.
        masque = torch.tril(torch.ones(cfg.taille_contexte, cfg.taille_contexte))
        self.register_buffer("masque", masque.view(1, 1, cfg.taille_contexte, cfg.taille_contexte))

    def forward(self, x):
        B, T, C = x.shape  # lot, longueur de la séquence, dimension
        q, k, v = self.qkv(x).split(C, dim=2)
        # On découpe en plusieurs têtes : (B, nb_tetes, T, dim_tete).
        q = q.view(B, T, self.nb_tetes, self.dim_tete).transpose(1, 2)
        k = k.view(B, T, self.nb_tetes, self.dim_tete).transpose(1, 2)
        v = v.view(B, T, self.nb_tetes, self.dim_tete).transpose(1, 2)

        # Score d'affinité entre chaque paire de positions : Q·K / √d.
        scores = (q @ k.transpose(-2, -1)) / math.sqrt(self.dim_tete)
        scores = scores.masked_fill(self.masque[:, :, :T, :T] == 0, float("-inf"))
        poids = self.dropout(F.softmax(scores, dim=-1))

        # Chaque position récupère un mélange des valeurs qu'elle juge importantes.
        sortie = (poids @ v).transpose(1, 2).contiguous().view(B, T, C)
        return self.dropout(self.projection(sortie))


class FeedForward(nn.Module):
    """Petit réseau de neurones appliqué à chaque position : c'est là que le modèle « réfléchit »."""

    def __init__(self, cfg):
        super().__init__()
        self.reseau = nn.Sequential(
            nn.Linear(cfg.dim, 4 * cfg.dim),
            nn.GELU(),
            nn.Linear(4 * cfg.dim, cfg.dim),
            nn.Dropout(cfg.dropout),
        )

    def forward(self, x):
        return self.reseau(x)


class Bloc(nn.Module):
    """Un bloc Transformer : communication (attention) puis calcul (feed-forward).

    Les « connexions résiduelles » (x + ...) permettent d'empiler beaucoup de blocs
    sans que l'apprentissage ne s'effondre.
    """

    def __init__(self, cfg):
        super().__init__()
        self.norme1 = nn.LayerNorm(cfg.dim)
        self.attention = AttentionCausale(cfg)
        self.norme2 = nn.LayerNorm(cfg.dim)
        self.feed_forward = FeedForward(cfg)

    def forward(self, x):
        x = x + self.attention(self.norme1(x))
        x = x + self.feed_forward(self.norme2(x))
        return x


class MiniGPT(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.plongement_caracteres = nn.Embedding(cfg.taille_vocab, cfg.dim)
        self.plongement_positions = nn.Embedding(cfg.taille_contexte, cfg.dim)
        self.dropout = nn.Dropout(cfg.dropout)
        self.blocs = nn.ModuleList([Bloc(cfg) for _ in range(cfg.nb_couches)])
        self.norme_finale = nn.LayerNorm(cfg.dim)
        self.tete = nn.Linear(cfg.dim, cfg.taille_vocab, bias=False)
        # Partage de poids : la même matrice sert à lire et à écrire les caractères.
        self.tete.weight = self.plongement_caracteres.weight
        self.apply(self._initialiser)

    @staticmethod
    def _initialiser(module):
        if isinstance(module, (nn.Linear, nn.Embedding)):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
        if isinstance(module, nn.Linear) and module.bias is not None:
            nn.init.zeros_(module.bias)

    def nb_parametres(self):
        return sum(p.numel() for p in self.parameters())

    def forward(self, idx, cibles=None):
        B, T = idx.shape
        assert T <= self.cfg.taille_contexte, "séquence plus longue que le contexte"
        positions = torch.arange(T, device=idx.device)
        x = self.dropout(self.plongement_caracteres(idx) + self.plongement_positions(positions))
        for bloc in self.blocs:
            x = bloc(x)
        logits = self.tete(self.norme_finale(x))

        perte = None
        if cibles is not None:
            perte = F.cross_entropy(logits.view(-1, logits.size(-1)), cibles.view(-1))
        return logits, perte

    @torch.no_grad()
    def generer(self, idx, nb_nouveaux, temperature=0.8, top_k=None):
        """Écrit la suite caractère par caractère.

        temperature < 1 : texte plus sage et prévisible ; > 1 : plus créatif (et plus fou).
        top_k : ne tire qu'au sort parmi les k caractères les plus probables.
        """
        for _ in range(nb_nouveaux):
            contexte = idx[:, -self.cfg.taille_contexte:]
            logits, _ = self(contexte)
            logits = logits[:, -1, :] / max(temperature, 1e-6)
            if top_k is not None:
                seuil = torch.topk(logits, min(top_k, logits.size(-1))).values[:, [-1]]
                logits = logits.masked_fill(logits < seuil, float("-inf"))
            probas = F.softmax(logits, dim=-1)
            suivant = torch.multinomial(probas, num_samples=1)
            idx = torch.cat([idx, suivant], dim=1)
            yield suivant.item()
