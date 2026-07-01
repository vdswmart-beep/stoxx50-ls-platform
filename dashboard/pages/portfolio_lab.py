# dashboard/pages/portfolio_lab.py — LIVE (compte IBKR réel) + BACKTEST (simulation)

from dash import html, dcc, get_app
from dashboard.components.charts import line_chart, donut_chart
from dashboard.components.tables import base_table
import pandas as pd
import numpy as np

_CARD  = {"backgroundColor":"#0f141b","border":"1px solid #1e2a38","borderRadius":"8px","padding":"16px","marginBottom":"14px"}
_LABEL = {"fontSize":"10px","color":"#7eb8d8","textTransform":"uppercase","letterSpacing":".08em","marginBottom":"8px","fontWeight":"600"}


def _fmt(v, suffix="", decimals=2):
    if v is None: return "—"
    try:
        return f"{float(v):.{decimals}f}{suffix}"
    except Exception:
        return "—"


def layout():
    app = get_app()
    dp  = app.data_provider

    kpis = {}
    try:
        kpis = dp.get_portfolio_kpis()
    except Exception:
        kpis = {}
    is_live = kpis.get("is_live", False)

    nav_df = pd.DataFrame(columns=["date", "nav"])
    df_positions = pd.DataFrame()
    labels, weights_vals = [], []

    # ══════════════════ MODE LIVE : vrai compte IBKR ══════════════════
    if is_live:
        live = {}
        try:
            live = dp.get_live_account() or {}
        except Exception:
            live = {}
        positions = live.get("positions", [])
        rows = []
        for p in positions:
            mp = p.get("market_price"); mv = p.get("market_value"); up = p.get("unrealized_pnl")
            rows.append({
                "Ticker":   p.get("ticker", ""),
                "Side":     p.get("side", ""),
                "Qty":      p.get("qty", 0),
                "Avg Cost": f"€{p['avg_cost']:,.2f}" if p.get("avg_cost") else "—",
                "Price":    f"€{mp:,.2f}" if mp else "—",
                "Value":    f"€{mv:,.0f}" if mv else "—",
                "P&L":      f"€{up:+,.0f}" if up is not None else "—",
            })
        df_positions = pd.DataFrame(rows)

        # Donut : valeur de marché par position
        if positions:
            mvs = [(p.get("ticker",""), abs(p.get("market_value") or 0)) for p in positions]
            mvs = [(t, v) for t, v in mvs if v > 0]
            mvs.sort(key=lambda x: x[1], reverse=True)
            for t, v in mvs[:10]:
                labels.append(t); weights_vals.append(round(v, 0))
            if len(mvs) > 10:
                labels.append(f"Autres ({len(mvs)-10})")
                weights_vals.append(round(sum(v for _, v in mvs[10:]), 0))

    # ══════════════════ MODE BACKTEST : simulation ═══════════════════
    else:
        try:
            nav_df, weights_dict = dp.get_portfolio()
            if not isinstance(weights_dict, dict):
                weights_dict = {}
        except Exception:
            nav_df = pd.DataFrame(columns=["date", "nav"]); weights_dict = {}

        try:
            df_positions = dp.get_positions_df()
        except Exception:
            if weights_dict:
                rows = [{"ticker":t,"weight":round(v,4),"side":"LONG" if v>0 else "SHORT",
                         "weight_pct":f"{v:.2%}"} for t,v in weights_dict.items() if abs(v)>1e-5]
                df_positions = pd.DataFrame(rows)
            else:
                df_positions = pd.DataFrame(columns=["ticker","weight","side","weight_pct"])

        # Donut : top 10 poids + Autres
        if not df_positions.empty and "weight" in df_positions.columns:
            _d = df_positions.copy()
            _d["abs_w"] = _d["weight"].abs() * 100
            _d = _d.sort_values("abs_w", ascending=False)
            for _, r in _d.head(10).iterrows():
                labels.append(r["ticker"]); weights_vals.append(round(r["abs_w"], 2))
            rest = _d["abs_w"].iloc[10:].sum()
            if rest > 0.01:
                labels.append(f"Autres ({len(_d)-10})"); weights_vals.append(round(rest, 2))

    # ── KPIs ──────────────────────────────────────────────────────
    nav_val = kpis.get("nav", 0)
    if nav_val >= 1e7:
        nav_fmt = f"€{nav_val/1e6:.2f}M"
    elif nav_val > 0:
        nav_fmt = f"€{nav_val:,.0f}"
    else:
        nav_fmt = "—"

    tr_val   = kpis.get("total_ret", 0)
    tr_fmt   = f"{tr_val:+.2f}%" if tr_val else ("0.00%" if is_live else "—")
    tr_class = "kpi-positive" if (tr_val or 0) >= 0 else "kpi-negative"

    # Cartes différentes selon le mode
    if is_live:
        upnl = kpis.get("unrealized_pnl", 0)
        cash = kpis.get("cash", 0)
        card2 = ("P&L Latent", f"€{upnl:+,.0f}",
                 "kpi-positive" if (upnl or 0) >= 0 else "kpi-negative", "Non réalisé")
        card3 = ("Cash", f"€{cash:,.0f}", "kpi-neutral", "Disponible")
        card4 = ("Positions", f"{kpis.get('n_longs',0)}L / {kpis.get('n_shorts',0)}S",
                 "kpi-neutral", "Compte IBKR paper")
    else:
        card2 = ("Sharpe Ratio", _fmt(kpis.get("sharpe")), "kpi-neutral", "Annualisé")
        card3 = ("Volatilité Ann.", _fmt(kpis.get("vol"), "%"), "kpi-neutral", "Réalisée")
        card4 = ("Max Drawdown", _fmt(kpis.get("max_dd"), "%"), "kpi-negative",
                 f"{kpis.get('n_longs',0)}L / {kpis.get('n_shorts',0)}S positions")

    def _kpi_card(label, value, klass, sub):
        return html.Div(className="panel col-3", children=[
            html.Div(className="kpi", children=[
                html.Div(label, className="kpi-label"),
                html.Div(value, className="kpi-value" + ("" if klass=="kpi-neutral" and label!="NAV" else "")),
                html.Div(sub, className=f"kpi-sub {klass}"),
            ])
        ])

    mode_badge = html.Span(
        "● LIVE — Compte IBKR paper" if is_live else "○ BACKTEST — Simulation",
        style={"fontSize":"11px","color":"#4ade80" if is_live else "#f0a500",
               "fontWeight":"600","marginLeft":"12px"})

    # NAV panel : courbe en backtest, cash-info en live
    if is_live:
        nav_panel_content = html.Div([
            html.Div("VALEUR DU COMPTE", style=_LABEL),
            html.Div(nav_fmt, style={"fontSize":"42px","fontWeight":"700","color":"#e8f2ff",
                                     "letterSpacing":"-1px","marginTop":"20px"}),
            html.Div(f"P&L latent : {kpis.get('unrealized_pnl',0):+,.0f} €",
                     style={"fontSize":"14px","color":"#7090a8","marginTop":"12px"}),
            html.Div("Le compte IBKR ne fournit pas d'historique NAV en temps réel. "
                     "Utilise le Backtest Lab pour tester des stratégies sur l'historique.",
                     style={"fontSize":"11px","color":"#5a7080","marginTop":"20px","lineHeight":"1.6"}),
        ])
    else:
        nav_panel_content = html.Div([
            html.Div("NAV PERFORMANCE", style=_LABEL),
            dcc.Graph(
                figure=line_chart(nav_df if not nav_df.empty else pd.DataFrame(columns=["date","nav"]),
                                  "date", "nav", title="NAV", height=300),
                config={"displayModeBar":False},
            ),
        ])

    return html.Div([
        html.Div([
            html.Span("Portfolio", style={**_LABEL,"fontSize":"11px","letterSpacing":".1em","display":"inline"}),
            mode_badge,
        ], style={"marginBottom":"18px"}),

        # KPIs
        html.Div(className="grid", children=[
            _kpi_card("NAV", nav_fmt, tr_class, f"{tr_fmt} total"),
            _kpi_card(*card2),
            _kpi_card(*card3),
            _kpi_card(*card4),
        ]),

        html.Div(style={"height":"12px"}),

        # NAV + Donut
        html.Div(className="grid", children=[
            html.Div(className="panel col-8", children=[nav_panel_content]),
            html.Div(className="panel col-4", children=[
                html.Div("ALLOCATION" + (" (VALEUR)" if is_live else " (GROSS)"), style=_LABEL),
                dcc.Graph(
                    figure=donut_chart(labels, weights_vals, height=300) if labels
                           else donut_chart(["Aucune position"],[1], height=300),
                    config={"displayModeBar":False},
                ),
            ]),
        ]),

        html.Div(style={"height":"12px"}),

        # Positions table
        html.Div(className="panel col-12", children=[
            html.Div("POSITIONS" + (" (TEMPS RÉEL IBKR)" if is_live else ""), style=_LABEL),
            base_table(df_positions, id="portfolio-positions-tbl") if not df_positions.empty
            else html.Div(
                "Aucune position ouverte. Passe un ordre dans Execution pour voir tes positions ici."
                if is_live else "Aucune position — lancez le pipeline ou un Backtest",
                style={"color":"#5a7080","fontSize":"12px","padding":"16px 0"}),
        ], style=_CARD),

    ], style={"paddingBottom":"30px"})