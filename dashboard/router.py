# dashboard/router.py — FIXED: gère layout() ET layout(dp)

import inspect
import logging
from dash import Input, Output, html

logger = logging.getLogger("Router")


def _call_layout(layout_fn, dp):
    """
    Appelle layout_fn avec dp si elle l'accepte, sinon sans argument.
    Compatible avec les pages existantes (def layout():)
    et les nouvelles pages (def layout(dp=None):).
    """
    try:
        sig    = inspect.signature(layout_fn)
        n_args = len(sig.parameters)
        if n_args >= 1:
            return layout_fn(dp)
        else:
            return layout_fn()
    except Exception as e:
        logger.error(f"layout() call failed: {e}", exc_info=True)
        return html.Div(
            [html.Div(f"Erreur layout : {type(e).__name__}",
                      style={"color": "#f85149", "fontSize": "13px"}),
             html.Pre(str(e), style={"color": "#8899aa", "fontSize": "11px"})],
            style={"padding": "24px"},
        )


def register_router(app, dp):

    @app.callback(
        Output("page-content", "children"),
        Input("url", "pathname"),
    )
    def route(pathname):
        path = (pathname or "/").rstrip("/") or "/"

        PAGE_MAP = {
            "/":          "dashboard.pages.overview",
            "/research":  "dashboard.pages.research_lab",
            "/ideas":     "dashboard.pages.idea_lab",
            "/math":      "dashboard.pages.math_lab",
            "/ai":        "dashboard.pages.ai_lab",
            "/portfolio": "dashboard.pages.portfolio_lab",
            "/risk":      "dashboard.pages.risk_lab",
            "/backtest":  "dashboard.pages.backtest_lab",
            "/execution": "dashboard.pages.execution_lab",
            "/rebalance": "dashboard.pages.rebalance_lab",
            "/company":   "dashboard.pages.company_analyzer",
            "/watchlist": "dashboard.pages.watchlist",
            "/options":   "dashboard.pages.options_lab",
        }

        module_path = PAGE_MAP.get(path)
        if module_path is None:
            return html.Div(
                [html.H3("404", style={"color": "#f85149"}),
                 html.P(f"Page '{path}' introuvable.",
                        style={"color": "#8899aa"})],
                style={"padding": "40px"},
            )

        try:
            import importlib
            mod = importlib.import_module(module_path)
            return _call_layout(mod.layout, dp)
        except ImportError as e:
            return html.Div(
                f"Module '{module_path}' introuvable : {e}",
                style={"color": "#f85149", "padding": "24px", "fontSize": "12px"},
            )
        except Exception as e:
            logger.error(f"Route '{path}' error: {e}", exc_info=True)
            return html.Div(
                [html.Div(f"Erreur page '{path}'",
                          style={"color": "#f85149", "fontSize": "13px",
                                 "padding": "24px"}),
                 html.Pre(str(e),
                          style={"color": "#8899aa", "fontSize": "11px",
                                 "padding": "0 24px"})],
            )

    # ── Surlignage de la page active dans la sidebar ─────────────────
    @app.callback(
        Output("nav-container", "children"),
        Input("url", "pathname"),
    )
    def highlight_nav(pathname):
        from dashboard.layout import _build_nav
        path = (pathname or "/").rstrip("/") or "/"
        return _build_nav(path)