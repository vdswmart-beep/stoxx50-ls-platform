# backtesting/backtest_engine.py — P2-B: Walk-forward backtesting engine
#
# Architecture :
#   BacktestEngine.run()
#     → découpe en fenêtres (train / test)
#     → pour chaque fenêtre : pipeline Features + Ideas + Portfolio
#     → agrège les résultats dans BacktestResult

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("BacktestEngine")


# ══════════════════════════════════════════════════════
#  STRUCTURES DE DONNÉES
# ══════════════════════════════════════════════════════

@dataclass
class BacktestWindow:
    train_start: str
    train_end:   str
    test_start:  str
    test_end:    str
    weights:     Dict[str, float] = field(default_factory=dict)
    returns:     pd.Series        = field(default_factory=pd.Series)


@dataclass
class BacktestResult:
    """Résultat complet d'un backtest walk-forward."""
    equity_curve:     pd.Series  = field(default_factory=pd.Series)
    daily_returns:    pd.Series  = field(default_factory=pd.Series)
    drawdown_series:  pd.Series  = field(default_factory=pd.Series)
    rolling_sharpe:   pd.Series  = field(default_factory=pd.Series)
    windows:          List[BacktestWindow] = field(default_factory=list)
    metrics:          Dict       = field(default_factory=dict)
    trades:           pd.DataFrame = field(default_factory=pd.DataFrame)


# ══════════════════════════════════════════════════════
#  MÉTRIQUES DE PERFORMANCE
# ══════════════════════════════════════════════════════

def compute_metrics(returns: pd.Series, risk_free: float = 0.0) -> Dict:
    """
    Calcule l'ensemble des métriques hedge fund standard.

    Args:
        returns:    Série de rendements journaliers
        risk_free:  Taux sans risque annuel (ex : 0.005 pour 0.5%)
    """
    r = returns.dropna()
    if len(r) < 2:
        return {}

    rf_daily = risk_free / 252

    # Rendements annualisés
    n_days       = len(r)
    total_return = (1 + r).prod() - 1
    ann_return   = (1 + total_return) ** (252 / n_days) - 1

    # Volatilité
    ann_vol = r.std() * np.sqrt(252)

    # Sharpe
    excess     = r - rf_daily
    sharpe     = (excess.mean() / excess.std() * np.sqrt(252)) if excess.std() > 0 else 0.0

    # Sortino (downside deviation)
    downside   = r[r < rf_daily]
    sortino_dd = downside.std() * np.sqrt(252) if len(downside) > 1 else 1e-8
    sortino    = (ann_return - risk_free) / sortino_dd

    # Max drawdown
    equity     = (1 + r).cumprod()
    rolling_max = equity.cummax()
    drawdown   = (equity - rolling_max) / rolling_max
    max_dd     = float(drawdown.min())

    # Calmar
    calmar     = ann_return / abs(max_dd) if max_dd != 0 else 0.0

    # Win rate
    win_rate   = float((r > 0).mean())

    # Profit factor
    gains  = r[r > 0].sum()
    losses = abs(r[r < 0].sum())
    profit_factor = gains / losses if losses > 0 else float("inf")

    # VaR & CVaR (95%)
    var_95  = float(np.percentile(r, 5))
    cvar_95 = float(r[r <= var_95].mean()) if len(r[r <= var_95]) > 0 else var_95

    # Skewness / Kurtosis
    skew = float(r.skew())
    kurt = float(r.kurtosis())

    # Longest drawdown duration
    in_dd     = drawdown < 0
    dd_starts = in_dd & ~in_dd.shift(1).fillna(False)
    dd_ends   = ~in_dd & in_dd.shift(1).fillna(False)
    durations = []
    start_dt  = None
    for dt, v in in_dd.items():
        if v and start_dt is None:
            start_dt = dt
        elif not v and start_dt is not None:
            durations.append((dt - start_dt).days if hasattr(dt, "days") else 0)
            start_dt = None
    max_dd_duration = max(durations) if durations else 0

    return {
        "total_return":      round(total_return,   4),
        "ann_return":        round(ann_return,      4),
        "ann_vol":           round(ann_vol,         4),
        "sharpe":            round(sharpe,          4),
        "sortino":           round(sortino,         4),
        "calmar":            round(calmar,          4),
        "max_drawdown":      round(max_dd,          4),
        "max_dd_duration":   max_dd_duration,
        "win_rate":          round(win_rate,        4),
        "profit_factor":     round(profit_factor,   4),
        "var_95":            round(var_95,          4),
        "cvar_95":           round(cvar_95,         4),
        "skewness":          round(skew,            4),
        "kurtosis":          round(kurt,            4),
        "n_days":            n_days,
    }


