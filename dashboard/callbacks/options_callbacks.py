# dashboard/callbacks/options_callbacks.py — Options Lab (dark theme)

import logging
from functools import lru_cache
from datetime import date, timedelta

import numpy as np
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import Input, Output, State, html, dcc, ctx, ALL
from dash.exceptions import PreventUpdate

logger = logging.getLogger("OptionsCallbacks")

_BG = "#0f141b"; _GRID = "rgba(255,255,255,0.05)"; _TEXT = "#c8d8e8"; _MUTED = "#7090a8"
_FONT = dict(family="Inter, system-ui, sans-serif", color=_TEXT, size=11)
_ACCENT = "#4a9eff"; _TEAL = "#4ade80"; _AMBER = "#f0a500"; _PURPLE = "#c084fc"; _RED = "#f87171"


def _layout(height=300, title=""):
    return dict(
        paper_bgcolor=_BG, plot_bgcolor=_BG, font=_FONT, height=height,
        margin=dict(l=50, r=20, t=36, b=36), hovermode="x unified",
        legend=dict(orientation="h", y=1.06, font=dict(size=10, color=_MUTED)),
        title=dict(text=title, font=dict(size=11, color=_MUTED), x=0),
        xaxis=dict(gridcolor=_GRID, linecolor="#1e2a38", zeroline=False,
                   tickfont=dict(size=10, color=_MUTED)),
        yaxis=dict(gridcolor=_GRID, linecolor="#1e2a38", zeroline=True,
                   zerolinecolor="#243244", tickfont=dict(size=10, color=_MUTED)),
    )


# Référence vers la connexion IBKR vivante (injectée par register_options_callbacks)
_IB_REF = {"ib": None}
# IBKR opt-in : par défaut OFF (le mock est instantané). L'utilisateur active
# l'IV réelle via le bouton dédié, sinon chaque chargement de page attendrait
# plusieurs secondes par contrat (reqMktData bloquant) → spinner infini.
_USE_IBKR = {"on": False}


# Cache des chaînes (le spot live ne change pas à la seconde)
@lru_cache(maxsize=16)
def _get_chain(symbol: str, _bucket: int, _source: str):
    """
    Construit (et cache) une chaîne pour un symbole.
    _bucket invalide le cache toutes les ~5min.
    _source ("ibkr"/"mock") fait partie de la clé pour ne pas mélanger les sources.
    """
    from options.mock_provider import get_option_chain
    ib = _IB_REF.get("ib")
    prefer_ibkr = (_source == "ibkr")
    return get_option_chain(symbol, ib=ib, prefer_ibkr=prefer_ibkr)


