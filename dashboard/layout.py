# dashboard/layout.py — FIXED: active page highlight + nouveau titre

from dash import html, dcc

# Couleurs visibles
_NAV_BG   = "#0d1117"
_NAV_TEXT = "#a0b8cc"   # texte nav visible
_NAV_SEC  = "#4a6070"   # section titles visibles
_ACCENT   = "#4a9eff"
_BORDER   = "#1e2a38"
_BG       = "#0a0d12"

# Titre de la plateforme (modifiable ici)
_BRAND      = "Helios"
_BRAND_SUB  = "Capital"

# Liste des entrées de navigation : (icon, label, href)
_NAV_ITEMS = [
    ("section", "ANALYSIS", None),
    ("▣", "Overview",     "/"),
    ("⚗", "Research Lab", "/research"),
    ("💡", "Idea Lab",     "/ideas"),
    ("⊞", "Math Lab",     "/math"),
    ("🤖", "AI Lab",       "/ai"),
    ("section", "BACKTEST", None),
    ("📈", "Backtest Lab", "/backtest"),
    ("section", "PORTFOLIO", None),
    ("◎", "Portfolio",    "/portfolio"),
    ("⊘", "Risk Lab",     "/risk"),
    ("section", "WATCHLIST", None),
    ("📋", "Watchlist",    "/watchlist"),
    ("section", "DERIVATIVES", None),
    ("∫", "Options Lab",  "/options"),
    ("section", "EXECUTION", None),
    ("⇄", "Execution",    "/execution"),
    ("⚖", "Rebalancing",  "/rebalance"),
    ("▣", "Company",      "/company"),
]


def _nav_link(icon, label, href, active=False):
    """Lien de navigation, surligné si c'est la page active."""
    bg     = "rgba(74,158,255,0.14)" if active else "transparent"
    color  = _ACCENT if active else _NAV_TEXT
    weight = "600" if active else "400"
    border = f"2px solid {_ACCENT}" if active else "2px solid transparent"
    return html.A([
        html.Span(icon, style={"marginRight": "8px", "fontSize": "13px"}),
        html.Span(label),
    ], href=href, id={"type": "nav-link", "href": href}, style={
        "display": "flex", "alignItems": "center",
        "padding": "7px 12px",
        "color": color,
        "textDecoration": "none",
        "borderRadius": "5px",
        "borderLeft": border,
        "backgroundColor": bg,
        "marginBottom": "2px",
        "fontSize": "12px",
        "fontWeight": weight,
        "transition": "all .12s ease",
    })


def _nav_section(title):
    return html.Div(title, style={
        "fontSize": "9px", "fontWeight": "600",
        "color": _NAV_SEC,
        "textTransform": "uppercase", "letterSpacing": ".1em",
        "padding": "14px 12px 5px",
    })


def _build_nav(active_path="/"):
    """Construit la liste des liens avec le bon surlignage."""
    items = []
    for icon, label, href in _NAV_ITEMS:
        if icon == "section":
            items.append(_nav_section(label))
        else:
            items.append(_nav_link(icon, label, href, active=(href == active_path)))
    return items


def build_layout(dp=None):

    # Conservés pour rétrocompatibilité avec d'éventuels appels externes
    def nav_section(title):
        return _nav_section(title)

    def nav_link(icon, label, href):
        return _nav_link(icon, label, href, active=False)

    sidebar = html.Div([
        # Logo
        html.Div([
            html.Span(_BRAND, style={"fontSize": "15px", "fontWeight": "700",
                                     "color": _ACCENT}),
            html.Span(f" {_BRAND_SUB}", style={"fontSize": "12px", "color": "#5a7080",
                                               "marginLeft": "4px"}),
        ], style={"padding": "18px 14px 16px",
                  "borderBottom": f"1px solid {_BORDER}",
                  "marginBottom": "8px"}),

        # Navigation (surlignage géré par callback via id nav-container)
        html.Div(_build_nav("/"), id="nav-container"),

        html.Div(f"{_BRAND} {_BRAND_SUB} · v2.0", style={
            "fontSize": "9px", "color": "#2e3d4f",
            "padding": "16px 14px", "marginTop": "auto",
            "borderTop": f"1px solid {_BORDER}",
        }),
    ], style={
        "width": "210px", "minWidth": "210px",
        "backgroundColor": _NAV_BG,
        "borderRight": f"1px solid {_BORDER}",
        "position": "fixed",
        "top": "0", "left": "0",
        "height": "100vh",
        "display": "flex", "flexDirection": "column",
        "overflowY": "auto",
        "zIndex": "100",
    })

    topbar = html.Div([
        html.Div([
            html.Span("SX5E ", style={"fontSize": "11px", "color": "#5a7080",
                                       "textTransform": "uppercase", "letterSpacing": ".06em"}),
            html.Span("5,189", style={"fontSize": "13px", "fontWeight": "600",
                                        "color": "#c8d8e8", "marginRight": "20px"}),
            html.Span("EUR/USD ", style={"fontSize": "11px", "color": "#5a7080",
                                          "textTransform": "uppercase", "letterSpacing": ".06em"}),
            html.Span("1.08", style={"fontSize": "13px", "fontWeight": "600",
                                        "color": "#c8d8e8"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "4px"}),
        html.Div([
            html.Span("● LIVE", style={"fontSize": "10px", "fontWeight": "600",
                                        "color": "#3fb950", "marginRight": "16px"}),
            html.Span(id="topbar-clock",
                      style={"fontSize": "11px", "color": "#7090a8",
                             "fontVariantNumeric": "tabular-nums"}),
        ], style={"display": "flex", "alignItems": "center"}),
        dcc.Interval(id="clock-interval", interval=2000, n_intervals=0),
    ], style={
        "position": "fixed",
        "top": "0", "left": "210px", "right": "0",
        "height": "44px",
        "backgroundColor": "#08090f",
        "borderBottom": f"1px solid {_BORDER}",
        "display": "flex",
        "alignItems": "center",
        "justifyContent": "space-between",
        "padding": "0 24px",
        "zIndex": "99",
    })

    content = html.Div(
        id="page-content",
        style={
            "marginLeft": "210px",
            "marginTop":  "44px",
            "padding":    "20px 24px",
            "minHeight":  "calc(100vh - 44px)",
            "backgroundColor": _BG,
        },
    )

    return html.Div([
        sidebar,
        topbar,
        content,
        dcc.Location(id="url", refresh=False),
        # Stop-loss monitor (vérifie toutes les 60 secondes)
        dcc.Interval(id="stop-loss-interval", interval=60000, n_intervals=0),
        # Stop-loss log (hidden)
        html.Div(id="stop-loss-log", style={"display":"none"}),
    ], style={
        "backgroundColor": _BG,
        "minHeight": "100vh",
        "fontFamily": "Inter, system-ui, sans-serif",
        "color": "#c8d8e8",
    })