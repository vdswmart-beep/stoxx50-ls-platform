# dashboard/callbacks/rebalance_callbacks.py — callbacks de l'onglet Rebalancing

import json
import logging
from dash import Input, Output, State, html
from dash.exceptions import PreventUpdate

logger = logging.getLogger("RebalanceCallbacks")

_GREEN = "#4ade80"; _RED = "#f87171"; _BLUE = "#4a9eff"; _MUTED = "#7090a8"


def register_rebalance_callbacks(app, exec_engine=None):
    dp = app.data_provider
    is_ibkr = exec_engine is not None and hasattr(exec_engine, "is_connected")

    @app.callback(
        Output("rb-summary-card",   "children"),
        Output("rb-orders-table",   "children"),
        Output("rb-orders-store",   "data"),
        Output("rb-execute-zone",   "style"),
        Input("rb-generate-btn",    "n_clicks"),
        State("rb-strategy",        "value"),
        State("rb-capital",         "value"),
        State("rb-topn",            "value"),
        prevent_initial_call=True,
    )
    def generate(n, strategy, capital, top_n):
        if not n:
            raise PreventUpdate
        from execution.rebalancer import (
            compute_target_portfolio, compute_orders, summarize)

        capital = float(capital or 1_000_000)
        top_n = int(top_n or 5)
        strategy = strategy or "hrp"

        # Données
        try:
            returns = dp.get_returns()
        except Exception as e:
            return (_err(f"Erreur données : {e}"), None, None, {"display": "none"})
        if returns is None or returns.empty:
            return (_err("Pas de rendements disponibles."), None, None, {"display": "none"})
        try:
            prices = dp.get_current_prices()
        except Exception:
            prices = {}

        # Portefeuille cible
        try:
            targets = compute_target_portfolio(
                returns, prices, capital=capital, top_n=top_n, strategy=strategy)
        except Exception as e:
            return (_err(f"Erreur calcul cible : {e}"), None, None, {"display": "none"})
        if not targets:
            return (_err("Aucune position cible (prix manquants ?)."), None, None, {"display": "none"})

        # Positions actuelles IBKR
        current = {}
        if is_ibkr and exec_engine.is_connected:
            try:
                current = exec_engine.get_positions()
            except Exception:
                current = {}

        orders = compute_orders(targets, current)
        s = summarize(targets, orders)

        # ── Carte résumé ──
        strat_label = {"hrp": "Multi-facteur + HRP",
                       "multifactor": "Multi-facteur (inverse-vol)",
                       "momentum": "Momentum seul"}.get(strategy, strategy)
        summary_card = html.Div([
            html.Div("PORTEFEUILLE CIBLE", style={"fontSize": "10px", "color": "#7eb8d8",
                     "textTransform": "uppercase", "letterSpacing": ".08em",
                     "fontWeight": "600", "marginBottom": "12px"}),
            html.Div([
                _kpi("Stratégie", strat_label, _BLUE),
                _kpi("Positions", f"{s['n_long']}L / {s['n_short']}S", "#e8f2ff"),
                _kpi("Gross", f"€{s['gross_exposure']:,.0f}", "#e8f2ff"),
                _kpi("Ordres à passer", str(s['n_orders']),
                     "#f0a500" if s['n_orders'] > 0 else _GREEN),
            ], style={"display": "flex", "gap": "32px", "flexWrap": "wrap"}),
            _targets_table(targets),
        ], style={"backgroundColor": "#0f141b", "border": "1px solid #1e2a38",
                  "borderRadius": "8px", "padding": "20px", "marginBottom": "16px"})

        # ── Table des ordres ──
        orders_table = _orders_table(orders)

        orders_data = json.dumps([{
            "ticker": o.ticker, "action": o.action, "qty": o.qty, "reason": o.reason
        } for o in orders])
        show = {"display": "block"} if orders else {"display": "none"}
        return summary_card, orders_table, orders_data, show

    @app.callback(
        Output("rb-execute-status", "children"),
        Input("rb-execute-btn",     "n_clicks"),
        State("rb-orders-store",    "data"),
        prevent_initial_call=True,
    )
    def execute(n, orders_data):
        if not n or not orders_data:
            raise PreventUpdate
        if not (is_ibkr and exec_engine.is_connected):
            return _err("IBKR non connecté — lance en --mode live avec TWS ouvert.")

        from execution.ibkr_live import IBKROrder
        orders = json.loads(orders_data)
        logger.info(f"[Rebalance] Exécution de {len(orders)} ordres...")

        results, n_ok = [], 0
        for od in orders:
            try:
                order = IBKROrder(ticker=od["ticker"], action=od["action"],
                                  qty=int(od["qty"]), order_type="MARKET")
                fill = exec_engine.execute_order(order)
                if fill:
                    n_ok += 1
                    results.append((f"✓ {od['action']} {od['qty']} {od['ticker']} "
                                    f"@ {fill.fill_price:.2f}", _GREEN))
                else:
                    results.append((f"⏳ {od['action']} {od['qty']} {od['ticker']} "
                                    f"— soumis (fill à l'ouverture)", "#f0a500"))
            except Exception as e:
                results.append((f"✗ {od['ticker']} — {e}", _RED))

        head = html.Div(f"Exécution terminée : {n_ok}/{len(orders)} remplis immédiatement.",
                        style={"color": _GREEN if n_ok else "#f0a500",
                               "fontWeight": "600", "marginBottom": "10px"})
        detail = html.Div([html.Div(txt, style={"fontSize": "11px", "color": col,
                          "fontFamily": "monospace", "padding": "2px 0"})
                          for txt, col in results])
        return html.Div([head, detail])


