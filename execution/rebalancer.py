# execution/rebalancer.py — boucle stratégie → exécution
"""
Traduit les signaux de la stratégie L/S momentum en ordres exécutables.

Workflow :
  1. compute_target_portfolio() : signaux momentum → poids → nb d'actions cibles
  2. compute_orders()           : diff entre positions actuelles et cible → ordres
  3. (exécution via IBKRLiveEngine.execute_order, géré côté callback)

Le capital cible par défaut est 1 000 000 € (comme le compte paper).
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger("Rebalancer")

DEFAULT_CAPITAL_EUR = 1_000_000.0


@dataclass
class TargetPosition:
    ticker:       str
    side:         str      # "LONG" | "SHORT"
    weight:       float    # poids signé (-0.1 à +0.1)
    target_qty:   int      # nb d'actions cibles (signé)
    price:        float    # prix unitaire utilisé
    notional:     float    # exposition en €


@dataclass
class RebalanceOrder:
    ticker:       str
    action:       str      # "BUY" | "SELL"
    qty:          int      # nb d'actions (positif)
    reason:       str      # "OPEN LONG", "CLOSE SHORT", "INCREASE", etc.
    current_qty:  int
    target_qty:   int


def compute_target_portfolio(
    returns,
    prices: Dict[str, float],
    capital: float = DEFAULT_CAPITAL_EUR,
    top_n: int = 5,
    strategy: str = "momentum",
    fundamentals=None,
) -> List[TargetPosition]:
    """
    Calcule le portefeuille cible à partir des signaux de la stratégie choisie.

    Args:
        returns      : DataFrame de rendements quotidiens (colonnes = tickers)
        prices       : dict {ticker: prix unitaire actuel}
        capital      : capital total à déployer (défaut 1M€)
        top_n        : nb de positions par côté (défaut 5)
        strategy     : "momentum" | "momentum_fundamental" | "hrp" | "multifactor"
        fundamentals : DataFrame de fondamentaux (requis pour momentum_fundamental,
                       typiquement dp.get_fundamentals() qui est mis en cache)

    Returns:
        Liste de TargetPosition (2*top_n positions : long + short).
    """
    from backtesting.backtest_engine import momentum_pipeline, multifactor_pipeline

    if strategy == "hrp":
        from backtesting.hrp import hrp_long_short_pipeline
        weights = hrp_long_short_pipeline(returns, top_n=top_n)
    elif strategy == "multifactor":
        weights = multifactor_pipeline(returns, top_n=top_n)
    elif strategy == "momentum_fundamental":
        from backtesting.backtest_engine import momentum_fundamental_pipeline
        weights = momentum_fundamental_pipeline(returns, top_n=top_n,
                                                fundamentals=fundamentals)
    else:
        weights = momentum_pipeline(returns, top_n=top_n)

    targets: List[TargetPosition] = []
    for ticker, w in weights.items():
        px = prices.get(ticker, 0)
        if px <= 0:
            logger.warning(f"{ticker} : pas de prix, position ignorée")
            continue
        # Exposition € = poids × capital ; nb actions = exposition / prix
        notional = w * capital
        qty = int(round(notional / px))
        if qty == 0:
            continue
        targets.append(TargetPosition(
            ticker     = ticker,
            side       = "LONG" if w > 0 else "SHORT",
            weight     = round(w, 4),
            target_qty = qty,
            price      = px,
            notional   = round(notional, 0),
        ))
    # Trier : longs d'abord (poids décroissant), puis shorts
    targets.sort(key=lambda t: -t.weight)
    return targets


def compute_orders(
    targets: List[TargetPosition],
    current_positions: Dict[str, int],
) -> List[RebalanceOrder]:
    """
    Calcule les ordres nécessaires pour passer des positions actuelles à la cible.

    Gère :
      - Ouvrir une nouvelle position (BUY pour long, SELL pour short)
      - Ajuster une position existante (BUY/SELL le delta)
      - Fermer une position qui n'est plus dans la cible

    Args:
        targets           : portefeuille cible (sortie de compute_target_portfolio)
        current_positions : positions actuelles {ticker: qty signé}

    Returns:
        Liste de RebalanceOrder à exécuter.
    """
    orders: List[RebalanceOrder] = []
    target_map = {t.ticker: t.target_qty for t in targets}
    current = dict(current_positions)

    # 1. Positions cibles : ouvrir ou ajuster
    for t in targets:
        cur = current.get(t.ticker, 0)
        delta = t.target_qty - cur
        if delta == 0:
            continue
        action = "BUY" if delta > 0 else "SELL"
        if cur == 0:
            reason = f"OUVRIR {t.side}"
        elif (cur > 0) == (t.target_qty > 0):
            reason = "AJUSTER" + (" +" if delta > 0 else " -")
        else:
            reason = f"INVERSER → {t.side}"
        orders.append(RebalanceOrder(
            ticker=t.ticker, action=action, qty=abs(delta),
            reason=reason, current_qty=cur, target_qty=t.target_qty,
        ))

    # 2. Positions actuelles PLUS dans la cible → fermer
    for ticker, cur in current.items():
        if ticker in target_map or cur == 0:
            continue
        action = "SELL" if cur > 0 else "BUY"   # fermer = sens inverse
        orders.append(RebalanceOrder(
            ticker=ticker, action=action, qty=abs(cur),
            reason="FERMER (hors cible)", current_qty=cur, target_qty=0,
        ))

    return orders


def summarize(targets: List[TargetPosition], orders: List[RebalanceOrder]) -> dict:
    """Petit résumé chiffré pour l'affichage."""
    gross = sum(abs(t.notional) for t in targets)
    n_long  = sum(1 for t in targets if t.side == "LONG")
    n_short = sum(1 for t in targets if t.side == "SHORT")
    return {
        "n_targets": len(targets),
        "n_long": n_long,
        "n_short": n_short,
        "gross_exposure": round(gross, 0),
        "n_orders": len(orders),
    }