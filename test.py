#!/usr/bin/env python3
# test_strategies.py — compare plusieurs versions de la strategie L/S sur tes donnees
# Usage : place a la racine ~/STOXX50/ et lance : python test_strategies.py

import sys, logging
sys.path.insert(0, ".")
logging.disable(logging.CRITICAL)
import pandas as pd, numpy as np
from typing import Dict

print("=" * 70)
print("  COMPARAISON DE STRATEGIES L/S — donnees reelles STOXX 50")
print("=" * 70)

from config.universe import get_universe
from data.data_service import DataService
from backtesting.backtest_engine import BacktestEngine

tickers = get_universe("full")
ds = DataService(mode="backtest")
returns = ds.get_returns(tickers, "2022-01-01", "2026-01-01")
print(f"\nDonnees : {returns.shape[1]} tickers, {len(returns)} jours\n")


# ══════════════ LES STRATEGIES A COMPARER ══════════════

def strat_baseline(returns: pd.DataFrame, top_n: int = 5) -> Dict[str, float]:
    """ACTUELLE : momentum 12M brut, equal-weight."""
    mom = returns.tail(252).mean(axis=0)
    ranked = mom.sort_values(ascending=False)
    longs, shorts = ranked.head(top_n).index, ranked.tail(top_n).index
    w = {t: 0.5/top_n for t in longs}
    for t in shorts: w[t] = -0.5/top_n
    return w


def strat_skip_month(returns: pd.DataFrame, top_n: int = 5) -> Dict[str, float]:
    """AMELIORATION 1 : momentum 12M-1M (skip dernier mois, evite le reversal)."""
    mom = returns.tail(252).head(252-21).mean(axis=0)  # 12M sauf dernier mois
    ranked = mom.sort_values(ascending=False)
    longs, shorts = ranked.head(top_n).index, ranked.tail(top_n).index
    w = {t: 0.5/top_n for t in longs}
    for t in shorts: w[t] = -0.5/top_n
    return w


def strat_vol_weighted(returns: pd.DataFrame, top_n: int = 5) -> Dict[str, float]:
    """AMELIORATION 2 : momentum 12M-1M + ponderation inverse-volatilite."""
    mom = returns.tail(252).head(252-21).mean(axis=0)
    vol = returns.tail(63).std(axis=0)  # vol recente 3M
    ranked = mom.sort_values(ascending=False)
    longs  = ranked.head(top_n).index.tolist()
    shorts = ranked.tail(top_n).index.tolist()
    # Poids inverse-vol (moins sur les actions volatiles)
    inv_vol = {t: 1.0/vol[t] if vol[t] > 0 else 0 for t in longs+shorts}
    long_sum  = sum(inv_vol[t] for t in longs) or 1
    short_sum = sum(inv_vol[t] for t in shorts) or 1
    w = {t: 0.5 * inv_vol[t]/long_sum for t in longs}
    for t in shorts: w[t] = -0.5 * inv_vol[t]/short_sum
    return w


def strat_wider(returns: pd.DataFrame, top_n: int = 8) -> Dict[str, float]:
    """AMELIORATION 3 : skip-month + inverse-vol + PLUS de positions (8 vs 5)."""
    return strat_vol_weighted(returns, top_n=8)


# ══════════════ COMPARAISON ══════════════

strategies = {
    "ACTUELLE (12M, equal-wt)":        (strat_baseline, 5),
    "12M-1M skip (anti-reversal)":     (strat_skip_month, 5),
    "12M-1M + inverse-vol":            (strat_vol_weighted, 5),
    "12M-1M + inv-vol + 8 positions":  (strat_wider, 8),
}

results = {}
print(f"{'Strategie':<34}{'Sharpe':>8}{'Rend.':>9}{'MaxDD':>8}{'Win%':>7}")
print("-" * 70)
for name, (fn, tn) in strategies.items():
    try:
        engine = BacktestEngine(train_months=12, test_months=3)
        res = engine.run(returns, lambda r, f=fn, t=tn: f(r, t))
        m = res.metrics
        results[name] = m
        print(f"{name:<34}{m.get('sharpe',0):>8.2f}"
              f"{m.get('total_return',0)*100:>+8.1f}%"
              f"{m.get('max_drawdown',0)*100:>7.1f}%"
              f"{m.get('win_rate',0)*100:>6.0f}%")
    except Exception as e:
        print(f"{name:<34}  Erreur: {e}")

print("-" * 70)

# Meilleure par Sharpe
if results:
    best = max(results.items(), key=lambda x: x[1].get('sharpe', 0))
    print(f"\n★ Meilleur Sharpe : {best[0]} ({best[1].get('sharpe',0):.2f})")
    base_sharpe = results.get("ACTUELLE (12M, equal-wt)", {}).get('sharpe', 0)
    best_sharpe = best[1].get('sharpe', 0)
    if best_sharpe > base_sharpe:
        gain = (best_sharpe - base_sharpe)
        print(f"  Amelioration vs actuelle : +{gain:.2f} de Sharpe")
    print(f"\n→ Dis-moi quelle strategie tu preferes, je l'integre au dashboard.")

print("=" * 70)