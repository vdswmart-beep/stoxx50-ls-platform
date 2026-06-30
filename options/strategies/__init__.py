"""Multi-leg option strategies and payoff/Greek analytics."""
from .base import LegKind, OptionLeg, Strategy, as_vol_fn
from .strategies import STRATEGY_REGISTRY, StrategySpec, build_strategy
__all__ = [
    "LegKind", "OptionLeg", "Strategy", "as_vol_fn",
    "StrategySpec", "STRATEGY_REGISTRY", "build_strategy",
]
