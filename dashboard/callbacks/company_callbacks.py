# dashboard/callbacks/company_callbacks.py — v2: formatage + comparaison sectorielle

import logging
import pandas as pd
import numpy as np
from dash import Input, Output, html
import plotly.graph_objects as go
from dashboard.components.charts import empty_fig

logger = logging.getLogger("CompanyCallbacks")

_BG   = "#0f141b"
_BG2  = "#0a0d12"
_TEXT = "#c8d8e8"
_MUTED= "#7090a8"
_GRID = "rgba(255,255,255,0.04)"
_FONT = dict(family="Inter, system-ui, sans-serif", color=_TEXT, size=11)
_BORDER = "1px solid #1e2a38"

# Moyennes sectorielles estimées (EURO STOXX 50, 2025-2026)
SECTOR_AVERAGES = {
    "Automotive":       {"P/E": 9.5,   "P/B": 0.9,  "ROE": 9.8,   "EV/EBITDA": 5.2,  "Div Yield": 2.8},
    "Technology":       {"P/E": 22.0,  "P/B": 3.5,  "ROE": 14.0,  "EV/EBITDA": 13.0, "Div Yield": 1.2},
    "Financials":       {"P/E": 11.0,  "P/B": 0.7,  "ROE": 7.2,   "EV/EBITDA": 8.0,  "Div Yield": 3.5},
    "Healthcare":       {"P/E": 28.0,  "P/B": 2.8,  "ROE": 10.5,  "EV/EBITDA": 14.0, "Div Yield": 1.5},
    "Materials":        {"P/E": 14.0,  "P/B": 1.2,  "ROE": 9.0,   "EV/EBITDA": 7.5,  "Div Yield": 2.5},
    "Industrials":      {"P/E": 18.0,  "P/B": 1.8,  "ROE": 10.0,  "EV/EBITDA": 10.0, "Div Yield": 2.0},
    "Consumer":         {"P/E": 25.0,  "P/B": 4.0,  "ROE": 16.0,  "EV/EBITDA": 12.0, "Div Yield": 1.0},
    "Consumer Staples": {"P/E": 20.0,  "P/B": 2.0,  "ROE": 11.0,  "EV/EBITDA": 9.0,  "Div Yield": 2.2},
    "Telecom":          {"P/E": 14.0,  "P/B": 1.5,  "ROE": 11.0,  "EV/EBITDA": 6.5,  "Div Yield": 3.8},
    "Real Estate":      {"P/E": 20.0,  "P/B": 1.3,  "ROE": 7.0,   "EV/EBITDA": 18.0, "Div Yield": 3.0},
    "Transport":        {"P/E": 16.0,  "P/B": 1.0,  "ROE": 8.5,   "EV/EBITDA": 7.0,  "Div Yield": 2.5},
    "Utilities":        {"P/E": 16.0,  "P/B": 0.9,  "ROE": 5.5,   "EV/EBITDA": 8.0,  "Div Yield": 3.2},
    "Trading":          {"P/E": 8.0,   "P/B": 0.8,  "ROE": 12.0,  "EV/EBITDA": 5.0,  "Div Yield": 3.5},
}


