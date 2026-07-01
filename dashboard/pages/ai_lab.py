# dashboard/pages/ai_lab.py

from dash import html, dcc, get_app
from dashboard.components.filters import dropdown


def layout():
    app = get_app()
    dp  = app.data_provider

    try:
        from config.universe import EURO_STOXX_50
        tickers = EURO_STOXX_50
    except Exception:
        tickers = dp.tickers
    try:
        from config.universe import TICKER_NAMES as names
    except Exception:
        names = {}
    ticker_opts = [{"label": f"{t} — {names.get(t,t)}", "value": t} for t in tickers]

    mode_opts = [
        {"label": "Hypothesis — single ticker",   "value": "hypothesis"},
        {"label": "Pair trade thesis",             "value": "pair"},
        {"label": "Portfolio commentary",          "value": "portfolio"},
        {"label": "Free analysis",                 "value": "free"},
    ]

    ta_style = {
        "width":"100%","background":"#0a0d12","color":"#c0ccd8",
        "border":"1px solid #1e2a38","borderRadius":"4px","padding":"10px",
        "fontSize":"12px","fontFamily":"Inter,system-ui,sans-serif",
        "resize":"vertical","minHeight":"80px",
    }

    return html.Div([
        html.Div("AI Lab — Grok Analysis", className="section-title"),

        html.Div(className="grid", children=[

            # Left: Controls
            html.Div(className="panel col-4", children=[
                html.Div("Analysis Mode", className="section-title"),
                dcc.Dropdown(id="ai-mode-dd", options=mode_opts,
                             value="hypothesis", clearable=False,
                             style={"background":"#0f141b","border":"1px solid #1e2a38",
                                    "color":"#c0ccd8","fontSize":"12px","marginBottom":"10px"}),

                html.Div(id="ai-ticker-controls", children=[
                    html.Div("Ticker A", className="section-title", style={"marginTop":"8px"}),
                    dcc.Dropdown(id="ai-ticker-a", options=ticker_opts,
                                 value=tickers[0] if tickers else None, clearable=False,
                                 style={"background":"#0f141b","border":"1px solid #1e2a38",
                                        "color":"#c0ccd8","fontSize":"12px","marginBottom":"8px"}),
                    html.Div(id="ai-ticker-b-wrap", children=[
                        html.Div("Ticker B (pair trade)", className="section-title"),
                        dcc.Dropdown(id="ai-ticker-b", options=ticker_opts,
                                     value=tickers[1] if len(tickers)>1 else None, clearable=True,
                                     style={"background":"#0f141b","border":"1px solid #1e2a38",
                                            "color":"#c0ccd8","fontSize":"12px","marginBottom":"8px"}),
                    ]),
                ]),

                html.Div("Additional Context / Question", className="section-title", style={"marginTop":"8px"}),
                dcc.Textarea(id="ai-context-input", value="",
                             placeholder="e.g. Focus on ECB rate impact. What's the downside if the euro strengthens 10%?",
                             style=ta_style),

                html.Div(style={"marginTop":"10px"}, children=[
                    html.Button(
                        [html.I(className="ti ti-brand-openai", style={"marginRight":"6px"}),
                         "Ask Grok"],
                        id="ai-submit-btn",
                        style={"background":"#192334","border":"1px solid #4a9eff",
                               "color":"#4a9eff","padding":"8px 20px","borderRadius":"4px",
                               "cursor":"pointer","fontSize":"12px","fontWeight":"500","width":"100%"},
                    ),
                ]),

                html.Div(style={"marginTop":"12px"}, children=[
                    html.Div("Quick Prompts", className="section-title"),
                    *[html.Button(label, id={"type":"ai-quick","index":i},
                                  style={"display":"block","width":"100%","textAlign":"left",
                                         "background":"transparent","border":"1px solid #1e2a38",
                                         "color":"#8899aa","padding":"6px 10px","borderRadius":"4px",
                                         "cursor":"pointer","fontSize":"11px","marginBottom":"4px"})
                      for i, label in enumerate([
                          "What is the current macro risk for this stock?",
                          "Compare valuation vs sector peers",
                          "Generate a bear case thesis",
                          "What would trigger a change in direction?",
                      ])]
                ]),
            ]),

            # Right: Grok output
            html.Div(className="panel col-8", children=[
                html.Div("Grok Response", className="section-title"),
                dcc.Loading(
                    html.Div(id="ai-output",
                             style={"minHeight":"400px","fontSize":"12px","color":"#c0ccd8",
                                    "lineHeight":"1.7","whiteSpace":"pre-wrap"}),
                    type="dot", color="#4a9eff",
                ),
            ]),

            # Hypothesis history
            html.Div(className="panel col-12", children=[
                html.Div("Hypothesis Log", className="section-title"),
                html.Div(id="ai-history-output",
                         style={"maxHeight":"200px","overflowY":"auto"}),
            ]),
        ]),

        dcc.Store(id="ai-history-store", data=[]),
    ])