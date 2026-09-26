"""PageRank : l'algorithme qui a rendu Google célèbre en 1998.

Idée : un internaute clique au hasard de lien en lien. De temps en temps (15 % du temps),
il s'ennuie et saute sur une page complètement au hasard. Le PageRank d'une page, c'est la
proportion du temps qu'il passe dessus. Une page vers laquelle pointent beaucoup de pages
importantes sera donc elle-même importante.
"""


def pagerank(liens, amortissement=0.85, iterations=100, tolerance=1e-10):
    """liens : dictionnaire {page: [pages vers lesquelles elle pointe]}. Renvoie {page: score}, total = 1."""
    pages = set(liens) | {cible for cibles in liens.values() for cible in cibles}
    n = len(pages)
    if n == 0:
        return {}
    sortants = {p: [c for c in set(liens.get(p, [])) if c != p] for p in pages}
    rang = dict.fromkeys(pages, 1 / n)
    for _ in range(iterations):
        # Les pages sans lien sortant (« culs-de-sac ») redistribuent leur score à tout le monde.
        cul_de_sac = sum(rang[p] for p in pages if not sortants[p])
        nouveau = dict.fromkeys(pages, (1 - amortissement) / n + amortissement * cul_de_sac / n)
        for page, cibles in sortants.items():
            if cibles:
                part = amortissement * rang[page] / len(cibles)
                for cible in cibles:
                    nouveau[cible] += part
        ecart = sum(abs(nouveau[p] - rang[p]) for p in pages)
        rang = nouveau
        if ecart < tolerance:
            break
    return rang
