#!/usr/bin/env python3
# test_frequency.py — quelle frequence de rebalancement ? (Sharpe brut, turnover, Sharpe NET de couts)
# Usage : python test_frequency.py

import sys, logging
sys.path.insert(0, ".")
logging.disable(logging.CRITICAL)
import pandas as pd, numpy as np

print("=" * 74)
print("  FREQUENCE DE REBALANCEMENT — Sharpe brut vs NET de couts (donnees reelles)")
print("=" * 74)

from config.universe import get_universe
from data.data_service import DataService
from backtesting.backtest_engine import BacktestEngine, momentum_pipeline

tickers = get_universe("full")
ds = DataService(mode="backtest")
returns = ds.get_returns(tickers, "2022-01-01", "2026-01-01")
print(f"\nDonnees : {returns.shape[1]} tickers, {len(returns)} jours")

COST_BPS = 10   # 10 bps par unite de turnover (commission ~5bps + spread ~5bps, large caps EU)

def turnover_series(windows):
    """Somme |Δw| entre fenetres consecutives (unites de gross tradees)."""
    tos = []
    prev = {}
    for w in windows:
        cur = dict(w.weights)
        keys = set(prev) | set(cur)
        to = sum(abs(cur.get(k, 0) - prev.get(k, 0)) for k in keys)
        tos.append(to)
        prev = cur
    return tos

print(f"\n{'Frequence':<14}{'Sharpe':>8}{'Rend.':>9}{'MaxDD':>8}"
      f"{'Turnover/reb':>13}{'Cout/an':>9}{'Sharpe NET':>11}")
print("-" * 74)
for tm, label in [(1, "Mensuelle"), (3, "Trimestrielle"), (6, "Semestrielle")]:
    res = BacktestEngine(train_months=12, test_months=tm).run(returns, momentum_pipeline)
    m = res.metrics
    tos = turnover_series(res.windows)
    avg_to = float(np.mean(tos[1:])) if len(tos) > 1 else 0   # ignorer l'initiation
    n_reb_per_year = 12 / tm
    annual_cost = avg_to * n_reb_per_year * COST_BPS / 10_000
    ann_ret, ann_vol = m.get("ann_return", 0), m.get("ann_vol", 1e-9)
    net_sharpe = (ann_ret - annual_cost) / ann_vol if ann_vol > 0 else 0
    star = " ★" if tm == 3 else ""
    print(f"{label:<14}{m['sharpe']:>8.2f}{m['total_return']*100:>+8.1f}%"
          f"{m['max_drawdown']*100:>7.1f}%{avg_to:>12.0%}"
          f"{annual_cost*100:>8.2f}%{net_sharpe:>11.2f}{star}")
print("-" * 74)
print(f"""
LECTURE :
- Turnover/reb = part du gross tradee a chaque rebalancement (Σ|Δw|).
- Cout/an = turnover x frequence x {COST_BPS} bps (commission + spread, large caps).
- Le Sharpe NET est celui qui compte : la frequence gagnante brute peut
  perdre une fois les couts inclus.
- Regle de decision : choisis la frequence au meilleur Sharpe NET, a
  condition qu'elle reste dans la zone validee par les tests de robustesse.
""")
print("=" * 74)