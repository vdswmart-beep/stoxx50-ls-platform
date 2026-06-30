# dashboard/callbacks/math_callbacks.py — Pair Trading Engine

import logging
import numpy as np
import pandas as pd
from dash import Input, Output, State, html, dcc
import plotly.graph_objects as go
from dashboard.components.charts import empty_fig

logger = logging.getLogger("MathCallbacks")
_BG = "#0f141b"; _BG2 = "#0a0d12"; _GRID = "rgba(255,255,255,0.04)"
_TEXT = "#c8d8e8"; _MUTED = "#7090a8"
_FONT = dict(family="Inter, system-ui, sans-serif", color=_TEXT, size=11)


def _base_layout(height=260, title=""):
    return dict(
        paper_bgcolor=_BG, plot_bgcolor=_BG, font=_FONT, height=height,
        margin=dict(l=50, r=20, t=36, b=36), showlegend=True,
        hovermode="x unified", legend=dict(font=dict(size=10, color=_MUTED)),
        xaxis=dict(gridcolor=_GRID, linecolor="#1e2a38",
                   tickfont=dict(size=10, color=_MUTED), zeroline=False),
        yaxis=dict(gridcolor=_GRID, linecolor="#1e2a38",
                   tickfont=dict(size=10, color=_MUTED), zeroline=True,
                   zerolinecolor="#243244"),
        title=dict(text=title, font=dict(size=11, color=_MUTED), x=0),
    )


def _ols_beta(y: pd.Series, x: pd.Series) -> float:
    """Estime β par OLS : y = α + β·x"""
    x_, y_ = x.dropna().align(y.dropna(), join="inner")
    if len(x_) < 10:
        return 1.0
    X = np.column_stack([np.ones(len(x_)), x_.values])
    try:
        beta = np.linalg.lstsq(X, y_.values, rcond=None)[0][1]
        return float(beta)
    except Exception:
        return 1.0


def _compute_spread(prices_a: pd.Series, prices_b: pd.Series,
                    window: int = 63):
    """
    Calcule le spread de coïntégration :
    spread_t = log(A_t) - β_t · log(B_t)
    β_t estimé sur une fenêtre glissante.
    """
    log_a = np.log(prices_a.clip(lower=1e-8))
    log_b = np.log(prices_b.clip(lower=1e-8))

    # Rolling OLS beta
    betas = pd.Series(index=log_a.index, dtype=float)
    for i in range(window, len(log_a)):
        ya = log_a.iloc[i-window:i]
        xb = log_b.iloc[i-window:i]
        betas.iloc[i] = _ols_beta(ya, xb)

    betas.ffill(inplace=True)
    betas.fillna(1.0, inplace=True)

    spread = log_a - betas * log_b
    return spread, betas


def _compute_zscore(spread: pd.Series, window: int) -> pd.Series:
    mu  = spread.rolling(window).mean()
    sig = spread.rolling(window).std()
    return (spread - mu) / sig.replace(0, np.nan)


def _cointegration_test(log_a: pd.Series, log_b: pd.Series):
    """Engle-Granger cointegration test."""
    try:
        from statsmodels.tsa.stattools import coint
        la, lb = log_a.align(log_b, join="inner")
        la, lb = la.dropna(), lb.dropna()
        la, lb = la.align(lb, join="inner")
        score, pvalue, _ = coint(la.values, lb.values)
        return {"score": float(score), "p_value": float(pvalue),
                "is_cointegrated": pvalue < 0.05}
    except Exception as e:
        return {"score": np.nan, "p_value": np.nan, "is_cointegrated": False}


def _adf_test(series: pd.Series):
    """ADF test on the spread."""
    try:
        from statsmodels.tsa.stattools import adfuller
        clean = series.dropna()
        result = adfuller(clean.values, maxlags=5, autolag="AIC")
        return {"adf_stat": float(result[0]), "p_value": float(result[1]),
                "is_stationary": result[1] < 0.05,
                "critical_5pct": float(result[4].get("5%", 0))}
    except Exception:
        return {"adf_stat": np.nan, "p_value": np.nan,
                "is_stationary": False, "critical_5pct": np.nan}


