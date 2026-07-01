# dashboard/pages/overview.py — Real portfolio: positions, P&L, sector exposure

from dash import html, dcc, get_app
import dash_bootstrap_components as dbc
import pandas as pd
import numpy as np
from dashboard.components.charts import line_chart, empty_fig
import plotly.graph_objects as go

_CARD  = {"backgroundColor":"#0f141b","border":"1px solid #1e2a38","borderRadius":"8px","padding":"16px","marginBottom":"14px"}
_LABEL = {"fontSize":"10px","color":"#7eb8d8","textTransform":"uppercase","letterSpacing":".08em","marginBottom":"8px","fontWeight":"600"}
_H1    = {"fontSize":"11px","color":"#7eb8d8","textTransform":"uppercase","letterSpacing":".1em","marginBottom":"18px","fontWeight":"600"}
_BG    = "#0f141b"; _BG2 = "#0a0d12"; _GRID = "rgba(255,255,255,0.04)"
_FONT  = dict(family="Inter, system-ui, sans-serif", color="#c8d8e8", size=11)


def _kpi(label, value, color="#4a9eff", sub=None):
    return html.Div([
        html.Div(label, style={**_LABEL, "marginBottom":"10px"}),
        html.Div(str(value), style={"fontSize":"30px","fontWeight":"700","color":color,
                                    "fontVariantNumeric":"tabular-nums","lineHeight":"1.1",
                                    "letterSpacing":"-0.5px"}),
        html.Div(sub, style={"fontSize":"12px","color":"#7090a8","marginTop":"6px"}) if sub else None,
    ], style={**_CARD,"padding":"22px 24px","minHeight":"112px"})


