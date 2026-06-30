# dashboard/pages/options_lab.py — Options analytics (dark theme)
#
# 5 sous-onglets : Pricer · Greeks · Stratégies · Parité · Surface Vol
# Underlying = ticker EURO STOXX 50 (options européennes, pricing Black-Scholes)
# IV réelle via IBKR si TWS tourne, sinon mock théorique (spot live Yahoo)

from dash import html, dcc, get_app
import dash_bootstrap_components as dbc

_BG    = "#0f141b"; _BG2 = "#0a0d12"; _GRID = "rgba(255,255,255,0.04)"
_TEXT  = "#c8d8e8"; _MUTED = "#7090a8"; _BORDER = "1px solid #1e2a38"
_CARD  = {"backgroundColor":_BG,"border":"1px solid #1e2a38","borderRadius":"8px","padding":"16px","marginBottom":"14px"}
_LABEL = {"fontSize":"10px","color":"#7eb8d8","textTransform":"uppercase","letterSpacing":".08em","marginBottom":"8px","fontWeight":"600"}
_H1    = {"fontSize":"11px","color":"#7eb8d8","textTransform":"uppercase","letterSpacing":".1em","marginBottom":"18px","fontWeight":"600"}
_DD    = {"backgroundColor":_BG2,"color":_TEXT,"border":_BORDER,"borderRadius":"4px","fontSize":"12px"}
_INP   = {"backgroundColor":_BG2,"color":_TEXT,"border":_BORDER,"borderRadius":"4px","padding":"6px 10px","fontSize":"12px","width":"100%"}

# Tickers disponibles pour le pricing d'options — EURO STOXX 50
def _options_universe():
    """Construit la liste déroulante depuis l'univers EURO STOXX 50."""
    try:
        from config.universe import EURO_STOXX_50, TICKER_NAMES
        return [{"label": f"{TICKER_NAMES.get(t, t)} ({t})", "value": t}
                for t in EURO_STOXX_50]
    except Exception:
        return [{"label": "LVMH (MC.PA)", "value": "MC.PA"}]

OPTIONS_UNIVERSE = _options_universe()
# Défaut : ASML (très liquide, options actives sur Eurex) plutôt que le 1er alphabétique
_PREFERRED_DEFAULT = "ASML.AS"
_DEFAULT_UNDERLYING = (_PREFERRED_DEFAULT
                       if any(o["value"] == _PREFERRED_DEFAULT for o in OPTIONS_UNIVERSE)
                       else (OPTIONS_UNIVERSE[0]["value"] if OPTIONS_UNIVERSE else "MC.PA"))


def _greek_box(label, gid, hint=""):
    return html.Div([
        html.Div(label, style={"fontSize":"10px","color":_MUTED,"textTransform":"uppercase",
                               "letterSpacing":".06em","marginBottom":"4px"}),
        html.Div("—", id=gid, style={"fontSize":"20px","fontWeight":"700","color":_TEXT,
                                     "fontVariantNumeric":"tabular-nums"}),
        html.Div(hint, style={"fontSize":"9px","color":"#5a7080","marginTop":"2px"}) if hint else None,
    ], style={"backgroundColor":_BG2,"borderRadius":"6px","padding":"12px","textAlign":"center","border":_BORDER})


def _underlying_selector(default=None):
    if default is None:
        default = _DEFAULT_UNDERLYING
    """Sélecteur de sous-jacent partagé par tous les onglets."""
    return html.Div([
        html.Div("SOUS-JACENT", style=_LABEL),
        dcc.Dropdown(id="opt-underlying", options=OPTIONS_UNIVERSE, value=default,
                     clearable=False, style=_DD),
        html.Div(id="opt-spot-display", style={"fontSize":"11px","color":_MUTED,"marginTop":"6px"}),
    ], style={**_CARD,"marginBottom":"14px"})


