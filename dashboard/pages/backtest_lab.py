# dashboard/pages/backtest_lab.py — FIXED: erreur dict.empty + sliders corrects

from dash import html, dcc
import dash_bootstrap_components as dbc

_CARD  = {"backgroundColor":"#0f141b","border":"1px solid #1e2a38",
           "borderRadius":"8px","padding":"16px","marginBottom":"14px"}
_LABEL = {"fontSize":"10px","color":"#7eb8d8","textTransform":"uppercase",
           "letterSpacing":".08em","marginBottom":"6px","fontWeight":"600"}
_H1    = {"fontSize":"11px","color":"#7eb8d8","textTransform":"uppercase",
           "letterSpacing":".1em","marginBottom":"18px","fontWeight":"600"}


def _kpi(label, vid, color):
    return html.Div([
        html.Div(label, style=_LABEL),
        html.Div(id=vid, children="—", style={
            "fontSize":"28px","fontWeight":"700",
            "color":color,"fontVariantNumeric":"tabular-nums","marginTop":"6px",
        }),
    ], style={**_CARD,"padding":"18px 20px","minHeight":"96px"})


def layout(dp=None):
    # Vérification sécurisée du backtest_result
    has_result = False
    try:
        if dp is not None and hasattr(dp, "_last_backtest"):
            has_result = dp._last_backtest is not None
    except Exception:
        pass

    # Config panel
    config = html.Div([
        html.Div("CONFIGURATION", style=_LABEL),
        dbc.Row([
            dbc.Col(html.Div([
                html.Div("FENÊTRE TRAIN (mois)", style={**_LABEL,"marginBottom":"12px"}),
                dcc.Slider(
                    id="bt-train-months", min=3, max=24, step=3, value=12,
                    marks={3:"3M", 6:"6M", 12:"12M", 18:"18M", 24:"24M"},
                    tooltip={"always_visible": False},
                ),
                html.Div("→ Plus long = signal plus stable, moins de fenêtres",
                         style={"fontSize":"9px","color":"#5a7080","marginTop":"6px"}),
            ]), width=4),
            dbc.Col(html.Div([
                html.Div("FENÊTRE TEST out-of-sample (mois)", style={**_LABEL,"marginBottom":"12px"}),
                dcc.Slider(
                    id="bt-test-months", min=1, max=6, step=1, value=3,
                    marks={1:"1M", 2:"2M", 3:"3M", 6:"6M"},
                    tooltip={"always_visible": False},
                ),
                html.Div("→ Plus court = plus réaliste mais plus de friction",
                         style={"fontSize":"9px","color":"#5a7080","marginTop":"6px"}),
            ]), width=4),
            dbc.Col(html.Div([
                html.Div("STRATÉGIE", style=_LABEL),
                dcc.Dropdown(
                    id="bt-strategy",
                    options=[
                        {"label": "Momentum L/S — Long top performers, Short bottom",
                         "value": "momentum"},
                        {"label": "Equal Weight — Long-only pondération égale",
                         "value": "equal_weight"},
                    ],
                    value="momentum", clearable=False,
                    style={"backgroundColor":"#0a0d12","color":"#c8d8e8",
                           "border":"1px solid #1e2a38","fontSize":"12px"},
                ),
                html.Div(
                    "💡 Momentum L/S : long les 20% supérieurs, short les 20% inférieurs "
                    "(rendement momentum 12M). Market-neutral : exposition nette ≈ 0.",
                    style={"fontSize":"9px","color":"#5a7080","marginTop":"6px","lineHeight":"1.5"},
                ),
            ]), width=4),
        ], className="g-3"),
        html.Div(style={"height":"16px"}),

        # Futur : idées custom
        html.Div([
            html.Div("PROCHAINEMENT — Stratégies custom", style={**_LABEL,"color":"#5a7080"}),
            html.Div(
                "Tester : Long LVMH (MC.PA) / Short Kering  •  "
                "Long Tech (SAP, ASML) / Short Autos  •  Paires coïntégrées",
                style={"fontSize":"11px","color":"#3a5060","fontStyle":"italic"},
            ),
        ], style={"backgroundColor":"#090c10","border":"1px solid #141d24",
                  "borderRadius":"6px","padding":"10px 14px","marginBottom":"12px"}),

        html.Button("▶  Lancer Backtest", id="bt-run-btn", style={
            "backgroundColor":"#1a3a5c","color":"#4a9eff",
            "border":"1px solid #4a9eff","borderRadius":"6px",
            "padding":"10px 28px","fontSize":"13px","fontWeight":"600",
            "cursor":"pointer","width":"100%","letterSpacing":".04em",
        }),
    ], style=_CARD)

    # KPIs
    kpis = dbc.Row([
        dbc.Col(_kpi("Sharpe",       "bt-kpi-sharpe",  "#4a9eff"), width=2),
        dbc.Col(_kpi("Sortino",      "bt-kpi-sortino", "#60c4cc"), width=2),
        dbc.Col(_kpi("Ann. Return",  "bt-kpi-return",  "#4ade80"), width=2),
        dbc.Col(_kpi("Max Drawdown", "bt-kpi-maxdd",   "#f87171"), width=2),
        dbc.Col(_kpi("Win Rate",     "bt-kpi-winrate", "#f0a500"), width=2),
        dbc.Col(_kpi("Calmar",       "bt-kpi-calmar",  "#c084fc"), width=2),
    ], className="g-3", style={"marginBottom":"14px"})

    hint = html.Div(
        "⚠ Momentum sur seulement 10 tickers peut donner Sharpe négatif. "
        "Utilise --universe liquid40 (40 tickers) pour de meilleurs résultats.",
        style={"fontSize":"11px","color":"#5a7080","marginBottom":"14px",
               "padding":"8px 12px","backgroundColor":"#0d1520",
               "border":"1px solid #1a2a38","borderRadius":"6px"},
    )

    status_div = html.Div(id="bt-status", style={
        "fontSize":"12px","color":"#7eb8d8","marginBottom":"10px","minHeight":"20px",
    })

    graphs_top = dbc.Row([
        dbc.Col(html.Div([
            html.Div("EQUITY CURVE (BASE 100)", style=_LABEL),
            dcc.Graph(id="bt-equity-fig", config={"displayModeBar":False},
                      style={"height":"320px"}),
        ], style=_CARD), width=8),
        dbc.Col(html.Div([
            html.Div("DRAWDOWN", style=_LABEL),
            dcc.Graph(id="bt-dd-fig", config={"displayModeBar":False},
                      style={"height":"320px"}),
        ], style=_CARD), width=4),
    ], className="g-3", style={"marginBottom":"14px"})

    graphs_bot = dbc.Row([
        dbc.Col(html.Div([
            html.Div("ROLLING SHARPE (63j)", style=_LABEL),
            dcc.Graph(id="bt-sharpe-fig", config={"displayModeBar":False},
                      style={"height":"240px"}),
        ], style=_CARD), width=6),
        dbc.Col(html.Div([
            html.Div("PnL MENSUEL (%)", style=_LABEL),
            dcc.Graph(id="bt-monthly-fig", config={"displayModeBar":False},
                      style={"height":"240px"}),
        ], style=_CARD), width=6),
    ], className="g-3", style={"marginBottom":"14px"})

    export = html.Div([
        html.Button("⬇  Exporter Track Record Excel", id="bt-export-btn", style={
            "backgroundColor":"transparent","color":"#4a9eff",
            "border":"1px solid #4a9eff","borderRadius":"6px",
            "padding":"8px 20px","fontSize":"12px","cursor":"pointer","marginRight":"14px",
        }),
        html.Span(id="bt-export-status",
                  style={"fontSize":"12px","color":"#4ade80"}),
        dcc.Download(id="bt-download"),
    ])

    return html.Div([
        html.Div("Backtest Lab", style=_H1),
        config,
        status_div,
        kpis,
        hint,
        graphs_top,
        graphs_bot,
        export,
    ], style={"paddingBottom":"30px"})