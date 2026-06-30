"""Option strategy primitives.

This module provides the two building blocks used by every multi-leg payoff in
the platform:

* :class:`OptionLeg` -- a single signed position (an option, a holding of the
  underlying, or a financing cash/bond leg).
* :class:`Strategy` -- an ordered collection of legs together with the analytics
  a trader expects: net cost, terminal payoff, profit/loss, max profit, max
  loss, break-evens and *aggregated* first-order Greeks.

The payoff of any combination of these legs is a continuous piecewise-linear
function of the terminal spot, so its extrema and zeros can be computed exactly
from the kinks (the strikes) and the asymptotic slope of the right tail rather
than by brute-force sampling.  That keeps ``max_profit`` / ``max_loss`` correct
even for unbounded structures (a long straddle, a naked short call, ...).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable, Sequence

import numpy as np
from numpy.typing import NDArray

from options.pricing import BSParams, BlackScholes, Greeks, OptionType

# A vol source is either a flat number or a callable ``strike -> vol``.
VolLike = "float | Callable[[float], float]"

_INF = math.inf
_SLOPE_EPS = 1e-9


def as_vol_fn(vol: "float | Callable[[float], float]") -> Callable[[float], float]:
    """Coerce *vol* into a callable ``strike -> implied vol``.

    A scalar is treated as a flat volatility across strikes; a callable is
    returned unchanged.  This lets the strategy builders accept either a single
    number or a smile function sampled from the volatility surface.
    """
    if callable(vol):
        return vol
    flat = float(vol)
    return lambda _strike: flat


class LegKind(str, Enum):
    """Discriminates the three economic leg types a strategy can hold."""

    OPTION = "option"
    UNDERLYING = "underlying"
    CASH = "cash"


@dataclass(frozen=True)
class OptionLeg:
    """A single signed leg of a strategy.

    Parameters
    ----------
    kind:
        Whether the leg is an option, a holding of the underlying or a cash /
        zero-coupon bond used for financing (e.g. the bond in a fiduciary call).
    quantity:
        Signed size.  ``+`` is long, ``-`` is short.  One unit of an option leg
        is assumed to cover one unit of the underlying leg, so the quantities
        net consistently (no 100x contract multiplier is applied here).
    premium:
        Entry cost *per unit* (always quoted as a positive number for a long).
        The cash-flow sign is carried by ``quantity`` so that a short leg
        (``quantity < 0``) contributes a credit to the net cost.
    strike:
        Option strike (``OPTION`` legs only).
    maturity:
        Year-fraction to expiry; used for valuation Greeks and for discounting
        the cash leg.  Terminal payoffs do not depend on it.
    vol:
        Implied volatility used to value an option leg (``OPTION`` legs only).
    option_type:
        Call or put (``OPTION`` legs only).
    face:
        Guaranteed maturity value per unit of a ``CASH`` leg (e.g. ``K`` for the
        bond inside a fiduciary call).
    """

    kind: LegKind
    quantity: float
    premium: float
    strike: float = 0.0
    maturity: float = 0.0
    vol: float = 0.0
    option_type: OptionType | None = None
    face: float = 0.0

    # ------------------------------------------------------------------ #
    # Convenience constructors
    # ------------------------------------------------------------------ #
    @classmethod
    def option(
        cls,
        option_type: "str | OptionType",
        strike: float,
        maturity: float,
        quantity: float,
        premium: float,
        vol: float,
    ) -> "OptionLeg":
        """Build an option leg."""
        return cls(
            kind=LegKind.OPTION,
            quantity=float(quantity),
            premium=float(premium),
            strike=float(strike),
            maturity=float(maturity),
            vol=float(vol),
            option_type=OptionType.parse(option_type),
        )

    @classmethod
    def underlying(cls, quantity: float, premium: float) -> "OptionLeg":
        """Build a holding of the underlying (``premium`` = entry spot)."""
        return cls(
            kind=LegKind.UNDERLYING,
            quantity=float(quantity),
            premium=float(premium),
        )

    @classmethod
    def cash(cls, face: float, maturity: float, rate: float, quantity: float = 1.0) -> "OptionLeg":
        """Build a zero-coupon cash leg worth ``face`` at ``maturity``.

        The entry premium is the present value ``face * exp(-rate * maturity)``.
        """
        pv = float(face) * math.exp(-rate * float(maturity))
        return cls(
            kind=LegKind.CASH,
            quantity=float(quantity),
            premium=pv,
            maturity=float(maturity),
            face=float(face),
        )

    # ------------------------------------------------------------------ #
    # Economics
    # ------------------------------------------------------------------ #
    @property
    def cost(self) -> float:
        """Signed cash outlay at inception (``+`` debit, ``-`` credit)."""
        return self.quantity * self.premium

    def payoff(self, spot: NDArray[np.float64]) -> NDArray[np.float64]:
        """Vectorised terminal payoff of the leg at expiry over *spot*."""
        spot = np.asarray(spot, dtype=float)
        if self.kind is LegKind.OPTION:
            if self.option_type is OptionType.CALL:
                intrinsic = np.maximum(spot - self.strike, 0.0)
            else:
                intrinsic = np.maximum(self.strike - spot, 0.0)
            return self.quantity * intrinsic
        if self.kind is LegKind.UNDERLYING:
            return self.quantity * spot
        # CASH: constant maturity value, broadcast across the grid.
        return self.quantity * np.full_like(spot, self.face)

    def greeks(self, spot: float, rate: float, dividend: float) -> Greeks:
        """First-order Greeks of the leg (raw units, already scaled by size)."""
        q = self.quantity
        if self.kind is LegKind.OPTION:
            g = BlackScholes.greeks(
                BSParams(
                    spot=spot,
                    strike=self.strike,
                    maturity=self.maturity,
                    rate=rate,
                    vol=self.vol,
                    dividend=dividend,
                    option_type=self.option_type or OptionType.CALL,
                )
            )
            return Greeks(
                price=q * g.price,
                delta=q * g.delta,
                gamma=q * g.gamma,
                vega=q * g.vega,
                theta=q * g.theta,
                rho=q * g.rho,
            )
        if self.kind is LegKind.UNDERLYING:
            # A share has unit delta and no convexity / vol / time sensitivity.
            return Greeks(price=q * spot, delta=q * 1.0, gamma=0.0, vega=0.0, theta=0.0, rho=0.0)
        # CASH / zero-coupon bond: only carries rate sensitivity.
        pv = self.face * math.exp(-rate * self.maturity)
        return Greeks(
            price=q * pv,
            delta=0.0,
            gamma=0.0,
            vega=0.0,
            theta=q * rate * pv,          # value accretes as time passes
            rho=q * (-self.maturity * pv),
        )

    def describe(self) -> str:
        """Human-readable one-liner for tables and tooltips."""
        side = "Long" if self.quantity >= 0 else "Short"
        size = abs(self.quantity)
        if self.kind is LegKind.OPTION:
            kind = (self.option_type or OptionType.CALL).value.capitalize()
            return f"{side} {size:g} {kind} @ {self.strike:g}"
        if self.kind is LegKind.UNDERLYING:
            return f"{side} {size:g} Underlying @ {self.premium:g}"
        return f"{side} {size:g} Cash (PV of {self.face:g})"


@dataclass
class Strategy:
    """An ordered set of legs plus the analytics traders care about.

    All payoff analytics assume the legs settle at a single common horizon
    (true for every strategy shipped in :mod:`src.strategies.strategies`).  The
    Greeks, by contrast, use each leg's own time-to-maturity so the aggregate is
    a correct *current* risk snapshot.
    """

    name: str
    legs: list[OptionLeg]
    spot: float
    rate: float
    dividend: float = 0.0
    description: str = ""

    # ------------------------------------------------------------------ #
    # Cost & payoff
    # ------------------------------------------------------------------ #
    def net_cost(self) -> float:
        """Net debit (``+``) or credit (``-``) paid to enter the structure."""
        return float(sum(leg.cost for leg in self.legs))

    def payoff(self, spot: NDArray[np.float64]) -> NDArray[np.float64]:
        """Gross terminal payoff (excludes the entry cost)."""
        spot = np.asarray(spot, dtype=float)
        total = np.zeros_like(spot)
        for leg in self.legs:
            total = total + leg.payoff(spot)
        return total

    def pnl(self, spot: NDArray[np.float64]) -> NDArray[np.float64]:
        """Profit / loss at expiry: terminal payoff minus net cost."""
        return self.payoff(spot) - self.net_cost()

    # ------------------------------------------------------------------ #
    # Exact piecewise-linear extrema / zeros
    # ------------------------------------------------------------------ #
    def _strikes(self) -> list[float]:
        return sorted({leg.strike for leg in self.legs if leg.kind is LegKind.OPTION})

    def _right_tail_slope(self) -> float:
        """d(payoff)/dS as ``S -> +inf`` (puts and cash vanish; calls/stock don't)."""
        slope = 0.0
        for leg in self.legs:
            if leg.kind is LegKind.UNDERLYING:
                slope += leg.quantity
            elif leg.kind is LegKind.OPTION and leg.option_type is OptionType.CALL:
                slope += leg.quantity
        return slope

    def _reference_spots(self) -> NDArray[np.float64]:
        strikes = self._strikes()
        upper = max(strikes + [self.spot]) if strikes else self.spot
        # Breakpoints (0 and each strike) plus a point past the last kink to
        # evaluate the flat right tail when the slope is zero.
        pts = [0.0] + strikes + [upper * 2.0 + 1.0]
        return np.array(sorted(set(pts)), dtype=float)

    def max_profit(self) -> float:
        """Maximum attainable profit (``+inf`` if the upside is unbounded)."""
        pnl_bp = self.pnl(self._reference_spots())
        slope = self._right_tail_slope()
        if slope > _SLOPE_EPS:
            return _INF
        return float(np.max(pnl_bp))

    def max_loss(self) -> float:
        """Maximum loss as a negative number (``-inf`` if unbounded)."""
        pnl_bp = self.pnl(self._reference_spots())
        slope = self._right_tail_slope()
        if slope < -_SLOPE_EPS:
            return -_INF
        return float(np.min(pnl_bp))

    def breakevens(self, samples: int = 4000) -> list[float]:
        """Spot levels where the strategy P&L crosses zero at expiry.

        Detected from sign changes of the P&L on a dense grid and refined by
        linear interpolation (exact for a piecewise-linear payoff).  Tangential
        zeros (e.g. a butterfly that just touches zero) are intentionally not
        reported as break-evens.
        """
        ref = self._reference_spots()
        hi = float(ref[-1])
        grid = np.linspace(0.0, hi, samples)
        pnl = self.pnl(grid)

        crossings: list[float] = []
        sign = np.sign(pnl)
        for i in range(len(grid) - 1):
            a, b = sign[i], sign[i + 1]
            if a == 0.0:
                crossings.append(float(grid[i]))
            elif a * b < 0.0:
                x0, x1 = grid[i], grid[i + 1]
                y0, y1 = pnl[i], pnl[i + 1]
                crossings.append(float(x0 - y0 * (x1 - x0) / (y1 - y0)))

        # De-duplicate near-equal roots.
        crossings.sort()
        unique: list[float] = []
        for x in crossings:
            if not unique or abs(x - unique[-1]) > 1e-4 * max(1.0, hi):
                unique.append(x)
        return unique

    # ------------------------------------------------------------------ #
    # Aggregated Greeks
    # ------------------------------------------------------------------ #
    def greeks(self, spot: float | None = None) -> Greeks:
        """Net first-order Greeks of the book at *spot* (defaults to current)."""
        s = self.spot if spot is None else float(spot)
        price = delta = gamma = vega = theta = rho = 0.0
        for leg in self.legs:
            g = leg.greeks(s, self.rate, self.dividend)
            price += g.price
            delta += g.delta
            gamma += g.gamma
            vega += g.vega
            theta += g.theta
            rho += g.rho
        return Greeks(price=price, delta=delta, gamma=gamma, vega=vega, theta=theta, rho=rho)

    # ------------------------------------------------------------------ #
    # Plotting / reporting helpers
    # ------------------------------------------------------------------ #
    def payoff_curve(
        self,
        n: int = 240,
        lo: float | None = None,
        hi: float | None = None,
    ) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
        """Return ``(spot_grid, payoff, pnl)`` arrays for charting."""
        strikes = self._strikes()
        ref_hi = max(strikes + [self.spot]) if strikes else self.spot
        ref_lo = min(strikes + [self.spot]) if strikes else self.spot
        lo = 0.0 if lo is None else lo
        hi = ref_hi * 1.5 if hi is None else hi
        # Ensure the window comfortably brackets every kink.
        hi = max(hi, ref_hi * 1.2)
        grid = np.linspace(lo, hi, n)
        return grid, self.payoff(grid), self.pnl(grid)

    def summary(self) -> dict[str, object]:
        """Everything the dashboard needs to render a strategy card."""
        be = self.breakevens()
        greeks = self.greeks().as_dict(desk_units=True)

        def _fmt(x: float) -> float | str:
            if x == _INF:
                return "unlimited"
            if x == -_INF:
                return "unlimited"
            return float(x)

        return {
            "name": self.name,
            "description": self.description,
            "legs": [leg.describe() for leg in self.legs],
            "net_cost": self.net_cost(),
            "net_debit": self.net_cost() > 0,
            "max_profit": _fmt(self.max_profit()),
            "max_loss": _fmt(self.max_loss()),
            "breakevens": be,
            "greeks": greeks,
        }