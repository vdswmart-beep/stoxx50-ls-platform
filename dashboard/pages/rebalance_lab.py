# dashboard/pages/rebalance_lab.py — onglet dédié Rebalancing (stratégie → exécution)

from dash import html, dcc, get_app

_CARD  = {"backgroundColor": "#0f141b", "border": "1px solid #1e2a38",
          "borderRadius": "8px", "padding": "20px", "marginBottom": "16px"}
_LABEL = {"fontSize": "10px", "color": "#7eb8d8", "textTransform": "uppercase",
          "letterSpacing": ".08em", "marginBottom": "8px", "fontWeight": "600"}
_H1    = {"fontSize": "11px", "color": "#7eb8d8", "textTransform": "uppercase",
          "letterSpacing": ".1em", "marginBottom": "18px", "fontWeight": "600"}
_INP   = {"width": "150px", "backgroundColor": "#0a0d12", "color": "#e8f2ff",
          "border": "1px solid #1e2a38", "borderRadius": "4px",
          "padding": "8px 10px", "fontSize": "13px"}


def _btn(label, bid, color="#4a9eff", outline=False):
    return html.Button(label, id=bid, n_clicks=0, style={
        "backgroundColor": "transparent" if outline else color,
        "color": color if outline else "#fff",
        "border": f"1px solid {color}", "borderRadius": "6px",
        "padding": "10px 22px", "fontSize": "13px", "fontWeight": "600",
        "cursor": "pointer", "marginRight": "10px",
    })


def layout(dp=None):
    if dp is None:
        dp = get_app().data_provider

    # Détecter si on est connecté à IBKR (mode live)
    is_live = False
    try:
        eng = getattr(dp, "_exec_engine", None)
        is_live = eng is not None and getattr(eng, "is_connected", False)
    except Exception:
        is_live = False

    live_badge = html.Span(
        "● LIVE — connecté à IBKR" if is_live else "○ Hors ligne — lance en --mode live",
        style={"fontSize": "11px", "fontWeight": "600",
               "color": "#4ade80" if is_live else "#f0a500", "marginLeft": "12px"})

    # ── Panneau de configuration ──────────────────────────────────
    config = html.Div([
        html.Div([html.Span("Rebalancing", style={**_H1, "display": "inline"}), live_badge],
                 style={"marginBottom": "16px"}),
        html.Div(
            "Génère le portefeuille cible depuis les signaux de la stratégie "
            "(sélection multi-facteur + construction HRP), le compare à tes positions "
            "IBKR actuelles, et liste les ordres à passer. Valide en un clic pour "
            "atteindre le portefeuille idéal.",
            style={"fontSize": "12px", "color": "#94b8cc", "marginBottom": "18px",
                   "lineHeight": "1.6"}),
        html.Div([
            html.Div([
                html.Div("STRATÉGIE", style=_LABEL),
                dcc.Dropdown(
                    id="rb-strategy",
                    options=[
                        {"label": "Momentum (12M-1M) — meilleur backtest, Sharpe 1.6", "value": "momentum"},
                        {"label": "Momentum + fondamentaux (overlay ROE/marges/P-E)",   "value": "momentum_fundamental"},
                        {"label": "Multi-facteur + HRP — Sharpe 1.1",                    "value": "hrp"},
                        {"label": "Multi-facteur (3 signaux) — Sharpe 0.8",             "value": "multifactor"},
                    ],
                    value="momentum", clearable=False,
                    style={"width": "380px"}),
            ]),
            html.Div([
                html.Div("CAPITAL CIBLE (€)", style=_LABEL),
                dcc.Input(id="rb-capital", type="number", value=1_000_000,
                          min=10_000, step=10_000, style=_INP),
            ]),
            html.Div([
                html.Div("POSITIONS / CÔTÉ", style=_LABEL),
                dcc.Input(id="rb-topn", type="number", value=5, min=3, max=10,
                          step=1, style={**_INP, "width": "80px"}),
            ]),
        ], style={"display": "flex", "gap": "24px", "alignItems": "flex-end",
                  "flexWrap": "wrap", "marginBottom": "18px"}),
        _btn("⟳  Générer le portefeuille cible", "rb-generate-btn", "#4ade80"),
    ], style=_CARD)

    # ── Résumé (rempli par callback) ──────────────────────────────
    summary_card = html.Div(id="rb-summary-card")

    # ── Table des ordres ──────────────────────────────────────────
    orders_card = html.Div([
        html.Div("ORDRES À EXÉCUTER", style=_LABEL),
        html.Div(id="rb-orders-table",
                 children=html.Div("Clique « Générer » pour calculer les ordres.",
                                   style={"color": "#5a7080", "fontSize": "12px",
                                          "padding": "20px 0"})),
        html.Div(id="rb-execute-zone", style={"display": "none"}, children=[
            html.Div(style={"height": "16px"}),
            _btn("✔  Valider et exécuter tous les ordres", "rb-execute-btn", "#f0a500"),
            html.Span("  Envoie les ordres réels vers IBKR paper",
                      style={"fontSize": "11px", "color": "#f0a500", "marginLeft": "8px"}),
        ]),
        html.Div(id="rb-execute-status", style={"marginTop": "14px"}),
    ], style=_CARD)

    return html.Div([
        config,
        summary_card,
        orders_card,
        dcc.Store(id="rb-orders-store"),
    ], style={"paddingBottom": "30px"})