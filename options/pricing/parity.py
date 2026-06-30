"""Put-call parity verification.

For a European option on a dividend-paying underlying the parity relation is

    C - P = S * e^{-qT} - K * e^{-rT}

which is equivalent to the textbook ``C + PV(K) = P + S`` once dividends are
taken into account.  Any non-zero residual either reflects a genuine arbitrage
or -- far more often -- the frictions the desk lives with: bid/ask spreads,
borrow costs, discrete dividends, stale quotes, or an imperfect rate curve.

This module quantifies the residual and flags it, while being explicit that a
flag is *not* a tradeable signal on its own.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["ParityResult", "check_put_call_parity"]


@dataclass(frozen=True)
class ParityResult:
    """Outcome of a put-call parity check for one (strike, maturity) pair.

    Attributes
    ----------
    strike, maturity:
        The contract coordinates the check refers to.
    call_price, put_price, spot:
        The market inputs used.
    lhs:
        ``C - P`` (the option side of the relation).
    rhs:
        ``S*e^{-qT} - K*e^{-rT}`` (the cash-and-carry side).
    residual:
        ``lhs - rhs``.  Zero under perfect parity.
    arbitrage_flag:
        ``True`` when ``|residual|`` exceeds ``tolerance``.
    direction:
        Human-readable hint on which leg looks rich/cheap, or ``""`` when the
        relation holds within tolerance.
    """

    strike: float
    maturity: float
    call_price: float
    put_price: float
    spot: float
    lhs: float
    rhs: float
    residual: float
    tolerance: float
    arbitrage_flag: bool
    direction: str

    def as_dict(self) -> dict[str, float | bool | str]:
        """Serialise to a plain dict (useful for tables / JSON)."""
        return {
            "strike": self.strike,
            "maturity": round(self.maturity, 4),
            "call_price": round(self.call_price, 4),
            "put_price": round(self.put_price, 4),
            "lhs_C_minus_P": round(self.lhs, 4),
            "rhs_carry": round(self.rhs, 4),
            "residual": round(self.residual, 4),
            "arbitrage_flag": self.arbitrage_flag,
            "direction": self.direction,
        }


def check_put_call_parity(
    call_price: float,
    put_price: float,
    spot: float,
    strike: float,
    maturity: float,
    rate: float,
    dividend: float = 0.0,
    tolerance: float = 0.05,
) -> ParityResult:
    """Verify the put-call parity relation for a single contract pair.

    Parameters
    ----------
    call_price, put_price:
        Market premia of the call and put sharing ``strike`` / ``maturity``.
    spot, strike, maturity, rate, dividend:
        Standard market inputs (continuously-compounded ``rate``/``dividend``).
    tolerance:
        Absolute residual (in price units) above which the pair is flagged.

    Returns
    -------
    ParityResult
        A fully-populated result object.
    """
    disc_r = float(np.exp(-rate * maturity))
    disc_q = float(np.exp(-dividend * maturity))

    lhs = call_price - put_price
    rhs = spot * disc_q - strike * disc_r
    residual = lhs - rhs

    flag = abs(residual) > tolerance
    direction = ""
    if flag:
        if residual > 0:
            # C - P too large => call rich / put cheap relative to carry.
            direction = (
                "Call expensive vs put (sell call / buy put / short forward)"
            )
        else:
            direction = (
                "Put expensive vs call (buy call / sell put / long forward)"
            )

    return ParityResult(
        strike=strike,
        maturity=maturity,
        call_price=call_price,
        put_price=put_price,
        spot=spot,
        lhs=lhs,
        rhs=rhs,
        residual=residual,
        tolerance=tolerance,
        arbitrage_flag=flag,
        direction=direction,
    )