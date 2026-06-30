"""Concrete option strategies and a registry the dashboard can introspect.

Every builder shares one uniform signature::

    builder(spot, maturity, rate, dividend, vol_fn, strikes, quantity) -> Strategy

where ``vol_fn`` maps a strike to an implied vol (typically sampled from the
volatility smile) and ``strikes`` is a ``dict`` whose keys match the strike
names declared on the strategy's :class:`StrategySpec`.  This uniformity lets
the Flask layer render an input form and call any strategy generically, and
makes adding a new structure a one-function, one-registry-line change.

Entry premiums are the Black-Scholes theoretical values at the supplied vols,
so a freshly built strategy is parity-consistent (e.g. a fiduciary call and a
protective put price to the same net cost and Greeks).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from options.pricing import BlackScholes, OptionType

from .base import OptionLeg, Strategy, as_vol_fn

StrikeMap = Mapping[str, float]
VolFn = Callable[[float], float]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _opt_leg(
    option_type: OptionType,
    strike: float,
    maturity: float,
    quantity: float,
    vol_fn: VolFn,
    spot: float,
    rate: float,
    dividend: float,
) -> OptionLeg:
    """Build an option leg priced at its Black-Scholes theoretical value."""
    vol = float(vol_fn(strike))
    premium = float(
        BlackScholes.price(spot, strike, maturity, rate, vol, dividend, option_type)
    )
    return OptionLeg.option(option_type, strike, maturity, quantity, premium, vol)


def _round(value: float, step: float = 5.0) -> float:
    """Round a strike to a clean tick for default form values."""
    return float(round(value / step) * step)


# --------------------------------------------------------------------------- #
# Builders -- all share the uniform signature
# --------------------------------------------------------------------------- #
def long_call(spot, maturity, rate, dividend, vol_fn, strikes, quantity=1.0) -> Strategy:
    """Long a single call: bullish, limited risk, unlimited upside."""
    k = strikes["strike"]
    leg = _opt_leg(OptionType.CALL, k, maturity, +quantity, vol_fn, spot, rate, dividend)
    return Strategy(
        "Long Call", [leg], spot, rate, dividend,
        "Bullish. Loss limited to the premium; profit unbounded above the strike.",
    )


def long_put(spot, maturity, rate, dividend, vol_fn, strikes, quantity=1.0) -> Strategy:
    """Long a single put: bearish, limited risk."""
    k = strikes["strike"]
    leg = _opt_leg(OptionType.PUT, k, maturity, +quantity, vol_fn, spot, rate, dividend)
    return Strategy(
        "Long Put", [leg], spot, rate, dividend,
        "Bearish. Loss limited to the premium; profit grows as spot falls toward zero.",
    )


def covered_call(spot, maturity, rate, dividend, vol_fn, strikes, quantity=1.0) -> Strategy:
    """Long stock plus a short call: income, capped upside."""
    k = strikes["strike"]
    legs = [
        OptionLeg.underlying(+quantity, spot),
        _opt_leg(OptionType.CALL, k, maturity, -quantity, vol_fn, spot, rate, dividend),
    ]
    return Strategy(
        "Covered Call", legs, spot, rate, dividend,
        "Hold the underlying and sell a call for income. Upside capped at the strike.",
    )


def protective_put(spot, maturity, rate, dividend, vol_fn, strikes, quantity=1.0) -> Strategy:
    """Long stock plus a long put: downside insurance."""
    k = strikes["strike"]
    legs = [
        OptionLeg.underlying(+quantity, spot),
        _opt_leg(OptionType.PUT, k, maturity, +quantity, vol_fn, spot, rate, dividend),
    ]
    return Strategy(
        "Protective Put", legs, spot, rate, dividend,
        "Hold the underlying and buy a put as insurance. Downside floored at the strike.",
    )


def fiduciary_call(spot, maturity, rate, dividend, vol_fn, strikes, quantity=1.0) -> Strategy:
    """Long call plus cash PV(K): the parity twin of a protective put."""
    k = strikes["strike"]
    legs = [
        _opt_leg(OptionType.CALL, k, maturity, +quantity, vol_fn, spot, rate, dividend),
        OptionLeg.cash(face=k, maturity=maturity, rate=rate, quantity=quantity),
    ]
    return Strategy(
        "Fiduciary Call", legs, spot, rate, dividend,
        "Long call financed with a bond paying K at expiry. Equivalent to a protective put.",
    )


def bull_call_spread(spot, maturity, rate, dividend, vol_fn, strikes, quantity=1.0) -> Strategy:
    """Long a lower-strike call, short a higher-strike call: capped bullish."""
    lo, hi = strikes["lower"], strikes["upper"]
    legs = [
        _opt_leg(OptionType.CALL, lo, maturity, +quantity, vol_fn, spot, rate, dividend),
        _opt_leg(OptionType.CALL, hi, maturity, -quantity, vol_fn, spot, rate, dividend),
    ]
    return Strategy(
        "Bull Call Spread", legs, spot, rate, dividend,
        "Bullish debit spread. Both profit and loss are capped by the two strikes.",
    )


def bear_put_spread(spot, maturity, rate, dividend, vol_fn, strikes, quantity=1.0) -> Strategy:
    """Long a higher-strike put, short a lower-strike put: capped bearish."""
    lo, hi = strikes["lower"], strikes["upper"]
    legs = [
        _opt_leg(OptionType.PUT, hi, maturity, +quantity, vol_fn, spot, rate, dividend),
        _opt_leg(OptionType.PUT, lo, maturity, -quantity, vol_fn, spot, rate, dividend),
    ]
    return Strategy(
        "Bear Put Spread", legs, spot, rate, dividend,
        "Bearish debit spread. Both profit and loss are capped by the two strikes.",
    )


def long_butterfly(spot, maturity, rate, dividend, vol_fn, strikes, quantity=1.0) -> Strategy:
    """Long 1 / short 2 / long 1 calls: a bet on low realised movement."""
    lo, mid, hi = strikes["lower"], strikes["middle"], strikes["upper"]
    legs = [
        _opt_leg(OptionType.CALL, lo, maturity, +quantity, vol_fn, spot, rate, dividend),
        _opt_leg(OptionType.CALL, mid, maturity, -2 * quantity, vol_fn, spot, rate, dividend),
        _opt_leg(OptionType.CALL, hi, maturity, +quantity, vol_fn, spot, rate, dividend),
    ]
    return Strategy(
        "Long Call Butterfly", legs, spot, rate, dividend,
        "Neutral. Peak profit if spot pins the middle strike; risk limited to the debit.",
    )


def iron_butterfly(spot, maturity, rate, dividend, vol_fn, strikes, quantity=1.0) -> Strategy:
    """Short ATM straddle financed with a long strangle: a capped short-vol trade."""
    lo, mid, hi = strikes["lower"], strikes["middle"], strikes["upper"]
    legs = [
        _opt_leg(OptionType.CALL, mid, maturity, -quantity, vol_fn, spot, rate, dividend),
        _opt_leg(OptionType.PUT, mid, maturity, -quantity, vol_fn, spot, rate, dividend),
        _opt_leg(OptionType.CALL, hi, maturity, +quantity, vol_fn, spot, rate, dividend),
        _opt_leg(OptionType.PUT, lo, maturity, +quantity, vol_fn, spot, rate, dividend),
    ]
    return Strategy(
        "Iron Butterfly", legs, spot, rate, dividend,
        "Short-vol credit structure. Max profit if spot pins the middle strike; loss capped by the wings.",
    )


def straddle(spot, maturity, rate, dividend, vol_fn, strikes, quantity=1.0) -> Strategy:
    """Long a call and a put at the same strike: a long-vol breakout trade."""
    k = strikes["strike"]
    legs = [
        _opt_leg(OptionType.CALL, k, maturity, +quantity, vol_fn, spot, rate, dividend),
        _opt_leg(OptionType.PUT, k, maturity, +quantity, vol_fn, spot, rate, dividend),
    ]
    return Strategy(
        "Long Straddle", legs, spot, rate, dividend,
        "Long volatility. Profits from a large move in either direction; risk limited to the combined premium.",
    )


def strangle(spot, maturity, rate, dividend, vol_fn, strikes, quantity=1.0) -> Strategy:
    """Long an OTM put and an OTM call: a cheaper long-vol breakout trade."""
    lo, hi = strikes["lower"], strikes["upper"]
    legs = [
        _opt_leg(OptionType.PUT, lo, maturity, +quantity, vol_fn, spot, rate, dividend),
        _opt_leg(OptionType.CALL, hi, maturity, +quantity, vol_fn, spot, rate, dividend),
    ]
    return Strategy(
        "Long Strangle", legs, spot, rate, dividend,
        "Long volatility with OTM wings. Cheaper than a straddle but needs a larger move to pay off.",
    )


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StrategySpec:
    """Metadata describing how to build and parameterise one strategy."""

    key: str
    label: str
    description: str
    strikes: tuple[str, ...]
    builder: Callable[..., Strategy]
    defaults: Callable[[float], dict[str, float]]

    def build(
        self,
        spot: float,
        maturity: float,
        rate: float,
        dividend: float,
        vol: "float | VolFn",
        strikes: StrikeMap | None = None,
        quantity: float = 1.0,
    ) -> Strategy:
        """Construct the strategy, filling any missing strikes with defaults."""
        chosen = dict(self.defaults(spot))
        if strikes:
            chosen.update({k: float(v) for k, v in strikes.items() if v is not None})
        return self.builder(
            spot, maturity, rate, dividend, as_vol_fn(vol), chosen, quantity
        )


def _single(spot: float) -> dict[str, float]:
    return {"strike": _round(spot)}


def _two_wide(spot: float) -> dict[str, float]:
    return {"lower": _round(spot * 0.95), "upper": _round(spot * 1.05)}


def _three_wide(spot: float) -> dict[str, float]:
    return {
        "lower": _round(spot * 0.90),
        "middle": _round(spot),
        "upper": _round(spot * 1.10),
    }


STRATEGY_REGISTRY: dict[str, StrategySpec] = {
    spec.key: spec
    for spec in (
        StrategySpec("long_call", "Long Call",
                     "Single long call.", ("strike",), long_call, _single),
        StrategySpec("long_put", "Long Put",
                     "Single long put.", ("strike",), long_put, _single),
        StrategySpec("covered_call", "Covered Call",
                     "Long underlying + short call.", ("strike",), covered_call, _single),
        StrategySpec("protective_put", "Protective Put",
                     "Long underlying + long put.", ("strike",), protective_put, _single),
        StrategySpec("fiduciary_call", "Fiduciary Call",
                     "Long call + bond PV(K).", ("strike",), fiduciary_call, _single),
        StrategySpec("bull_call_spread", "Bull Call Spread",
                     "Long low call / short high call.", ("lower", "upper"),
                     bull_call_spread, _two_wide),
        StrategySpec("bear_put_spread", "Bear Put Spread",
                     "Long high put / short low put.", ("lower", "upper"),
                     bear_put_spread, _two_wide),
        StrategySpec("long_butterfly", "Long Call Butterfly",
                     "Long 1 / short 2 / long 1 calls.", ("lower", "middle", "upper"),
                     long_butterfly, _three_wide),
        StrategySpec("iron_butterfly", "Iron Butterfly",
                     "Short ATM straddle + long strangle wings.",
                     ("lower", "middle", "upper"), iron_butterfly, _three_wide),
        StrategySpec("straddle", "Long Straddle",
                     "Long call + long put, same strike.", ("strike",), straddle, _single),
        StrategySpec("strangle", "Long Strangle",
                     "Long OTM put + long OTM call.", ("lower", "upper"),
                     strangle, _two_wide),
    )
}


def build_strategy(
    key: str,
    spot: float,
    maturity: float,
    rate: float,
    dividend: float = 0.0,
    vol: "float | VolFn" = 0.25,
    strikes: StrikeMap | None = None,
    quantity: float = 1.0,
) -> Strategy:
    """Look up *key* in the registry and build the corresponding strategy."""
    try:
        spec = STRATEGY_REGISTRY[key]
    except KeyError as exc:  # pragma: no cover - guarded by the UI
        raise KeyError(f"Unknown strategy '{key}'. "
                       f"Available: {', '.join(STRATEGY_REGISTRY)}") from exc
    return spec.build(spot, maturity, rate, dividend, vol, strikes, quantity)