# ── Helpers d'affichage ──────────────────────────────────────────
def _err(msg):
    return html.Div(msg, style={"color": "#f87171", "fontSize": "13px", "padding": "12px 0"})


def _kpi(label, value, color):
    return html.Div([
        html.Div(label, style={"fontSize": "10px", "color": "#7090a8",
                 "textTransform": "uppercase", "marginBottom": "4px"}),
        html.Div(value, style={"fontSize": "20px", "fontWeight": "700", "color": color}),
    ])


def _targets_table(targets):
    header = html.Tr([html.Th(h, style={"textAlign": "left", "padding": "6px 10px",
                      "fontSize": "10px", "color": "#7090a8",
                      "borderBottom": "1px solid #1e2a38"})
                      for h in ["Ticker", "Side", "Qty cible", "Prix", "Notionnel", "Poids"]])
    rows = [header]
    for t in targets:
        color = _GREEN if t.side == "LONG" else _RED
        rows.append(html.Tr([
            html.Td(t.ticker, style={"padding": "5px 10px", "color": _BLUE, "fontSize": "12px"}),
            html.Td(t.side, style={"padding": "5px 10px", "color": color, "fontWeight": "600", "fontSize": "11px"}),
            html.Td(f"{t.target_qty:+,}", style={"padding": "5px 10px", "color": "#e8f2ff", "fontSize": "12px"}),
            html.Td(f"€{t.price:,.2f}", style={"padding": "5px 10px", "color": "#94b8cc", "fontSize": "11px"}),
            html.Td(f"€{t.notional:+,.0f}", style={"padding": "5px 10px", "color": "#94b8cc", "fontSize": "11px"}),
            html.Td(f"{t.weight:+.1%}", style={"padding": "5px 10px", "color": "#7090a8", "fontSize": "11px"}),
        ]))
    return html.Div(html.Table(rows, style={"width": "100%", "borderCollapse": "collapse",
                    "marginTop": "16px"}))


def _orders_table(orders):
    if not orders:
        return html.Div("✓ Portefeuille déjà aligné sur la cible — aucun ordre nécessaire.",
                        style={"color": _GREEN, "fontSize": "13px", "padding": "16px 0"})
    header = html.Tr([html.Th(h, style={"textAlign": "left", "padding": "6px 10px",
                      "fontSize": "10px", "color": "#7090a8",
                      "borderBottom": "1px solid #1e2a38"})
                      for h in ["Action", "Qty", "Ticker", "Raison", "Actuel → Cible"]])
    rows = [header]
    for o in orders:
        color = _GREEN if o.action == "BUY" else _RED
        rows.append(html.Tr([
            html.Td(o.action, style={"padding": "5px 10px", "color": color, "fontWeight": "600", "fontSize": "12px"}),
            html.Td(f"{o.qty:,}", style={"padding": "5px 10px", "color": "#e8f2ff", "fontSize": "12px"}),
            html.Td(o.ticker, style={"padding": "5px 10px", "color": _BLUE, "fontSize": "12px"}),
            html.Td(o.reason, style={"padding": "5px 10px", "color": "#94b8cc", "fontSize": "11px"}),
            html.Td(f"{o.current_qty:+d} → {o.target_qty:+d}", style={"padding": "5px 10px", "color": "#7090a8", "fontSize": "11px"}),
        ]))
    return html.Div(html.Table(rows, style={"width": "100%", "borderCollapse": "collapse"}))