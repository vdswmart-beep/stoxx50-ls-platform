# dashboard/utils/strategy_monitor.py — Sharpe live par stratégie
"""
Calcule, à la demande, le Sharpe walk-forward de chaque stratégie sur les
données jusqu'à AUJOURD'HUI. Résultats mis en cache 1h (le calcul prend
10-30s pour 4 stratégies × 12 fenêtres).

Usage quotidien : ouvrir l'app → cliquer "Recalculer" → comparer les Sharpe
du moment → choisir la stratégie → aller dans Rebalancing.
"""

from __future__ import annotations
import time
import logging

logger = logging.getLogger("StrategyMonitor")

_CACHE = {"results": None, "t": 0, "computing": False}
CACHE_TTL = 3600  # 1 heure


STRATEGIES = [
    ("momentum",             "Momentum 12M-1M",        "Signal validé — référence"),
    ("momentum_fundamental", "Momentum + fondamentaux","Overlay ROE/marges/P-E (live)"),
    ("hrp",                  "Multi-facteur + HRP",    "Construction par clustering"),
    ("multifactor",          "Multi-facteur",          "3 signaux prix z-scorés"),
]


def compute_live_sharpes(dp, force: bool = False) -> dict:
    """
    Calcule le Sharpe walk-forward de chaque stratégie sur les données actuelles.

    Returns:
        {
          "computed_at": timestamp str,
          "age_min": minutes depuis calcul,
          "rows": [{key, label, note, sharpe, total_return, max_dd, win_rate,
                    last_window_return}],
        }
    """
    now = time.time()
    if not force and _CACHE["results"] is not None and (now - _CACHE["t"]) < CACHE_TTL:
        res = dict(_CACHE["results"])
        res["age_min"] = int((now - _CACHE["t"]) / 60)
        return res

    from backtesting.backtest_engine import (
        BacktestEngine, momentum_pipeline, multifactor_pipeline,
        momentum_fundamental_pipeline)
    from backtesting.hrp import hrp_long_short_pipeline

    returns = dp.get_returns()
    if returns is None or returns.empty:
        return {"error": "Pas de données de rendements", "rows": []}

    fundamentals = None
    try:
        fundamentals = dp.get_fundamentals()
    except Exception:
        pass

    pipelines = {
        "momentum":             momentum_pipeline,
        "momentum_fundamental": lambda r: momentum_fundamental_pipeline(r, fundamentals=fundamentals),
        "hrp":                  hrp_long_short_pipeline,
        "multifactor":          multifactor_pipeline,
    }

    rows = []
    for key, label, note in STRATEGIES:
        try:
            engine = BacktestEngine(train_months=12, test_months=3)
            res = engine.run(returns, pipelines[key])
            m = res.metrics
            # Rendement de la dernière fenêtre (le "momentum de la stratégie")
            last_ret = None
            if res.windows:
                lw = res.windows[-1].returns.dropna()
                if len(lw) > 0:
                    last_ret = float((1 + lw).prod() - 1)
            rows.append({
                "key": key, "label": label, "note": note,
                "sharpe":       round(float(m.get("sharpe", 0)), 2),
                "total_return": round(float(m.get("total_return", 0)) * 100, 1),
                "max_dd":       round(float(m.get("max_drawdown", 0)) * 100, 1),
                "win_rate":     round(float(m.get("win_rate", 0)) * 100, 0),
                "last_window":  round(last_ret * 100, 1) if last_ret is not None else None,
            })
        except Exception as e:
            logger.error(f"Stratégie {key}: {e}")
            rows.append({"key": key, "label": label, "note": f"Erreur : {e}",
                         "sharpe": None, "total_return": None, "max_dd": None,
                         "win_rate": None, "last_window": None})

    rows.sort(key=lambda r: (r["sharpe"] is not None, r["sharpe"] or -99), reverse=True)

    results = {
        "computed_at": time.strftime("%H:%M"),
        "age_min": 0,
        "rows": rows,
    }
    _CACHE["results"] = results
    _CACHE["t"] = now
    return results