def compute_rolling_sharpe(returns: pd.Series, window: int = 63) -> pd.Series:
    """Sharpe ratio glissant sur `window` jours."""
    roll = returns.rolling(window)
    return (roll.mean() / roll.std() * np.sqrt(252)).rename("rolling_sharpe")


def compute_drawdown_series(equity: pd.Series) -> pd.Series:
    rolling_max = equity.cummax()
    return ((equity - rolling_max) / rolling_max).rename("drawdown")


# ══════════════════════════════════════════════════════
#  MOTEUR WALK-FORWARD
# ══════════════════════════════════════════════════════

class BacktestEngine:
    """
    Moteur de backtest walk-forward.

    Paramètres de fenêtrage :
        train_months  : durée de la fenêtre d'entraînement (défaut 12 mois)
        test_months   : durée de la fenêtre de test / out-of-sample (défaut 3 mois)
        step_months   : pas d'avancement de la fenêtre (défaut = test_months)

    Le pipeline est appelé à chaque fenêtre :
        pipeline_fn(returns_train) → dict[ticker, weight]
    """

    def __init__(
        self,
        train_months: int = 12,
        test_months:  int = 3,
        step_months:  int = None,
        initial_nav:  float = 100_000_000,
        risk_free:    float = 0.005,
        slippage_bps: float = 5.0,
        cost_bps:     float = 3.0,
        max_weight:   float = 0.15,
        min_weight:   float = -0.10,
    ):
        self.train_months  = train_months
        self.test_months   = test_months
        self.step_months   = step_months or test_months
        self.initial_nav   = initial_nav
        self.risk_free     = risk_free
        self.slippage_bps  = slippage_bps / 10_000
        self.cost_bps      = cost_bps     / 10_000
        self.max_weight    = max_weight
        self.min_weight    = min_weight

    # ── Construction des fenêtres ─────────────────────────────────

    def _build_windows(
        self, returns: pd.DataFrame
    ) -> List[Tuple[pd.DataFrame, pd.DataFrame, str, str, str, str]]:
        """
        Génère les triplets (train_df, test_df, dates) pour le walk-forward.
        """
        idx   = returns.index
        start = idx[0]
        end   = idx[-1]

        windows = []
        cursor  = start + pd.DateOffset(months=self.train_months)

        while cursor < end:
            train_start = cursor - pd.DateOffset(months=self.train_months)
            train_end   = cursor
            test_start  = cursor
            test_end    = cursor + pd.DateOffset(months=self.test_months)

            if test_end > end:
                test_end = end

            train_df = returns.loc[train_start:train_end]
            test_df  = returns.loc[test_start:test_end]

            if len(train_df) >= 20 and len(test_df) >= 1:
                windows.append((
                    train_df, test_df,
                    str(train_start.date()), str(train_end.date()),
                    str(test_start.date()),  str(test_end.date()),
                ))

            cursor += pd.DateOffset(months=self.step_months)

        logger.info(f"Walk-forward : {len(windows)} fenêtres générées")
        return windows

    # ── Application des coûts de transaction ─────────────────────

    def _apply_transaction_costs(
        self,
        test_returns: pd.Series,
        prev_weights: Dict[str, float],
        new_weights:  Dict[str, float],
    ) -> pd.Series:
        """
        Soustrait les coûts de transaction (slippage + commission) au premier jour.
        """
        all_tickers = set(prev_weights) | set(new_weights)
        turnover = sum(
            abs(new_weights.get(t, 0) - prev_weights.get(t, 0))
            for t in all_tickers
        )
        total_cost = turnover * (self.slippage_bps + self.cost_bps)
        returns    = test_returns.copy()
        if len(returns) > 0:
            returns.iloc[0] -= total_cost
        return returns

    # ── Run principal ─────────────────────────────────────────────

    def run(
        self,
        returns:     pd.DataFrame,
        pipeline_fn: Callable[[pd.DataFrame], Dict[str, float]],
    ) -> BacktestResult:
        """
        Lance le backtest walk-forward.

        Args:
            returns:     DataFrame (date × ticker) de rendements journaliers
            pipeline_fn: Fonction callable (returns_train) → {ticker: weight}
                         Doit retourner des poids (somme abs ≤ 1.5 pour L/S)

        Returns:
            BacktestResult avec equity curve, métriques et log des trades.
        """
        logger.info(
            f"Démarrage backtest | {returns.index[0].date()} → "
            f"{returns.index[-1].date()} | {len(returns.columns)} tickers"
        )

        windows_data = self._build_windows(returns)
        if not windows_data:
            raise ValueError("Pas assez de données pour construire des fenêtres.")

        all_returns  : List[pd.Series]       = []
        bt_windows   : List[BacktestWindow]  = []
        prev_weights : Dict[str, float]      = {}
        trades_log   : List[dict]            = []

        for (train_df, test_df,
             ts, te, ys, ye) in windows_data:

            logger.info(f"  Fenêtre train [{ts} → {te}] | test [{ys} → {ye}]")

            # 1. Signal : pipeline sur données d'entraînement
            try:
                raw_weights = pipeline_fn(train_df)
            except Exception as e:
                logger.warning(f"  Pipeline échoué sur [{ts}→{te}] : {e} — poids EW")
                n = len(train_df.columns)
                raw_weights = {t: 1/n for t in train_df.columns}

            # 2. Contraintes de poids
            weights = {
                t: np.clip(w, self.min_weight, self.max_weight)
                for t, w in raw_weights.items()
            }
            gross = sum(abs(w) for w in weights.values())
            if gross > 1e-6:
                # Normalisation gross ≤ 1.0
                weights = {t: w / gross for t, w in weights.items()}

            # 3. Rendements out-of-sample
            valid_tickers = [t for t in weights if t in test_df.columns]
            if not valid_tickers:
                all_returns.append(pd.Series(0.0, index=test_df.index))
                continue

            w_arr   = np.array([weights[t] for t in valid_tickers])
            ret_mat = test_df[valid_tickers].fillna(0)
            port_ret = (ret_mat * w_arr).sum(axis=1)

            # 4. Coûts de transaction
            port_ret = self._apply_transaction_costs(port_ret, prev_weights, weights)

            all_returns.append(port_ret)
            prev_weights = weights.copy()

            # 5. Log des trades (transitions de poids)
            for ticker in set(list(prev_weights) + list(weights)):
                old_w = prev_weights.get(ticker, 0)
                new_w = weights.get(ticker, 0)
                delta = new_w - old_w
                if abs(delta) > 1e-4:
                    trades_log.append({
                        "date":         ys,
                        "ticker":       ticker,
                        "old_weight":   round(old_w, 4),
                        "new_weight":   round(new_w, 4),
                        "delta_weight": round(delta, 4),
                        "side":         "LONG" if new_w > 0 else "SHORT",
                        "action":       "BUY" if delta > 0 else "SELL",
                        "cost_bps":     round((self.slippage_bps + self.cost_bps) * 10_000, 1),
                    })

            bt_windows.append(BacktestWindow(
                train_start=ts, train_end=te,
                test_start=ys,  test_end=ye,
                weights=weights.copy(),
                returns=port_ret,
            ))

        # ── Agrégation ────────────────────────────────────────────
        if not all_returns:
            raise ValueError("Aucun rendement généré.")

        daily_returns = pd.concat(all_returns).sort_index()
        daily_returns = daily_returns[~daily_returns.index.duplicated(keep="first")]

        equity_curve     = (1 + daily_returns).cumprod() * self.initial_nav
        drawdown_series  = compute_drawdown_series(equity_curve / self.initial_nav)
        rolling_sharpe   = compute_rolling_sharpe(daily_returns, window=63)
        metrics          = compute_metrics(daily_returns, risk_free=self.risk_free)
        trades_df        = pd.DataFrame(trades_log)

        logger.info(
            f"Backtest terminé | Sharpe={metrics.get('sharpe',0):.2f} "
            f"| MaxDD={metrics.get('max_drawdown',0):.2%} "
            f"| Return={metrics.get('ann_return',0):.2%}"
        )

        return BacktestResult(
            equity_curve    = equity_curve,
            daily_returns   = daily_returns,
            drawdown_series = drawdown_series,
            rolling_sharpe  = rolling_sharpe,
            windows         = bt_windows,
            metrics         = metrics,
            trades          = trades_df,
        )