# ─────────────────────────────────────────────────────────────────────
# ONGLET 1 — PRICER
# ─────────────────────────────────────────────────────────────────────
def _tab_pricer():
    return html.Div([
        dbc.Row([
            dbc.Col([
                _underlying_selector(),
                html.Div([
                    html.Div("CONTRAT", style=_LABEL),
                    html.Div("Échéance (jours)", style={**_LABEL,"fontSize":"9px","marginBottom":"4px"}),
                    dcc.Dropdown(id="pricer-expiry",
                                 options=[{"label":f"{d}j","value":d} for d in [30,60,91,182,273,365]],
                                 value=91, clearable=False, style=_DD),
                    html.Div(style={"height":"10px"}),
                    html.Div("Type", style={**_LABEL,"fontSize":"9px","marginBottom":"4px"}),
                    dcc.RadioItems(id="pricer-type",
                                   options=[{"label":" Call","value":"call"},{"label":" Put","value":"put"}],
                                   value="call", inline=True,
                                   style={"fontSize":"12px","color":_TEXT},
                                   inputStyle={"marginRight":"4px","marginLeft":"10px"}),
                    html.Div(style={"height":"10px"}),
                    html.Div("Strike", style={**_LABEL,"fontSize":"9px","marginBottom":"4px"}),
                    dcc.Input(id="pricer-strike", type="number", value=250, step=1, style=_INP),
                    html.Div(style={"height":"14px"}),
                    html.Button("Pricer l'option", id="pricer-btn", style={
                        "backgroundColor":"#1a3a5c","color":"#4a9eff","border":"1px solid #4a9eff",
                        "borderRadius":"6px","padding":"10px 20px","fontSize":"13px",
                        "fontWeight":"600","cursor":"pointer","width":"100%"}),
                ], style=_CARD),
            ], width=4),
            dbc.Col([
                # Prix + IV
                dbc.Row([
                    dbc.Col(_greek_box("Black-Scholes price", "pricer-price", "valeur théorique"), width=4),
                    dbc.Col(_greek_box("Implied vol", "pricer-iv", "vol surface"), width=4),
                    dbc.Col(_greek_box("Maturité", "pricer-mat", "années"), width=4),
                ], className="g-2", style={"marginBottom":"12px"}),
                # Greeks
                html.Div([
                    html.Div("GREEKS  (desk units — vega/ρ per 1%, θ per day)", style=_LABEL),
                    dbc.Row([
                        dbc.Col(_greek_box("Delta", "pricer-delta"), width=2),
                        dbc.Col(_greek_box("Gamma", "pricer-gamma"), width=2),
                        dbc.Col(_greek_box("Vega",  "pricer-vega"),  width=2),
                        dbc.Col(_greek_box("Theta", "pricer-theta"), width=2),
                        dbc.Col(_greek_box("Rho",   "pricer-rho"),   width=2),
                        dbc.Col(_greek_box("Spot",  "pricer-spot"),  width=2),
                    ], className="g-2"),
                ], style=_CARD),
                # Payoff
                html.Div([
                    html.Div("PAYOFF À MATURITÉ", style=_LABEL),
                    dcc.Loading(dcc.Graph(id="pricer-payoff", config={"displayModeBar":False},
                                          style={"height":"300px"}), type="dot", color="#4a9eff"),
                ], style=_CARD),
            ], width=8),
        ], className="g-3"),
    ])


# ─────────────────────────────────────────────────────────────────────
# ONGLET 2 — GREEKS EXPLORER (sliders live)
# ─────────────────────────────────────────────────────────────────────
def _slider_field(label, sid, mn, mx, step, val, suffix=""):
    return html.Div([
        html.Div([
            html.Span(label, style={"fontSize":"11px","color":_MUTED}),
            html.Span("—", id=f"{sid}-out", style={"fontSize":"13px","fontWeight":"600",
                                                    "color":"#4a9eff","float":"right",
                                                    "fontVariantNumeric":"tabular-nums"}),
        ], style={"marginBottom":"6px","overflow":"hidden"}),
        dcc.Slider(id=sid, min=mn, max=mx, step=step, value=val,
                   marks=None, tooltip={"placement":"bottom","always_visible":False}),
    ], style={"marginBottom":"18px"})