def _chain_for(symbol: str):
    import time
    bucket = int(time.time() // 300)  # 5 minutes
    # Source = ibkr UNIQUEMENT si l'utilisateur l'a activé ET qu'une connexion existe.
    # Par défaut → mock (instantané), pour éviter le spinner infini en mode live.
    source = "mock"
    if _USE_IBKR.get("on"):
        ib = _IB_REF.get("ib")
        try:
            if ib is not None and ib.isConnected():
                source = "ibkr"
        except Exception:
            source = "mock"
    return _get_chain(symbol, bucket, source)


def _market_for(symbol: str):
    from options.mock_provider import TICKER_MARKET
    return TICKER_MARKET.get(symbol, {"rate": 0.025, "dividend": 0.0, "currency": "EUR"})


def _sym(symbol: str):
    return "€" if _market_for(symbol)["currency"] == "EUR" else "$"


def _iv_for(symbol: str, strike: float, maturity: float) -> float:
    """
    IV pour un (strike, maturité) donné.
    - Si chaîne IBKR réelle : interpole l'IV de marché depuis la surface.
    - Sinon : skew théorique du MockProvider.
    Retombe toujours sur le skew si l'interpolation échoue.
    """
    try:
        chain = _chain_for(symbol)
        if not chain.is_empty and "ibkr" in (chain.source or ""):
            # Vraie surface de marché — interpolation
            from options.volatility import VolatilitySurface
            surf = VolatilitySurface(chain)
            if not surf.is_empty:
                v = surf.interpolate(maturity, strike)
                if v and v > 0:
                    return float(v)
    except Exception:
        pass
    # Fallback skew théorique
    from options.mock_provider import MockProvider
    spot = None
    try:
        spot = _chain_for(symbol).spot
    except Exception:
        pass
    return MockProvider(symbol, spot=spot)._skew_vol(strike, maturity)


def _is_real_iv(symbol: str) -> bool:
    """True si la chaîne provient d'IBKR (IV de marché réelle)."""
    try:
        return "ibkr" in (_chain_for(symbol).source or "")
    except Exception:
        return False


def register_options_callbacks(app, dp, exec_engine=None):
    # Récupérer la connexion IBKR vivante depuis l'exec_engine (IBKRLiveEngine)
    ib = None
    eng = exec_engine or getattr(dp, "_exec_engine", None)
    if eng is not None and hasattr(eng, "_ib"):
        try:
            if eng.is_connected:
                ib = eng._ib
                logger.info("OptionsLab : connexion IBKR partagée détectée (IV de marché activée)")
        except Exception:
            pass
    _IB_REF["ib"] = ib

    # ── Routeur de sous-onglets ──────────────────────────────────
    @app.callback(
        Output("options-tab-content", "children"),
        Input("options-tabs", "active_tab"),
    )
    def render_subtab(active_tab):
        from dashboard.pages.options_lab import (
            _tab_pricer, _tab_greeks, _tab_strategies, _tab_parity, _tab_surface,
            _tab_structured
        )
        return {
            "pricer":     _tab_pricer,
            "greeks":     _tab_greeks,
            "strategies": _tab_strategies,
            "structured": _tab_structured,
            "parity":     _tab_parity,
            "surface":    _tab_surface,
        }.get(active_tab, _tab_pricer)()

    # ── Spot display partagé ─────────────────────────────────────
    @app.callback(
        Output("opt-spot-display", "children"),
        Input("opt-underlying", "value"),
    )
    def show_spot(symbol):
        if not symbol:
            raise PreventUpdate
        try:
            chain = _chain_for(symbol)
            mk = _market_for(symbol)
            sym = _sym(symbol)
            real = "ibkr" in (chain.source or "")
            if real:
                src_badge = html.Span("IV marché (IBKR)", style={
                    "color":"#4ade80","fontSize":"10px","fontWeight":"600",
                    "backgroundColor":"rgba(74,222,128,.12)","border":"1px solid rgba(74,222,128,.3)",
                    "borderRadius":"4px","padding":"1px 8px","marginLeft":"10px"})
            else:
                src_badge = html.Span("IV théorique (mock)", style={
                    "color":"#f0a500","fontSize":"10px","fontWeight":"600",
                    "backgroundColor":"rgba(240,165,0,.10)","border":"1px solid rgba(240,165,0,.25)",
                    "borderRadius":"4px","padding":"1px 8px","marginLeft":"10px"})
            return html.Span([
                html.Span(f"Spot {sym}{chain.spot:,.2f}", style={"color":_ACCENT, "fontWeight":"600"}),
                html.Span(f"  ·  r {mk['rate']*100:.2f}%  ·  q {mk['dividend']*100:.2f}%",
                          style={"color":_MUTED}),
                src_badge,
            ])
        except Exception as e:
            return html.Span(f"Erreur spot : {e}", style={"color":_RED})

    # ═══════════════════════════════════════════════════════════════
    # ONGLET 1 — PRICER
    # ═══════════════════════════════════════════════════════════════
    @app.callback(
        Output("pricer-price", "children"), Output("pricer-iv", "children"),
        Output("pricer-mat", "children"),   Output("pricer-delta", "children"),
        Output("pricer-gamma", "children"), Output("pricer-vega", "children"),
        Output("pricer-theta", "children"), Output("pricer-rho", "children"),
        Output("pricer-spot", "children"),  Output("pricer-payoff", "figure"),
        Input("pricer-btn", "n_clicks"),
        State("opt-underlying", "value"), State("pricer-expiry", "value"),
        State("pricer-type", "value"),    State("pricer-strike", "value"),
        prevent_initial_call=True,
    )
    def price_option(n, symbol, dte, opt_type, strike):
        if not n or not symbol:
            raise PreventUpdate
        try:
            from options.pricing import BlackScholes, BSParams, OptionType
            from options.strategies import build_strategy

            chain = _chain_for(symbol)
            mk    = _market_for(symbol)
            sym   = _sym(symbol)
            spot  = chain.spot
            maturity = dte / 365.0
            ot    = OptionType.parse(opt_type)
            strike = float(strike or spot)

            # IV depuis la surface (skew du MockProvider)
            from options.mock_provider import MockProvider
            iv = _iv_for(symbol, strike, maturity)

            params = BSParams(spot, strike, maturity, mk["rate"], iv, mk["dividend"], ot)
            g = BlackScholes.greeks(params)
            d = g.as_dict(desk_units=True)

            # Payoff via la stratégie long_call/long_put
            strat_key = "long_call" if ot is OptionType.CALL else "long_put"
            strat = build_strategy(strat_key, spot, maturity, mk["rate"], mk["dividend"],
                                   iv, {"strike": strike}, 1.0)
            grid, payoff, pnl = strat.payoff_curve(n=200)

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=grid, y=np.maximum(pnl,0), mode="lines",
                                     line=dict(width=0), fill="tozeroy",
                                     fillcolor="rgba(74,222,128,0.12)", hoverinfo="skip", showlegend=False))
            fig.add_trace(go.Scatter(x=grid, y=np.minimum(pnl,0), mode="lines",
                                     line=dict(width=0), fill="tozeroy",
                                     fillcolor="rgba(248,113,113,0.12)", hoverinfo="skip", showlegend=False))
            fig.add_trace(go.Scatter(x=grid, y=pnl, mode="lines", name="P&L",
                                     line=dict(color=_TEXT, width=2.2),
                                     hovertemplate=f"S_T {sym}%{{x:.1f}}<br>P&L {sym}%{{y:.2f}}<extra></extra>"))
            fig.add_hline(y=0, line_color="#243244")
            fig.add_vline(x=spot, line_dash="dot", line_color=_MUTED,
                          annotation_text="spot", annotation_font_size=9)
            for be in strat.breakevens():
                fig.add_vline(x=be, line_dash="dash", line_color=_TEAL)
            fig.update_layout(**_layout(300, f"{symbol} {opt_type.upper()} K={strike:.0f}"))

            return (f"{sym}{d['price']:.2f}", f"{iv*100:.1f}%", f"{maturity:.3f}y",
                    f"{d['delta']:.4f}", f"{d['gamma']:.4f}", f"{d['vega']:.4f}",
                    f"{d['theta']:.4f}", f"{d['rho']:.4f}", f"{sym}{spot:.2f}", fig)
        except Exception as e:
            logger.error(f"price_option: {e}", exc_info=True)
            empty = go.Figure().update_layout(**_layout(300))
            return ("—",)*9 + (empty,)

    # ═══════════════════════════════════════════════════════════════
    # ONGLET 2 — GREEKS EXPLORER (sliders live)
    # ═══════════════════════════════════════════════════════════════
    # Sync des labels de sliders
    @app.callback(
        Output("greeks-spot-out","children"), Output("greeks-strike-out","children"),
        Output("greeks-vol-out","children"),  Output("greeks-mat-out","children"),
        Input("greeks-spot","value"), Input("greeks-strike","value"),
        Input("greeks-vol","value"),  Input("greeks-mat","value"),
    )
    def sync_slider_labels(spot, strike, vol, mat):
        return (f"{spot:.0f}", f"{strike:.0f}",
                f"{vol*100:.1f}%", f"{mat:.2f}y · {int(mat*365)}d")

    # Recalcul live des Greeks
    @app.callback(
        Output("greeks-price","children"),     Output("greeks-intrinsic","children"),
        Output("greeks-timevalue","children"), Output("greeks-delta","children"),
        Output("greeks-gamma","children"),     Output("greeks-vega","children"),
        Output("greeks-theta","children"),     Output("greeks-rho","children"),
        Output("greeks-money","children"),     Output("greeks-profile","figure"),
        Input("greeks-spot","value"),   Input("greeks-strike","value"),
        Input("greeks-vol","value"),    Input("greeks-mat","value"),
        Input("greeks-type","value"),   Input("opt-underlying","value"),
    )
    def live_greeks(spot, strike, vol, mat, opt_type, symbol):
        try:
            from options.pricing import BlackScholes, BSParams, OptionType
            mk = _market_for(symbol or "ASML.AS")
            sym = _sym(symbol or "ASML.AS")
            ot = OptionType.parse(opt_type)
            params = BSParams(float(spot), float(strike), float(mat),
                              mk["rate"], float(vol), mk["dividend"], ot)
            g = BlackScholes.greeks(params)
            d = g.as_dict(desk_units=True)
            intrinsic = max((spot-strike) if ot is OptionType.CALL else (strike-spot), 0.0)
            tv = d["price"] - intrinsic
            money = spot / strike

            # Profil delta vs spot (call & put)
            lo, hi = max(1, spot*0.6), spot*1.4
            spots = np.linspace(lo, hi, 120)
            calls = [float(BlackScholes.delta(s, strike, mat, mk["rate"], vol, mk["dividend"], OptionType.CALL)) for s in spots]
            puts  = [float(BlackScholes.delta(s, strike, mat, mk["rate"], vol, mk["dividend"], OptionType.PUT)) for s in spots]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=spots, y=calls, mode="lines", name="Call Δ",
                                     line=dict(color=_ACCENT, width=2.2)))
            fig.add_trace(go.Scatter(x=spots, y=puts, mode="lines", name="Put Δ",
                                     line=dict(color=_TEAL, width=2.2)))
            fig.add_vline(x=spot, line_dash="dot", line_color=_MUTED,
                          annotation_text="spot", annotation_font_size=9)
            fig.add_vline(x=strike, line_dash="dash", line_color="#243244",
                          annotation_text="K", annotation_font_size=9)
            fig.update_layout(**_layout(300, "Delta vs Spot"))

            return (f"{sym}{d['price']:.2f}", f"{sym}{intrinsic:.2f}", f"{sym}{tv:.2f}",
                    f"{d['delta']:.4f}", f"{d['gamma']:.4f}", f"{d['vega']:.4f}",
                    f"{d['theta']:.4f}", f"{d['rho']:.4f}", f"{money:.3f}", fig)
        except Exception as e:
            logger.error(f"live_greeks: {e}")
            empty = go.Figure().update_layout(**_layout(300))
            return ("—",)*9 + (empty,)

    # ═══════════════════════════════════════════════════════════════
    # ONGLET 3 — STRATÉGIES
    # ═══════════════════════════════════════════════════════════════
    # Strikes dynamiques selon la stratégie choisie
    @app.callback(
        Output("strat-strikes-container", "children"),
        Input("strat-key", "value"),
        State("opt-underlying", "value"),
    )
    def update_strike_inputs(strat_key, symbol):
        try:
            from options.strategies import STRATEGY_REGISTRY
            spec = STRATEGY_REGISTRY.get(strat_key)
            if not spec:
                raise PreventUpdate
            chain = _chain_for(symbol or "ASML.AS")
            defaults = spec.defaults(chain.spot)
            _INP = {"backgroundColor":"#0a0d12","color":_TEXT,"border":"1px solid #1e2a38",
                    "borderRadius":"4px","padding":"6px 10px","fontSize":"12px","width":"100%"}
            fields = []
            for name in spec.strikes:
                fields.append(html.Div([
                    html.Div(name.capitalize(), style={"fontSize":"9px","color":_MUTED,
                                                       "textTransform":"uppercase","marginBottom":"4px"}),
                    dcc.Input(id={"type":"strat-strike","name":name}, type="number",
                              value=round(defaults[name]), step=1, style=_INP),
                ], style={"marginBottom":"8px"}))
            return [html.Div("Strikes", style={"fontSize":"10px","color":"#7eb8d8",
                                               "textTransform":"uppercase","letterSpacing":".06em",
                                               "marginBottom":"6px","fontWeight":"600"})] + fields
        except Exception as e:
            logger.error(f"update_strike_inputs: {e}")
            return html.Div()

    @app.callback(
        Output("strat-cost","children"),      Output("strat-maxprofit","children"),
        Output("strat-maxloss","children"),   Output("strat-legs","children"),
        Output("strat-breakevens","children"),Output("strat-g-value","children"),
        Output("strat-g-delta","children"),   Output("strat-g-gamma","children"),
        Output("strat-g-vega","children"),    Output("strat-g-theta","children"),
        Output("strat-g-rho","children"),     Output("strat-payoff","figure"),
        Output("strat-description","children"),
        Input("strat-btn","n_clicks"),
        State("strat-key","value"),    State("opt-underlying","value"),
        State("strat-expiry","value"), State("strat-qty","value"),
        State({"type":"strat-strike","name":ALL}, "value"),
        State({"type":"strat-strike","name":ALL}, "id"),
        prevent_initial_call=True,
    )
    def build_strat(n, key, symbol, dte, qty, strike_values, strike_ids):
        if not n or not key or not symbol:
            raise PreventUpdate
        try:
            from options.strategies import build_strategy, STRATEGY_REGISTRY
            from options.mock_provider import MockProvider

            chain = _chain_for(symbol)
            mk    = _market_for(symbol)
            sym   = _sym(symbol)
            spot  = chain.spot
            maturity = dte / 365.0
            qty   = float(qty or 1)

            spec = STRATEGY_REGISTRY[key]

            # Récupérer les strikes depuis le pattern-matching (ALL)
            strikes = {}
            for cid, val in zip(strike_ids or [], strike_values or []):
                if isinstance(cid, dict) and cid.get("type") == "strat-strike" and val is not None:
                    strikes[cid["name"]] = float(val)
            if not strikes:
                strikes = spec.defaults(spot)

            # vol_fn depuis le skew
            vol_fn = lambda k: _iv_for(symbol, k, maturity)

            strat = build_strategy(key, spot, maturity, mk["rate"], mk["dividend"],
                                   vol_fn, strikes, qty)
            summ = strat.summary()

            # Coût / profit / loss
            cost = summ["net_cost"]
            cost_str = f"{sym}{abs(cost):.2f} {'débit' if cost>0 else 'crédit'}"
            mp_str = "Illimité" if summ["max_profit"]=="unlimited" else f"{sym}{summ['max_profit']:.2f}"
            ml_str = "Illimité" if summ["max_loss"]=="unlimited" else f"{sym}{summ['max_loss']:.2f}"

            # Legs
            legs = html.Ul([html.Li(l, style={"fontSize":"11px","color":_TEXT,"marginBottom":"4px",
                                              "fontFamily":"monospace"}) for l in summ["legs"]],
                           style={"paddingLeft":"14px","margin":"0"})

            # Breakevens
            if summ["breakevens"]:
                be = html.Div([html.Span(f"{sym}{b:.2f}", style={
                    "backgroundColor":"rgba(240,165,0,.12)","color":_AMBER,"border":"1px solid rgba(240,165,0,.3)",
                    "borderRadius":"4px","padding":"2px 8px","fontSize":"11px","marginRight":"6px",
                    "fontFamily":"monospace"}) for b in summ["breakevens"]])
            else:
                be = html.Div("Aucun break-even fini", style={"fontSize":"11px","color":_MUTED})

            g = summ["greeks"]

            # Payoff
            grid, payoff, pnl = strat.payoff_curve(n=300)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=grid, y=np.maximum(pnl,0), mode="lines", line=dict(width=0),
                                     fill="tozeroy", fillcolor="rgba(74,222,128,0.12)", hoverinfo="skip", showlegend=False))
            fig.add_trace(go.Scatter(x=grid, y=np.minimum(pnl,0), mode="lines", line=dict(width=0),
                                     fill="tozeroy", fillcolor="rgba(248,113,113,0.12)", hoverinfo="skip", showlegend=False))
            fig.add_trace(go.Scatter(x=grid, y=pnl, mode="lines", name="P&L",
                                     line=dict(color=_TEXT, width=2.2),
                                     hovertemplate=f"S_T {sym}%{{x:.1f}}<br>P&L {sym}%{{y:.2f}}<extra></extra>"))
            fig.add_trace(go.Scatter(x=grid, y=payoff, mode="lines", name="Gross payoff",
                                     line=dict(color=_AMBER, width=1.3, dash="dash")))
            fig.add_hline(y=0, line_color="#243244")
            fig.add_vline(x=spot, line_dash="dot", line_color=_MUTED,
                          annotation_text="spot", annotation_font_size=9)
            for b in strat.breakevens():
                fig.add_vline(x=b, line_dash="dash", line_color=_TEAL)
            fig.update_layout(**_layout(320, f"{summ['name']}"))

            return (cost_str, mp_str, ml_str, legs, be,
                    f"{sym}{g['price']:.2f}", f"{g['delta']:.4f}", f"{g['gamma']:.4f}",
                    f"{g['vega']:.4f}", f"{g['theta']:.4f}", f"{g['rho']:.4f}",
                    fig, summ["description"])
        except Exception as e:
            logger.error(f"build_strat: {e}", exc_info=True)
            empty = go.Figure().update_layout(**_layout(320))
            return ("—",)*5 + ("—",)*6 + (empty, f"Erreur : {e}")

    # ═══════════════════════════════════════════════════════════════
    # ONGLET 4 — PARITÉ
    # ═══════════════════════════════════════════════════════════════
    @app.callback(
        Output("parity-result", "children"),
        Input("parity-btn", "n_clicks"),
        State("opt-underlying","value"), State("parity-expiry","value"),
        State("parity-strike","value"),  State("parity-tol","value"),
        prevent_initial_call=True,
    )
    def check_parity(n, symbol, dte, strike, tol):
        if not n or not symbol:
            raise PreventUpdate
        try:
            from options.pricing import BlackScholes, OptionType, check_put_call_parity
            from options.mock_provider import MockProvider

            chain = _chain_for(symbol)
            mk    = _market_for(symbol)
            sym   = _sym(symbol)
            spot  = chain.spot
            maturity = dte / 365.0
            strike = float(strike or spot)
            tol    = float(tol or 0.5)

            iv = _iv_for(symbol, strike, maturity)
            call_p = float(BlackScholes.price(spot, strike, maturity, mk["rate"], iv, mk["dividend"], OptionType.CALL))
            put_p  = float(BlackScholes.price(spot, strike, maturity, mk["rate"], iv, mk["dividend"], OptionType.PUT))

            res = check_put_call_parity(call_p, put_p, spot, strike, maturity,
                                        mk["rate"], mk["dividend"], tol)

            flag = res.arbitrage_flag
            _CARD = {"backgroundColor":_BG,"border":"1px solid #1e2a38","borderRadius":"8px","padding":"16px","marginBottom":"14px"}
            _LBL  = {"fontSize":"10px","color":"#7eb8d8","textTransform":"uppercase","letterSpacing":".08em","marginBottom":"8px","fontWeight":"600"}

            def stat(label, val, color=_TEXT):
                return html.Div([
                    html.Div(label, style={"fontSize":"10px","color":_MUTED,"textTransform":"uppercase","marginBottom":"4px"}),
                    html.Div(val, style={"fontSize":"16px","fontWeight":"700","color":color,"fontVariantNumeric":"tabular-nums"}),
                ], style={"backgroundColor":"#0a0d12","borderRadius":"6px","padding":"12px","textAlign":"center","border":"1px solid #1e2a38"})

            badge = (html.Span("⚠ Dislocation potentielle", style={
                        "backgroundColor":"rgba(248,113,113,.12)","color":_RED,"border":"1px solid #f87171",
                        "borderRadius":"999px","padding":"4px 12px","fontSize":"12px","fontWeight":"600"})
                     if flag else
                     html.Span("✓ Dans la tolérance", style={
                        "backgroundColor":"rgba(74,222,128,.12)","color":_TEAL,"border":"1px solid #4ade80",
                        "borderRadius":"999px","padding":"4px 12px","fontSize":"12px","fontWeight":"600"}))

            return html.Div([
                html.Div([
                    html.Div([
                        html.Span("Relation  C + PV(K) = P + S·e", style={"fontSize":"13px","color":_TEXT,"fontWeight":"600"}),
                        html.Span("-qT", style={"fontSize":"9px","color":_TEXT,"verticalAlign":"super"}),
                    ]),
                    badge,
                ], style={"display":"flex","justifyContent":"space-between","alignItems":"center","marginBottom":"16px"}),
                dbc.Row([
                    dbc.Col(stat("C − P (marché)", f"{sym}{res.lhs:.4f}"), width=4),
                    dbc.Col(stat("Carry  S·e⁻qT − K·e⁻ʳT", f"{sym}{res.rhs:.4f}"), width=4),
                    dbc.Col(stat("Résidu", f"{sym}{res.residual:.4f}", _RED if flag else _TEAL), width=4),
                ], className="g-2", style={"marginBottom":"14px"}),
                dbc.Row([
                    dbc.Col(stat("Call mid", f"{sym}{call_p:.2f}"), width=3),
                    dbc.Col(stat("Put mid", f"{sym}{put_p:.2f}"), width=3),
                    dbc.Col(stat("Strike", f"{strike:.0f}"), width=3),
                    dbc.Col(stat("Maturité", f"{maturity:.3f}y"), width=3),
                ], className="g-2"),
                html.Div([
                    html.Span("Lecture : ", style={"fontSize":"11px","color":_MUTED,"fontWeight":"600"}),
                    html.Span(res.direction or "Parité respectée — pas de signal.",
                              style={"fontSize":"11px","color":_TEXT}),
                ], style={"marginTop":"16px","padding":"12px","backgroundColor":"#0a0d12","borderRadius":"6px"}),
            ], style=_CARD)
        except Exception as e:
            logger.error(f"check_parity: {e}", exc_info=True)
            return html.Div(f"Erreur : {e}", style={"color":_RED,"fontSize":"12px","padding":"16px"})

    # ═══════════════════════════════════════════════════════════════
    # ONGLET 5 — SURFACE DE VOL
    # ═══════════════════════════════════════════════════════════════
    @app.callback(
        Output("surface-3d","figure"), Output("surface-smiles","figure"),
        Output("surface-term","figure"),
        Input("opt-underlying","value"),
    )
    def render_surface(symbol):
        if not symbol:
            raise PreventUpdate
        try:
            from options.volatility import VolatilitySurface
            from options.pricing import OptionType
            chain = _chain_for(symbol)
            surf  = VolatilitySurface(chain)
            sym   = _sym(symbol)

            # 3D Surface
            fig3d = go.Figure()
            if not surf.is_empty:
                grid = surf.build_grid()
                fig3d.add_trace(go.Surface(
                    x=grid.strikes, y=grid.maturities, z=grid.iv*100,
                    colorscale="Viridis", colorbar=dict(title="IV %", thickness=14, len=0.7),
                    contours={"z":{"show":True,"usecolormap":True,"highlightcolor":"#ffffff","project_z":True}},
                    hovertemplate="K %{x:.0f}<br>T %{y:.2f}y<br>IV %{z:.1f}%<extra></extra>",
                ))
            fig3d.update_layout(
                paper_bgcolor=_BG, font=dict(family="Inter, system-ui", size=11, color=_TEXT),
                height=480, margin=dict(l=0,r=0,t=20,b=0),
                scene=dict(
                    xaxis_title="Strike", yaxis_title="Maturity (y)", zaxis_title="IV (%)",
                    xaxis=dict(backgroundcolor=_BG, gridcolor=_GRID, color=_MUTED),
                    yaxis=dict(backgroundcolor=_BG, gridcolor=_GRID, color=_MUTED),
                    zaxis=dict(backgroundcolor=_BG, gridcolor=_GRID, color=_MUTED),
                    camera=dict(eye=dict(x=1.6, y=-1.6, z=0.9)),
                ),
            )

            # Smiles
            figs = go.Figure()
            for exp in chain.expiries()[:6]:
                smile = chain.smile(exp, OptionType.CALL)
                if smile.empty:
                    continue
                dte = (exp - chain.as_of).days
                figs.add_trace(go.Scatter(x=smile["strike"], y=smile["iv"]*100,
                                          mode="lines+markers", name=f"{dte}d",
                                          marker=dict(size=4)))
            figs.add_vline(x=chain.spot, line_dash="dot", line_color=_MUTED,
                           annotation_text="spot", annotation_font_size=9)
            figs.update_layout(**_layout(320, "IV Smiles"))
            figs.update_xaxes(title_text="Strike"); figs.update_yaxes(title_text="IV (%)")

            # Term structure
            ts = chain.atm_term_structure(OptionType.CALL)
            figt = go.Figure()
            if not ts.empty:
                figt.add_trace(go.Scatter(x=ts["T"], y=ts["iv"]*100, mode="lines+markers",
                                          line=dict(color=_TEAL, width=2),
                                          marker=dict(size=7, color=_TEAL),
                                          hovertemplate="T %{x:.2f}y<br>ATM IV %{y:.1f}%<extra></extra>"))
            figt.update_layout(**_layout(320, "ATM Term Structure"))
            figt.update_xaxes(title_text="Maturity (y)"); figt.update_yaxes(title_text="ATM IV (%)")

            return fig3d, figs, figt
        except Exception as e:
            logger.error(f"render_surface: {e}", exc_info=True)
            empty = go.Figure().update_layout(**_layout(320))
            return empty, empty, empty


    # ═══════════════════════════════════════════════════════════════
    # ONGLET PRODUITS STRUCTURÉS
    # ═══════════════════════════════════════════════════════════════
    from dash import ALL, ctx as _ctx

    # Store des legs (liste de dicts)
    @app.callback(
        Output("struct-legs-container", "children"),
        Input("struct-add-leg", "n_clicks"),
        Input({"type": "struct-leg-del", "idx": ALL}, "n_clicks"),
        Input("preset-capital-protected", "n_clicks"),
        Input("preset-reverse-conv", "n_clicks"),
        Input("preset-autocall", "n_clicks"),
        Input("preset-bonus", "n_clicks"),
        State("struct-legs-container", "children"),
        State("opt-underlying", "value"),
        prevent_initial_call=True,
    )
    def manage_struct_legs(add, dels, p_cap, p_rev, p_auto, p_bonus, current, symbol):
        from dashboard.pages.options_lab import _leg_row
        trig = _ctx.triggered_id

        # Spot approximatif pour des strikes par défaut sensés
        try:
            spot = _chain_for(symbol).spot
        except Exception:
            spot = 100.0
        s = round(spot)

        # ── Presets : produits structurés classiques ──
        if trig == "preset-capital-protected":
            # Zéro-coupon (approx via cash) + call ATM long → capital garanti + upside
            return [_leg_row(0, "underlying", s, 0),
                    _leg_row(1, "call", s, 1)]
        if trig == "preset-reverse-conv":
            # Long sous-jacent + short put OTM → coupon élevé, risque à la baisse
            return [_leg_row(0, "underlying", s, 1),
                    _leg_row(1, "put", round(s*0.9), 1)]
        if trig == "preset-autocall":
            # Approx : long sous-jacent + short call (plafonne) + short put (barrière)
            return [_leg_row(0, "underlying", s, 1),
                    _leg_row(1, "call", round(s*1.1), 1),
                    _leg_row(2, "put", round(s*0.7), 1)]
        if trig == "preset-bonus":
            # Bonus certificate : long sous-jacent + long put OTM (protection) financé
            return [_leg_row(0, "underlying", s, 1),
                    _leg_row(1, "put", round(s*0.85), 1)]

        # ── Suppression d'un leg précis (par son idx) ──
        if isinstance(trig, dict) and trig.get("type") == "struct-leg-del":
            del_idx = trig["idx"]
            rows = current or []
            kept = []
            for c in rows:
                # L'idx est encodé dans l'id du bouton × de chaque row
                try:
                    row_children = c["props"]["children"][1]["props"]["children"]
                    del_btn = row_children[-1]
                    row_idx = del_btn["props"]["id"]["idx"]
                except Exception:
                    row_idx = None
                if row_idx != del_idx:
                    kept.append(c)
            return kept

        # ── Ajout d'un leg ──
        current = current or []
        idx = len(current)
        current.append(_leg_row(idx, "call", s, 1))
        return current

    # Construire le produit structuré + payoff zoomé
    @app.callback(
        Output("struct-cost", "children"),      Output("struct-maxprofit", "children"),
        Output("struct-maxloss", "children"),   Output("struct-delta", "children"),
        Output("struct-legs-summary", "children"), Output("struct-payoff", "figure"),
        Input("struct-btn", "n_clicks"),
        Input("struct-zoom", "value"),
        State("opt-underlying", "value"),
        State("struct-expiry", "value"),
        State({"type": "struct-leg-kind", "idx": ALL}, "value"),
        State({"type": "struct-leg-side", "idx": ALL}, "value"),
        State({"type": "struct-leg-strike", "idx": ALL}, "value"),
        State({"type": "struct-leg-qty", "idx": ALL}, "value"),
        prevent_initial_call=True,
    )
    def build_structured(n, zoom, symbol, dte, kinds, sides, strikes, qtys):
        if not kinds:
            empty = go.Figure().update_layout(**_layout(400))
            return "—", "—", "—", "—", "Ajoute des composants puis clique Construire.", empty
        try:
            import numpy as np
            from options.strategies.base import OptionLeg, Strategy
            from options.pricing.black_scholes import BlackScholes
            from options.pricing.implied_vol import OptionType

            spot = _chain_for(symbol).spot
            T = float(dte) / 365.0
            rate = 0.03
            vol = 0.25  # vol par défaut ; le pricer réel utilise la surface
            sym = "€"

            legs = []
            for kind, side, strike, qty in zip(kinds, sides, strikes, qtys):
                q = float(qty or 0) * (1 if side == "long" else -1)
                if q == 0:
                    continue
                if kind == "underlying":
                    legs.append(OptionLeg.underlying(quantity=q, premium=spot))
                else:
                    K = float(strike or spot)
                    prem = float(BlackScholes.price(spot, K, T, rate, vol,
                                 option_type=OptionType.parse(kind)))
                    legs.append(OptionLeg.option(kind, K, T, q, prem, vol))

            if not legs:
                empty = go.Figure().update_layout(**_layout(400))
                return "—", "—", "—", "—", "Aucun composant valide.", empty

            strat = Strategy(name="Produit structuré", legs=legs, spot=spot,
                             rate=rate, dividend=0.0)
            cost = strat.net_cost()
            try:    mp = strat.max_profit()
            except Exception: mp = float("nan")
            try:    ml = strat.max_loss()
            except Exception: ml = float("nan")
            g = strat.greeks()

            # ── Grille de payoff avec ZOOM ──
            if zoom == "20":
                lo, hi = spot*0.80, spot*1.20
            elif zoom == "10":
                lo, hi = spot*0.90, spot*1.10
            else:  # auto : autour des strikes + spot
                ks = [float(s) for s, k in zip(strikes, kinds) if k != "underlying" and s] + [spot]
                lo, hi = min(ks)*0.75, max(ks)*1.25
            grid = np.linspace(lo, hi, 400)
            payoff = strat.payoff(grid)
            pnl = payoff - cost

            fig = go.Figure()
            # Zones profit/perte colorées
            fig.add_trace(go.Scatter(x=grid, y=np.maximum(pnl, 0), mode="lines", line=dict(width=0),
                                     fill="tozeroy", fillcolor="rgba(74,222,128,0.15)",
                                     hoverinfo="skip", showlegend=False))
            fig.add_trace(go.Scatter(x=grid, y=np.minimum(pnl, 0), mode="lines", line=dict(width=0),
                                     fill="tozeroy", fillcolor="rgba(248,113,113,0.15)",
                                     hoverinfo="skip", showlegend=False))
            # Courbe P&L
            fig.add_trace(go.Scatter(x=grid, y=pnl, mode="lines", name="P&L net",
                                     line=dict(color=_TEXT, width=2.4),
                                     hovertemplate=f"S_T {sym}%{{x:.1f}}<br>P&L {sym}%{{y:.2f}}<extra></extra>"))
            # Ligne zéro ÉPAISSE et visible (le point clé de ta demande)
            fig.add_hline(y=0, line_color="#4a9eff", line_width=1.5)
            # Spot
            fig.add_vline(x=spot, line_dash="dot", line_color=_MUTED,
                          annotation_text="spot", annotation_font_size=9)
            # Strikes marqués
            for st, k in zip(strikes, kinds):
                if k != "underlying" and st:
                    fig.add_vline(x=float(st), line_dash="dash", line_color="#c9a84c",
                                  annotation_text=f"K={st}", annotation_font_size=8)
            # Break-evens
            try:
                for b in strat.breakevens():
                    if lo <= b <= hi:
                        fig.add_vline(x=b, line_dash="dot", line_color="#4ade80")
            except Exception:
                pass

            lay = _layout(400, "Payoff structuré — P&L net du coût d'entrée")
            # Symétriser l'axe Y autour de 0 pour bien voir les écarts
            ymax = float(np.nanmax(np.abs(pnl))) * 1.15 or 1
            lay["yaxis"]["range"] = [-ymax, ymax]
            lay["yaxis"]["zerolinewidth"] = 2
            fig.update_layout(**lay)

            # Résumé des legs
            leg_desc = []
            for kind, side, strike, qty in zip(kinds, sides, strikes, qtys):
                if not qty:
                    continue
                sign = "+" if side == "long" else "−"
                if kind == "underlying":
                    leg_desc.append(f"{sign}{qty} × sous-jacent @ {sym}{spot:.1f}")
                else:
                    leg_desc.append(f"{sign}{qty} × {kind} K={strike}")
            legs_summary = html.Div([html.Div(d, style={"padding":"3px 0",
                            "borderBottom":"1px solid #141a22"}) for d in leg_desc])

            fmt = lambda x: f"{sym}{x:.2f}" if x == x else "—"  # NaN-safe
            return (fmt(cost), fmt(mp), fmt(ml), f"{g.delta:.3f}",
                    legs_summary, fig)
        except Exception as e:
            logger.error(f"build_structured: {e}", exc_info=True)
            empty = go.Figure().update_layout(**_layout(400))
            return "—", "—", "—", "—", f"Erreur : {e}", empty