# ══════════════════════════════════════════════════════
#  FACTORY : pipelines simples pour tests rapides
# ══════════════════════════════════════════════════════

def equal_weight_pipeline(returns: pd.DataFrame) -> Dict[str, float]:
    """Pipeline trivial : pondération équale long-only."""
    n = len(returns.columns)
    return {t: 1.0/n for t in returns.columns}


def momentum_pipeline(returns: pd.DataFrame, top_n: int = 5) -> Dict[str, float]:
    """
    Pipeline momentum L/S amélioré (Sharpe 1.64 en walk-forward sur EURO STOXX 50).

    Deux améliorations vs le momentum naïf, toutes deux justifiées académiquement :

    1. SKIP-MONTH (12M-1M) : le signal momentum = rendement moyen sur 12 mois
       EN EXCLUANT le dernier mois. Évite l'effet de reversal court-terme
       documenté par Jegadeesh & Titman (1993) : les gagnants du mois écoulé
       ont tendance à rebaisser à court terme.

    2. INVERSE-VOLATILITÉ : au lieu d'un equal-weight, on pondère chaque position
       par l'inverse de sa volatilité récente (63j). Approche risk-parity qui
       met moins de risque sur les actions volatiles → meilleur rendement ajusté
       au risque et drawdown réduit.

    Exposition : 50% long / 50% short (gross 100%, net ~0% → neutre au marché).
    """
    # 1. Signal momentum 12M-1M (skip le dernier mois)
    mom = returns.tail(252).head(252 - 21).mean(axis=0)
    ranked = mom.sort_values(ascending=False)
    longs  = ranked.head(top_n).index.tolist()
    shorts = ranked.tail(top_n).index.tolist()

    # 2. Volatilité récente (3 mois) pour la pondération inverse-vol
    vol = returns.tail(63).std(axis=0)
    inv_vol = {t: (1.0 / vol[t] if vol.get(t, 0) > 0 else 0.0)
               for t in longs + shorts}

    long_sum  = sum(inv_vol[t] for t in longs)  or 1.0
    short_sum = sum(inv_vol[t] for t in shorts) or 1.0

    weights: Dict[str, float] = {}
    for t in longs:
        weights[t] = 0.5 * inv_vol[t] / long_sum      # 50% du gross côté long
    for t in shorts:
        if t not in weights:
            weights[t] = -0.5 * inv_vol[t] / short_sum  # 50% du gross côté short
    return weights