def _tab_greeks():
    return html.Div([
        dbc.Row([
            dbc.Col([
                _underlying_selector(),
                html.Div([
                    html.Div("PARAMÈTRES — glisse pour repricer", style=_LABEL),
                    dcc.RadioItems(id="greeks-type",
                                   options=[{"label":" Call","value":"call"},{"label":" Put","value":"put"}],
                                   value="call", inline=True,
                                   style={"fontSize":"12px","color":_TEXT,"marginBottom":"16px"},
                                   inputStyle={"marginRight":"4px","marginLeft":"10px"}),
                    _slider_field("Spot (S)",        "greeks-spot",   50, 500, 1,   250),
                    _slider_field("Strike (K)",      "greeks-strike", 50, 500, 1,   250),
                    _slider_field("Volatility (σ)",  "greeks-vol",    0.05, 1.2, 0.005, 0.30, "%"),
                    _slider_field("Maturity (T)",    "greeks-mat",    0.02, 2.0, 0.01, 0.25, "y"),
                    html.Div([
                        html.Span("Rate et dividend yield fixés aux hypothèses desk. ",
                                  style={"fontSize":"10px","color":_MUTED}),
                        html.Span("Greeks recalculés instantanément.",
                                  style={"fontSize":"10px","color":"#4a9eff"}),
                    ], style={"backgroundColor":_BG2,"borderRadius":"6px","padding":"10px 12px",
                              "borderLeft":"3px solid #0f766e"}),
                ], style=_CARD),
            ], width=4),
            dbc.Col([
                dbc.Row([
                    dbc.Col(_greek_box("Black-Scholes price", "greeks-price"), width=4),
                    dbc.Col(_greek_box("Intrinsic", "greeks-intrinsic"), width=4),
                    dbc.Col(_greek_box("Time value", "greeks-timevalue"), width=4),
                ], className="g-2", style={"marginBottom":"12px"}),
                html.Div([
                    html.Div("GREEKS", style=_LABEL),
                    dbc.Row([
                        dbc.Col(_greek_box("Delta", "greeks-delta"), width=2),
                        dbc.Col(_greek_box("Gamma", "greeks-gamma"), width=2),
                        dbc.Col(_greek_box("Vega",  "greeks-vega"),  width=2),
                        dbc.Col(_greek_box("Theta", "greeks-theta"), width=2),
                        dbc.Col(_greek_box("Rho",   "greeks-rho"),   width=2),
                        dbc.Col(_greek_box("Moneyness", "greeks-money"), width=2),
                    ], className="g-2"),
                ], style=_CARD),
                html.Div([
                    html.Div("DELTA PROFILE vs SPOT — call & put", style=_LABEL),
                    dcc.Loading(dcc.Graph(id="greeks-profile", config={"displayModeBar":False},
                                          style={"height":"300px"}), type="dot", color="#4a9eff"),
                ], style=_CARD),
            ], width=8),
        ], className="g-3"),
    ])


