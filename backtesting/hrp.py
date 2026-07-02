# backtesting/hrp.py — Hierarchical Risk Parity (López de Prado, 2016)
"""
Implémentation de l'algorithme HRP (Hierarchical Risk Parity) de Marcos López de
Prado ("Building Diversified Portfolios that Outperform Out-of-Sample", 2016).

HRP construit un portefeuille sans inverser la matrice de covariance (contrairement
à Markowitz), ce qui le rend robuste au bruit d'estimation. Trois étapes :

  1. TREE CLUSTERING     : distance = sqrt(0.5*(1-corr)), clustering hiérarchique.
  2. QUASI-DIAGONALIZATION : réordonne la matrice pour regrouper les actifs
     similaires (les corrélations élevées se retrouvent près de la diagonale).
  3. RECURSIVE BISECTION : alloue le capital récursivement en divisant les clusters
     et en pondérant par l'inverse de la variance de chaque sous-cluster.

Le résultat : des poids diversifiés qui respectent la structure de corrélation,
sans les positions extrêmes typiques de l'optimisation moyenne-variance.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform


def _get_ivp(cov: pd.DataFrame) -> np.ndarray:
    """Inverse-variance portfolio : poids ∝ 1/variance."""
    ivp = 1.0 / np.diag(cov.values)
    ivp /= ivp.sum()
    return ivp


def _get_cluster_var(cov: pd.DataFrame, cluster_items: list) -> float:
    """Variance d'un cluster pondéré par inverse-variance interne."""
    cov_slice = cov.loc[cluster_items, cluster_items]
    w = _get_ivp(cov_slice).reshape(-1, 1)
    return float((w.T @ cov_slice.values @ w)[0, 0])


def _get_quasi_diag(link: np.ndarray) -> list:
    """Réordonne les feuilles de l'arbre de clustering (quasi-diagonalisation)."""
    link = link.astype(int)
    sort_ix = pd.Series([link[-1, 0], link[-1, 1]])
    num_items = link[-1, 3]  # nb d'items originaux
    while sort_ix.max() >= num_items:
        sort_ix.index = range(0, sort_ix.shape[0] * 2, 2)  # espace pour insertion
        df0 = sort_ix[sort_ix >= num_items]                 # clusters à décomposer
        i = df0.index
        j = df0.values - num_items
        sort_ix[i] = link[j, 0]                             # item 1
        df0 = pd.Series(link[j, 1], index=i + 1)
        sort_ix = pd.concat([sort_ix, df0])                 # item 2
        sort_ix = sort_ix.sort_index()
        sort_ix.index = range(sort_ix.shape[0])
    return sort_ix.tolist()


def _get_rec_bipart(cov: pd.DataFrame, sort_ix: list) -> pd.Series:
    """Allocation par bisection récursive (cœur de HRP)."""
    w = pd.Series(1.0, index=sort_ix)
    clusters = [sort_ix]  # on commence avec tous les items dans un cluster
    while len(clusters) > 0:
        # Bisecter chaque cluster de plus de 1 élément
        clusters = [c[j:k] for c in clusters
                    for j, k in ((0, len(c) // 2), (len(c) // 2, len(c)))
                    if len(c) > 1]
        # Traiter les clusters par paires
        for i in range(0, len(clusters), 2):
            c0 = clusters[i]
            c1 = clusters[i + 1]
            var0 = _get_cluster_var(cov, c0)
            var1 = _get_cluster_var(cov, c1)
            alpha = 1.0 - var0 / (var0 + var1)  # moins de poids au cluster + risqué
            w[c0] *= alpha
            w[c1] *= (1.0 - alpha)
    return w


def hrp_weights(returns: pd.DataFrame) -> pd.Series:
    """
    Calcule les poids HRP (long-only, somme = 1) à partir des rendements.

    Args:
        returns : DataFrame de rendements (colonnes = actifs).

    Returns:
        pd.Series de poids indexée par actif (somme = 1, tous positifs).
    """
    if returns.shape[1] < 2:
        # Un seul actif → 100%
        return pd.Series(1.0, index=returns.columns)

    cov = returns.cov()
    corr = returns.corr()

    # 1. Distance de corrélation + clustering hiérarchique
    dist = np.sqrt(np.clip(0.5 * (1.0 - corr), 0, 1))
    # squareform attend une matrice de distance condensée
    condensed = squareform(dist.values, checks=False)
    link = linkage(condensed, method="single")

    # 2. Quasi-diagonalisation
    sort_ix = _get_quasi_diag(link)
    sort_ix = [corr.index[i] for i in sort_ix]  # indices → noms d'actifs

    # 3. Bisection récursive
    w = _get_rec_bipart(cov, sort_ix)
    return w.reindex(returns.columns).fillna(0)


def hrp_long_short_pipeline(returns: pd.DataFrame, top_n: int = 5) -> dict:
    """
    Pipeline L/S utilisant HRP pour la CONSTRUCTION (pondération), après sélection
    des titres par le signal multi-facteur.

    - Sélection : top_n / bottom_n par score multi-facteur (momentum+lowvol+reversal)
    - Construction : HRP appliqué séparément au panier long et au panier short
      (au lieu de l'inverse-vol simple), pour une diversification tenant compte
      des corrélations entre titres.

    50% du gross au long (via HRP), 50% au short (via HRP).
    """
    from backtesting.backtest_engine import multifactor_pipeline

    # Réutilise la SÉLECTION multi-facteur (mêmes longs/shorts)
    base = multifactor_pipeline(returns, top_n=top_n)
    longs  = [t for t, w in base.items() if w > 0]
    shorts = [t for t, w in base.items() if w < 0]

    weights: dict = {}

    # HRP sur le panier long
    if len(longs) >= 2:
        w_long = hrp_weights(returns[longs].dropna(how="all", axis=1))
        for t in longs:
            weights[t] = 0.5 * float(w_long.get(t, 1.0 / len(longs)))
    elif longs:
        weights[longs[0]] = 0.5

    # HRP sur le panier short
    if len(shorts) >= 2:
        w_short = hrp_weights(returns[shorts].dropna(how="all", axis=1))
        for t in shorts:
            weights[t] = -0.5 * float(w_short.get(t, 1.0 / len(shorts)))
    elif shorts:
        weights[shorts[0]] = -0.5

    return weights