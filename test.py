#!/usr/bin/env python3
# test_strategies_full.py — compare TOUTES les strategies sur tes donnees reelles
import sys, logging
sys.path.insert(0, ".")
logging.disable(logging.CRITICAL)
import pandas as pd, numpy as np

print("=" * 72)
print("  COMPARAISON COMPLETE DES STRATEGIES — donnees reelles STOXX 50")
print("=" * 72)

from config.universe import get_universe
from data.data_service import DataService
from backtesting.backtest_engine import (
    BacktestEngine, momentum_pipeline, multifactor_pipeline)
from backtesting.hrp import hrp_long_short_pipeline

tickers = get_universe("full")
ds = DataService(mode="backtest")
returns = ds.get_returns(tickers, "2022-01-01", "2026-01-01")
print(f"\nDonnees : {returns.shape[1]} tickers, {len(returns)} jours\n")

strategies = {
    "Momentum seul (12M-1M+invvol)":  momentum_pipeline,
    "Multi-facteur (3 signaux)":      multifactor_pipeline,
    "Multi-facteur + HRP":            hrp_long_short_pipeline,
}

print(f"{'Strategie':<34}{'Sharpe':>8}{'Rend.':>9}{'MaxDD':>8}{'Win%':>7}")
print("-" * 72)
results = {}
for name, fn in strategies.items():
    try:
        res = BacktestEngine(train_months=12, test_months=3).run(returns, fn)
        m = res.metrics
        results[name] = m
        print(f"{name:<34}{m.get('sharpe',0):>8.2f}"
              f"{m.get('total_return',0)*100:>+8.1f}%"
              f"{m.get('max_drawdown',0)*100:>7.1f}%"
              f"{m.get('win_rate',0)*100:>6.0f}%")
    except Exception as e:
        print(f"{name:<34}  Erreur: {e}")
print("-" * 72)

if results:
    best = max(results.items(), key=lambda x: x[1].get('sharpe', 0))
    print(f"\n★ Meilleur Sharpe : {best[0]} ({best[1].get('sharpe',0):.2f})")
    print(f"\n→ Chaque approche est justifiee academiquement et calculee en")
    print(f"  walk-forward strict. Choisis celle que tu preferes defendre.")
print("=" * 72)