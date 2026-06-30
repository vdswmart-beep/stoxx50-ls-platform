# dashboard/pages/idea_lab.py — Click → fiche complète + exécution IBKR

from dash import html, dcc, get_app, callback, Input, Output, State, ctx
import dash_bootstrap_components as dbc
import pandas as pd
import numpy as np

_CARD  = {"backgroundColor":"#0f141b","border":"1px solid #1e2a38","borderRadius":"8px","padding":"16px","marginBottom":"14px"}
_LABEL = {"fontSize":"10px","color":"#7eb8d8","textTransform":"uppercase","letterSpacing":".08em","marginBottom":"10px","fontWeight":"600"}
_H1    = {"fontSize":"11px","color":"#7eb8d8","textTransform":"uppercase","letterSpacing":".1em","marginBottom":"18px","fontWeight":"600"}


def _conviction_badge(conv):
    colors = {"HIGH":("#4a9eff","rgba(74,158,255,.12)"),
               "MEDIUM":("#f0a500","rgba(240,165,0,.12)"),
               "LOW":("#7090a8","rgba(112,144,168,.12)")}
    c, bg = colors.get(conv, ("#7090a8","transparent"))
    return html.Span(conv, style={"color":c,"backgroundColor":bg,"border":f"1px solid {c}",
                                   "borderRadius":"4px","padding":"1px 8px","fontSize":"10px","fontWeight":"700"})


def _side_badge(side):
    if side == "LONG":
        return html.Span("LONG", style={"color":"#4ade80","backgroundColor":"rgba(74,222,128,.12)",
                                         "border":"1px solid rgba(74,222,128,.3)",
                                         "borderRadius":"4px","padding":"2px 10px","fontSize":"11px","fontWeight":"700"})
    return html.Span("SHORT", style={"color":"#f87171","backgroundColor":"rgba(248,113,113,.12)",
                                      "border":"1px solid rgba(248,113,113,.3)",
                                      "borderRadius":"4px","padding":"2px 10px","fontSize":"11px","fontWeight":"700"})


def _mini_card(idea, is_selected=False):
    """Carte compacte dans la liste — cliquable."""
    score = float(idea.get("score", 50))
    side  = idea.get("side", "LONG")
    bar_color = "#4ade80" if side == "LONG" else "#f87171"
    border = "1px solid #4a9eff" if is_selected else "1px solid #1e2a38"

    return html.Div([
        html.Div([
            html.Span(idea.get("ticker",""), style={"fontSize":"13px","fontWeight":"700","color":"#e8f2ff","marginRight":"8px"}),
            _side_badge(side),
            html.Span(f"{score:.0f}/100", style={"fontSize":"11px","color":"#5a7080","marginLeft":"auto"}),
        ], style={"display":"flex","alignItems":"center","marginBottom":"6px"}),

        # Score bar
        html.Div([html.Div(style={"height":"3px","borderRadius":"2px","backgroundColor":bar_color,"width":f"{int(score)}%"})],
                 style={"backgroundColor":"#1a2436","borderRadius":"2px","height":"3px","marginBottom":"6px"}),

        html.Div([
            _conviction_badge(idea.get("conviction","LOW")),
            html.Span(idea.get("duration","—"), style={"fontSize":"10px","color":"#5a7080","marginLeft":"8px"}),
            html.Span(idea.get("sector",""), style={"fontSize":"10px","color":"#5a7080","marginLeft":"8px"}),
        ], style={"display":"flex","alignItems":"center","marginBottom":"4px"}),

        html.Div(idea.get("name","")[:35], style={"fontSize":"11px","color":"#7090a8"}),

    ], id={"type":"idea-card","ticker":idea.get("ticker","")},
       n_clicks=0,
       style={**_CARD,"cursor":"pointer","border":border,"marginBottom":"8px","padding":"12px 14px"})


