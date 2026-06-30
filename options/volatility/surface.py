"""Volatility analytics: smiles, term structure and an interpolated surface.

The :class:`VolatilitySurface` turns the discrete implied-vol observations of an
:class:`~src.data.option_chain.OptionChain` into continuous objects a desk can
reason about:

* a **smile** -- IV as a function of strike for a fixed maturity;
* a **term structure** -- ATM IV as a function of maturity;
* a **surface** -- IV over the full (strike, maturity) plane, obtained by
  scattered-data interpolation (SciPy's :func:`griddata`) with a nearest-
  neighbour fill so the grid has no holes for 3-D rendering.

To stay faithful to how surfaces are built in practice, the default takes the
**out-of-the-money** side of the chain (puts below spot, calls above), which
avoids the noisier deep-ITM quotes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy.interpolate import griddata

from options.option_chain import OptionChain
from options.pricing.black_scholes import OptionType


@dataclass
class SurfaceGrid:
    """A rectangular grid of interpolated implied volatilities.

    Attributes
    ----------
    strikes:
        1-D array of strike coordinates (the X axis).
    maturities:
        1-D array of maturities in years (the Y axis).
    iv:
        2-D array of shape ``(len(maturities), len(strikes))`` of vols.
    """

    strikes: NDArray[np.float64]
    maturities: NDArray[np.float64]
    iv: NDArray[np.float64]


class VolatilitySurface:
    """Continuous implied-volatility surface built from an option chain."""

    def __init__(
        self,
        chain: OptionChain,
        *,
        otm_blend: bool = True,
        option_type: OptionType = OptionType.CALL,
    ) -> None:
        """Initialise the surface.

        Parameters
        ----------
        chain:
            The source option chain.
        otm_blend:
            When ``True`` (default) build the cloud from OTM options (puts for
            ``K < S``, calls for ``K >= S``).  When ``False`` use a single
            ``option_type`` across all strikes.
        option_type:
            The right used when ``otm_blend`` is ``False``.
        """
        self.chain = chain
        self.otm_blend = otm_blend
        self.option_type = OptionType.parse(option_type)
        self._points = self._collect_points()

    # ------------------------------------------------------------------ #
    # Point cloud
    # ------------------------------------------------------------------ #
    def _collect_points(self) -> pd.DataFrame:
        """Assemble the (T, strike, iv) observation cloud used for fitting."""
        frame = self.chain.frame.dropna(subset=["iv"]).copy()
        if frame.empty:
            return pd.DataFrame(columns=["T", "strike", "iv"])

        if self.otm_blend:
            spot = self.chain.spot
            is_otm = (
                ((frame["option_type"] == "put") & (frame["strike"] < spot))
                | ((frame["option_type"] == "call") & (frame["strike"] >= spot))
            )
            frame = frame[is_otm]
        else:
            frame = frame[frame["option_type"] == self.option_type.value]

        return (
            frame[["T", "strike", "iv"]]
            .dropna()
            .query("T > 0 and iv > 0")
            .reset_index(drop=True)
        )

    @property
    def points(self) -> pd.DataFrame:
        """The raw observation cloud (defensive copy)."""
        return self._points.copy()

    @property
    def is_empty(self) -> bool:
        """``True`` when there are not enough points to build a surface."""
        return len(self._points) < 4

    # ------------------------------------------------------------------ #
    # Slices
    # ------------------------------------------------------------------ #
    def smile(
        self, expiry: date, option_type: OptionType | None = None
    ) -> pd.DataFrame:
        """Return the IV smile (strike vs IV) for a given expiry."""
        ot = option_type or self.option_type
        return self.chain.smile(expiry, ot)

    def term_structure(
        self, option_type: OptionType | None = None
    ) -> pd.DataFrame:
        """Return the ATM term structure (maturity vs IV)."""
        ot = option_type or self.option_type
        return self.chain.atm_term_structure(ot)

    # ------------------------------------------------------------------ #
    # Surface
    # ------------------------------------------------------------------ #
    def interpolate(self, maturity: float, strike: float) -> float:
        """Interpolate the IV at an arbitrary (maturity, strike) point.

        Uses linear interpolation inside the data hull and nearest-neighbour
        extrapolation outside it, so a quote is always returned.
        """
        pts = self._points[["T", "strike"]].to_numpy()
        vals = self._points["iv"].to_numpy()
        target = np.array([[maturity, strike]])

        linear = griddata(pts, vals, target, method="linear")
        if np.isnan(linear).any():
            linear = griddata(pts, vals, target, method="nearest")
        return float(linear[0])

    def build_grid(
        self, *, n_strikes: int = 40, n_maturities: int = 24
    ) -> SurfaceGrid:
        """Interpolate the observation cloud onto a rectangular grid.

        Parameters
        ----------
        n_strikes, n_maturities:
            Resolution of the output grid along each axis.

        Returns
        -------
        SurfaceGrid
            A hole-free grid suitable for a 3-D surface plot.
        """
        if self.is_empty:
            raise ValueError("Not enough implied-vol points to build a surface.")

        pts = self._points[["T", "strike"]].to_numpy()
        vals = self._points["iv"].to_numpy()

        strikes = np.linspace(
            self._points["strike"].min(), self._points["strike"].max(), n_strikes
        )
        maturities = np.linspace(
            self._points["T"].min(), self._points["T"].max(), n_maturities
        )
        grid_t, grid_k = np.meshgrid(maturities, strikes, indexing="ij")
        targets = np.column_stack([grid_t.ravel(), grid_k.ravel()])

        iv = griddata(pts, vals, targets, method="linear")
        holes = np.isnan(iv)
        if holes.any():
            iv[holes] = griddata(pts, vals, targets[holes], method="nearest")

        iv_grid = iv.reshape(grid_t.shape)
        return SurfaceGrid(strikes=strikes, maturities=maturities, iv=iv_grid)