# dashboard/utils/decision_score.py — moteur de décision justifiée pour la watchlist
"""
Calcule un score de décision 0-100 par action, décomposé en 4 piliers VISIBLES,
chacun justifié par ses composantes. Objectif : chaque verdict (BUY/HOLD/AVOID)
est explicable en un coup d'œil — pas une boîte noire.

Piliers (pondérations) :
  MOMENTUM   35%  — 12M-1M return, prix vs MM200, RSI
  QUALITÉ    25%  — ROE, marges opérationnelles, croissance CA
  VALORISATION 20% — P/E vs borne sectorielle, P/B, EV/EBITDA
  RISQUE     20%  — volatilité, beta, dette/equity, drawdown 52s

Chaque pilier renvoie : score 0-100 + liste de (label, valeur, verdict, points).
Le verdict final : ≥65 BUY · 45-65 HOLD · <45 AVOID.
"""

from __future__ import annotations
import numpy as np
import pandas as pd


def _clamp(x, lo=0, hi=100):
    try:
        return max(lo, min(hi, float(x)))
    except Exception:
        return 50.0


def _pillar_momentum(close: pd.Series) -> dict:
    """Momentum : 12M-1M, position vs MM200, RSI(14)."""
    details = []
    score = 50.0
    if close is None or len(close) < 60:
        return {"score": 50, "details": [("Données insuffisantes", "—", "neutre", 0)]}

    # 12M-1M return
    try:
        if len(close) >= 252:
            mom = close.iloc[-21] / close.iloc[-252] - 1
        else:
            mom = close.iloc[-1] / close.iloc[0] - 1
        pts = _clamp(50 + mom * 150, 0, 100) - 50   # ±50 pts max
        score += pts * 0.5
        verdict = "positif" if mom > 0.05 else "négatif" if mom < -0.05 else "neutre"
        details.append((f"Momentum 12M-1M", f"{mom:+.1%}", verdict, round(pts * 0.5)))
    except Exception:
        pass

    # Prix vs MM200
    try:
        ma200 = close.rolling(min(200, len(close))).mean().iloc[-1]
        px = close.iloc[-1]
        above = (px / ma200 - 1)
        pts = 15 if above > 0.02 else -15 if above < -0.02 else 0
        score += pts
        verdict = "positif" if pts > 0 else "négatif" if pts < 0 else "neutre"
        details.append((f"Prix vs MM200", f"{above:+.1%}", verdict, pts))
    except Exception:
        pass

    # RSI (14) — extrêmes pénalisés
    try:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = float((100 - 100 / (1 + rs)).iloc[-1])
        if rsi > 75:
            pts, verdict = -10, "suracheté"
        elif rsi < 25:
            pts, verdict = -5, "survendu (couteau qui tombe ?)"
        elif 45 <= rsi <= 65:
            pts, verdict = 8, "sain"
        else:
            pts, verdict = 0, "neutre"
        score += pts
        details.append((f"RSI (14)", f"{rsi:.0f}", verdict, pts))
    except Exception:
        pass

    return {"score": _clamp(score), "details": details}


def _pillar_quality(info: dict) -> dict:
    """Qualité : ROE, marge opérationnelle, croissance du CA."""
    details = []
    score = 50.0

    roe = info.get("returnOnEquity")
    if roe is not None:
        pts = 15 if roe > 0.15 else 8 if roe > 0.08 else -12 if roe < 0 else 0
        verdict = "excellent" if pts >= 15 else "bon" if pts >= 8 else "négatif" if pts < 0 else "moyen"
        score += pts
        details.append(("ROE", f"{roe:.1%}", verdict, pts))

    om = info.get("operatingMargins")
    if om is not None:
        pts = 12 if om > 0.20 else 6 if om > 0.10 else -10 if om < 0 else 0
        verdict = "élevée" if pts >= 12 else "correcte" if pts >= 6 else "négative" if pts < 0 else "faible"
        score += pts
        details.append(("Marge opérationnelle", f"{om:.1%}", verdict, pts))

    rg = info.get("revenueGrowth")
    if rg is not None:
        pts = 12 if rg > 0.10 else 6 if rg > 0.03 else -10 if rg < -0.03 else 0
        verdict = "forte" if pts >= 12 else "modérée" if pts >= 6 else "en recul" if pts < 0 else "stable"
        score += pts
        details.append(("Croissance CA (yoy)", f"{rg:+.1%}", verdict, pts))

    if not details:
        details.append(("Fondamentaux indisponibles", "—", "neutre", 0))
    return {"score": _clamp(score), "details": details}