def _full_detail(idea, dp):
    """Fiche complète d'une idée."""
    ticker = idea.get("ticker","")
    side   = idea.get("side","LONG")
    score  = float(idea.get("score",50))
    side_color = "#4ade80" if side=="LONG" else "#f87171"

    # Prix et graphique
    try:
        price_df = dp.get_price_history(ticker)
        from dashboard.components.charts import line_chart, empty_fig
        import plotly.graph_objects as go

        if not price_df.empty and "close" in price_df.columns:
            start_p = float(price_df["close"].iloc[0])
            end_p   = float(price_df["close"].iloc[-1])
            chg_pct = (end_p/start_p - 1)*100
            lc = "#4ade80" if chg_pct >= 0 else "#f87171"

            fig = go.Figure()
            date_col = "date" if "date" in price_df.columns else price_df.columns[0]
            fig.add_trace(go.Scatter(
                x=price_df[date_col], y=price_df["close"],
                mode="lines", line=dict(color=lc, width=1.8),
                fill="tozeroy", fillcolor=f"rgba({'74,222,128' if chg_pct>=0 else '248,113,113'},0.06)",
                name="Prix",
            ))
            _BG = "#0f141b"; _GRID = "rgba(255,255,255,0.04)"
            fig.update_layout(
                paper_bgcolor=_BG, plot_bgcolor=_BG, height=220,
                margin=dict(l=50,r=20,t=30,b=30), showlegend=False,
                title=dict(text=f"{ticker}  €{end_p:,.0f}  {chg_pct:+.1f}%",
                           font=dict(size=11,color="#7090a8"), x=0),
                xaxis=dict(gridcolor=_GRID,tickfont=dict(size=9,color="#7090a8")),
                yaxis=dict(gridcolor=_GRID,tickprefix="€",tickformat=",.0f",tickfont=dict(size=9,color="#7090a8")),
                font=dict(family="Inter, system-ui, sans-serif"),
            )
            price_chart = dcc.Graph(figure=fig, config={"displayModeBar":False})
        else:
            price_chart = html.Div("Prix non disponible", style={"color":"#5a7080","fontSize":"11px"})
    except Exception as e:
        price_chart = html.Div(f"Erreur prix: {e}", style={"color":"#f87171","fontSize":"11px"})

    # Fondamentaux
    try:
        info = dp.get_ticker_info(ticker)
        def f(v, fmt="pct"):
            if v is None or (isinstance(v,float) and np.isnan(v)): return "—"
            v = float(v)
            if fmt=="pct": return f"{v*100:.1f}%"
            if fmt=="x":   return f"{v:.1f}x" if 0<v<300 else "—"
            if fmt=="n":   return f"€{v/1e9:.0f}B" if v>1e9 else f"€{v/1e6:.0f}M"
            if fmt=="b":   return f"{v:.3f}"
            return f"{v:.2f}"
    except Exception:
        info = {}
        def f(v, fmt="pct"): return "—"

    def metric_row(label, val, color="#c8d8e8"):
        return html.Div([
            html.Span(label, style={"color":"#7090a8","fontSize":"10px","flex":"1"}),
            html.Span(val,   style={"color":color,"fontSize":"11px","fontWeight":"600","fontVariantNumeric":"tabular-nums"}),
        ], style={"display":"flex","justifyContent":"space-between",
                  "padding":"5px 0","borderBottom":"1px solid #1a2030"})

    # Facteurs
    mom_12m = idea.get("mom_12m", 0) or 0
    mom_6m  = idea.get("mom_6m", 0)  or 0
    vol_63d = idea.get("vol_63d", 0) or 0
    z_mom   = idea.get("z_momentum", 0) or 0
    z_qual  = idea.get("z_quality", 0)  or 0
    z_val   = idea.get("z_value", 0)    or 0
    z_sec   = idea.get("z_sector", 0)   or 0

    def z_color(z): return "#4ade80" if z>0.5 else "#f87171" if z<-0.5 else "#f0a500"

    # Secteur
    try:
        from config.universe import SECTOR_MAP
        sector = SECTOR_MAP.get(ticker, "Unknown")
    except Exception:
        sector = idea.get("sector","Unknown")

    return html.Div([
        # Header
        html.Div([
            html.Div([
                html.Span(ticker, style={"fontSize":"20px","fontWeight":"700","color":"#e8f2ff","marginRight":"12px"}),
                _side_badge(side),
                html.Span("  ", style={"marginLeft":"8px"}),
                _conviction_badge(idea.get("conviction","LOW")),
                html.Span(f" Score : {score:.0f}/100",
                          style={"fontSize":"12px","color":"#7090a8","marginLeft":"12px"}),
                html.Span(f"Durée cible : {idea.get('duration','—')}",
                          style={"fontSize":"11px","color":"#5a7080","marginLeft":"16px"}),
            ], style={"display":"flex","alignItems":"center","flexWrap":"wrap","gap":"4px"}),
            html.Div(idea.get("name",""), style={"fontSize":"12px","color":"#7090a8","marginTop":"4px"}),
        ], style={"marginBottom":"14px"}),

        dbc.Row([
            # Colonne gauche : prix + fondamentaux
            dbc.Col([
                # Prix
                html.Div([price_chart], style={**_CARD,"padding":"12px"}),
                # Fondamentaux
                html.Div([
                    html.Div("FONDAMENTAUX vs SECTEUR", style=_LABEL),
                    html.Div([
                        html.Div([
                            metric_row("P/E",            f(info.get("trailingPE"),   "x")),
                            metric_row("P/B",            f(info.get("priceToBook"),  "x")),
                            metric_row("EV/EBITDA",      f(info.get("enterpriseToEbitda"), "x")),
                            metric_row("ROE",            f(info.get("returnOnEquity"), "pct")),
                            metric_row("ROA",            f(info.get("returnOnAssets"), "pct")),
                            metric_row("Marge opér.",    f(info.get("operatingMargins"), "pct")),
                            metric_row("Marge nette",    f(info.get("profitMargins"), "pct")),
                            metric_row("Rev. Growth",    f(info.get("revenueGrowth"), "pct")),
                            metric_row("Beta",           f(info.get("beta"), "b")),
                            metric_row("Div. Yield",     f(info.get("dividendYield"), "pct")),
                            metric_row("Market Cap",     f(info.get("marketCap"), "n")),
                        ], style={"flex":"1"}),
                    ], style={"display":"flex","gap":"16px"}),
                ], style=_CARD),
            ], width=7),

            # Colonne droite : signaux + exécution
            dbc.Col([
                # Signaux factoriels
                html.Div([
                    html.Div("SIGNAUX FACTORIELS", style=_LABEL),
                    metric_row("Momentum 12M",    f"{mom_12m*100:+.1f}%",
                               "#4ade80" if mom_12m>0 else "#f87171"),
                    metric_row("Momentum 6M",     f"{mom_6m*100:+.1f}%",
                               "#4ade80" if mom_6m>0 else "#f87171"),
                    metric_row("Volatilité 63j",  f"{vol_63d*100:.1f}%", "#94b8cc"),
                    html.Div(style={"height":"8px"}),
                    html.Div("Z-SCORES (vs univers)", style={**_LABEL,"fontSize":"9px","marginBottom":"6px"}),
                    metric_row("Z Momentum",   f"{z_mom:+.3f}", z_color(z_mom)),
                    metric_row("Z Qualité",    f"{z_qual:+.3f}", z_color(z_qual)),
                    metric_row("Z Valeur",     f"{z_val:+.3f}", z_color(z_val)),
                    metric_row("Z Secteur",    f"{z_sec:+.3f}", z_color(z_sec)),
                    html.Div(style={"height":"8px"}),
                    html.Div("SECTEUR", style={**_LABEL,"fontSize":"9px","marginBottom":"4px"}),
                    html.Div(sector, style={"fontSize":"11px","color":"#94b8cc"}),
                ], style=_CARD),

                # Thèse
                html.Div([
                    html.Div("THÈSE D'INVESTISSEMENT", style=_LABEL),
                    html.Div(idea.get("thesis",""), style={"fontSize":"11px","color":"#94b8cc","lineHeight":"1.6","marginBottom":"10px"}),
                    html.Div("CATALYSEURS", style={**_LABEL,"fontSize":"9px","marginBottom":"4px"}),
                    html.Ul([html.Li(c, style={"fontSize":"11px","color":"#4ade80","marginBottom":"2px"})
                             for c in (idea.get("catalysts") if isinstance(idea.get("catalysts"),list)
                                       else [str(idea.get("catalysts","—"))])],
                            style={"paddingLeft":"14px","marginBottom":"8px"}),
                    html.Div("RISQUES", style={**_LABEL,"fontSize":"9px","marginBottom":"4px"}),
                    html.Ul([html.Li(r, style={"fontSize":"11px","color":"#f87171","marginBottom":"2px"})
                             for r in (idea.get("risks") if isinstance(idea.get("risks"),list)
                                       else [str(idea.get("risks","—"))])],
                            style={"paddingLeft":"14px"}),
                ], style=_CARD),

                # Boutons d'exécution
                html.Div([
                    html.Div("EXÉCUTION IBKR PAPER", style={**_LABEL,"color":"#4a9eff"}),
                    html.Div([
                        html.Div([
                            html.Div("QUANTITÉ", style={**_LABEL,"fontSize":"9px","marginBottom":"4px"}),
                            dcc.Input(id="idea-exec-qty", type="number", value=100, min=1, step=1,
                                      style={"backgroundColor":"#0a0d12","color":"#c8d8e8","border":"1px solid #1e2a38",
                                             "borderRadius":"4px","padding":"6px 10px","fontSize":"12px","width":"100%"}),
                        ], style={"flex":"1"}),
                        html.Div([
                            html.Div("TYPE", style={**_LABEL,"fontSize":"9px","marginBottom":"4px"}),
                            dcc.Dropdown(id="idea-exec-type",
                                        options=[{"label":"Market","value":"MARKET"},
                                                 {"label":"Limit","value":"LIMIT"}],
                                        value="MARKET", clearable=False,
                                        style={"backgroundColor":"#0a0d12","border":"1px solid #1e2a38",
                                               "fontSize":"12px","color":"#c8d8e8"}),
                        ], style={"flex":"1"}),
                    ], style={"display":"flex","gap":"10px","marginBottom":"10px"}),

                    html.Button(
                        f"▶  Exécuter {side} {ticker} → IBKR",
                        id="idea-exec-btn",
                        style={"backgroundColor":side_color if side=="LONG" else "#1a3a5c",
                               "color":"#0a0d12" if side=="LONG" else "#f87171",
                               "border":f"1px solid {side_color}","borderRadius":"6px",
                               "padding":"10px 20px","fontSize":"13px","fontWeight":"700",
                               "cursor":"pointer","width":"100%","letterSpacing":".04em"},
                    ),
                    dcc.Store(id="idea-exec-ticker", data=ticker),
                    dcc.Store(id="idea-exec-side",   data=side),
                    html.Div(id="idea-exec-status",
                             style={"marginTop":"8px","fontSize":"12px","minHeight":"18px"}),

                    # Stop-loss reminder
                    html.Div([
                        html.Span("⚠ Stop-loss automatique à ",
                                  style={"fontSize":"10px","color":"#5a7080"}),
                        html.Span("-6.0%", style={"fontSize":"10px","color":"#f87171","fontWeight":"700"}),
                        html.Span(" par position", style={"fontSize":"10px","color":"#5a7080"}),
                    ], style={"marginTop":"8px"}),
                ], style=_CARD),
            ], width=5),
        ], className="g-3"),
    ], style={**_CARD,"borderColor":"#4a9eff","marginTop":"6px"})


