"""In-memory representation of an option chain (adapted from ASML desk).

Lightweight wrapper around a tidy pandas DataFrame. The lingua franca between
the MockProvider (which produces it), the analytics (surface, pricer,
strategies) and the Dash dashboard (which renders it).
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from options.pricing.black_scholes import OptionType

COLUMNS: tuple[str, ...] = (
    "symbol", "spot", "expiry", "dte", "T", "strike", "option_type",
    "bid", "ask", "mid", "last", "volume", "open_interest", "iv",
)
_DAYS_PER_YEAR = 365.0


@dataclass
class OptionChain:
    symbol: str
    spot: float
    as_of: date
    frame: pd.DataFrame
    source: str = "unknown"

    @classmethod
    def from_records(cls, symbol, spot, records, *, as_of=None, source="unknown"):
        as_of = as_of or date.today()
        rows = [dict(r) for r in records]
        frame = pd.DataFrame(rows)
        if frame.empty:
            return cls(symbol, spot, as_of, pd.DataFrame(columns=COLUMNS), source)

        frame["symbol"] = symbol
        frame["spot"] = spot
        frame["option_type"] = frame["option_type"].map(lambda v: OptionType.parse(v).value)
        frame["expiry"] = pd.to_datetime(frame["expiry"]).dt.date
        frame["dte"] = frame["expiry"].map(lambda d: max((d - as_of).days, 0))
        frame["T"] = frame["dte"] / _DAYS_PER_YEAR

        for col in ("bid", "ask", "mid", "last", "volume", "open_interest", "iv"):
            if col not in frame.columns:
                frame[col] = np.nan

        needs_mid = frame["mid"].isna() & frame["bid"].notna() & frame["ask"].notna()
        frame.loc[needs_mid, "mid"] = (frame.loc[needs_mid, "bid"] + frame.loc[needs_mid, "ask"]) / 2.0

        frame = frame[list(COLUMNS)].sort_values(["expiry", "strike", "option_type"]).reset_index(drop=True)
        return cls(symbol, spot, as_of, frame, source)

    def __len__(self):
        return len(self.frame)

    @property
    def is_empty(self):
        return self.frame.empty

    def expiries(self):
        return sorted(self.frame["expiry"].unique().tolist())

    def strikes(self, expiry=None):
        sub = self.frame if expiry is None else self.frame[self.frame["expiry"] == expiry]
        return sorted(float(k) for k in sub["strike"].unique())

    def maturity_for(self, expiry):
        return max((expiry - self.as_of).days, 0) / _DAYS_PER_YEAR

    def nearest_strike(self, target, expiry=None):
        strikes = np.asarray(self.strikes(expiry))
        if len(strikes) == 0:
            return float(target)
        return float(strikes[np.abs(strikes - target).argmin()])

    def nearest_expiry(self, target):
        expiries = self.expiries()
        return min(expiries, key=lambda d: abs((d - target).days)) if expiries else target

    def get(self, strike, expiry, option_type):
        ot = OptionType.parse(option_type).value
        mask = (np.isclose(self.frame["strike"], strike) &
                (self.frame["expiry"] == expiry) &
                (self.frame["option_type"] == ot))
        match = self.frame[mask]
        return None if match.empty else match.iloc[0]

    def get_iv(self, strike, expiry, option_type):
        row = self.get(strike, expiry, option_type)
        if row is None:
            return None
        iv = row["iv"]
        return None if pd.isna(iv) else float(iv)

    def smile(self, expiry, option_type=OptionType.CALL):
        ot = OptionType.parse(option_type).value
        mask = (self.frame["expiry"] == expiry) & (self.frame["option_type"] == ot)
        return (self.frame.loc[mask, ["strike", "iv", "mid", "volume", "open_interest"]]
                .dropna(subset=["iv"]).sort_values("strike").reset_index(drop=True))

    def atm_term_structure(self, option_type=OptionType.CALL):
        ot = OptionType.parse(option_type).value
        records = []
        for expiry in self.expiries():
            atm_strike = self.nearest_strike(self.spot, expiry)
            iv = self.get_iv(atm_strike, expiry, ot)
            if iv is None:
                continue
            records.append({"expiry": expiry, "T": self.maturity_for(expiry),
                            "atm_strike": atm_strike, "iv": iv})
        return pd.DataFrame(records)

    def to_frame(self):
        return self.frame.copy()