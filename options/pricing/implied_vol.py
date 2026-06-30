"""Implied-volatility solver.

The primary algorithm is Newton-Raphson, which converges quadratically when
vega is well-behaved (i.e. for most liquid, not-too-deep options).  Whenever
Newton stalls -- vega collapses, the iterate leaves the admissible band, or the
maximum number of steps is exhausted -- the solver falls back to Brent's method
(:func:`scipy.optimize.brentq`), a bracketing root-finder that is slower but
globally convergent on a sign-changing interval.

A price below the option's intrinsic value admits no positive implied vol; in
that case the solver returns ``nan`` together with a descriptive status rather
than raising, so a whole option chain can be processed without try/except noise.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

import numpy as np
from scipy.optimize import brentq

from .black_scholes import BlackScholes, OptionType

__all__ = ["IVResult", "IVStatus", "ImpliedVolatilitySolver"]

_VOL_LOWER: Final[float] = 1e-6
_VOL_UPPER: Final[float] = 5.0  # 500 % annualised - generous upper band
_PRICE_TOL: Final[float] = 1e-8
_VEGA_FLOOR: Final[float] = 1e-8


class IVStatus(str, Enum):
    """Outcome of an implied-vol calculation."""

    NEWTON = "newton"          # converged via Newton-Raphson
    BRENT = "brent"            # converged via Brent fallback
    NO_SOLUTION = "no_solution"  # price below intrinsic / no root in band
    FAILED = "failed"          # both methods failed to converge


@dataclass(frozen=True)
class IVResult:
    """Result of an implied-vol solve."""

    implied_vol: float
    status: IVStatus
    iterations: int = 0

    @property
    def ok(self) -> bool:
        """``True`` when a finite implied vol was recovered."""
        return np.isfinite(self.implied_vol)


class ImpliedVolatilitySolver:
    """Recover Black-Scholes implied volatility from a market price."""

    def __init__(
        self,
        *,
        max_iterations: int = 100,
        price_tolerance: float = _PRICE_TOL,
        vol_tolerance: float = 1e-8,
        vol_bounds: tuple[float, float] = (_VOL_LOWER, _VOL_UPPER),
    ) -> None:
        self.max_iterations = max_iterations
        self.price_tolerance = price_tolerance
        # Convergence is primarily measured in *vol space*: a tiny price
        # residual is meaningless when vega is small (deep ITM/OTM), so we stop
        # on the Newton step size (residual / vega) instead.
        self.vol_tolerance = vol_tolerance
        self.vol_lower, self.vol_upper = vol_bounds

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def solve(
        self,
        market_price: float,
        spot: float,
        strike: float,
        maturity: float,
        rate: float,
        dividend: float = 0.0,
        option_type: OptionType = OptionType.CALL,
        initial_guess: float | None = None,
    ) -> IVResult:
        """Return the implied volatility consistent with ``market_price``.

        Parameters
        ----------
        market_price:
            Observed option premium (typically the mid of bid/ask).
        spot, strike, maturity, rate, dividend, option_type:
            Standard Black-Scholes inputs (see :mod:`black_scholes`).
        initial_guess:
            Optional warm start for Newton-Raphson.  When omitted a
            Brenner-Subrahmanyam style closed-form approximation is used.
        """
        option_type = OptionType.parse(option_type)

        # ---- 1. Arbitrage / sanity bounds -------------------------------- #
        if not np.isfinite(market_price) or market_price <= 0.0 or maturity <= 0.0:
            return IVResult(np.nan, IVStatus.NO_SOLUTION)

        disc_r = np.exp(-rate * maturity)
        disc_q = np.exp(-dividend * maturity)
        if option_type is OptionType.CALL:
            intrinsic = max(spot * disc_q - strike * disc_r, 0.0)
            upper_bound = spot * disc_q
        else:
            intrinsic = max(strike * disc_r - spot * disc_q, 0.0)
            upper_bound = strike * disc_r

        # Price must sit strictly inside the no-arbitrage band.
        if market_price < intrinsic - self.price_tolerance:
            return IVResult(np.nan, IVStatus.NO_SOLUTION)
        if market_price >= upper_bound:
            return IVResult(np.nan, IVStatus.NO_SOLUTION)

        # ---- 2. Newton-Raphson ------------------------------------------- #
        sigma = initial_guess if initial_guess is not None else self._initial_guess(
            market_price, spot, maturity
        )
        sigma = float(np.clip(sigma, self.vol_lower, self.vol_upper))

        for iteration in range(1, self.max_iterations + 1):
            model = float(
                BlackScholes.price(
                    spot, strike, maturity, rate, sigma, dividend, option_type
                )
            )
            diff = model - market_price

            vega = float(
                BlackScholes.vega(spot, strike, maturity, rate, sigma, dividend)
            )
            if vega < _VEGA_FLOOR:
                break  # flat objective -> hand over to Brent

            step = diff / vega
            sigma_next = sigma - step

            # Converge on the Newton step (vol space): this is robust even when
            # vega is tiny and a small price residual would otherwise stop the
            # iteration prematurely with a poorly-identified volatility.
            if abs(step) < self.vol_tolerance:
                sigma_final = float(np.clip(sigma_next, self.vol_lower, self.vol_upper))
                return IVResult(sigma_final, IVStatus.NEWTON, iteration)

            if not np.isfinite(sigma_next) or not (
                self.vol_lower <= sigma_next <= self.vol_upper
            ):
                break  # left the admissible band -> hand over to Brent
            sigma = sigma_next

        # ---- 3. Brent fallback ------------------------------------------- #
        return self._brent_fallback(
            market_price, spot, strike, maturity, rate, dividend, option_type
        )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    @staticmethod
    def _initial_guess(market_price: float, spot: float, maturity: float) -> float:
        """Brenner-Subrahmanyam ATM approximation, clamped to a sane range."""
        guess = np.sqrt(2.0 * np.pi / maturity) * (market_price / spot)
        if not np.isfinite(guess) or guess <= 0.0:
            return 0.20
        return float(np.clip(guess, 0.01, 3.0))

    def _brent_fallback(
        self,
        market_price: float,
        spot: float,
        strike: float,
        maturity: float,
        rate: float,
        dividend: float,
        option_type: OptionType,
    ) -> IVResult:
        """Bracketing root-find of ``BS(sigma) - market_price``."""

        def objective(sigma: float) -> float:
            return (
                float(
                    BlackScholes.price(
                        spot, strike, maturity, rate, sigma, dividend, option_type
                    )
                )
                - market_price
            )

        f_lo, f_hi = objective(self.vol_lower), objective(self.vol_upper)
        if np.sign(f_lo) == np.sign(f_hi):
            # No sign change -> the price is not attainable in the band.
            return IVResult(np.nan, IVStatus.NO_SOLUTION)
        try:
            sigma = brentq(
                objective,
                self.vol_lower,
                self.vol_upper,
                xtol=1e-8,
                rtol=1e-10,
                maxiter=200,
            )
            return IVResult(float(sigma), IVStatus.BRENT)
        except (ValueError, RuntimeError):
            return IVResult(np.nan, IVStatus.FAILED)