def _backtest_spread(zscore: pd.Series, spread: pd.Series,
                     entry_z: float = 2.0, exit_z: float = 0.5):
    """
    Stratégie mean-reversion sur le spread :
    - Long spread  (Long A, Short B) quand z < -entry_z
    - Short spread (Short A, Long B) quand z > +entry_z
    - Sortie quand |z| < exit_z
    """
    position = pd.Series(0, index=zscore.index, dtype=float)
    in_position = 0

    for i in range(1, len(zscore)):
        z = zscore.iloc[i]
        if np.isnan(z):
            position.iloc[i] = in_position
            continue
        if in_position == 0:
            if z < -entry_z:
                in_position = 1    # Long spread
            elif z > entry_z:
                in_position = -1   # Short spread
        elif in_position == 1 and z >= -exit_z:
            in_position = 0
        elif in_position == -1 and z <= exit_z:
            in_position = 0
        position.iloc[i] = in_position

    spread_ret    = spread.diff()
    strategy_ret  = position.shift(1) * spread_ret
    cumulative    = strategy_ret.cumsum()

    n_trades = int(position.diff().abs().sum() / 2)
    if len(strategy_ret.dropna()) > 0:
        ann_return = float(strategy_ret.mean() * 252)
        ann_vol    = float(strategy_ret.std() * np.sqrt(252))
        sharpe     = ann_return / ann_vol if ann_vol > 0 else 0.0
    else:
        ann_return = ann_vol = sharpe = 0.0

    return cumulative, position, {
        "n_trades": n_trades,
        "ann_return": ann_return,
        "ann_vol": ann_vol,
        "sharpe": sharpe,
    }