def _pillar_valuation(info: dict) -> dict:
    """Valorisation : P/E, P/B, EV/EBITDA — moins cher = mieux."""
    details = []
    score = 50.0

    pe = info.get("trailingPE")
    if pe is not None and pe > 0:
        pts = 12 if pe < 12 else 6 if pe < 18 else -6 if pe < 30 else -12
        verdict = "bon marché" if pts >= 12 else "raisonnable" if pts >= 6 else "chère" if pts <= -6 else "neutre"
        score += pts
        details.append(("P/E (trailing)", f"{pe:.1f}x", verdict, pts))
    elif pe is not None and pe <= 0:
        score -= 8
        details.append(("P/E (trailing)", "négatif", "pertes", -8))

    pb = info.get("priceToBook")
    if pb is not None and pb > 0:
        pts = 8 if pb < 1.5 else 4 if pb < 3 else -6 if pb > 6 else 0
        verdict = "décoté" if pts >= 8 else "correct" if pts >= 4 else "premium" if pts < 0 else "neutre"
        score += pts
        details.append(("P/B", f"{pb:.1f}x", verdict, pts))

    ev = info.get("enterpriseToEbitda")
    if ev is not None and ev > 0:
        pts = 8 if ev < 8 else 4 if ev < 12 else -6 if ev > 20 else 0
        verdict = "attractif" if pts >= 8 else "correct" if pts >= 4 else "élevé" if pts < 0 else "neutre"
        score += pts
        details.append(("EV/EBITDA", f"{ev:.1f}x", verdict, pts))

    if not details:
        details.append(("Valorisation indisponible", "—", "neutre", 0))
    return {"score": _clamp(score), "details": details}


def _pillar_risk(info: dict, close: pd.Series) -> dict:
    """Risque : volatilité réalisée, beta, dette, drawdown 52 semaines."""
    details = []
    score = 50.0

    if close is not None and len(close) > 63:
        vol = float(close.pct_change().tail(63).std() * np.sqrt(252))
        pts = 10 if vol < 0.20 else 5 if vol < 0.30 else -10 if vol > 0.45 else 0
        verdict = "faible" if pts >= 10 else "modérée" if pts >= 5 else "élevée" if pts < 0 else "normale"
        score += pts
        details.append(("Volatilité ann. (3M)", f"{vol:.0%}", verdict, pts))

        # Drawdown depuis le plus haut 52 semaines
        try:
            win = close.tail(252)
            dd = float(win.iloc[-1] / win.max() - 1)
            pts = 6 if dd > -0.05 else -8 if dd < -0.25 else 0
            verdict = "proche des hauts" if pts > 0 else "loin des hauts" if pts < 0 else "neutre"
            score += pts
            details.append(("Vs plus-haut 52s", f"{dd:+.1%}", verdict, pts))
        except Exception:
            pass

    beta = info.get("beta")
    if beta is not None:
        pts = 6 if beta < 0.9 else -6 if beta > 1.4 else 0
        verdict = "défensif" if pts > 0 else "agressif" if pts < 0 else "marché"
        score += pts
        details.append(("Beta", f"{beta:.2f}", verdict, pts))

    de = info.get("debtToEquity")
    if de is not None:
        pts = 8 if de < 50 else 0 if de < 120 else -10
        verdict = "peu endetté" if pts >= 8 else "endettement élevé" if pts < 0 else "normal"
        score += pts
        details.append(("Dette/Equity", f"{de:.0f}%", verdict, pts))

    if not details:
        details.append(("Risque non mesurable", "—", "neutre", 0))
    return {"score": _clamp(score), "details": details}


WEIGHTS = {"momentum": 0.35, "quality": 0.25, "valuation": 0.20, "risk": 0.20}


def compute_decision(info: dict, close: pd.Series) -> dict:
    """
    Score de décision complet pour une action.

    Returns:
        {
          "score": 0-100,
          "verdict": "BUY"|"HOLD"|"AVOID",
          "pillars": {name: {"score", "weight", "details":[(label,val,verdict,pts)]}},
        }
    """
    pillars = {
        "momentum":  {**_pillar_momentum(close),        "weight": WEIGHTS["momentum"]},
        "quality":   {**_pillar_quality(info or {}),    "weight": WEIGHTS["quality"]},
        "valuation": {**_pillar_valuation(info or {}),  "weight": WEIGHTS["valuation"]},
        "risk":      {**_pillar_risk(info or {}, close),"weight": WEIGHTS["risk"]},
    }
    total = sum(p["score"] * p["weight"] for p in pillars.values())
    verdict = "BUY" if total >= 65 else "HOLD" if total >= 45 else "AVOID"
    return {"score": round(total, 1), "verdict": verdict, "pillars": pillars}