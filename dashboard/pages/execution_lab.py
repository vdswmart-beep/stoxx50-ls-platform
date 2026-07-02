# dashboard/pages/execution_lab.py — pleine largeur, couleurs visibles

from dash import html, dcc, dash_table
import dash_bootstrap_components as dbc

_CARD  = {"backgroundColor": "#0f141b", "border": "1px solid #1e2a38",
           "borderRadius": "8px", "padding": "16px", "marginBottom": "14px"}
_LABEL = {"fontSize": "10px", "color": "#7eb8d8", "textTransform": "uppercase",
           "letterSpacing": ".08em", "marginBottom": "6px", "fontWeight": "600"}
_H1    = {"fontSize": "11px", "color": "#7eb8d8", "textTransform": "uppercase",
           "letterSpacing": ".1em", "marginBottom": "18px", "fontWeight": "600"}
_DD    = {"backgroundColor": "#0a0d12", "color": "#c8d8e8",
           "border": "1px solid #1e2a38", "borderRadius": "4px", "fontSize": "12px"}
_INP   = {"backgroundColor": "#0a0d12", "color": "#c8d8e8",
           "border": "1px solid #1e2a38", "borderRadius": "4px",
           "padding": "7px 10px", "fontSize": "12px", "width": "100%"}


def _btn(label, bid, color="#4a9eff", outline=False):
    return html.Button(label, id=bid, style={
        "backgroundColor": "transparent" if outline else color,
        "color": color if outline else "#fff",
        "border": f"1px solid {color}", "borderRadius": "6px",
        "padding": "8px 18px", "fontSize": "12px", "fontWeight": "600",
        "cursor": "pointer", "marginRight": "8px",
    })


