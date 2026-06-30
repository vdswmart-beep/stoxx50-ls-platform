# dashboard/callbacks/idea_callbacks.py — Click detail + exécution IBKR + stop-loss

import logging
from dash import Input, Output, State, html, ALL, ctx, no_update
from dash.exceptions import PreventUpdate

logger = logging.getLogger("IdeaCallbacks")


def register_idea_callbacks(app, dp, exec_engine=None):

    # ── Clic sur une carte → fiche complète ──────────────────────
    @app.callback(
        Output("idea-detail-panel",   "children"),
        Output("idea-selected-store", "data"),
        Input({"type":"idea-card","ticker":ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def show_detail(n_clicks_list):
        if not any(n_clicks_list):
            raise PreventUpdate

        # Trouver quelle carte a été cliquée
        triggered = ctx.triggered_id
        if not triggered or not isinstance(triggered, dict):
            raise PreventUpdate

        ticker = triggered.get("ticker")
        if not ticker:
            raise PreventUpdate

        try:
            from dashboard.pages.idea_lab import _full_detail
            ideas = dp.get_trade_ideas()
            if hasattr(ideas, "to_dict"):
                ideas = ideas.to_dict("records")
            idea = next((i for i in ideas if i.get("ticker") == ticker), None)
            if not idea:
                return html.Div(f"Idée {ticker} non trouvée", style={"color":"#f87171"}), None
            detail = _full_detail(idea, dp)
            # Scroll vers le bas
            return detail, ticker
        except Exception as e:
            logger.error(f"show_detail {ticker}: {e}", exc_info=True)
            return html.Div(f"Erreur : {e}", style={"color":"#f87171","fontSize":"11px"}), None

    # ── Exécution IBKR depuis la fiche ───────────────────────────
    @app.callback(
        Output("idea-exec-status", "children"),
        Input("idea-exec-btn",     "n_clicks"),
        State("idea-exec-ticker",  "data"),
        State("idea-exec-side",    "data"),
        State("idea-exec-qty",     "value"),
        State("idea-exec-type",    "value"),
        prevent_initial_call=True,
    )
    def execute_idea(n, ticker, side, qty, order_type):
        if not n or not ticker:
            raise PreventUpdate

        action = "BUY" if side == "LONG" else "SELL"
        qty    = int(qty or 100)

        try:
            prices = dp.get_current_prices()
            ref    = float(prices.get(ticker, 1000))
        except Exception:
            ref = 1000.0

        # IBKR réel
        is_ibkr = exec_engine and hasattr(exec_engine, "is_connected") and exec_engine.is_connected
        if is_ibkr:
            try:
                from execution.ibkr_live import IBKROrder
                order = IBKROrder(ticker=ticker, action=action, qty=qty,
                                  order_type=order_type)
                fill  = exec_engine.execute_order(order)
                if fill:
                    # Enregistrer dans dp
                    fill_dict = {"ticker":fill.ticker,"action":fill.action,"qty":fill.qty,
                                 "fill_price":fill.fill_price,"commission":fill.commission,
                                 "filled_at":fill.filled_at,"side":side}
                    if not hasattr(dp,"_fills"): dp._fills = []
                    dp._fills.append(fill_dict)
                    return html.Div([
                        html.Span("✔ IBKR FILL : ", style={"color":"#4ade80","fontWeight":"700"}),
                        html.Span(f"{action} {qty:,} × {ticker} @ ¥{fill.fill_price:,.0f}",
                                  style={"color":"#c8d8e8"}),
                    ])
                return html.Div("⚠ Ordre non exécuté (marché fermé ?)",
                                style={"color":"#f0a500"})
            except Exception as e:
                logger.error(f"IBKR exec: {e}")
                return html.Div(f"⚠ IBKR Erreur : {e}", style={"color":"#f87171"})

        # Paper local
        try:
            from execution.execution_engine import Order
            order = Order(ticker=ticker, action=action, qty=qty,
                          order_type=order_type, side=side)
            fill  = exec_engine.execute_order(order, ref) if exec_engine else None
            if fill:
                if not hasattr(dp,"_fills"): dp._fills = []
                dp._fills.append({"ticker":fill.ticker,"action":fill.action,"qty":fill.qty,
                                   "fill_price":fill.fill_price,"side":side})
                return html.Div([
                    html.Span("✔ Paper : ", style={"color":"#4ade80"}),
                    html.Span(f"{action} {qty:,} × {ticker} @ ¥{fill.fill_price:,.0f}"),
                ])
        except Exception as e:
            logger.error(f"Paper exec: {e}")

        return html.Div("⚠ Moteur d'exécution non disponible", style={"color":"#f0a500"})


def register_stop_loss_callbacks(app, dp, exec_engine=None, stop_loss_pct=0.06):
    """
    Monitor automatique de stop-loss.
    Vérifie toutes les 60 secondes les positions ouvertes.
    Si P&L < -stop_loss_pct → ferme automatiquement via IBKR ou paper.
    """

    @app.callback(
        Output("stop-loss-log", "children"),
        Input("stop-loss-interval", "n_intervals"),
    )
    def monitor_stop_losses(n):
        if not n:
            raise PreventUpdate

        fills = getattr(dp, "_fills", [])
        if not fills:
            return no_update

        try:
            current_prices = dp.get_current_prices()
        except Exception:
            return no_update

        triggered = []
        for fill in fills:
            ticker     = fill.get("ticker")
            side       = fill.get("side","LONG")
            fill_price = fill.get("fill_price", 0)
            qty        = fill.get("qty", 0)
            curr_price = current_prices.get(ticker)

            if not curr_price or not fill_price or not qty:
                continue

            # P&L par position
            if side == "LONG":
                pnl_pct = (curr_price - fill_price) / fill_price
            else:
                pnl_pct = (fill_price - curr_price) / fill_price

            if pnl_pct < -stop_loss_pct:
                # DÉCLENCHER LE STOP-LOSS
                close_action = "SELL" if side == "LONG" else "BUY"
                logger.warning(
                    f"⛔ STOP-LOSS DÉCLENCHÉ : {ticker} | "
                    f"P&L {pnl_pct:.2%} < -{stop_loss_pct:.0%} | "
                    f"Fermeture automatique {close_action} {qty}"
                )

                is_ibkr = (exec_engine and hasattr(exec_engine,"is_connected")
                           and exec_engine.is_connected)
                try:
                    if is_ibkr:
                        from execution.ibkr_live import IBKROrder
                        order = IBKROrder(ticker=ticker, action=close_action,
                                          qty=qty, order_type="MARKET")
                        exec_engine.execute_order(order)
                    else:
                        from execution.execution_engine import Order
                        order = Order(ticker=ticker, action=close_action, qty=qty,
                                      order_type="MARKET", side=side)
                        exec_engine.execute_order(order, curr_price)

                    triggered.append(
                        html.Div([
                            html.Span(f"⛔ STOP-LOSS {ticker} ",
                                      style={"color":"#f87171","fontWeight":"700"}),
                            html.Span(f"{pnl_pct:.2%} → {close_action} automatique",
                                      style={"color":"#c8d8e8"}),
                        ], style={"marginBottom":"4px","fontSize":"11px"})
                    )
                    # Retirer du registre des fills
                    dp._fills = [f for f in dp._fills if f.get("ticker") != ticker]

                except Exception as e:
                    logger.error(f"Stop-loss execution {ticker}: {e}")

        return triggered if triggered else no_update