def _fmt_number(v, kind="auto"):
    """Formate un nombre selon son contexte."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    try:
        v = float(v)
    except (ValueError, TypeError):
        return str(v)

    if kind == "market_cap":
        if abs(v) >= 1e12:  return f"€{v/1e12:.2f}T"
        if abs(v) >= 1e9:   return f"€{v/1e9:.1f}B"
        if abs(v) >= 1e6:   return f"€{v/1e6:.0f}M"
        return f"€{v:,.0f}"

    if kind == "price":
        return f"€{v:,.0f}"

    if kind == "pct":
        return f"{v*100:.2f}%"

    if kind == "beta":
        return f"{v:.3f}"

    if kind == "ratio":
        if abs(v) > 100:  return "—"   # valeur aberrante
        return f"{v:.2f}x"

    if kind == "multiple":
        return f"{v:.1f}x"

    if kind == "count":
        return f"{v:,.0f}"

    return f"{v:.2f}"


def _get_sector(ticker):
    try:
        from config.universe import SECTOR_MAP
        return SECTOR_MAP.get(ticker, "Unknown")
    except Exception:
        return "Unknown"


def _color_vs_sector(company_val, sector_val, metric, higher_is_better=True):
    """Couleur comparative : vert si meilleur que secteur, rouge sinon."""
    if company_val is None or sector_val is None:
        return _MUTED
    try:
        cv = float(company_val)
        sv = float(sector_val)
        if cv == 0 or sv == 0:
            return _MUTED
        better = cv > sv if higher_is_better else cv < sv
        if abs(cv - sv) / max(abs(sv), 1e-8) < 0.05:
            return "#f0a500"   # quasi-égal → orange
        return "#4ade80" if better else "#f87171"
    except Exception:
        return _MUTED


def _make_price_fig(df, ticker, height=360):
    if df is None or df.empty:
        return empty_fig(height=height, message=f"Pas de données pour {ticker}")
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    if "close" not in df.columns:
        return empty_fig(height=height, message="Colonne close introuvable")
    if "date" not in df.columns:
        df = df.reset_index()
        cols = [c for c in df.columns if "date" in c.lower()]
        if cols: df = df.rename(columns={cols[0]: "date"})
        else:    df["date"] = range(len(df))

    # Calcul variation
    start_p = float(df["close"].iloc[0])
    end_p   = float(df["close"].iloc[-1])
    chg_pct = (end_p / start_p - 1) * 100
    line_color = "#4ade80" if chg_pct >= 0 else "#f87171"
    fill_color = "rgba(74,222,128,0.06)" if chg_pct >= 0 else "rgba(248,113,113,0.06)"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["close"], name="Prix", mode="lines",
        line=dict(color=line_color, width=1.8),
        fill="tozeroy", fillcolor=fill_color,
        hovertemplate="%{x|%Y-%m-%d}<br><b>€%{y:,.0f}</b><extra></extra>",
    ))

    if "volume" in df.columns:
        fig.add_trace(go.Bar(
            x=df["date"], y=df["volume"], name="Vol", yaxis="y2",
            marker=dict(color=f"rgba(74,158,255,0.12)", line=dict(width=0)),
            hovertemplate="%{x|%Y-%m-%d}<br>Vol: %{y:,.0f}<extra></extra>",
        ))

    chg_str = f"+{chg_pct:.1f}%" if chg_pct >= 0 else f"{chg_pct:.1f}%"
    fig.update_layout(
        paper_bgcolor=_BG, plot_bgcolor=_BG, font=_FONT, height=height,
        margin=dict(l=50, r=60, t=44, b=36), showlegend=False,
        hovermode="x unified",
        title=dict(
            text=f"{ticker}   €{end_p:,.0f}   <span style='color:{line_color}'>{chg_str} (période)</span>",
            font=dict(size=12, color=_TEXT), x=0, pad=dict(l=0),
        ),
        xaxis=dict(gridcolor=_GRID, linecolor="#1e2a38",
                   tickfont=dict(size=10, color=_MUTED), zeroline=False),
        yaxis=dict(gridcolor=_GRID, linecolor="#1e2a38",
                   tickfont=dict(size=10, color=_MUTED), zeroline=False,
                   tickprefix="€", tickformat=",.0f"),
        yaxis2=dict(overlaying="y", side="right", showgrid=False, zeroline=False,
                    tickfont=dict(size=9, color="#2a3d50"),
                    range=[0, df["volume"].max()*6] if "volume" in df.columns else [0,1]),
    )
    return fig


def _row(label, company_val, sector_val=None, fmt="auto", higher_better=True,
          company_raw=None, sector_raw=None):
    """Ligne de métrique : label | valeur company | valeur secteur | indicateur."""

    color = _color_vs_sector(company_raw or company_val,
                              sector_raw or sector_val, label, higher_better)

    label_cell = html.Td(label, style={
        "fontSize": "11px", "color": _MUTED,
        "padding": "6px 10px 6px 0", "whiteSpace": "nowrap",
        "borderBottom": _BORDER,
    })
    val_cell = html.Td(company_val, style={
        "fontSize": "12px", "color": _TEXT, "fontWeight": "500",
        "padding": "6px 12px", "textAlign": "right",
        "borderBottom": _BORDER, "fontVariantNumeric": "tabular-nums",
    })

    if sector_val is not None:
        sec_cell = html.Td(sector_val, style={
            "fontSize": "11px", "color": "#5a7080",
            "padding": "6px 8px", "textAlign": "right",
            "borderBottom": _BORDER, "fontVariantNumeric": "tabular-nums",
        })
        ind_cell = html.Td("▲" if color == "#4ade80" else ("▼" if color == "#f87171" else "◆"),
                            style={"color": color, "fontSize": "10px",
                                   "padding": "6px 4px", "borderBottom": _BORDER,
                                   "textAlign": "center"})
        return html.Tr([label_cell, val_cell, sec_cell, ind_cell])
    return html.Tr([label_cell, val_cell])


def _make_fund_panel(info: dict, ticker: str) -> html.Div:
    sector = _get_sector(ticker)
    sa     = SECTOR_AVERAGES.get(sector, {})

    # --- Extraction des métriques ---
    pe         = info.get("trailingPE")
    pb         = info.get("priceToBook")
    ev_ebitda  = info.get("enterpriseToEbitda")
    roe        = info.get("returnOnEquity")         # décimal
    roa        = info.get("returnOnAssets")         # décimal
    gross_m    = info.get("grossMargins")           # décimal
    oper_m     = info.get("operatingMargins")       # décimal
    net_m      = info.get("profitMargins")          # décimal
    mkt_cap    = info.get("marketCap")
    beta       = info.get("beta")
    div_yield  = info.get("dividendYield")          # décimal
    hi52       = info.get("fiftyTwoWeekHigh")
    lo52       = info.get("fiftyTwoWeekLow")
    rev_growth = info.get("revenueGrowth")
    eps        = info.get("trailingEps")
    debt_eq    = info.get("debtToEquity")           # en %
    curr_ratio = info.get("currentRatio")
    employees  = info.get("fullTimeEmployees")
    name       = info.get("longName") or info.get("shortName") or ticker

    def safe_pct(v):
        if v is None or (isinstance(v, float) and np.isnan(v)): return None
        return float(v)

    def safe_val(v):
        if v is None: return None
        try:
            f = float(v)
            return None if np.isnan(f) else f
        except Exception:
            return None

    # Header
    header = html.Div([
        html.Div(name, style={"fontSize": "13px", "fontWeight": "600",
                               "color": _TEXT, "marginBottom": "2px"}),
        html.Div([
            html.Span(ticker, style={"color": _MUTED, "fontSize": "11px",
                                     "marginRight": "12px"}),
            html.Span(sector, style={
                "backgroundColor": "rgba(74,158,255,.12)",
                "color": "#4a9eff", "border": "1px solid rgba(74,158,255,.2)",
                "borderRadius": "4px", "padding": "1px 8px",
                "fontSize": "10px", "fontWeight": "600",
            }),
        ]),
    ], style={"marginBottom": "14px"})

    # Market Cap + 52W
    summary_row = html.Div([
        html.Div([
            html.Div("Market Cap", style={"fontSize": "9px", "color": _MUTED,
                                           "textTransform": "uppercase", "letterSpacing": ".06em"}),
            html.Div(_fmt_number(mkt_cap, "market_cap"),
                     style={"fontSize": "18px", "fontWeight": "700", "color": _TEXT}),
        ], style={"flex": "1"}),
        html.Div([
            html.Div("52W Range", style={"fontSize": "9px", "color": _MUTED,
                                          "textTransform": "uppercase", "letterSpacing": ".06em"}),
            html.Div(
                f"{_fmt_number(lo52,'price')} — {_fmt_number(hi52,'price')}",
                style={"fontSize": "12px", "color": "#94b8cc"},
            ),
        ], style={"flex": "1"}),
        html.Div([
            html.Div("EPS (TTM)", style={"fontSize": "9px", "color": _MUTED,
                                          "textTransform": "uppercase", "letterSpacing": ".06em"}),
            html.Div(_fmt_number(eps, "price") if eps else "—",
                     style={"fontSize": "12px", "color": "#94b8cc"}),
        ], style={"flex": "1"}),
    ], style={"display": "flex", "gap": "16px", "marginBottom": "16px",
              "padding": "10px 12px", "backgroundColor": _BG2,
              "borderRadius": "6px", "border": _BORDER})

    # En-têtes colonnes
    col_headers = html.Thead(html.Tr([
        html.Th("MÉTRIQUE",  style={"fontSize":"9px","color":_MUTED,"fontWeight":"600",
                                    "textTransform":"uppercase","letterSpacing":".06em",
                                    "padding":"4px 0","borderBottom":_BORDER}),
        html.Th("COMPANY",   style={"fontSize":"9px","color":"#4a9eff","fontWeight":"600",
                                    "textTransform":"uppercase","letterSpacing":".06em",
                                    "padding":"4px 12px","textAlign":"right","borderBottom":_BORDER}),
        html.Th(f"{sector[:10]}…" if len(sector)>12 else f"SECTEUR",
                style={"fontSize":"9px","color":_MUTED,"fontWeight":"600",
                       "textTransform":"uppercase","letterSpacing":".06em",
                       "padding":"4px 8px","textAlign":"right","borderBottom":_BORDER}),
        html.Th("±", style={"fontSize":"9px","color":_MUTED,"fontWeight":"600",
                             "textTransform":"uppercase","padding":"4px 4px",
                             "textAlign":"center","borderBottom":_BORDER}),
    ]))

    def make_rows():
        rows = []
        # P/E
        pe_v  = safe_val(pe)
        pe_s  = sa.get("P/E")
        if pe_v and 0 < pe_v < 200:
            rows.append(_row("P/E (trailing)", f"{pe_v:.1f}x",
                             f"{pe_s:.1f}x" if pe_s else None,
                             higher_better=False,
                             company_raw=pe_v, sector_raw=pe_s))
        # P/B
        pb_v = safe_val(pb)
        pb_s = sa.get("P/B")
        if pb_v and pb_v > 0:
            rows.append(_row("P/B", f"{pb_v:.2f}x",
                             f"{pb_s:.2f}x" if pb_s else None,
                             higher_better=False,
                             company_raw=pb_v, sector_raw=pb_s))
        # EV/EBITDA
        ev_v = safe_val(ev_ebitda)
        if ev_v and 0 < ev_v < 200:
            rows.append(_row("EV/EBITDA", f"{ev_v:.1f}x",
                             f"{sa.get('EV/EBITDA', 0):.1f}x" if sa.get("EV/EBITDA") else None,
                             higher_better=False,
                             company_raw=ev_v, sector_raw=sa.get("EV/EBITDA")))
        # ROE
        roe_v = safe_val(roe)
        roe_s = sa.get("ROE", 0) / 100 if sa.get("ROE") else None
        if roe_v is not None:
            rows.append(_row("ROE", f"{roe_v*100:.1f}%",
                             f"{sa.get('ROE', 0):.1f}%" if sa.get("ROE") else None,
                             higher_better=True,
                             company_raw=roe_v, sector_raw=roe_s))
        # ROA
        roa_v = safe_val(roa)
        if roa_v is not None:
            rows.append(_row("ROA", f"{roa_v*100:.1f}%", None, higher_better=True))
        # Marges
        gm_v = safe_val(gross_m)
        if gm_v is not None:
            rows.append(_row("Marge Brute", f"{gm_v*100:.1f}%", None, higher_better=True))
        om_v = safe_val(oper_m)
        if om_v is not None:
            rows.append(_row("Marge Opér.", f"{om_v*100:.1f}%", None, higher_better=True))
        nm_v = safe_val(net_m)
        if nm_v is not None:
            rows.append(_row("Marge Nette", f"{nm_v*100:.1f}%", None, higher_better=True))
        # Beta
        b_v = safe_val(beta)
        if b_v is not None and 0 < abs(b_v) < 10:
            rows.append(_row("Beta", f"{b_v:.3f}", "1.000",
                             higher_better=False,
                             company_raw=abs(b_v-1), sector_raw=0))
        # Dividende
        dy_v = safe_val(div_yield)
        dy_s = sa.get("Div Yield", 0) / 100 if sa.get("Div Yield") else None
        if dy_v is not None and 0 < dy_v < 0.5:
            rows.append(_row("Div. Yield", f"{dy_v*100:.2f}%",
                             f"{sa.get('Div Yield', 0):.1f}%" if sa.get("Div Yield") else None,
                             higher_better=True,
                             company_raw=dy_v, sector_raw=dy_s))
        # Croissance revenus
        rg_v = safe_val(rev_growth)
        if rg_v is not None:
            rows.append(_row("Rev. Growth", f"{rg_v*100:+.1f}%", None, higher_better=True))
        # Dette/Equity
        de_v = safe_val(debt_eq)
        if de_v is not None and de_v >= 0:
            rows.append(_row("Debt/Equity", f"{de_v:.0f}%", None, higher_better=False))
        # Ratio courant
        cr_v = safe_val(curr_ratio)
        if cr_v is not None:
            rows.append(_row("Current Ratio", f"{cr_v:.2f}x", "1.00x",
                             higher_better=True,
                             company_raw=cr_v, sector_raw=1.0))
        # Employés
        if employees:
            rows.append(_row("Employés", f"{int(employees):,}", None))

        return rows

    table = html.Table([
        col_headers,
        html.Tbody(make_rows()),
    ], style={"width": "100%", "borderCollapse": "collapse"})

    return html.Div([
        header,
        summary_row,
        table,
        html.Div(
            f"Secteur : {sector} — moyennes sectorielles estimées (EURO STOXX 50, 2025)",
            style={"fontSize": "9px", "color": "#2e4050", "marginTop": "10px",
                   "textAlign": "right"},
        ),
    ])


def register_company_callbacks(app, dp):

    @app.callback(
        Output("company-price-chart", "figure"),
        Output("company-fund-table",  "children"),
        Input("company-ticker-dd",    "value"),
    )
    def update_company(ticker):
        if not ticker:
            return empty_fig(message="Sélectionner un ticker"), html.Div()

        try:
            prices    = dp.get_price_history(ticker)
            price_fig = _make_price_fig(prices, ticker, height=360)
        except Exception as e:
            logger.error(f"Price load {ticker}: {e}")
            price_fig = empty_fig(message=f"Erreur prix : {e}", height=360)

        try:
            info  = dp.get_ticker_info(ticker)
            panel = _make_fund_panel(info, ticker)
        except Exception as e:
            logger.error(f"Fund load {ticker}: {e}")
            panel = html.Div(f"Erreur fondamentaux : {e}",
                             style={"color": "#f87171", "fontSize": "11px"})

        return price_fig, panel