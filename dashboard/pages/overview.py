# dashboard/pages/overview.py — v3: P&L réel, positions, secteurs

from dash import html, dcc
import dash_bootstrap_components as dbc
import pandas as pd
import numpy as np
import plotly.graph_objects as go

_CARD  = {"backgroundColor":"#0f141b","border":"1px solid #1e2a38","borderRadius":"8px","padding":"16px","marginBottom":"14px"}
_LABEL = {"fontSize":"10px","color":"#7eb8d8","textTransform":"uppercase","letterSpacing":".08em","marginBottom":"8px","fontWeight":"600"}
_H1    = {"fontSize":"11px","color":"#7eb8d8","textTransform":"uppercase","letterSpacing":".1em","marginBottom":"18px","fontWeight":"600"}
_BG    = "#0f141b"; _BG2 = "#0a0d12"; _GRID = "rgba(255,255,255,0.04)"
_FONT  = dict(family="Inter, system-ui, sans-serif", color="#7090a8", size=11)


def _sector_fig(sector_exposure: dict, height=220):
    if not sector_exposure:
        return go.Figure()
    sectors = list(sector_exposure.keys())
    values  = [sector_exposure[s] * 100 for s in sectors]
    colors  = ["#4ade80" if v > 0 else "#f87171" for v in values]
    fig = go.Figure(go.Bar(
        x=values, y=sectors, orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        hovertemplate="%{y}: <b>%{x:.1f}%</b><extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor=_BG, plot_bgcolor=_BG, font=_FONT, height=height,
        margin=dict(l=120, r=30, t=16, b=36), showlegend=False,
        xaxis=dict(gridcolor=_GRID, ticksuffix="%", zeroline=True,
                   zerolinecolor="#2a3d50", tickfont=dict(size=10)),
        yaxis=dict(gridcolor="rgba(0,0,0,0)", tickfont=dict(size=11, color="#c8d8e8")),
    )
    return fig


def _positions_table(positions: list) -> html.Div:
    """Table des positions avec P&L par ligne."""
    if not positions:
        return html.Div("Aucune position — lancez le pipeline ou un Backtest",
                        style={"color":"#5a7080","fontSize":"12px","padding":"12px 0"})

    header = html.Tr([
        html.Th(col, style={"fontSize":"9px","color":"#5a7080","fontWeight":"600",
                             "textTransform":"uppercase","letterSpacing":".06em",
                             "padding":"6px 10px","borderBottom":"1px solid #1e2a38",
                             "textAlign":"right" if i>1 else "left"})
        for i, col in enumerate(["Ticker","Nom","Side","Poids","Notionnel (¥)","Mom 12M","Expected Ann. Ret","P&L (est.)"])
    ])

    rows = []
    for p in positions:
        side   = p.get("side","LONG")
        sc     = "#4ade80" if side=="LONG" else "#f87171"
        mom    = p.get("mom_12m", 0) or 0
        exp_ret= p.get("expected_ann_ret", 0) or 0
        pnl    = p.get("pnl_est", 0) or 0
        pnl_c  = "#4ade80" if pnl >= 0 else "#f87171"
        exp_c  = "#4ade80" if exp_ret >= 0 else "#f87171"

        rows.append(html.Tr([
            html.Td(p.get("ticker",""), style={"padding":"7px 10px","fontSize":"12px",
                                               "fontWeight":"600","color":"#e8f2ff",
                                               "borderBottom":"1px solid #0a0d12"}),
            html.Td(p.get("name","")[:20], style={"padding":"7px 10px","fontSize":"11px",
                                                   "color":"#7090a8","borderBottom":"1px solid #0a0d12"}),
            html.Td(side, style={"padding":"7px 10px","fontSize":"11px","fontWeight":"700",
                                  "color":sc,"borderBottom":"1px solid #0a0d12"}),
            html.Td(f"{p.get('weight',0)*100:.1f}%", style={"padding":"7px 10px","fontSize":"11px",
                                                              "textAlign":"right","color":"#c8d8e8",
                                                              "borderBottom":"1px solid #0a0d12",
                                                              "fontVariantNumeric":"tabular-nums"}),
            html.Td(f"¥{p.get('notional',0)/1e6:.1f}M", style={"padding":"7px 10px","fontSize":"11px",
                                                                  "textAlign":"right","color":"#c8d8e8",
                                                                  "borderBottom":"1px solid #0a0d12",
                                                                  "fontVariantNumeric":"tabular-nums"}),
            html.Td(f"{mom*100:+.1f}%", style={"padding":"7px 10px","fontSize":"11px","textAlign":"right",
                                                 "color":"#4ade80" if mom>=0 else "#f87171",
                                                 "borderBottom":"1px solid #0a0d12","fontVariantNumeric":"tabular-nums"}),
            html.Td(f"{exp_ret*100:+.1f}%", style={"padding":"7px 10px","fontSize":"11px","textAlign":"right",
                                                     "color":exp_c,"borderBottom":"1px solid #0a0d12",
                                                     "fontVariantNumeric":"tabular-nums"}),
            html.Td(f"{pnl*100:+.2f}%", style={"padding":"7px 10px","fontSize":"12px","textAlign":"right",
                                                  "color":pnl_c,"fontWeight":"600",
                                                  "borderBottom":"1px solid #0a0d12",
                                                  "fontVariantNumeric":"tabular-nums"}),
        ]))

    return html.Table([
        html.Thead(header),
        html.Tbody(rows),
    ], style={"width":"100%","borderCollapse":"collapse"})


def layout(dp=None):
    # ── Données ───────────────────────────────────────────────────
    last_nav = "—"; nav_pct = 0.0; n_longs = 0; n_shorts = 0
    total_pnl = 0.0; ann_ret = 0.0; sharpe = 0.0; max_dd = 0.0
    equity_fig = go.Figure()
    sector_fig  = go.Figure()
    positions   = []
    n_tickers   = 0

    if dp is not None:
        n_tickers = len(dp.tickers)
        try:
            from config.universe import TICKER_NAMES, SECTOR_MAP
        except Exception:
            TICKER_NAMES = {}; SECTOR_MAP = {}

        # NAV & rendements
        try:
            nav_df, weights_dict = dp.get_portfolio()
            if not isinstance(weights_dict, dict):
                weights_dict = {}

            if not nav_df.empty and "nav" in nav_df.columns:
                fv = float(nav_df["nav"].iloc[0]); lv = float(nav_df["nav"].iloc[-1])
                last_nav = f"¥{lv/1e6:.1f}M"
                nav_pct  = (lv/fv - 1)*100 if fv > 0 else 0
                n_longs  = sum(1 for v in weights_dict.values() if v > 0.001)
                n_shorts = sum(1 for v in weights_dict.values() if v < -0.001)

                # Equity curve
                ef = go.Figure()
                ef.add_trace(go.Scatter(
                    x=nav_df["date"], y=nav_df["nav"]/1e6, mode="lines",
                    line=dict(color="#4a9eff", width=2),
                    fill="tozeroy", fillcolor="rgba(74,158,255,0.06)",
                    hovertemplate="%{x|%Y-%m-%d}<br><b>¥%{y:.1f}M</b><extra></extra>",
                ))
                ef.update_layout(
                    paper_bgcolor=_BG, plot_bgcolor=_BG, font=_FONT, height=240,
                    margin=dict(l=50,r=16,t=16,b=36), showlegend=False,
                    xaxis=dict(gridcolor=_GRID, zeroline=False),
                    yaxis=dict(gridcolor=_GRID, zeroline=False, tickprefix="¥", ticksuffix="M"),
                )
                equity_fig = ef
        except Exception as e:
            pass

        # KPIs risk
        try:
            risk = dp.get_risk_metrics()
            if isinstance(risk, tuple) and len(risk) >= 5:
                _, port_rets, dd_series, var_val, cvar_val = risk
                if hasattr(port_rets, "mean") and len(port_rets) > 1:
                    ann_ret  = float(port_rets.mean() * 252 * 100)
                    sharpe   = float(port_rets.mean() / port_rets.std() * np.sqrt(252)) if port_rets.std() > 0 else 0
                if hasattr(dd_series, "min") and len(dd_series) > 0:
                    max_dd   = float(dd_series.min() * 100)
        except Exception:
            pass

        # Positions avec P&L estimé
        try:
            returns = dp.get_returns()
            paper_nav = getattr(dp, "paper_nav", 1e8)

            for ticker, weight in weights_dict.items():
                if abs(weight) < 1e-5:
                    continue
                side = "LONG" if weight > 0 else "SHORT"
                mom  = 0.0; exp_r = 0.0; pnl_e = 0.0

                if not returns.empty and ticker in returns.columns:
                    ret = returns[ticker].dropna()
                    mom   = float(ret.tail(252).mean() * 252)
                    exp_r = mom * (1 if side=="LONG" else -1)
                    # P&L estimé depuis le début du backtest
                    if len(ret) > 63:
                        pnl_e = float(ret.tail(63).sum()) * (1 if side=="LONG" else -1)

                total_pnl += pnl_e * abs(weight)

                positions.append({
                    "ticker":       ticker,
                    "name":         TICKER_NAMES.get(ticker, ticker),
                    "side":         side,
                    "weight":       weight,
                    "notional":     abs(weight) * paper_nav,
                    "mom_12m":      mom,
                    "expected_ann_ret": exp_r,
                    "pnl_est":      pnl_e,
                    "sector":       SECTOR_MAP.get(ticker, "Unknown"),
                })

            positions.sort(key=lambda x: abs(x["pnl_est"]), reverse=True)
        except Exception:
            pass

        # Exposition sectorielle
        try:
            sector_exp = {}
            for p in positions:
                sec = p.get("sector", "Unknown")
                sector_exp[sec] = sector_exp.get(sec, 0) + p["weight"]
            if sector_exp:
                sector_fig = _sector_fig(sector_exp, height=max(180, len(sector_exp)*28))
        except Exception:
            pass

    # ── Layout ────────────────────────────────────────────────────
    def kpi(label, value, color="#4a9eff", sub=None):
        return html.Div([
            html.Div(label, style=_LABEL),
            html.Div(str(value), style={"fontSize":"24px","fontWeight":"700","color":color,
                                         "fontVariantNumeric":"tabular-nums","lineHeight":"1.15"}),
            html.Div(sub, style={"fontSize":"11px","color":"#5a7080","marginTop":"4px"}) if sub else None,
        ], style={**_CARD,"padding":"14px 18px"})

    nav_color = "#4ade80" if nav_pct >= 0 else "#f87171"
    pnl_color = "#4ade80" if total_pnl >= 0 else "#f87171"

    return html.Div([
        html.Div("Portfolio Overview", style=_H1),

        # ── KPIs ligne 1 ──────────────────────────────────────────
        dbc.Row([
            dbc.Col(kpi("NAV", last_nav, "#4a9eff",
                        sub=f"{nav_pct:+.2f}% vs départ"), width=3),
            dbc.Col(kpi("P&L Total (63j)", f"{total_pnl*100:+.2f}%", pnl_color), width=3),
            dbc.Col(kpi("Ann. Return", f"{ann_ret:+.1f}%",
                        "#4ade80" if ann_ret >= 0 else "#f87171"), width=3),
            dbc.Col(kpi("Sharpe", f"{sharpe:.2f}",
                        "#4a9eff" if sharpe >= 0.5 else "#f0a500"), width=3),
        ], className="g-3", style={"marginBottom":"14px"}),

        dbc.Row([
            dbc.Col(kpi("Long Ideas",  str(n_longs),  "#4ade80"), width=3),
            dbc.Col(kpi("Short Ideas", str(n_shorts), "#f87171"), width=3),
            dbc.Col(kpi("Max Drawdown", f"{max_dd:.1f}%", "#f87171"), width=3),
            dbc.Col(kpi("Tickers",  str(n_tickers), "#f0a500",
                        sub="Univers actif"), width=3),
        ], className="g-3", style={"marginBottom":"14px"}),

        # ── Equity curve + Sector exposure ────────────────────────
        dbc.Row([
            dbc.Col(html.Div([
                html.Div("EQUITY CURVE (¥M)", style=_LABEL),
                dcc.Graph(figure=equity_fig, config={"displayModeBar":False},
                          style={"height":"240px"}),
            ], style=_CARD), width=8),
            dbc.Col(html.Div([
                html.Div("EXPOSITION SECTORIELLE (poids net)", style=_LABEL),
                dcc.Graph(figure=sector_fig, config={"displayModeBar":False},
                          style={"height":"240px"}),
            ], style=_CARD), width=4),
        ], className="g-3", style={"marginBottom":"14px"}),

        # ── Table des positions ───────────────────────────────────
        html.Div([
            html.Div([
                html.Div("POSITIONS & P&L ESTIMÉS", style={**_LABEL,"marginBottom":"12px"}),
                html.Div("⚠ P&L basé sur les rendements out-of-sample 63j × poids. "
                         "Lancez un Backtest pour des métriques précises.",
                         style={"fontSize":"10px","color":"#3a5060","marginBottom":"12px"}),
            ]),
            _positions_table(positions),
        ], style=_CARD),

        # ── Liens rapides ────────────────────────────────────────
        dbc.Row([
            dbc.Col(html.A("📈 Backtest →", href="/backtest", style={
                "color":"#4a9eff","fontSize":"12px","textDecoration":"none",
                "backgroundColor":"#111827","border":"1px solid #1e2a38",
                "borderRadius":"6px","padding":"9px 16px","display":"block",
                "textAlign":"center","fontWeight":"500",
            }), width=3),
            dbc.Col(html.A("💡 Idea Lab →", href="/ideas", style={
                "color":"#4ade80","fontSize":"12px","textDecoration":"none",
                "backgroundColor":"#111827","border":"1px solid #1e2a38",
                "borderRadius":"6px","padding":"9px 16px","display":"block",
                "textAlign":"center","fontWeight":"500",
            }), width=3),
            dbc.Col(html.A("⊘ Risk Lab →", href="/risk", style={
                "color":"#f87171","fontSize":"12px","textDecoration":"none",
                "backgroundColor":"#111827","border":"1px solid #1e2a38",
                "borderRadius":"6px","padding":"9px 16px","display":"block",
                "textAlign":"center","fontWeight":"500",
            }), width=3),
            dbc.Col(html.A("⇄ Exécution →", href="/execution", style={
                "color":"#f0a500","fontSize":"12px","textDecoration":"none",
                "backgroundColor":"#111827","border":"1px solid #1e2a38",
                "borderRadius":"6px","padding":"9px 16px","display":"block",
                "textAlign":"center","fontWeight":"500",
            }), width=3),
        ], className="g-3"),

    ], style={"paddingBottom":"30px"})