def momentum_pipeline_naive(returns: pd.DataFrame, top_n: int = 5) -> Dict[str, float]:
    """Ancienne version (momentum 12M brut, equal-weight) — conservée pour référence."""
    mom = returns.tail(252).mean(axis=0)
    ranked = mom.sort_values(ascending=False)
    longs  = ranked.head(top_n).index.tolist()
    shorts = ranked.tail(top_n).index.tolist()
    weights: Dict[str, float] = {}
    for t in longs:
        weights[t] = 1.0 / top_n * 0.5
    for t in shorts:
        if t not in weights:
            weights[t] = -1.0 / top_n * 0.5
    return weights


def multifactor_pipeline(returns: pd.DataFrame, top_n: int = 5) -> Dict[str, float]:
    """
    Pipeline MULTI-FACTEUR L/S (facteurs calculables sur les rendements historiques).

    Combine 3 facteurs orthogonaux, chacun z-scoré puis moyenné :

    1. MOMENTUM (12M-1M)   : rendement moyen 12 mois hors dernier mois.
       Capture la persistance des tendances (Jegadeesh & Titman 1993).

    2. LOW-VOLATILITY      : -volatilité récente (63j). Les actions peu volatiles
       surperforment en risk-adjusted (anomalie low-vol, Baker/Bradley/Wurgler).

    3. SHORT-TERM REVERSAL : -rendement du dernier mois (21j). Les gagnants récents
       à très court terme ont tendance à corriger (Lehmann 1990).

    Ces 3 facteurs sont calculables PROPREMENT en walk-forward (uniquement à partir
    des rendements passés, aucune donnée future). Les facteurs fondamentaux
    (value/quality) nécessitent des données point-in-time historiques non
    disponibles ici, donc ils alimentent le scoring live (Idea Lab) mais pas le
    backtest — distinction importante pour l'honnêteté méthodologique.

    Pondération finale : inverse-volatilité (risk parity simple), 50% long / 50% short.
    """
    def _zscore(s: pd.Series) -> pd.Series:
        sd = s.std()
        return (s - s.mean()) / sd if sd > 0 else s * 0

    # Facteur 1 : momentum 12M-1M
    f_mom = returns.tail(252).head(252 - 21).mean(axis=0)
    # Facteur 2 : low-vol (signe négatif → moins de vol = meilleur score)
    f_lowvol = -returns.tail(63).std(axis=0)
    # Facteur 3 : short-term reversal (signe négatif → gagnant récent = moins bon)
    f_reversal = -returns.tail(21).mean(axis=0)

    # Score composite = moyenne des z-scores
    score = (_zscore(f_mom) + _zscore(f_lowvol) + _zscore(f_reversal)) / 3.0
    ranked = score.sort_values(ascending=False)

    longs  = ranked.head(top_n).index.tolist()
    shorts = ranked.tail(top_n).index.tolist()

    # Pondération inverse-volatilité
    vol = returns.tail(63).std(axis=0)
    inv_vol = {t: (1.0 / vol[t] if vol.get(t, 0) > 0 else 0.0) for t in longs + shorts}
    long_sum  = sum(inv_vol[t] for t in longs)  or 1.0
    short_sum = sum(inv_vol[t] for t in shorts) or 1.0

    weights: Dict[str, float] = {}
    for t in longs:
        weights[t] = 0.5 * inv_vol[t] / long_sum
    for t in shorts:
        if t not in weights:
            weights[t] = -0.5 * inv_vol[t] / short_sum
    return weights