# ─────────────────────────────────────────────────────────────────────
# ONGLET 3 — STRATÉGIES
# ─────────────────────────────────────────────────────────────────────
def _tab_strategies():
    # Liste des stratégies depuis le registre
    try:
        from options.strategies import STRATEGY_REGISTRY
        strat_opts = [{"label": s.label, "value": k} for k, s in STRATEGY_REGISTRY.items()]
    except Exception:
        strat_opts = [{"label":"Bull Call Spread","value":"bull_call_spread"}]

    return html.Div([
        dbc.Row([
            dbc.Col([
                _underlying_selector(),
                html.Div([
                    html.Div("CONSTRUIRE", style=_LABEL),
                    html.Div("Stratégie", style={**_LABEL,"fontSize":"9px","marginBottom":"4px"}),
                    dcc.Dropdown(id="strat-key", options=strat_opts, value="bull_call_spread",
                                 clearable=False, style=_DD),
                    html.Div(style={"height":"10px"}),
                    html.Div("Échéance (jours)", style={**_LABEL,"fontSize":"9px","marginBottom":"4px"}),
                    dcc.Dropdown(id="strat-expiry",
                                 options=[{"label":f"{d}j","value":d} for d in [30,60,91,182,273,365]],
                                 value=91, clearable=False, style=_DD),
                    html.Div(style={"height":"10px"}),
                    # Strikes dynamiques (jusqu'à 3)
                    html.Div(id="strat-strikes-container"),
                    html.Div(style={"height":"10px"}),
                    html.Div("Quantité (lots)", style={**_LABEL,"fontSize":"9px","marginBottom":"4px"}),
                    dcc.Input(id="strat-qty", type="number", value=1, step=1, style=_INP),
                    html.Div(style={"height":"14px"}),
                    html.Button("Construire la stratégie", id="strat-btn", style={
                        "backgroundColor":"#1a3a5c","color":"#4a9eff","border":"1px solid #4a9eff",
                        "borderRadius":"6px","padding":"10px 20px","fontSize":"13px",
                        "fontWeight":"600","cursor":"pointer","width":"100%"}),
                    html.Div(id="strat-description", style={"fontSize":"11px","color":_MUTED,
                                                            "marginTop":"12px","lineHeight":"1.5"}),
                ], style=_CARD),
            ], width=4),
            dbc.Col([
                # Coût / max profit / max loss
                dbc.Row([
                    dbc.Col(_greek_box("Coût net", "strat-cost"), width=4),
                    dbc.Col(_greek_box("Max profit", "strat-maxprofit"), width=4),
                    dbc.Col(_greek_box("Max loss", "strat-maxloss"), width=4),
                ], className="g-2", style={"marginBottom":"12px"}),
                # Legs + breakevens
                dbc.Row([
                    dbc.Col(html.Div([
                        html.Div("LEGS", style=_LABEL),
                        html.Div(id="strat-legs", style={"fontSize":"11px","color":_TEXT}),
                    ], style=_CARD), width=6),
                    dbc.Col(html.Div([
                        html.Div("BREAK-EVENS", style=_LABEL),
                        html.Div(id="strat-breakevens", style={"fontSize":"11px"}),
                    ], style=_CARD), width=6),
                ], className="g-2"),
                # Greeks agrégés
                html.Div([
                    html.Div("GREEKS AGRÉGÉS — net book risk", style=_LABEL),
                    dbc.Row([
                        dbc.Col(_greek_box("Value", "strat-g-value"), width=2),
                        dbc.Col(_greek_box("Delta", "strat-g-delta"), width=2),
                        dbc.Col(_greek_box("Gamma", "strat-g-gamma"), width=2),
                        dbc.Col(_greek_box("Vega",  "strat-g-vega"),  width=2),
                        dbc.Col(_greek_box("Theta", "strat-g-theta"), width=2),
                        dbc.Col(_greek_box("Rho",   "strat-g-rho"),   width=2),
                    ], className="g-2"),
                ], style=_CARD),
                # Payoff
                html.Div([
                    html.Div("PAYOFF À MATURITÉ — P&L net du coût d'entrée", style=_LABEL),
                    dcc.Loading(dcc.Graph(id="strat-payoff", config={"displayModeBar":False},
                                          style={"height":"320px"}), type="dot", color="#4a9eff"),
                ], style=_CARD),
            ], width=8),
        ], className="g-3"),
    ])


