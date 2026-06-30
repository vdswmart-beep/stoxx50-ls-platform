# dashboard/callbacks/watchlist_callbacks.py — FIXED: IDs sans points, pas de re-render conflict

import logging
from dash import Input, Output, State, html, ctx
from dash.exceptions import PreventUpdate

logger = logging.getLogger("WatchlistCallbacks")


def _safe_id(key: str) -> str:
    """
    Convertit une clé ticker en identifiant Dash valide.
    Dash interdit '.' et '{' dans les IDs. On remplace tout caractère non
    alphanumérique par '-' pour garantir une correspondance exacte entre
    le layout (watchlist.py) et les callbacks.
    """
    return "".join(c if c.isalnum() else "-" for c in str(key))


# Mapping ticker_key → config (clés SANS points, alignées sur la page)
TICKER_CONFIG = {
    "JPM":    {"yf":"JPM",    "currency":"USD","exchange":"SMART"},
    "ISRG":   {"yf":"ISRG",   "currency":"USD","exchange":"SMART"},
    "SPCX":   {"yf":"SPCX",   "currency":"USD","exchange":"SMART"},
    "ENI-MI": {"yf":"ENI.MI", "currency":"EUR","exchange":"BVME"},
}
# Mapping tab_id → ticker_key
TAB_TO_TICKER = {"JPM":"JPM","ISRG":"ISRG","SPCX":"SPCX","ENI-MI":"ENI-MI"}


def register_watchlist_callbacks(app, dp, exec_engine=None):

    @app.callback(
        Output("watchlist-content","children"),
        Input("watchlist-tabs","active_tab"),
        # PAS de watchlist-refresh ici → évite le re-render qui écrase le status
    )
    def render_tab(active_tab):
        from dashboard.pages.watchlist import WATCHLIST, _build_panel
        ticker_key = TAB_TO_TICKER.get(active_tab, active_tab)
        config = WATCHLIST.get(ticker_key,{})
        if not config: return html.Div(f"Ticker {active_tab} non trouvé")
        return _build_panel(ticker_key, config)

    # Enregistrer un callback d'ordre pour chaque ticker
    for ticker_key, meta in TICKER_CONFIG.items():
        _register_order_callback(app, dp, exec_engine, ticker_key, meta)


def _register_order_callback(app, dp, exec_engine, ticker_key, meta):
    """
    Callback d'ordre pour un ticker.
    safe_id via _safe_id() → identique à celui du layout (watchlist.py).
    """
    safe_id = _safe_id(ticker_key)

    @app.callback(
        Output(f"wl-status-{safe_id}", "children"),
        Input(f"wl-buy-{safe_id}",    "n_clicks"),
        Input(f"wl-sell-{safe_id}",   "n_clicks"),
        State(f"wl-qty-{safe_id}",    "value"),
        State(f"wl-type-{safe_id}",   "value"),
        prevent_initial_call=True,
    )
    def execute_order(n_buy, n_sell, qty, order_type,
                      _ticker=ticker_key, _meta=meta):
        triggered = str(ctx.triggered_id or "")
        if not triggered: raise PreventUpdate

        action = "BUY" if f"wl-buy-{_safe_id(_ticker)}" in triggered else "SELL"
        qty    = int(qty or 10)
        sym    = "€" if _meta["currency"] == "EUR" else "$"

        is_ibkr = (exec_engine
                   and hasattr(exec_engine, "is_connected")
                   and exec_engine.is_connected)

        if is_ibkr:
            try:
                from execution.ibkr_live import IBKROrder
                # Pour ENI-MI, utiliser le ticker Yahoo (ENI.MI) ou l'ADR E sur NYSE
                ibkr_ticker = "E" if _ticker == "ENI-MI" else _ticker
                order = IBKROrder(
                    ticker     = ibkr_ticker,
                    action     = action,
                    qty        = qty,
                    order_type = order_type or "MARKET",
                    currency   = _meta["currency"],
                    exchange   = _meta["exchange"],
                )
                fill = exec_engine.execute_order(order)
                if fill:
                    if not hasattr(dp, "_fills"): dp._fills = []
                    dp._fills.append({
                        "ticker":     _ticker,
                        "action":     fill.action,
                        "qty":        fill.qty,
                        "fill_price": fill.fill_price,
                        "commission": fill.commission,
                        "filled_at":  fill.filled_at,
                        "side":       "LONG" if action == "BUY" else "SHORT",
                        "currency":   _meta["currency"],
                    })
                    return html.Div([
                        html.Span(f"✔ IBKR FILL : {action} {qty} × {ibkr_ticker} "
                                  f"@ {sym}{fill.fill_price:,.2f}",
                                  style={"color":"#4ade80","fontWeight":"600","fontSize":"11px"}),
                        html.Span(f" | commission {sym}{fill.commission:.2f}",
                                  style={"color":"#7090a8","fontSize":"10px"}),
                    ])
                # Pas de fill → expliquer pourquoi
                return html.Div([
                    html.Span("⚠ Ordre soumis mais pas encore exécuté. ",
                              style={"color":"#f0a500","fontSize":"11px"}),
                    html.Span("IBKR paper requiert parfois le marché ouvert même avec outsideRth=True pour certains instruments.",
                              style={"color":"#7090a8","fontSize":"10px"}),
                ])

            except Exception as e:
                logger.error(f"IBKR order {_ticker}: {e}")
                return html.Div(f"⚠ IBKR Erreur : {e}",
                                style={"color":"#f87171","fontSize":"11px"})

        # ── Fallback paper trading Python ────────────────────────
        try:
            import yfinance as yf
            data = yf.download(_meta["yf"], period="1d", progress=False,
                               auto_adjust=True, multi_level_index=False)
            if isinstance(data.columns, __import__("pandas").MultiIndex):
                data.columns = data.columns.get_level_values(0)
            curr = float(data["Close"].iloc[-1]) if not data.empty else 100.0
        except Exception:
            curr = 100.0

        if not hasattr(dp, "_fills"): dp._fills = []
        import datetime
        dp._fills.append({
            "ticker":     _ticker,
            "action":     action,
            "qty":        qty,
            "fill_price": curr,
            "commission": qty * 0.005,
            "filled_at":  datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "side":       "LONG" if action == "BUY" else "SHORT",
            "currency":   _meta["currency"],
        })
        return html.Div(
            f"✔ Paper : {action} {qty} × {_ticker} @ {sym}{curr:.2f}",
            style={"color":"#4ade80","fontSize":"11px","fontWeight":"600"},
        )