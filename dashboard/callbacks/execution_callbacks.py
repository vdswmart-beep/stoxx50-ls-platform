# dashboard/callbacks/execution_callbacks.py — IBKR real execution + paper fallback

from __future__ import annotations
import json
import logging
import tempfile
import os
from datetime import datetime
from typing import Optional

import pandas as pd
from dash import Input, Output, State, no_update, html, dash_table, dcc
from dash.exceptions import PreventUpdate

logger = logging.getLogger("ExecutionCallbacks")

_BG    = "#0f141b"; _BG2 = "#0a0d12"; _BORDER = "#1e2a38"
_GREEN = "#4ade80"; _RED = "#f87171"; _BLUE = "#4a9eff"
_TEXT  = "#c8d8e8"; _MUTED = "#7090a8"
_TABLE = dict(
    style_table  = {"overflowX":"auto","border":"none"},
    style_header = {"backgroundColor":_BG2,"color":_MUTED,"fontWeight":"500",
                    "fontSize":"10px","textTransform":"uppercase","letterSpacing":".06em",
                    "border":"none","borderBottom":f"1px solid {_BORDER}","padding":"6px 10px"},
    style_cell   = {"backgroundColor":_BG,"color":_TEXT,"fontSize":"11px",
                    "border":"none","borderBottom":f"1px solid {_BG2}","padding":"6px 10px"},
)


def _empty(msg="Aucune donnée"):
    return html.Div(msg, style={"color":_MUTED,"fontSize":"11px","padding":"8px 0"})