# ─────────────────────────────────────────────────────────────────────
# ONGLET 4 — PARITÉ PUT-CALL
# ─────────────────────────────────────────────────────────────────────
def _tab_parity():
    return html.Div([
        dbc.Row([
            dbc.Col([
                _underlying_selector(),
                html.Div([
                    html.Div("INPUTS", style=_LABEL),
                    html.Div("Échéance (jours)", style={**_LABEL,"fontSize":"9px","marginBottom":"4px"}),
                    dcc.Dropdown(id="parity-expiry",
                                 options=[{"label":f"{d}j","value":d} for d in [30,60,91,182,273,365]],
                                 value=91, clearable=False, style=_DD),
                    html.Div(style={"height":"10px"}),
                    html.Div("Strike", style={**_LABEL,"fontSize":"9px","marginBottom":"4px"}),
                    dcc.Input(id="parity-strike", type="number", value=250, step=1, style=_INP),
                    html.Div(style={"height":"10px"}),
                    html.Div("Tolérance (price units)", style={**_LABEL,"fontSize":"9px","marginBottom":"4px"}),
                    dcc.Input(id="parity-tol", type="number", value=0.50, step=0.01, style=_INP),
                    html.Div(style={"height":"14px"}),
                    html.Button("Vérifier la parité", id="parity-btn", style={
                        "backgroundColor":"#1a3a5c","color":"#4a9eff","border":"1px solid #4a9eff",
                        "borderRadius":"6px","padding":"10px 20px","fontSize":"13px",
                        "fontWeight":"600","cursor":"pointer","width":"100%"}),
                    html.Div([
                        html.Span("⚠ Les écarts apparents ne sont ", style={"fontSize":"10px","color":_MUTED}),
                        html.Span("pas", style={"fontSize":"10px","color":"#f0a500","fontWeight":"700"}),
                        html.Span(" du free money : bid-ask, coûts de financement, dividendes discrets "
                                  "ou quotes périmées. Signal de screening, pas un trade.",
                                  style={"fontSize":"10px","color":_MUTED}),
                    ], style={"backgroundColor":_BG2,"borderRadius":"6px","padding":"10px 12px",
                              "borderLeft":"3px solid #d97706","marginTop":"12px"}),
                ], style=_CARD),
            ], width=4),
            dbc.Col([
                dcc.Loading(html.Div(id="parity-result"), type="dot", color="#4a9eff"),
            ], width=8),
        ], className="g-3"),
    ])


# ─────────────────────────────────────────────────────────────────────
# ONGLET 5 — SURFACE DE VOLATILITÉ
# ─────────────────────────────────────────────────────────────────────
def _tab_surface():
    return html.Div([
        _underlying_selector(),
        html.Div([
            html.Div("SURFACE DE VOLATILITÉ IMPLICITE — strike × maturité × IV", style=_LABEL),
            dcc.Loading(dcc.Graph(id="surface-3d", config={"displayModeBar":True},
                                  style={"height":"480px"}), type="dot", color="#4a9eff"),
        ], style=_CARD),
        dbc.Row([
            dbc.Col(html.Div([
                html.Div("VOLATILITY SMILES — par échéance", style=_LABEL),
                dcc.Loading(dcc.Graph(id="surface-smiles", config={"displayModeBar":False},
                                      style={"height":"320px"}), type="dot", color="#4a9eff"),
            ], style=_CARD), width=6),
            dbc.Col(html.Div([
                html.Div("TERM STRUCTURE — ATM IV", style=_LABEL),
                dcc.Loading(dcc.Graph(id="surface-term", config={"displayModeBar":False},
                                      style={"height":"320px"}), type="dot", color="#4a9eff"),
            ], style=_CARD), width=6),
        ], className="g-3"),
    ])


# ─────────────────────────────────────────────────────────────────────
# LAYOUT principal
# ─────────────────────────────────────────────────────────────────────
def layout():
    tabs = dbc.Tabs([
        dbc.Tab(label="Pricer",       tab_id="pricer",     tab_style={"minWidth":"110px"}),
        dbc.Tab(label="Greeks",       tab_id="greeks",     tab_style={"minWidth":"110px"}),
        dbc.Tab(label="Stratégies",   tab_id="strategies", tab_style={"minWidth":"120px"}),
        dbc.Tab(label="Parité",       tab_id="parity",     tab_style={"minWidth":"110px"}),
        dbc.Tab(label="Surface Vol",  tab_id="surface",    tab_style={"minWidth":"120px"}),
    ], id="options-tabs", active_tab="pricer", style={"marginBottom":"14px"})

    return html.Div([
        html.Div("Options Lab — European Options · Black-Scholes", style=_H1),
        html.Div("Pricing d'options européennes sur l'EURO STOXX 50 · "
                 "IV de marché via IBKR (TWS) ou théorique (mock, spot live Yahoo)",
                 style={"fontSize":"11px","color":"#5a7080","marginBottom":"14px"}),
        tabs,
        dcc.Loading(html.Div(id="options-tab-content"), type="dot", color="#4a9eff"),
    ], style={"paddingBottom":"30px"})