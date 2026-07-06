#!/usr/bin/env python3
# test_ic.py — IC corrige : compare les facteurs sur tes donnees reelles
# Usage : python test_ic.py

import sys, logging
sys.path.insert(0, ".")
logging.disable(logging.CRITICAL)
import pandas as pd, numpy as np

print("=" * 72)
print("  INFORMATION COEFFICIENTS — facteurs compares (donnees reelles)")
print("=" * 72)

from config.universe import get_universe
from data.data_service import DataService

tickers = get_universe("full")
ds = DataService(mode="backtest")
returns = ds.get_returns(tickers, "2022-01-01", "2026-01-01")
print(f"\nDonnees : {returns.shape[1]} tickers, {len(returns)} jours\n")

FACTORS = {
    "Momentum 12M-1M (STRATEGIE)": lambda p: p.tail(252).head(231).mean(),
    "Momentum 6M":                 lambda p: p.tail(126).mean(),
    "Low-Volatility":              lambda p: -p.tail(63).std(),
    "Momentum 1M (ANCIEN CALCUL)": lambda p: p.tail(21).mean(),
}

print(f"{'Facteur':<30}{'IC Mean':>9}{'IC IR':>8}{'Hit%':>7}{'Obs':>6}")
print("-" * 72)
for name, fn in FACTORS.items():
    start = 273 if "12M" in name else 130 if "6M" in name else 70
    ics = []
    for i in range(start, len(returns) - 21, 21):
        sig = fn(returns.iloc[:i])
        fwd = returns.iloc[i:i+21].mean()
        al = pd.concat([sig, fwd], axis=1).dropna()
        if len(al) < 5: continue
        ics.append(float(al.iloc[:,0].corr(al.iloc[:,1], method="spearman")))
    s = pd.Series(ics)
    ir = s.mean()/s.std() if s.std() > 0 else 0
    flag = " ← ta strategie" if "STRATEGIE" in name else " ← l'ancien IC bugge" if "ANCIEN" in name else ""
    print(f"{name:<30}{s.mean():>+9.3f}{ir:>+8.2f}{(s>0).mean()*100:>6.0f}%{len(s):>6}{flag}")
print("-" * 72)
print("""
LECTURE :
- L'ancien Research Lab mesurait le Momentum 1M → IC negatif = short-term
  reversal (les gagnants du mois corrigent). C'est un resultat CONNU de la
  litterature, pas un defaut de ta strategie.
- Le facteur de TA strategie (12M-1M) doit montrer un IC positif — coherent
  avec son Sharpe de 1.6 en walk-forward.
- Un IC de +0.03 a +0.08 sur 50 titres est tout a fait respectable : avec
  seulement 50 noms, l'IC cross-sectionnel est bruite par construction.
""")
print("=" * 72)