def register_execution_callbacks(app, dp, exec_engine=None):
    """
    exec_engine peut être :
    - IBKRLiveEngine  (--mode live, connecté à TWS)
    - PaperTradingEngine (--mode backtest, simulation Python)
    """
    if exec_engine is None:
        try:
            from execution.execution_engine import PaperTradingEngine
            exec_engine = PaperTradingEngine()
        except Exception:
            exec_engine = None

    # Détection du type de moteur
    is_ibkr = hasattr(exec_engine, "is_connected")

    # Cache NAV (évite d'interroger IBKR chaque seconde → contention du lock)
    _nav_cache = {"val": None, "t": 0}

    # ── Badge mode ───────────────────────────────────────────────
    @app.callback(
        Output("exec-mode-badge",   "children"),
        Output("exec-ibkr-status",  "children"),
        Input("exec-refresh-btn",   "n_clicks"),
        Input("clock-interval",     "n_intervals"),
    )
    def update_mode_badge(_clicks, _tick):
        import time
        if is_ibkr and exec_engine.is_connected:
            # NAV mise en cache 30s pour ne pas bloquer sur chaque tick
            now = time.time()
            if _nav_cache["val"] is None or (now - _nav_cache["t"]) > 30:
                try:
                    _nav_cache["val"] = exec_engine.get_account_value()
                    _nav_cache["t"] = now
                except Exception:
                    pass
            nav = _nav_cache["val"]
            nav_str = f"€{nav:,.0f}" if nav else ""
            return "IBKR PAPER", f"✓ Connecté TWS  {nav_str}"
        elif is_ibkr:
            return "IBKR PAPER", "✗ TWS non connecté — paper Python actif"
        return "PAPER TRADING", "Simulation locale Python"

    # ── Prévisualisation ordre ────────────────────────────────────
    @app.callback(
        Output("exec-order-preview", "children"),
        Input("exec-ticker",      "value"),
        Input("exec-action",      "value"),
        Input("exec-order-type",  "value"),
        Input("exec-qty",         "value"),
        Input("exec-limit-price", "value"),
    )
    def preview_order(ticker, action, order_type, qty, limit_price):
        if not ticker or not qty:
            return "Sélectionnez un ticker et une quantité pour prévisualiser l'ordre."
        qty = int(qty)
        action_color = _GREEN if action == "BUY" else _RED

        # Prix de référence : un seul ticker via Yahoo (pas les 50 → pas de blocage)
        ref = 0
        try:
            import yfinance as yf
            h = yf.Ticker(ticker).history(period="2d")
            if not h.empty:
                ref = float(h["Close"].iloc[-1])
        except Exception:
            ref = 0

        # Statut du marché selon le suffixe du ticker
        _SUFFIX_EXCH = {".PA":"SBF",".DE":"XETRA",".AS":"AEB",".MC":"BME",
                        ".MI":"MILAN",".BR":"BRUSSELS",".HE":"HELSINKI"}
        exch = "NYSE"  # défaut US (JPM, AAPL, MSFT sans suffixe)
        for suf, ex in _SUFFIX_EXCH.items():
            if ticker.endswith(suf):
                exch = ex; break
        try:
            from dashboard.utils.market_hours import status_dot as _sd
            mkt_dot = _sd(exch)
        except Exception:
            mkt_dot = html.Span()

        notional = qty * (float(limit_price) if limit_price else ref)
        parts = [
            html.Span(f"{action} ", style={"color":action_color,"fontWeight":"700"}),
            html.Span(f"{qty:,} × "),
            html.Span(f"{ticker} ", style={"color":_BLUE,"fontWeight":"600"}),
            html.Span("@ "),
        ]
        if order_type == "LIMIT" and limit_price:
            parts.append(html.Span(f"LIMIT €{float(limit_price):,.0f}",
                                   style={"color":"#f0a500","fontWeight":"600"}))
        else:
            parts.append(html.Span("MARKET", style={"color":_MUTED}))
        if notional > 0:
            parts.append(html.Span(f"  |  Notionnel estimé : €{notional:,.0f}",
                                   style={"color":_MUTED,"marginLeft":"8px"}))
        # Avertissement IBKR
        if is_ibkr and exec_engine.is_connected:
            parts.append(html.Span(" → IBKR PAPER",
                                   style={"color":_GREEN,"fontSize":"10px","marginLeft":"8px"}))
        # Ligne statut marché
        return html.Div([
            html.Div(parts),
            html.Div([
                html.Span("Marché : ", style={"fontSize":"10px","color":_MUTED,"marginRight":"4px"}),
                mkt_dot,
            ], style={"marginTop":"8px","display":"flex","alignItems":"center"}),
        ])

    # ── Valider ordre ─────────────────────────────────────────────
    @app.callback(
        Output("exec-submit-status", "children"),
        Output("exec-fills-store",   "data"),
        Input("exec-submit-btn",     "n_clicks"),
        State("exec-ticker",         "value"),
        State("exec-action",         "value"),
        State("exec-order-type",     "value"),
        State("exec-qty",            "value"),
        State("exec-limit-price",    "value"),
        State("exec-fills-store",    "data"),
        prevent_initial_call=True,
    )
    def submit_order(n, ticker, action, order_type, qty, limit_price, fills_data):
        if not n or not ticker or not qty:
            raise PreventUpdate

        logger.info(f"[Execution UI] Clic Valider : {action} {qty} {ticker} ({order_type})")

        # Prix de référence : UNIQUEMENT pour le paper Python (pas pour IBKR,
        # qui récupère son propre prix). On évite de télécharger les 50 tickers.
        ref = 1000.0
        if not (is_ibkr and exec_engine.is_connected):
            try:
                import yfinance as yf
                h = yf.Ticker(ticker).history(period="2d")
                if not h.empty:
                    ref = float(h["Close"].iloc[-1])
            except Exception:
                ref = 1000.0

        current = json.loads(fills_data) if fills_data else []

        # ── IBKR live ────────────────────────────────────────────
        if is_ibkr and exec_engine.is_connected:
            try:
                from execution.ibkr_live import IBKROrder
                order = IBKROrder(
                    ticker     = ticker,
                    action     = action,
                    qty        = int(qty),
                    order_type = order_type,
                    limit_price= float(limit_price) if limit_price else None,
                )
                logger.info(f"[Execution UI] → appel execute_order pour {ticker}...")
                fill = exec_engine.execute_order(order)
                logger.info(f"[Execution UI] ← execute_order retourné : fill={fill is not None}")
                if fill:
                    fill_dict = {
                        "order_id":   fill.order_id,
                        "time":       fill.filled_at,
                        "ticker":     fill.ticker,
                        "action":     fill.action,
                        "qty":        fill.qty,
                        "fill_price": fill.fill_price,
                        "notional":   round(fill.qty * fill.fill_price),
                        "commission": fill.commission,
                        "status":     "IBKR FILL",
                    }
                    current.append(fill_dict)
                    # Stocker dans dp pour l'overview
                    if not hasattr(dp, "_fills"): dp._fills = []
                    dp._fills.append(fill_dict)

                    status = html.Div([
                        html.Span("✔ IBKR FILL : ", style={"color":_GREEN}),
                        html.Span(f"{fill.action} {fill.qty:,} × {fill.ticker} "
                                  f"@ €{fill.fill_price:,.0f}",
                                  style={"color":_TEXT,"fontWeight":"600"}),
                        html.Span(f" | Commission €{fill.commission:.0f}",
                                  style={"color":_MUTED}),
                    ], style={"fontSize":"12px"})
                    return status, json.dumps(current)
                else:
                    return html.Div("⚠ IBKR : ordre non exécuté (marché fermé ?)",
                                    style={"color":"#f0a500","fontSize":"12px"}), fills_data
            except Exception as e:
                logger.error(f"IBKR order error: {e}")
                return html.Div(f"⚠ IBKR Erreur : {e}",
                                style={"color":_RED,"fontSize":"12px"}), fills_data

        # ── Paper trading Python ──────────────────────────────────
        try:
            from execution.execution_engine import Order
            order = Order(
                ticker     = ticker,
                action     = action,
                qty        = int(qty),
                order_type = order_type,
                limit_price= float(limit_price) if limit_price else None,
                side       = "LONG" if action in ("BUY","COVER") else "SHORT",
            )
            fill = exec_engine.execute_order(order, ref)
            if fill:
                fill_dict = {
                    "order_id":   fill.order_id,
                    "time":       fill.filled_at,
                    "ticker":     fill.ticker,
                    "action":     fill.action,
                    "qty":        fill.qty,
                    "fill_price": fill.fill_price,
                    "notional":   round(fill.qty * fill.fill_price),
                    "commission": fill.commission,
                    "slippage":   fill.slippage,
                    "status":     "PAPER",
                }
                current.append(fill_dict)
                if not hasattr(dp, "_fills"): dp._fills = []
                dp._fills.append(fill_dict)
                status = html.Div([
                    html.Span("✔ Exécuté (paper) : ", style={"color":_GREEN}),
                    html.Span(f"{fill.action} {fill.qty:,} × {fill.ticker} @ €{fill.fill_price:,.0f}",
                              style={"color":_TEXT,"fontWeight":"600"}),
                ], style={"fontSize":"12px"})
                return status, json.dumps(current)
        except Exception as e:
            logger.error(f"Paper order: {e}")

        return html.Div("⚠ Ordre non exécuté", style={"color":_RED,"fontSize":"12px"}), fills_data

    # ── Blotter ───────────────────────────────────────────────────
    @app.callback(
        Output("exec-blotter-table",   "children"),
        Output("exec-blotter-summary", "children"),
        Input("exec-fills-store",      "data"),
        Input("exec-refresh-btn",      "n_clicks"),
    )
    def update_blotter(fills_data, _):
        # Merge fills Python + fills IBKR
        fills = json.loads(fills_data) if fills_data else []
        if is_ibkr and exec_engine.is_connected:
            try:
                ibkr_fills = exec_engine.get_fills()
                for f in ibkr_fills:
                    fills.append({
                        "order_id":f.order_id,"time":f.filled_at,"ticker":f.ticker,
                        "action":f.action,"qty":f.qty,"fill_price":f.fill_price,
                        "notional":round(f.qty*f.fill_price),"commission":f.commission,
                        "status":"IBKR",
                    })
            except Exception:
                pass

        if not fills:
            return _empty("Aucun ordre exécuté"), ""

        df = pd.DataFrame(fills).sort_values("time", ascending=False)
        total_notional = df["notional"].sum()
        table = dash_table.DataTable(
            columns=[{"name":c.upper().replace("_"," "),"id":c} for c in df.columns],
            data=df.round(2).to_dict("records"),
            page_size=10, sort_action="native",
            **_TABLE,
            style_data_conditional=[
                {"if":{"filter_query":"{action} = 'BUY'","column_id":"action"},"color":_GREEN},
                {"if":{"filter_query":"{action} = 'SELL'","column_id":"action"},"color":_RED},
                {"if":{"filter_query":"{status} = 'IBKR'","column_id":"status"},"color":"#4a9eff"},
            ],
        )
        return table, f"{len(df)} fills | Notionnel €{total_notional:,.0f}"

    # ── Positions (IBKR ou paper) ─────────────────────────────────
    @app.callback(
        Output("exec-positions-table", "children"),
        Input("exec-refresh-btn",      "n_clicks"),
        Input("exec-fills-store",      "data"),
    )
    def update_positions(_, __):
        # Positions IBKR réelles
        if is_ibkr and exec_engine.is_connected:
            try:
                positions = exec_engine.get_positions()
                if positions:
                    rows = [{"ticker":t, "qty":q,
                             "side":"LONG" if q>0 else "SHORT"}
                            for t,q in positions.items() if q != 0]
                    if rows:
                        df = pd.DataFrame(rows)
                        return dash_table.DataTable(
                            columns=[{"name":c.upper(),"id":c} for c in df.columns],
                            data=df.to_dict("records"),
                            **_TABLE,
                            style_data_conditional=[
                                {"if":{"filter_query":"{side} = 'LONG'","column_id":"side"},"color":_GREEN},
                                {"if":{"filter_query":"{side} = 'SHORT'","column_id":"side"},"color":_RED},
                            ],
                        )
            except Exception as e:
                logger.warning(f"IBKR positions: {e}")

        # Fallback paper
        try:
            positions = exec_engine.get_positions()
            if not positions:
                return _empty("Aucune position ouverte")
            rows = [{"ticker":t,"qty":q,"side":"LONG" if q>0 else "SHORT"}
                    for t,q in positions.items() if q != 0]
            if not rows:
                return _empty("Aucune position ouverte")
            df = pd.DataFrame(rows)
            return dash_table.DataTable(
                columns=[{"name":c.upper(),"id":c} for c in df.columns],
                data=df.to_dict("records"), **_TABLE,
            )
        except Exception:
            return _empty("Aucune position")

    # ── Deltas ────────────────────────────────────────────────────
    @app.callback(
        Output("exec-delta-table",  "children"),
        Input("exec-refresh-btn",   "n_clicks"),
    )
    def update_deltas(_):
        target = getattr(dp, "target_weights", {})
        if not target:
            return _empty("Aucun poids cible — lancez le Backtest d'abord")
        try:
            current = exec_engine.get_positions() if exec_engine else {}
        except Exception:
            current = {}
        rows = [{"ticker":t,"target_w":f"{w:.2%}","current_qty":current.get(t,0),
                 "action":"BUY" if w>0 else "SELL"}
                for t,w in target.items()]
        if not rows:
            return _empty()
        df = pd.DataFrame(rows)
        return dash_table.DataTable(
            columns=[{"name":c.upper().replace("_"," "),"id":c} for c in df.columns],
            data=df.to_dict("records"), **_TABLE,
            style_data_conditional=[
                {"if":{"filter_query":"{action} = 'BUY'","column_id":"action"},"color":_GREEN},
                {"if":{"filter_query":"{action} = 'SELL'","column_id":"action"},"color":_RED},
            ],
        )

    # ── Export ────────────────────────────────────────────────────
    @app.callback(
        Output("exec-download", "data"),
        Input("exec-export-btn", "n_clicks"),
        State("exec-fills-store", "data"),
        prevent_initial_call=True,
    )
    def export_blotter(n, fills_data):
        if not n or not fills_data: raise PreventUpdate
        try:
            df = pd.DataFrame(json.loads(fills_data))
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                path = tmp.name
            with pd.ExcelWriter(path, engine="openpyxl") as w:
                df.to_excel(w, sheet_name="Blotter", index=False)
            with open(path,"rb") as f: data = f.read()
            os.unlink(path)
            return dcc.send_bytes(data, f"blotter_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
        except Exception as e:
            raise PreventUpdate


    # ═══════════════ BOUCLE STRATÉGIE → EXÉCUTION ═══════════════

    @app.callback(
        Output("rebal-summary",       "children"),
        Output("rebal-orders-table",  "children"),
        Output("rebal-orders-store",  "data"),
        Output("rebal-execute-row",   "style"),
        Input("rebal-generate-btn",   "n_clicks"),
        State("rebal-capital",        "value"),
        prevent_initial_call=True,
    )
    def generate_target(n, capital):
        if not n:
            raise PreventUpdate
        import json as _json
        from execution.rebalancer import (
            compute_target_portfolio, compute_orders, summarize)
        capital = float(capital or 1_000_000)

        # Rendements + prix actuels
        try:
            returns = dp.get_returns()
        except Exception as e:
            return html.Span(f"Erreur données : {e}", style={"color": "#f87171"}), None, None, {"display": "none"}
        if returns is None or returns.empty:
            return html.Span("Pas de données de rendements disponibles.",
                             style={"color": "#f87171"}), None, None, {"display": "none"}

        try:
            prices = dp.get_current_prices()
        except Exception:
            prices = {}

        # Portefeuille cible
        targets = compute_target_portfolio(returns, prices, capital=capital, top_n=5)
        if not targets:
            return html.Span("Aucune position cible générée (prix manquants ?).",
                             style={"color": "#f0a500"}), None, None, {"display": "none"}

        # Positions actuelles (IBKR si live, sinon vide)
        current = {}
        try:
            if is_ibkr and exec_engine.is_connected:
                current = exec_engine.get_positions()
        except Exception:
            current = {}

        orders = compute_orders(targets, current)
        s = summarize(targets, orders)

        # Résumé
        summary = html.Div([
            html.Span(f"Portefeuille cible : ", style={"color": "#94b8cc"}),
            html.Span(f"{s['n_long']} longs / {s['n_short']} shorts", style={"color": "#e8f2ff", "fontWeight": "600"}),
            html.Span(f"  ·  Gross : €{s['gross_exposure']:,.0f}", style={"color": "#94b8cc"}),
            html.Span(f"  ·  {s['n_orders']} ordres à passer", style={"color": "#f0a500", "fontWeight": "600"}),
        ])

        # Table des ordres
        if orders:
            header = html.Tr([html.Th(h, style={"textAlign": "left", "padding": "4px 8px",
                              "fontSize": "10px", "color": "#7090a8", "borderBottom": "1px solid #1e2a38"})
                              for h in ["Action", "Qty", "Ticker", "Raison", "Actuel→Cible"]])
            rows = [header]
            for o in orders:
                color = "#4ade80" if o.action == "BUY" else "#f87171"
                rows.append(html.Tr([
                    html.Td(o.action, style={"padding": "4px 8px", "color": color, "fontWeight": "600", "fontSize": "11px"}),
                    html.Td(f"{o.qty:,}", style={"padding": "4px 8px", "color": "#e8f2ff", "fontSize": "11px"}),
                    html.Td(o.ticker, style={"padding": "4px 8px", "color": "#4a9eff", "fontSize": "11px"}),
                    html.Td(o.reason, style={"padding": "4px 8px", "color": "#94b8cc", "fontSize": "10px"}),
                    html.Td(f"{o.current_qty:+d} → {o.target_qty:+d}", style={"padding": "4px 8px", "color": "#7090a8", "fontSize": "10px"}),
                ]))
            table = html.Table(rows, style={"width": "100%", "borderCollapse": "collapse"})
        else:
            table = html.Div("✓ Portefeuille déjà aligné sur la cible — aucun ordre nécessaire.",
                             style={"color": "#4ade80", "fontSize": "12px", "padding": "10px 0"})

        # Sérialiser les ordres pour l'exécution
        orders_data = _json.dumps([{
            "ticker": o.ticker, "action": o.action, "qty": o.qty, "reason": o.reason
        } for o in orders])

        show_exec = {"display": "block"} if orders else {"display": "none"}
        return summary, table, orders_data, show_exec

    @app.callback(
        Output("rebal-execute-status", "children"),
        Input("rebal-execute-btn",     "n_clicks"),
        State("rebal-orders-store",    "data"),
        prevent_initial_call=True,
    )
    def execute_rebalance(n, orders_data):
        if not n or not orders_data:
            raise PreventUpdate
        import json as _json
        if not (is_ibkr and exec_engine.is_connected):
            return html.Span("IBKR non connecté — lance en --mode live avec TWS ouvert.",
                             style={"color": "#f87171"})

        from execution.ibkr_live import IBKROrder
        orders = _json.loads(orders_data)
        logger.info(f"[Rebalance] Exécution de {len(orders)} ordres...")

        results = []
        n_ok = 0
        for od in orders:
            try:
                order = IBKROrder(ticker=od["ticker"], action=od["action"],
                                  qty=int(od["qty"]), order_type="MARKET")
                fill = exec_engine.execute_order(order)
                if fill:
                    n_ok += 1
                    results.append(f"✓ {od['action']} {od['qty']} {od['ticker']} @ {fill.fill_price:.2f}")
                else:
                    results.append(f"⏳ {od['action']} {od['qty']} {od['ticker']} — soumis (fill à l'ouverture)")
            except Exception as e:
                results.append(f"✗ {od['ticker']} — erreur : {e}")

        summary_line = html.Div(f"Exécution terminée : {n_ok}/{len(orders)} remplis immédiatement.",
                                style={"color": "#4ade80" if n_ok > 0 else "#f0a500",
                                       "fontWeight": "600", "marginBottom": "8px"})
        detail = html.Div([html.Div(r, style={"fontSize": "10px", "color": "#94b8cc",
                          "fontFamily": "monospace"}) for r in results])
        return html.Div([summary_line, detail])