def layout():
    app = get_app()
    dp  = app.data_provider

    try:
        df = dp.get_trade_ideas()
        if df is None or not hasattr(df,"empty") or df.empty:
            ideas = []
        else:
            ideas = df.to_dict("records")
    except Exception:
        ideas = []

    longs  = [i for i in ideas if i.get("side")=="LONG"]
    shorts = [i for i in ideas if i.get("side")=="SHORT"]
    n_long  = len(longs)
    n_short = len(shorts)
    n_high  = len([i for i in ideas if i.get("conviction")=="HIGH"])

    # KPIs
    kpis = dbc.Row([
        dbc.Col(html.Div([html.Div("LONG IDEAS",style=_LABEL),html.Div(str(n_long),style={"fontSize":"26px","fontWeight":"700","color":"#4ade80"})],style={**_CARD,"padding":"14px 18px"}),width=3),
        dbc.Col(html.Div([html.Div("SHORT IDEAS",style=_LABEL),html.Div(str(n_short),style={"fontSize":"26px","fontWeight":"700","color":"#f87171"})],style={**_CARD,"padding":"14px 18px"}),width=3),
        dbc.Col(html.Div([html.Div("HIGH CONVICTION",style=_LABEL),html.Div(str(n_high),style={"fontSize":"26px","fontWeight":"700","color":"#4a9eff"})],style={**_CARD,"padding":"14px 18px"}),width=3),
        dbc.Col(html.Div([html.Div("MARKET REGIME",style=_LABEL),html.Div("Neutral",style={"fontSize":"26px","fontWeight":"700","color":"#f0a500"})],style={**_CARD,"padding":"14px 18px"}),width=3),
    ], className="g-3", style={"marginBottom":"14px"})

    # Instructions
    hint = html.Div(
        "💡 Clique sur une carte pour afficher la fiche complète et exécuter l'ordre.",
        style={"fontSize":"11px","color":"#5a7080","marginBottom":"10px"}
    )

    # Listes Long / Short
    long_col  = [_mini_card(i) for i in longs[:25]]
    short_col = [_mini_card(i) for i in shorts[:25]]

    lists = dbc.Row([
        dbc.Col([html.Div("LONG CANDIDATES", style={**_LABEL,"color":"#4ade80"})] +
                (long_col or [html.Div("Aucune idée LONG",style={"color":"#5a7080","fontSize":"12px"})]),
                width=6),
        dbc.Col([html.Div("SHORT CANDIDATES",style={**_LABEL,"color":"#f87171"})] +
                (short_col or [html.Div("Aucune idée SHORT",style={"color":"#5a7080","fontSize":"12px"})]),
                width=6),
    ], className="g-3")

    return html.Div([
        html.Div("Idea Lab", style=_H1),
        kpis,
        hint,
        lists,
        # Panel de détail (caché jusqu'au clic)
        html.Div(id="idea-detail-panel"),
        # Store pour l'idée sélectionnée
        dcc.Store(id="idea-selected-store"),
    ], style={"paddingBottom":"30px"})