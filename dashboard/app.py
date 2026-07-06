# dashboard/app.py — avec idea_callbacks + watchlist + stop-loss + IBKR

import os
import logging
import inspect
import dash
import dash_bootstrap_components as dbc
from dashboard.layout import build_layout
from dashboard.router  import register_router

logger = logging.getLogger("DashApp")
_ASSET_DIR = os.path.join(os.path.dirname(__file__), "asset")


def _register(label, fn, app, dp):
    try:
        n = len(inspect.signature(fn).parameters)
        fn(app, dp) if n >= 2 else fn(app)
        logger.info(f"✓ {label}")
    except Exception as e:
        logger.warning(f"✗ {label}: {e}")


def build_dashboard(data_provider=None, exec_engine=None, stop_loss_pct=0.06):
    app = dash.Dash(
        __name__,
        assets_folder=_ASSET_DIR,
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
        ],
        suppress_callback_exceptions=True,
        title="NK225 Platform",
    )

    dp = data_provider
    app.__dict__["data_provider"] = dp
    app.__dict__["exec_engine"]   = exec_engine

    app.layout = build_layout(dp)

    import importlib
    for label, module in [
        ("clock_callbacks",   "dashboard.callbacks.clock_callbacks"),
        ("math_callbacks",    "dashboard.callbacks.math_callbacks"),
        ("company_callbacks", "dashboard.callbacks.company_callbacks"),
        ("ai_callbacks",      "dashboard.callbacks.ai_callbacks"),
        ("backtest_callbacks","dashboard.callbacks.backtest_callbacks"),
    ]:
        try:
            mod = importlib.import_module(module)
            fn  = getattr(mod, f"register_{label.replace('_callbacks','')}_callbacks", None)
            if fn: _register(label, fn, app, dp)
        except ImportError as e:
            logger.warning(f"✗ {label}: {e}")

    try:
        from dashboard.callbacks.execution_callbacks import register_execution_callbacks
        register_execution_callbacks(app, dp, exec_engine)
        logger.info("✓ execution_callbacks")
    except Exception as e:
        logger.warning(f"✗ execution_callbacks: {e}")

    try:
        from dashboard.callbacks.rebalance_callbacks import (
            register_rebalance_callbacks, register_strategy_monitor_callbacks)
        register_rebalance_callbacks(app, exec_engine)
        register_strategy_monitor_callbacks(app)
        logger.info("✓ rebalance_callbacks")
    except Exception as e:
        logger.warning(f"✗ rebalance_callbacks: {e}")

    try:
        from dashboard.callbacks.idea_callbacks import (
            register_idea_callbacks, register_stop_loss_callbacks
        )
        register_idea_callbacks(app, dp, exec_engine)
        logger.info("✓ idea_callbacks")
        register_stop_loss_callbacks(app, dp, exec_engine, stop_loss_pct)
        logger.info(f"✓ stop_loss_monitor (-{stop_loss_pct*100:.0f}%)")
    except Exception as e:
        logger.warning(f"✗ idea_callbacks: {e}")

    try:
        from dashboard.callbacks.watchlist_callbacks import register_watchlist_callbacks
        register_watchlist_callbacks(app, dp, exec_engine)
        logger.info("✓ watchlist_callbacks")
    except Exception as e:
        logger.warning(f"✗ watchlist_callbacks: {e}")

    try:
        from dashboard.callbacks.options_callbacks import register_options_callbacks
        register_options_callbacks(app, dp, exec_engine)
        logger.info("✓ options_callbacks")
    except Exception as e:
        logger.warning(f"✗ options_callbacks: {e}")

    register_router(app, dp)
    return app