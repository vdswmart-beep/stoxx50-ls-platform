#!/usr/bin/env python3
# test_robustness.py — teste la SOLIDITE de la strategie momentum L/S
# Repond aux questions qu'un quant poserait :
#   1. Sensibilite aux parametres (top_n, lookback) — la perf tient-elle si on bouge les reglages ?
#   2. Stabilite par sous-periode — marche-t-elle chaque annee ou une seule ?
#   3. Contribution long vs short — les deux jambes contribuent-elles ?
# Usage : python test_robustness.py

import sys, logging
sys.path.insert(0, ".")
logging.disable(logging.CRITICAL)
import pandas as pd, numpy as np
from typing import Dict

print("=" * 72)
print("  TESTS DE ROBUSTESSE — strategie momentum L/S (donnees reelles)")
print("=" * 72)

from config.universe import get_universe
from data.data_service import DataService
from backtesting.backtest_engine import BacktestEngine

tickers = get_universe("full")
ds = DataService(mode="backtest")
returns = ds.get_returns(tickers, "2022-01-01", "2026-01-01")
print(f"\nDonnees : {returns.shape[1]} tickers, {len(returns)} jours")


def make_pipeline(top_n=5, lookback=252, skip=21):
    def pipe(rets: pd.DataFrame) -> Dict[str, float]:
        mom = rets.tail(lookback).head(lookback - skip).mean(axis=0)
        ranked = mom.sort_values(ascending=False)
        longs, shorts = ranked.head(top_n).index.tolist(), ranked.tail(top_n).index.tolist()
        vol = rets.tail(63).std(axis=0)
        iv = {t: (1/vol[t] if vol.get(t,0)>0 else 0) for t in longs+shorts}
        ls = sum(iv[t] for t in longs) or 1; ss = sum(iv[t] for t in shorts) or 1
        w = {t: 0.5*iv[t]/ls for t in longs}
        for t in shorts:
            if t not in w: w[t] = -0.5*iv[t]/ss
        return w
    return pipe


# ═══ TEST 1 : SENSIBILITE AU NOMBRE DE POSITIONS ═══
print("\n[1] Sensibilite a top_n (nb de positions par cote)")
print(f"    {'top_n':>6} {'Sharpe':>8} {'Rend.':>9} {'MaxDD':>8}")
print("    " + "-" * 34)
sharpes_topn = []
for tn in [3, 4, 5, 6, 7, 8]:
    res = BacktestEngine(train_months=12, test_months=3).run(returns, make_pipeline(top_n=tn))
    m = res.metrics
    sharpes_topn.append(m['sharpe'])
    star = " ★" if tn == 5 else ""
    print(f"    {tn:>6} {m['sharpe']:>8.2f} {m['total_return']*100:>+8.1f}% {m['max_drawdown']*100:>7.1f}%{star}")
stable1 = min(sharpes_topn) > 0.5
print(f"    → {'✓ ROBUSTE' if stable1 else '⚠ FRAGILE'} : Sharpe min {min(sharpes_topn):.2f} "
      f"(tous les reglages restent {'rentables' if stable1 else 'a surveiller'})")

# ═══ TEST 2 : SENSIBILITE AU LOOKBACK ═══
print("\n[2] Sensibilite au lookback momentum")
print(f"    {'lookback':>9} {'Sharpe':>8} {'Rend.':>9}")
print("    " + "-" * 28)
sharpes_lb = []
for lb, label in [(126, "6M"), (189, "9M"), (252, "12M"), (378, "18M")]:
    if lb >= len(returns): continue
    res = BacktestEngine(train_months=12, test_months=3).run(returns, make_pipeline(lookback=lb))
    m = res.metrics
    sharpes_lb.append(m['sharpe'])
    star = " ★" if lb == 252 else ""
    print(f"    {label:>9} {m['sharpe']:>8.2f} {m['total_return']*100:>+8.1f}%{star}")
stable2 = min(sharpes_lb) > 0.3
print(f"    → {'✓ ROBUSTE' if stable2 else '⚠ FRAGILE'} au choix du lookback")

# ═══ TEST 3 : STABILITE PAR ANNEE ═══
print("\n[3] Stabilite par sous-periode (annee par annee)")
res = BacktestEngine(train_months=12, test_months=3).run(returns, make_pipeline())
daily = res.daily_returns.dropna()
print(f"    {'Annee':>6} {'Rendement':>11} {'Sharpe':>8}")
print("    " + "-" * 28)
years_pos = 0; n_years = 0
for yr, grp in daily.groupby(daily.index.year):
    if len(grp) < 20: continue
    n_years += 1
    ret = (1+grp).prod()-1
    shp = grp.mean()/grp.std()*np.sqrt(252) if grp.std()>0 else 0
    if ret > 0: years_pos += 1
    print(f"    {yr:>6} {ret*100:>+10.1f}% {shp:>8.2f}  {'✓' if ret>0 else '✗'}")
print(f"    → {years_pos}/{n_years} annees positives")

# ═══ TEST 4 : CONTRIBUTION LONG vs SHORT ═══
print("\n[4] Contribution jambe LONG vs jambe SHORT")
def leg_pipeline(side):
    def pipe(rets):
        mom = rets.tail(252).head(231).mean(axis=0)
        ranked = mom.sort_values(ascending=False)
        vol = rets.tail(63).std(axis=0)
        if side == "long":
            names = ranked.head(5).index.tolist()
            iv = {t: (1/vol[t] if vol.get(t,0)>0 else 0) for t in names}
            s = sum(iv.values()) or 1
            return {t: iv[t]/s for t in names}          # 100% long
        else:
            names = ranked.tail(5).index.tolist()
            iv = {t: (1/vol[t] if vol.get(t,0)>0 else 0) for t in names}
            s = sum(iv.values()) or 1
            return {t: -iv[t]/s for t in names}         # 100% short
    return pipe

for side in ["long", "short"]:
    res_leg = BacktestEngine(train_months=12, test_months=3).run(returns, leg_pipeline(side))
    m = res_leg.metrics
    print(f"    Jambe {side.upper():5s} seule : Sharpe {m['sharpe']:>5.2f}, "
          f"rendement {m['total_return']*100:>+7.1f}%")
print("    → Ideal : les deux contribuent. Si le short est tres negatif,")
print("      c'est le cout normal du hedge en marche haussier.")

print("\n" + "=" * 72)
print("  VERDICT : si les tests 1-3 sont ✓, la strategie est defendable.")
print("=" * 72)