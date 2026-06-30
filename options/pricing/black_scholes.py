"""Analytic Black-Scholes-Merton pricing engine for European options.

The module is intentionally framework-agnostic: it depends only on NumPy and
SciPy and never imports anything from the data, web or strategy layers.  Every
public function accepts plain ``float`` *or* NumPy arrays for the spot / vol /
time arguments, which makes it trivial to build payoff curves and Greek
profiles without writing explicit loops.

Conventions
-----------
* ``maturity`` (``T``) is expressed in **years**.
* ``rate`` (``r``) and ``dividend`` (``q``) are **continuously compounded**
  annual rates.
* ``vol`` (``sigma``) is the annualised volatility expressed as a decimal
  (``0.30`` means 30 %).
* Greeks are returned in their *raw* analytic units:
    - ``vega``  : sensitivity to a **1.00** (i.e. 100 vol-point) move in sigma.
    - ``theta`` : sensitivity per **year**.
    - ``rho``   : sensitivity to a **1.00** (i.e. 100 bp x 100) move in rate.
  The presentation layer rescales these into the trader-friendly figures
  (vega / rho per 1 %, theta per calendar day) via :class:`Greeks`.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.stats import norm

__all__ = [
    "OptionType",
    "BSParams",
    "Greeks",
    "BlackScholes",
]

_SQRT_EPS: Final[float] = 1e-12
_DAYS_PER_YEAR: Final[float] = 365.0


class OptionType(str, Enum):
    """Enumeration of the two European option flavours."""

    CALL = "call"
    PUT = "put"

    @classmethod
    def parse(cls, value: "str | OptionType") -> "OptionType":
        """Coerce a free-form string (``"C"``, ``"put"``, ...) into the enum."""
        if isinstance(value, OptionType):
            return value
        token = str(value).strip().lower()
        if token in {"c", "call"}:
            return cls.CALL
        if token in {"p", "put"}:
            return cls.PUT
        raise ValueError(f"Unknown option type: {value!r}")

    @property
    def sign(self) -> int:
        """+1 for a call, -1 for a put (handy in unified formulae)."""
        return 1 if self is OptionType.CALL else -1


@dataclass(frozen=True)
class BSParams:
    """Immutable bundle of Black-Scholes inputs for a single option."""

    spot: float
    strike: float
    maturity: float
    rate: float
    vol: float
    dividend: float = 0.0
    option_type: OptionType = OptionType.CALL


@dataclass(frozen=True)
class Greeks:
    """Container for a price together with its first-order Greeks.

    The raw analytic values are stored; the convenience properties expose the
    figures in the units an equity-derivatives desk actually quotes.
    """

    price: float
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float

    @property
    def vega_per_pct(self) -> float:
        """Vega per **1 %** absolute change in volatility."""
        return self.vega / 100.0

    @property
    def theta_per_day(self) -> float:
        """Theta per **calendar day** (the desk's daily decay)."""
        return self.theta / _DAYS_PER_YEAR

    @property
    def rho_per_pct(self) -> float:
        """Rho per **1 %** absolute change in the risk-free rate."""
        return self.rho / 100.0

    def as_dict(self, *, desk_units: bool = True) -> dict[str, float]:
        """Serialise the Greeks to a plain dict.

        Parameters
        ----------
        desk_units:
            When ``True`` (default) vega / rho are reported per 1 % and theta
            per day; otherwise the raw analytic units are returned.
        """
        if desk_units:
            return {
                "price": float(self.price),
                "delta": float(self.delta),
                "gamma": float(self.gamma),
                "vega": float(self.vega_per_pct),
                "theta": float(self.theta_per_day),
                "rho": float(self.rho_per_pct),
            }
        return {
            "price": float(self.price),
            "delta": float(self.delta),
            "gamma": float(self.gamma),
            "vega": float(self.vega),
            "theta": float(self.theta),
            "rho": float(self.rho),
        }


class BlackScholes:
    """Stateless collection of Black-Scholes-Merton formulae.

    All methods are ``@staticmethod`` so the class behaves as a namespace.  The
    array-friendly implementation means a single call can price an entire grid
    of spots or volatilities at once.
    """

    # ------------------------------------------------------------------ #
    # Core building blocks
    # ------------------------------------------------------------------ #
    @staticmethod
    def d1(
        spot: ArrayLike,
        strike: ArrayLike,
        maturity: ArrayLike,
        rate: float,
        vol: ArrayLike,
        dividend: float = 0.0,
    ) -> NDArray[np.float64]:
        """First Black-Scholes auxiliary variable ``d1``."""
        spot = np.asarray(spot, dtype=float)
        strike = np.asarray(strike, dtype=float)
        maturity = np.asarray(maturity, dtype=float)
        vol = np.asarray(vol, dtype=float)
        denom = vol * np.sqrt(np.maximum(maturity, _SQRT_EPS))
        denom = np.where(denom <= _SQRT_EPS, np.nan, denom)
        return (
            np.log(spot / strike)
            + (rate - dividend + 0.5 * vol**2) * maturity
        ) / denom

    @staticmethod
    def d2(
        spot: ArrayLike,
        strike: ArrayLike,
        maturity: ArrayLike,
        rate: float,
        vol: ArrayLike,
        dividend: float = 0.0,
    ) -> NDArray[np.float64]:
        """Second Black-Scholes auxiliary variable ``d2 = d1 - sigma*sqrt(T)``."""
        vol = np.asarray(vol, dtype=float)
        maturity = np.asarray(maturity, dtype=float)
        return BlackScholes.d1(
            spot, strike, maturity, rate, vol, dividend
        ) - vol * np.sqrt(np.maximum(maturity, _SQRT_EPS))

    # ------------------------------------------------------------------ #
    # Price
    # ------------------------------------------------------------------ #
    @staticmethod
    def price(
        spot: ArrayLike,
        strike: ArrayLike,
        maturity: ArrayLike,
        rate: float,
        vol: ArrayLike,
        dividend: float = 0.0,
        option_type: OptionType = OptionType.CALL,
    ) -> NDArray[np.float64]:
        """Black-Scholes-Merton price of a European option.

        Degenerate inputs (``T <= 0`` or ``sigma <= 0``) collapse to the
        discounted intrinsic value of the forward, which keeps payoff diagrams
        well-behaved at the expiry boundary.
        """
        option_type = OptionType.parse(option_type)
        spot = np.asarray(spot, dtype=float)
        strike = np.asarray(strike, dtype=float)
        maturity = np.asarray(maturity, dtype=float)
        vol = np.asarray(vol, dtype=float)

        disc_r = np.exp(-rate * maturity)
        disc_q = np.exp(-dividend * maturity)

        _d1 = BlackScholes.d1(spot, strike, maturity, rate, vol, dividend)
        _d2 = _d1 - vol * np.sqrt(np.maximum(maturity, _SQRT_EPS))

        if option_type is OptionType.CALL:
            value = spot * disc_q * norm.cdf(_d1) - strike * disc_r * norm.cdf(_d2)
            intrinsic = np.maximum(spot * disc_q - strike * disc_r, 0.0)
        else:
            value = strike * disc_r * norm.cdf(-_d2) - spot * disc_q * norm.cdf(-_d1)
            intrinsic = np.maximum(strike * disc_r - spot * disc_q, 0.0)

        degenerate = (maturity <= _SQRT_EPS) | (vol <= _SQRT_EPS)
        return np.where(degenerate, intrinsic, value)

    # ------------------------------------------------------------------ #
    # Greeks
    # ------------------------------------------------------------------ #
    @staticmethod
    def delta(
        spot: ArrayLike,
        strike: ArrayLike,
        maturity: ArrayLike,
        rate: float,
        vol: ArrayLike,
        dividend: float = 0.0,
        option_type: OptionType = OptionType.CALL,
    ) -> NDArray[np.float64]:
        """Option delta ``dV/dS`` (dividend-adjusted)."""
        option_type = OptionType.parse(option_type)
        maturity = np.asarray(maturity, dtype=float)
        disc_q = np.exp(-dividend * maturity)
        _d1 = BlackScholes.d1(spot, strike, maturity, rate, vol, dividend)
        if option_type is OptionType.CALL:
            return disc_q * norm.cdf(_d1)
        return -disc_q * norm.cdf(-_d1)

    @staticmethod
    def gamma(
        spot: ArrayLike,
        strike: ArrayLike,
        maturity: ArrayLike,
        rate: float,
        vol: ArrayLike,
        dividend: float = 0.0,
    ) -> NDArray[np.float64]:
        """Option gamma ``d2V/dS2`` (identical for calls and puts)."""
        spot = np.asarray(spot, dtype=float)
        maturity = np.asarray(maturity, dtype=float)
        vol = np.asarray(vol, dtype=float)
        disc_q = np.exp(-dividend * maturity)
        _d1 = BlackScholes.d1(spot, strike, maturity, rate, vol, dividend)
        denom = spot * vol * np.sqrt(np.maximum(maturity, _SQRT_EPS))
        return disc_q * norm.pdf(_d1) / denom

    @staticmethod
    def vega(
        spot: ArrayLike,
        strike: ArrayLike,
        maturity: ArrayLike,
        rate: float,
        vol: ArrayLike,
        dividend: float = 0.0,
    ) -> NDArray[np.float64]:
        """Option vega ``dV/dsigma`` per 1.00 of vol (identical call/put)."""
        spot = np.asarray(spot, dtype=float)
        maturity = np.asarray(maturity, dtype=float)
        disc_q = np.exp(-dividend * maturity)
        _d1 = BlackScholes.d1(spot, strike, maturity, rate, vol, dividend)
        return spot * disc_q * norm.pdf(_d1) * np.sqrt(np.maximum(maturity, 0.0))

    @staticmethod
    def theta(
        spot: ArrayLike,
        strike: ArrayLike,
        maturity: ArrayLike,
        rate: float,
        vol: ArrayLike,
        dividend: float = 0.0,
        option_type: OptionType = OptionType.CALL,
    ) -> NDArray[np.float64]:
        """Option theta ``dV/dt`` per year (negative time decay for longs)."""
        option_type = OptionType.parse(option_type)
        spot = np.asarray(spot, dtype=float)
        strike = np.asarray(strike, dtype=float)
        maturity = np.asarray(maturity, dtype=float)
        vol = np.asarray(vol, dtype=float)

        disc_r = np.exp(-rate * maturity)
        disc_q = np.exp(-dividend * maturity)
        _d1 = BlackScholes.d1(spot, strike, maturity, rate, vol, dividend)
        _d2 = _d1 - vol * np.sqrt(np.maximum(maturity, _SQRT_EPS))

        carry = (
            -spot * disc_q * norm.pdf(_d1) * vol
            / (2.0 * np.sqrt(np.maximum(maturity, _SQRT_EPS)))
        )
        if option_type is OptionType.CALL:
            return (
                carry
                - rate * strike * disc_r * norm.cdf(_d2)
                + dividend * spot * disc_q * norm.cdf(_d1)
            )
        return (
            carry
            + rate * strike * disc_r * norm.cdf(-_d2)
            - dividend * spot * disc_q * norm.cdf(-_d1)
        )

    @staticmethod
    def rho(
        spot: ArrayLike,
        strike: ArrayLike,
        maturity: ArrayLike,
        rate: float,
        vol: ArrayLike,
        dividend: float = 0.0,
        option_type: OptionType = OptionType.CALL,
    ) -> NDArray[np.float64]:
        """Option rho ``dV/dr`` per 1.00 of rate."""
        option_type = OptionType.parse(option_type)
        strike = np.asarray(strike, dtype=float)
        maturity = np.asarray(maturity, dtype=float)
        disc_r = np.exp(-rate * maturity)
        _d2 = BlackScholes.d2(spot, strike, maturity, rate, vol, dividend)
        if option_type is OptionType.CALL:
            return strike * maturity * disc_r * norm.cdf(_d2)
        return -strike * maturity * disc_r * norm.cdf(-_d2)

    # ------------------------------------------------------------------ #
    # Aggregate helper
    # ------------------------------------------------------------------ #
    @staticmethod
    def greeks(params: BSParams) -> Greeks:
        """Compute price + all first-order Greeks for a *scalar* option.

        Returns a :class:`Greeks` object whose properties expose the desk
        conventions (vega / rho per 1 %, theta per day).
        """
        common = dict(
            spot=params.spot,
            strike=params.strike,
            maturity=params.maturity,
            rate=params.rate,
            vol=params.vol,
            dividend=params.dividend,
        )
        return Greeks(
            price=float(BlackScholes.price(option_type=params.option_type, **common)),
            delta=float(BlackScholes.delta(option_type=params.option_type, **common)),
            gamma=float(BlackScholes.gamma(**common)),
            vega=float(BlackScholes.vega(**common)),
            theta=float(BlackScholes.theta(option_type=params.option_type, **common)),
            rho=float(BlackScholes.rho(option_type=params.option_type, **common)),
        )