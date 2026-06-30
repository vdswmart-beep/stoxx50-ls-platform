# dashboard/pages/math_lab.py — REWRITE: Pair Trading Engine

from dash import html, dcc, get_app
import dash_bootstrap_components as dbc

_CARD  = {"backgroundColor":"#0f141b","border":"1px solid #1e2a38","borderRadius":"8px","padding":"16px","marginBottom":"14px"}
_LABEL = {"fontSize":"10px","color":"#7eb8d8","textTransform":"uppercase","letterSpacing":".08em","marginBottom":"6px","fontWeight":"600"}
_H1    = {"fontSize":"11px","color":"#7eb8d8","textTransform":"uppercase","letterSpacing":".1em","marginBottom":"18px","fontWeight":"600"}
_DD    = {"backgroundColor":"#0a0d12","color":"#c8d8e8","border":"1px solid #1e2a38","borderRadius":"4px","fontSize":"12px"}
_INP   = {"backgroundColor":"#0a0d12","color":"#c8d8e8","border":"1px solid #1e2a38","borderRadius":"4px","padding":"6px 10px","fontSize":"12px","width":"100%"}


def layout():
    app = get_app()
    dp  = app.data_provider

    tickers = dp.tickers
    opts    = [{"label": t, "value": t} for t in tickers]

    # Exemples de paires par secteur
    pairs_suggestions = [
        ("Toyota / Honda",     "7203.T", "7267.T"),
        ("Sony / Panasonic",   "6758.T", "6752.T"),
        ("MUFG / SMFG",        "8306.T", "8316.T"),
        ("SoftBank / NTT",     "9984.T", "9432.T"),
        ("Fanuc / Keyence",    "6954.T", "6861.T"),
    ]
    pair_btns = []
    for label, ta, tb in pairs_suggestions:
        if ta in tickers and tb in tickers:
            pair_btns.append(
                html.Button(label, id={"type":"pair-preset","ta":ta,"tb":tb},
                    style={"backgroundColor":"#0d1520","border":"1px solid #1e2a38","color":"#7eb8d8",
                           "borderRadius":"4px","padding":"4px 10px","fontSize":"11px",
                           "cursor":"pointer","marginRight":"6px","marginBottom":"6px"})
            )

    # Contrôles
    controls = html.Div([
        html.Div("PAIR TRADING — SPREAD ANALYSIS", style={**_LABEL,"fontSize":"11px","marginBottom":"14px"}),
        dbc.Row([
            dbc.Col(html.Div([
                html.Div("STOCK A  (Long leg)", style=_LABEL),
                dcc.Dropdown(id="math-ticker-a", options=opts,
                             value=tickers[0] if len(tickers)>0 else None,
                             clearable=False, style=_DD),
            ]), width=3),
            dbc.Col(html.Div([
                html.Div("STOCK B  (Short leg)", style=_LABEL),
                dcc.Dropdown(id="math-ticker-b", options=opts,
                             value=tickers[1] if len(tickers)>1 else None,
                             clearable=False, style=_DD),
            ]), width=3),
            dbc.Col(html.Div([
                html.Div("Z-SCORE ENTRY (σ)", style=_LABEL),
                dcc.Input(id="math-entry-z", type="number", value=2.0, step=0.1, min=0.5, max=4.0, style=_INP),
            ]), width=2),
            dbc.Col(html.Div([
                html.Div("Z-SCORE EXIT (σ)", style=_LABEL),
                dcc.Input(id="math-exit-z", type="number", value=0.5, step=0.1, min=0.0, max=2.0, style=_INP),
            ]), width=2),
            dbc.Col(html.Div([
                html.Div("ROLLING WINDOW (jours)", style=_LABEL),
                dcc.Input(id="math-window", type="number", value=63, step=1, min=20, max=252, style=_INP),
            ]), width=2),
        ], className="g-3"),
        html.Div(style={"height":"10px"}),
        html.Div([
            html.Div("Paires suggérées :", style={"fontSize":"10px","color":"#5a7080","marginBottom":"6px"}),
            *pair_btns,
        ]) if pair_btns else html.Div(),
        html.Div(style={"height":"10px"}),
        html.Button("▶  Analyser la Paire", id="math-run-btn", style={
            "backgroundColor":"#1a3a5c","color":"#4a9eff","border":"1px solid #4a9eff",
            "borderRadius":"6px","padding":"10px 28px","fontSize":"13px",
            "fontWeight":"600","cursor":"pointer","width":"100%",
        }),
    ], style=_CARD)

    # Résultats coïntégration
    coint_panel = html.Div([
        html.Div("COINTEGRATION STATISTICS", style=_LABEL),
        dcc.Loading(html.Div(id="math-stats-output"), type="dot", color="#4a9eff"),
    ], style=_CARD)

    # Spread chart
    spread_panel = html.Div([
        html.Div("SPREAD  =  log(A) − β · log(B)", style=_LABEL),
        dcc.Loading(
            dcc.Graph(id="math-chart-output", config={"displayModeBar":False},
                      style={"height":"280px"}),
            type="dot", color="#4a9eff",
        ),
    ], style=_CARD)

    # Z-score chart
    zscore_panel = html.Div([
        html.Div("Z-SCORE avec signaux entrée / sortie", style=_LABEL),
        dcc.Loading(
            dcc.Graph(id="math-zscore-output", config={"displayModeBar":False},
                      style={"height":"260px"}),
            type="dot", color="#4a9eff",
        ),
    ], style=_CARD)

    # Spread backtest PnL
    bt_panel = html.Div([
        html.Div("BACKTEST DU SPREAD (PnL cumulé)", style=_LABEL),
        dcc.Loading(
            dcc.Graph(id="math-pnl-output", config={"displayModeBar":False},
                      style={"height":"240px"}),
            type="dot", color="#4a9eff",
        ),
    ], style=_CARD)

    # Rolling beta + correlation
    beta_corr = dbc.Row([
        dbc.Col(html.Div([
            html.Div("ROLLING BETA (OLS)", style=_LABEL),
            dcc.Loading(
                dcc.Graph(id="math-beta-output", config={"displayModeBar":False},
                          style={"height":"220px"}),
                type="dot", color="#4a9eff",
            ),
        ], style=_CARD), width=6),
        dbc.Col(html.Div([
            html.Div("ROLLING CORRÉLATION", style=_LABEL),
            dcc.Loading(
                dcc.Graph(id="math-corr-output", config={"displayModeBar":False},
                          style={"height":"220px"}),
                type="dot", color="#4a9eff",
            ),
        ], style=_CARD), width=6),
    ], className="g-3")

    # Explication pédagogique
    explainer = html.Div([
        html.Div("COMMENT LIRE CES RÉSULTATS", style=_LABEL),
        html.Div([
            html.Div("📌  Le spread est stationnaire si les deux actions sont coïntégrées (p-value < 0.05).",
                     style={"marginBottom":"6px","fontSize":"11px","color":"#94b8cc"}),
            html.Div("📈  Signal LONG le spread : acheter A, vendre B quand le z-score descend sous −2σ.",
                     style={"marginBottom":"6px","fontSize":"11px","color":"#4ade80"}),
            html.Div("📉  Signal SHORT le spread : vendre A, acheter B quand le z-score monte au-dessus de +2σ.",
                     style={"marginBottom":"6px","fontSize":"11px","color":"#f87171"}),
            html.Div("🔄  Sortie de position quand le z-score revient vers 0 (±0.5σ par défaut).",
                     style={"marginBottom":"6px","fontSize":"11px","color":"#f0a500"}),
            html.Div("⚠️  Vérifier que la corrélation rolling reste > 0.6 — si elle chute, la paire a divergé structurellement.",
                     style={"fontSize":"11px","color":"#7090a8"}),
        ], style={"backgroundColor":"#0a0d12","borderRadius":"6px","padding":"12px 14px",
                  "border":"1px solid #1a2a38"}),
    ], style=_CARD)

    return html.Div([
        html.Div("Math Lab — Pair Trading", style=_H1),
        controls,
        dbc.Row([
            dbc.Col(coint_panel, width=4),
            dbc.Col(spread_panel, width=8),
        ], className="g-3", style={"marginBottom":"0"}),
        zscore_panel,
        bt_panel,
        beta_corr,
        explainer,
        # IDs legacy pour compatibilité callbacks existants
        html.Div(id="math-pca-output",  style={"display":"none"}),
    ], style={"paddingBottom":"30px"})