def _sector_fig(sector_exp: dict, height=200):
    if not sector_exp:
        return empty_fig(height=height, message="Aucune exposition sectorielle")
    sectors = list(sector_exp.keys())
    vals    = list(sector_exp.values())
    colors  = ["#4ade80" if v >= 0 else "#f87171" for v in vals]
    fig = go.Figure(go.Bar(
        x=vals, y=sectors, orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor=_BG, plot_bgcolor=_BG, font=_FONT, height=height,
        margin=dict(l=10, r=20, t=10, b=36),
        xaxis=dict(gridcolor=_GRID, ticksuffix="%", tickfont=dict(size=10, color="#7090a8"), zeroline=True, zerolinecolor="#243244"),
        yaxis=dict(gridcolor="rgba(0,0,0,0)", tickfont=dict(size=10, color="#c8d8e8")),
        showlegend=False,
    )
    return fig


def layout(dp=None):
    if dp is None:
        try:
            from dash import get_app
            dp = get_app().data_provider
        except Exception:
            pass

    # ── Données portfolio ──────────────────────────────────────────
    nav_df, weights = dp.get_portfolio() if dp else (pd.DataFrame(), {})
    if not isinstance(weights, dict):
        weights = {}

    kpis = dp.get_portfolio_kpis() if dp else {}

    nav_val  = kpis.get("nav", 0)
    nav_fmt  = f"€{nav_val/1e6:.1f}M" if nav_val else "—"
    tr_val   = kpis.get("total_ret", 0)
    tr_fmt   = f"{tr_val:+.2f}%" if tr_val else "—"
    tr_color = "#4ade80" if (tr_val or 0) >= 0 else "#f87171"
    n_longs  = kpis.get("n_longs", 0)
    n_shorts = kpis.get("n_shorts", 0)
    tickers  = dp.tickers if dp and hasattr(dp, "tickers") else []

    # ── Positions avec P&L ────────────────────────────────────────
    positions_rows = []
    sector_exposure: dict = {}

    try:
        from config.universe import TICKER_NAMES, SECTOR_MAP
    except Exception:
        TICKER_NAMES = {}; SECTOR_MAP = {}

    try:
        current_prices = dp.get_current_prices() if dp else {}
    except Exception:
        current_prices = {}

    # P&L calculé sur les fills stockés dans dp
    fills = getattr(dp, "_fills", [])

    for ticker, weight in weights.items():
        if abs(weight) < 1e-5:
            continue

        side      = "LONG" if weight > 0 else "SHORT"
        notional  = abs(weight) * nav_val
        curr_px   = current_prices.get(ticker)
        name      = TICKER_NAMES.get(ticker, ticker)
        sector    = SECTOR_MAP.get(ticker, "Other")

        # Exposition sectorielle (pondérée)
        sector_exposure[sector] = sector_exposure.get(sector, 0) + weight * 100

        # P&L estimé depuis les fills
        avg_fill = None
        qty      = 0
        for fill in fills:
            if fill.get("ticker") == ticker:
                avg_fill = fill.get("fill_price")
                qty      = fill.get("qty", 0)

        pnl_jpy = None
        pnl_pct = None
        if avg_fill and curr_px and qty:
            if side == "LONG":
                pnl_jpy = (curr_px - avg_fill) * qty
                pnl_pct = (curr_px / avg_fill - 1) * 100
            else:
                pnl_jpy = (avg_fill - curr_px) * qty
                pnl_pct = (avg_fill / curr_px - 1) * 100

        positions_rows.append({
            "ticker":    ticker,
            "name":      name,
            "sector":    sector,
            "side":      side,
            "weight":    f"{weight:.2%}",
            "notional":  f"€{notional/1e6:.1f}M" if notional else "—",
            "curr_px":   f"€{curr_px:,.0f}" if curr_px else "—",
            "pnl_jpy":   pnl_jpy,
            "pnl_pct":   pnl_pct,
        })

    # Exposition sectorielle nette
    sector_fig = _sector_fig(sector_exposure, height=220)

    # Equity curve
    equity_fig = empty_fig(height=240, message="Lancez un Backtest pour afficher la NAV")
    if nav_df is not None and not nav_df.empty and "nav" in nav_df.columns:
        equity_fig = line_chart(nav_df, "date", "nav",
                                title="NAV Equity Curve", color="#4a9eff", height=240)

    # ── Positions Table ───────────────────────────────────────────
    def pos_row(p):
        side_color  = "#4ade80" if p["side"] == "LONG" else "#f87171"
        pnl_j       = p.get("pnl_jpy")
        pnl_p       = p.get("pnl_pct")
        pnl_color   = "#4ade80" if pnl_j and pnl_j >= 0 else "#f87171" if pnl_j else "#7090a8"
        pnl_jpy_str = f"€{pnl_j:+,.0f}" if pnl_j is not None else "—"
        pnl_pct_str = f"{pnl_p:+.2f}%" if pnl_p is not None else "—"

        td = lambda content, color="#c8d8e8", align="left": html.Td(content, style={
            "fontSize":"11px","color":color,"padding":"7px 10px",
            "borderBottom":"1px solid #1a2030","textAlign":align,
            "fontVariantNumeric":"tabular-nums",
        })
        return html.Tr([
            td(p["ticker"], "#4a9eff"),
            td(p["name"][:22]),
            td(p["sector"], "#7090a8"),
            td(p["side"], side_color),
            td(p["weight"], align="right"),
            td(p["notional"], align="right"),
            td(p["curr_px"], align="right"),
            td(pnl_jpy_str, pnl_color, align="right"),
            td(pnl_pct_str, pnl_color, align="right"),
        ])

    th = lambda label, align="left": html.Th(label, style={
        "fontSize":"9px","color":"#5a7080","fontWeight":"600",
        "textTransform":"uppercase","letterSpacing":".06em",
        "padding":"6px 10px","borderBottom":"1px solid #1e2a38","textAlign":align,
    })
    positions_table = html.Table([
        html.Thead(html.Tr([
            th("Ticker"), th("Name"), th("Sector"),
            th("Side"), th("Weight","right"), th("Notional","right"),
            th("Price","right"), th("P&L (€)","right"), th("P&L (%)","right"),
        ])),
        html.Tbody([pos_row(p) for p in positions_rows] if positions_rows else [
            html.Tr([html.Td("Aucune position — lancez le pipeline ou un Backtest",
                             colSpan=9,
                             style={"color":"#5a7080","fontSize":"12px","padding":"20px 10px",
                                    "textAlign":"center"})])
        ]),
    ], style={"width":"100%","borderCollapse":"collapse"})

    # ── Total P&L ─────────────────────────────────────────────────
    total_pnl_jpy = sum(p["pnl_jpy"] for p in positions_rows
                        if p.get("pnl_jpy") is not None)
    total_pnl_str = f"€{total_pnl_jpy:+,.0f}" if positions_rows else "—"
    total_pnl_color = "#4ade80" if total_pnl_jpy >= 0 else "#f87171"

    # ── Expected annualised return from backtest ───────────────────
    exp_ret = "—"
    try:
        bt = dp._last_backtest
        if bt and bt.metrics:
            exp_ret = f"{bt.metrics.get('ann_return', 0):.2%}"
    except Exception:
        pass

    return html.Div([
        html.Div("Overview", style=_H1),

        # KPIs
        dbc.Row([
            dbc.Col(_kpi("NAV", nav_fmt, "#4a9eff", sub=f"{tr_fmt} période"), width=3),
            dbc.Col(_kpi("P&L Total", total_pnl_str, total_pnl_color if positions_rows else "#7090a8"), width=3),
            dbc.Col(_kpi("Long / Short", f"{n_longs}L  /  {n_shorts}S",
                         "#c8d8e8", sub=f"Gross: {abs(sum(weights.values())):.0%}"), width=3),
            dbc.Col(_kpi("Ann. Return (backtest)", exp_ret,
                         "#4ade80" if exp_ret != "—" and exp_ret[0] != "-" else "#f87171",
                         sub=f"{len(tickers)} tickers"), width=3),
        ], className="g-3", style={"marginBottom":"14px"}),

        # Equity curve + Sector exposure
        dbc.Row([
            dbc.Col(html.Div([
                html.Div("EQUITY CURVE", style=_LABEL),
                dcc.Graph(figure=equity_fig, config={"displayModeBar":False},
                          style={"height":"240px"}),
            ], style=_CARD), width=8),
            dbc.Col(html.Div([
                html.Div("EXPOSITION SECTORIELLE NETTE (%)", style=_LABEL),
                dcc.Graph(figure=sector_fig, config={"displayModeBar":False},
                          style={"height":"240px"}),
            ], style=_CARD), width=4),
        ], className="g-3", style={"marginBottom":"14px"}),

        # Positions table
        html.Div([
            html.Div([
                html.Span("POSITIONS ACTUELLES", style=_LABEL),
                html.Span(f"P&L total : {total_pnl_str}",
                          style={"fontSize":"12px","color":total_pnl_color,"fontWeight":"600",
                                 "marginLeft":"auto","fontVariantNumeric":"tabular-nums"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"10px"}),
            positions_table,
        ], style=_CARD),

        # Links
        dbc.Row([
            dbc.Col(html.A("📈 Backtest →", href="/backtest", style={"color":"#4a9eff","fontSize":"12px","textDecoration":"none","backgroundColor":"#111827","border":"1px solid #1e2a38","borderRadius":"6px","padding":"9px 16px","display":"block","textAlign":"center","fontWeight":"500"}), width=3),
            dbc.Col(html.A("💡 Idea Lab →", href="/ideas",   style={"color":"#4ade80","fontSize":"12px","textDecoration":"none","backgroundColor":"#111827","border":"1px solid #1e2a38","borderRadius":"6px","padding":"9px 16px","display":"block","textAlign":"center","fontWeight":"500"}), width=3),
            dbc.Col(html.A("🤖 AI Lab →",   href="/ai",      style={"color":"#c084fc","fontSize":"12px","textDecoration":"none","backgroundColor":"#111827","border":"1px solid #1e2a38","borderRadius":"6px","padding":"9px 16px","display":"block","textAlign":"center","fontWeight":"500"}), width=3),
            dbc.Col(html.A("⇄ Exécution →", href="/execution",style={"color":"#f0a500","fontSize":"12px","textDecoration":"none","backgroundColor":"#111827","border":"1px solid #1e2a38","borderRadius":"6px","padding":"9px 16px","display":"block","textAlign":"center","fontWeight":"500"}), width=3),
        ], className="g-3"),

    ], style={"paddingBottom":"30px"})