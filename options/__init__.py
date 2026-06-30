"""Options analytics package — European option pricing for the STOXX 50."""
from .option_chain import OptionChain
from .mock_provider import MockProvider, get_option_chain, TICKER_MARKET
from .ibkr_provider import IBKRProvider
from .pricing import (
    BlackScholes, BSParams, Greeks, OptionType,
    ImpliedVolatilitySolver, check_put_call_parity,
)
from .volatility import VolatilitySurface, SurfaceGrid
from .strategies import STRATEGY_REGISTRY, build_strategy

__all__ = [
    "OptionChain", "MockProvider", "IBKRProvider", "get_option_chain", "TICKER_MARKET",
    "BlackScholes", "BSParams", "Greeks", "OptionType",
    "ImpliedVolatilitySolver", "check_put_call_parity",
    "VolatilitySurface", "SurfaceGrid",
    "STRATEGY_REGISTRY", "build_strategy",
]