def layout(dp=None):
    try:
        from config.universe import EURO_STOXX_50
        # + tickers US pour tester l'exécution (données US gratuites en paper)
        tickers = EURO_STOXX_50 + ["JPM", "AAPL", "MSFT"]
    except Exception:
        tickers = dp.tickers if dp and hasattr(dp, "tickers") else []

    # Mode badge
    mode_bar = html.Div([
        html.Span("MODE : ", style={"color": "#7090a8", "fontSize": "11px", "fontWeight": "600"}),
        html.Span(id="exec-mode-badge", children="PAPER TRADING", style={
            "backgroundColor": "rgba(74,158,255,.12)",
            "color": "#4a9eff", "border": "1px solid rgba(74,158,255,.3)",
            "borderRadius": "4px", "padding": "2px 10px",
            "fontSize": "11px", "fontWeight": "700", "letterSpacing": ".06em",
        }),
        html.Span(id="exec-ibkr-status", style={"marginLeft": "16px", "fontSize": "11px", "color": "#7090a8"}),
    ], style={"marginBottom": "16px", "display": "flex", "alignItems": "center", "gap": "8px"})

    # Formulaire ordre
    order_form = html.Div([
        html.Div("PASSER UN ORDRE", style={**_LABEL, "color": "#4a9eff", "marginBottom": "14px"}),
        dbc.Row([
            dbc.Col(html.Div([
                html.Div("TICKER", style=_LABEL),
                dcc.Dropdown(id="exec-ticker",
                             options=[{"label": t, "value": t} for t in tickers],
                             placeholder="Sélectionner...", style=_DD),
            ]), width=3),
            dbc.Col(html.Div([
                html.Div("ACTION", style=_LABEL),
                dcc.Dropdown(id="exec-action",
                             options=[{"label":"BUY  (Long)","value":"BUY"},
                                      {"label":"SELL (Short)","value":"SELL"},
                                      {"label":"COVER","value":"COVER"}],
                             value="BUY", clearable=False, style=_DD),
            ]), width=2),
            dbc.Col(html.Div([
                html.Div("TYPE", style=_LABEL),
                dcc.Dropdown(id="exec-order-type",
                             options=[{"label":"Limit","value":"LIMIT"},
                                      {"label":"Market","value":"MARKET"}],
                             value="LIMIT", clearable=False, style=_DD),
            ]), width=2),
            dbc.Col(html.Div([
                html.Div("QUANTITÉ", style=_LABEL),
                dcc.Input(id="exec-qty", type="number", min=1, step=1, value=100, style=_INP),
            ]), width=2),
            dbc.Col(html.Div([
                html.Div("PRIX LIMITE (€)", style=_LABEL),
                dcc.Input(id="exec-limit-price", type="number", min=0,
                          placeholder="Auto (Market)", style=_INP),
            ]), width=3),
        ], className="g-3"),
        html.Div(style={"height": "14px"}),
        # Résumé
        html.Div(id="exec-order-preview", style={
            "backgroundColor": "#0a0d12", "border": "1px solid #1e2a38",
            "borderRadius": "6px", "padding": "10px 14px",
            "fontSize": "12px", "color": "#94b8cc", "marginBottom": "14px",
            "minHeight": "38px",
        }),
        # Boutons
        html.Div([
            _btn("✔  Valider l'ordre",    "exec-submit-btn",  "#4a9eff"),
            _btn("✖  Annuler",             "exec-cancel-btn",  "#f87171", outline=True),
            _btn("⟳  Refresh Positions",  "exec-refresh-btn", "#7090a8", outline=True),
        ]),
        html.Div(id="exec-submit-status",
                 style={"marginTop": "12px", "fontSize": "12px", "minHeight": "20px"}),
        dcc.Store(id="exec-fills-store"),
    ], style=_CARD)

    # Positions
    positions = html.Div([
        html.Div("POSITIONS COURANTES", style=_LABEL),
        html.Div(id="exec-positions-table",
                 style={"color": "#94b8cc", "fontSize": "11px"}),
    ], style={**_CARD, "minHeight": "160px"})

    # Blotter
    blotter = html.Div([
        html.Div("ORDER BLOTTER", style=_LABEL),
        html.Div(id="exec-blotter-table"),
        html.Div(style={"height": "10px"}),
        html.Div([
            html.Span(id="exec-blotter-summary",
                      style={"fontSize": "11px", "color": "#7090a8", "flexGrow": "1"}),
            _btn("⬇  Exporter", "exec-export-btn", "#7090a8", outline=True),
            dcc.Download(id="exec-download"),
        ], style={"display": "flex", "alignItems": "center"}),
    ], style=_CARD)

    # Deltas
    deltas = html.Div([
        html.Div("DELTAS CIBLES → POSITIONS", style=_LABEL),
        html.Div(id="exec-delta-table",
                 style={"color": "#94b8cc", "fontSize": "11px"}),
        html.Div(style={"height": "12px"}),
        _btn("⬆  Exécuter tous les deltas", "exec-execute-all-btn", "#f0a500"),
        html.Div(id="exec-delta-status",
                 style={"marginTop": "10px", "fontSize": "11px", "color": "#7090a8"}),
    ], style=_CARD)

    # ── Rebalance : boucle stratégie → exécution ──────────────────
    rebalance = html.Div([
        html.Div([
            html.Div("STRATÉGIE → EXÉCUTION", style={**_LABEL, "color": "#4ade80"}),
            html.Div("Génère le portefeuille cible depuis les signaux momentum L/S "
                     "(top 5 long / bottom 5 short, inverse-vol) et calcule les ordres "
                     "pour l'atteindre.",
                     style={"fontSize": "11px", "color": "#7090a8", "marginBottom": "12px"}),
        ]),
        html.Div([
            html.Span("Capital cible : ", style={"fontSize": "11px", "color": "#94b8cc"}),
            dcc.Input(id="rebal-capital", type="number", value=1_000_000, min=10_000,
                      step=10_000, style={"width": "140px", "backgroundColor": "#0a0d12",
                      "color": "#e8f2ff", "border": "1px solid #1e2a38",
                      "borderRadius": "4px", "padding": "6px 10px", "fontSize": "12px"}),
            html.Span(" €", style={"fontSize": "11px", "color": "#94b8cc", "marginRight": "16px"}),
            _btn("⟳  Générer le portefeuille cible", "rebal-generate-btn", "#4ade80"),
        ], style={"display": "flex", "alignItems": "center", "flexWrap": "wrap",
                  "gap": "8px", "marginBottom": "14px"}),
        html.Div(id="rebal-summary",
                 style={"fontSize": "12px", "color": "#c8d8e8", "marginBottom": "12px"}),
        html.Div(id="rebal-orders-table"),
        html.Div(style={"height": "12px"}),
        html.Div([
            _btn("⬆  Exécuter tous les ordres", "rebal-execute-btn", "#f0a500"),
            html.Span("  ⚠️ Envoie les ordres réels vers IBKR",
                      style={"fontSize": "10px", "color": "#f0a500", "marginLeft": "10px"}),
        ], id="rebal-execute-row", style={"display": "none"}),
        html.Div(id="rebal-execute-status",
                 style={"marginTop": "10px", "fontSize": "11px", "color": "#7090a8"}),
        dcc.Store(id="rebal-orders-store"),
    ], style=_CARD)

    return html.Div([
        html.Div("Execution Lab", style=_H1),
        mode_bar,
        dbc.Row([
            dbc.Col(order_form, width=8),
            dbc.Col(positions,  width=4),
        ], className="g-3", style={"marginBottom": "0"}),
        rebalance,
        dbc.Row([
            dbc.Col(blotter, width=7),
            dbc.Col(deltas,  width=5),
        ], className="g-3"),
    ], style={"paddingBottom": "30px"})