def register_math_callbacks(app, dp):

    @app.callback(
        Output("math-chart-output",  "figure"),
        Output("math-zscore-output", "figure"),
        Output("math-pnl-output",    "figure"),
        Output("math-beta-output",   "figure"),
        Output("math-corr-output",   "figure"),
        Output("math-stats-output",  "children"),
        Input("math-run-btn",        "n_clicks"),
        State("math-ticker-a",       "value"),
        State("math-ticker-b",       "value"),
        State("math-entry-z",        "value"),
        State("math-exit-z",         "value"),
        State("math-window",         "value"),
        prevent_initial_call=True,
    )
    def run_pair_analysis(n_clicks, ticker_a, ticker_b, entry_z, exit_z, window):
        empty = empty_fig(height=260)

        if not ticker_a or not ticker_b:
            return empty, empty, empty, empty, empty, "Sélectionner deux tickers."

        if ticker_a == ticker_b:
            return empty, empty, empty, empty, empty, "Les deux tickers doivent être différents."

        entry_z = float(entry_z or 2.0)
        exit_z  = float(exit_z  or 0.5)
        window  = int(window or 63)

        try:
            returns = dp.get_returns()
            if returns.empty or ticker_a not in returns.columns or ticker_b not in returns.columns:
                return empty, empty, empty, empty, empty, "Données non disponibles."

            # Reconstituer les prix depuis les rendements (base 100)
            ret_a = returns[ticker_a].dropna()
            ret_b = returns[ticker_b].dropna()
            idx   = ret_a.index.intersection(ret_b.index)
            ret_a, ret_b = ret_a.loc[idx], ret_b.loc[idx]

            prices_a = (1 + ret_a).cumprod() * 100
            prices_b = (1 + ret_b).cumprod() * 100

            # ── Spread & Z-score ───────────────────────────────────────
            spread, betas = _compute_spread(prices_a, prices_b, window)
            zscore        = _compute_zscore(spread, window)

            # ── Coïntégration ─────────────────────────────────────────
            log_a = np.log(prices_a.clip(lower=1e-8))
            log_b = np.log(prices_b.clip(lower=1e-8))
            coint = _cointegration_test(log_a, log_b)
            adf   = _adf_test(spread)

            # ── Backtest ──────────────────────────────────────────────
            pnl, position, bt_stats = _backtest_spread(zscore, spread, entry_z, exit_z)

            # ── FIGURE 1 : Spread ──────────────────────────────────────
            spread_clean = spread.dropna()
            fig_spread   = go.Figure()
            fig_spread.add_trace(go.Scatter(
                x=spread_clean.index, y=spread_clean.values,
                name="Spread", mode="lines",
                line=dict(color="#4a9eff", width=1.5),
                hovertemplate="%{x|%Y-%m-%d}<br>Spread: %{y:.4f}<extra></extra>",
            ))
            # Bandes ±1σ
            mu  = spread_clean.rolling(window).mean().dropna()
            sig = spread_clean.rolling(window).std().dropna()
            common = mu.index.intersection(sig.index).intersection(spread_clean.index)
            mu, sig = mu.loc[common], sig.loc[common]
            fig_spread.add_trace(go.Scatter(
                x=mu.index, y=(mu+sig).values,
                name="+1σ", line=dict(color="#f0a500", width=1, dash="dot"),
            ))
            fig_spread.add_trace(go.Scatter(
                x=mu.index, y=(mu-sig).values,
                name="−1σ", line=dict(color="#f0a500", width=1, dash="dot"),
                fill="tonexty", fillcolor="rgba(240,165,0,0.04)",
            ))
            fig_spread.update_layout(
                **_base_layout(280, f"Spread: log({ticker_a}) − β·log({ticker_b})")
            )

            # ── FIGURE 2 : Z-score avec signaux ───────────────────────
            z_clean = zscore.dropna()
            colors  = []
            for z in z_clean.values:
                if   z >  entry_z:  colors.append("#f87171")
                elif z < -entry_z:  colors.append("#4ade80")
                elif abs(z) < exit_z: colors.append("#f0a500")
                else:               colors.append("#4a9eff")

            fig_z = go.Figure()
            fig_z.add_trace(go.Scatter(
                x=z_clean.index, y=z_clean.values,
                name="Z-score", mode="lines",
                line=dict(color="#60c4cc", width=1.5),
                hovertemplate="%{x|%Y-%m-%d}<br>Z: %{y:.3f}<extra></extra>",
            ))
            for level, color, label in [
                ( entry_z,  "#f87171", f"+{entry_z}σ SHORT spread"),
                (-entry_z,  "#4ade80", f"−{entry_z}σ LONG spread"),
                ( exit_z,   "#f0a500", f"+{exit_z}σ exit"),
                (-exit_z,   "#f0a500", f"−{exit_z}σ exit"),
            ]:
                fig_z.add_hline(y=level, line_dash="dash",
                                line_color=color, line_width=1,
                                annotation_text=label,
                                annotation_font_size=9,
                                annotation_font_color=color)
            # Signaux
            long_signals  = z_clean[z_clean < -entry_z]
            short_signals = z_clean[z_clean >  entry_z]
            if not long_signals.empty:
                fig_z.add_trace(go.Scatter(
                    x=long_signals.index, y=long_signals.values,
                    mode="markers", name="LONG spread",
                    marker=dict(color="#4ade80", size=6, symbol="triangle-up"),
                ))
            if not short_signals.empty:
                fig_z.add_trace(go.Scatter(
                    x=short_signals.index, y=short_signals.values,
                    mode="markers", name="SHORT spread",
                    marker=dict(color="#f87171", size=6, symbol="triangle-down"),
                ))
            fig_z.update_layout(**_base_layout(260, "Z-Score du Spread"))

            # ── FIGURE 3 : PnL backtest ───────────────────────────────
            pnl_clean = pnl.dropna()
            pnl_color = "#4ade80" if (len(pnl_clean) > 0 and pnl_clean.iloc[-1] > 0) else "#f87171"
            fig_pnl   = go.Figure()
            fig_pnl.add_trace(go.Scatter(
                x=pnl_clean.index, y=pnl_clean.values,
                name="PnL cumulé", mode="lines",
                line=dict(color=pnl_color, width=1.8),
                fill="tozeroy", fillcolor=f"rgba({'74,222,128' if pnl_color=='#4ade80' else '248,113,113'},0.07)",
                hovertemplate="%{x|%Y-%m-%d}<br>PnL: %{y:.4f}<extra></extra>",
            ))
            fig_pnl.update_layout(**_base_layout(240,
                f"Backtest PnL — {bt_stats['n_trades']} trades | "
                f"Sharpe: {bt_stats['sharpe']:.2f} | "
                f"Ann. Return: {bt_stats['ann_return']*100:.1f}%"))

            # ── FIGURE 4 : Rolling Beta ───────────────────────────────
            b_clean = betas.dropna()
            fig_beta = go.Figure()
            fig_beta.add_trace(go.Scatter(
                x=b_clean.index, y=b_clean.values,
                name="β rolling", mode="lines",
                line=dict(color="#c084fc", width=1.5),
                hovertemplate="%{x|%Y-%m-%d}<br>β: %{y:.4f}<extra></extra>",
            ))
            fig_beta.add_hline(y=1.0, line_dash="dot", line_color="#5a7080",
                               annotation_text="β=1", annotation_font_size=9)
            fig_beta.update_layout(**_base_layout(220,
                f"Rolling Beta ({window}j) — {ticker_a} vs {ticker_b}"))

            # ── FIGURE 5 : Rolling Corrélation ────────────────────────
            corr = ret_a.rolling(window).corr(ret_b)
            c_clean = corr.dropna()
            corr_color_vals = ["#4ade80" if v > 0.6 else "#f0a500" if v > 0.3 else "#f87171"
                               for v in c_clean.values]
            fig_corr = go.Figure()
            fig_corr.add_trace(go.Scatter(
                x=c_clean.index, y=c_clean.values,
                name="Corrélation", mode="lines",
                line=dict(color="#4a9eff", width=1.5),
                hovertemplate="%{x|%Y-%m-%d}<br>ρ: %{y:.3f}<extra></extra>",
            ))
            fig_corr.add_hline(y=0.6, line_dash="dash", line_color="#4ade80",
                               line_width=1, annotation_text="seuil 0.6",
                               annotation_font_size=9, annotation_font_color="#4ade80")
            fig_corr.add_hline(y=0.3, line_dash="dash", line_color="#f0a500",
                               line_width=1)
            fig_corr.update_layout(**_base_layout(220, f"Rolling Corrélation ({window}j)"))

            # ── Stats panel ───────────────────────────────────────────
            coint_ok = coint.get("is_cointegrated", False)
            adf_ok   = adf.get("is_stationary", False)
            current_z = float(zscore.dropna().iloc[-1]) if len(zscore.dropna()) > 0 else 0
            signal_now = (
                f"LONG spread (buy {ticker_a}, sell {ticker_b})" if current_z < -entry_z else
                f"SHORT spread (sell {ticker_a}, buy {ticker_b})" if current_z > entry_z else
                "En attente (z-score dans les bandes)"
            )
            signal_color = "#4ade80" if current_z < -entry_z else "#f87171" if current_z > entry_z else "#f0a500"

            def _stat_row(label, val, color="#c8d8e8"):
                return html.Div([
                    html.Span(label, style={"color":"#7090a8","fontSize":"10px","flex":"1"}),
                    html.Span(str(val), style={"color":color,"fontSize":"11px","fontWeight":"600"}),
                ], style={"display":"flex","justifyContent":"space-between",
                          "padding":"5px 0","borderBottom":"1px solid #1e2a38"})

            stats = html.Div([
                html.Div(f"{ticker_a} / {ticker_b}", style={"fontSize":"13px","fontWeight":"700",
                                                              "color":"#e8f2ff","marginBottom":"12px"}),
                _stat_row("Coïntégrés",
                          "✓ OUI" if coint_ok else "✗ NON",
                          "#4ade80" if coint_ok else "#f87171"),
                _stat_row("p-value coint.",
                          f"{coint.get('p_value',0):.4f}",
                          "#4ade80" if coint_ok else "#f87171"),
                _stat_row("Spread stationnaire",
                          "✓ OUI" if adf_ok else "✗ NON",
                          "#4ade80" if adf_ok else "#f87171"),
                _stat_row("ADF p-value",
                          f"{adf.get('p_value',0):.4f}",
                          "#4ade80" if adf_ok else "#f87171"),
                _stat_row("β moyen",      f"{betas.mean():.4f}"),
                _stat_row("Z-score actuel", f"{current_z:.3f}",
                          "#4ade80" if current_z < -entry_z else "#f87171" if current_z > entry_z else "#f0a500"),
                _stat_row("Sharpe backtest", f"{bt_stats['sharpe']:.3f}",
                          "#4ade80" if bt_stats["sharpe"] > 0 else "#f87171"),
                _stat_row("Nb trades", str(bt_stats["n_trades"])),
                html.Div([
                    html.Div("SIGNAL ACTUEL", style={"fontSize":"9px","color":"#5a7080",
                                                      "textTransform":"uppercase","letterSpacing":".06em",
                                                      "marginTop":"10px","marginBottom":"4px"}),
                    html.Div(signal_now, style={"fontSize":"11px","fontWeight":"600",
                                                "color":signal_color,"lineHeight":"1.4"}),
                ]),
            ])

            return fig_spread, fig_z, fig_pnl, fig_beta, fig_corr, stats

        except Exception as e:
            logger.error(f"Pair analysis error: {e}", exc_info=True)
            err = html.Div(f"Erreur : {e}", style={"color":"#f87171","fontSize":"11px"})
            return empty, empty, empty, empty, empty, err