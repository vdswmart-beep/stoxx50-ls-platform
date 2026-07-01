# dashboard/pages/company_analyzer.py — tickers depuis dp (EURO STOXX 50)

from dash import html, dcc, get_app
from dashboard.components.charts import empty_fig
from dashboard.components.filters import dropdown


def layout():
    app = get_app()
    dp  = app.data_provider

    # ← Tous les tickers EURO STOXX 50 (indépendant de l'univers de lancement)
    try:
        from config.universe import EURO_STOXX_50
        tickers = EURO_STOXX_50
    except Exception:
        tickers = dp.tickers if dp and hasattr(dp, "tickers") else []

    # Noms depuis le registre global
    try:
        from config.universe import TICKER_NAMES
    except Exception:
        TICKER_NAMES = {}

    ticker_opts = [
        {"label": f"{t}  —  {TICKER_NAMES.get(t, t)}", "value": t}
        for t in tickers
    ]

    default_val = tickers[0] if tickers else None

    return html.Div([
        html.Div("Company Analyzer", style={
            "fontSize":"11px","color":"#7eb8d8","textTransform":"uppercase",
            "letterSpacing":".1em","marginBottom":"18px","fontWeight":"600",
        }),

        html.Div(className="grid", children=[

            html.Div(className="panel col-12", children=[
                html.Div("SELECT TICKER", style={
                    "fontSize":"10px","color":"#7090a8","textTransform":"uppercase",
                    "letterSpacing":".06em","marginBottom":"6px","fontWeight":"600",
                }),
                dcc.Dropdown(
                    id="company-ticker-dd",
                    options=ticker_opts,
                    value=default_val,
                    clearable=False,
                    placeholder="Rechercher un ticker...",
                    style={
                        "backgroundColor":"#0f141b","color":"#c8d8e8",
                        "border":"1px solid #1e2a38","borderRadius":"4px","fontSize":"13px",
                    },
                ),
            ]),

            html.Div(className="panel col-7", id="company-price-panel", children=[
                html.Div("PRICE HISTORY", style={
                    "fontSize":"10px","color":"#7090a8","textTransform":"uppercase",
                    "letterSpacing":".06em","marginBottom":"8px","fontWeight":"600",
                }),
                dcc.Graph(
                    id="company-price-chart",
                    figure=empty_fig(height=360, message="Sélectionner un ticker"),
                    config={"displayModeBar": False},
                    style={"height":"360px"},
                ),
            ]),

            html.Div(className="panel col-5", id="company-fund-panel", children=[
                html.Div("FUNDAMENTALS", style={
                    "fontSize":"11px","color":"#7eb8d8","textTransform":"uppercase",
                    "letterSpacing":".06em","marginBottom":"12px","fontWeight":"600",
                }),
                html.Div(id="company-fund-table",
                         style={"fontSize":"12px","color":"#8aadcc"}),
            ]),
        ]),
    ], style={"paddingBottom":"30px"})