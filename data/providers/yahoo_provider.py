import pandas as pd
import yfinance as yf
import os
import pickle
import hashlib
from typing import List
from datetime import datetime, timedelta

from .base_provider import BaseDataProvider


class YahooDataProvider(BaseDataProvider):
    """
    Yahoo Finance data provider.

    ⚠️ STRICT RULE:
    This provider is ONLY for backtesting purposes.
    """

    CACHE_DIR = "cache/yahoo"
    CACHE_TTL_HOURS = 24

    def __init__(self):
        os.makedirs(self.CACHE_DIR, exist_ok=True)

    def _cache_key(self, *args) -> str:
        raw = "_".join(map(str, args))
        return hashlib.md5(raw.encode()).hexdigest()

    def _load_cache(self, key: str):
        path = os.path.join(self.CACHE_DIR, key)
        if not os.path.exists(path):
            return None

        if datetime.now() - datetime.fromtimestamp(os.path.getmtime(path)) > timedelta(hours=self.CACHE_TTL_HOURS):
            return None

        with open(path, "rb") as f:
            return pickle.load(f)

    def _save_cache(self, key: str, data):
        path = os.path.join(self.CACHE_DIR, key)
        with open(path, "wb") as f:
            pickle.dump(data, f)

    def get_prices(self, tickers: List[str], start_date: str, end_date: str) -> pd.DataFrame:
        key = self._cache_key("prices", tickers, start_date, end_date)
        cached = self._load_cache(key)
        if cached is not None:
            return cached
    
        try:
            data = yf.download(
                tickers,
                start=start_date,
                end=end_date,
                auto_adjust=False,
                progress=False
            )
            self._save_cache(key, data)
            return data
        except Exception as e:
            raise RuntimeError(f"Yahoo get_prices failed: {e}")


    def get_returns(self, tickers: List[str], start_date: str, end_date: str) -> pd.DataFrame:
        prices = self.get_prices(tickers, start_date, end_date)
        return prices["Close"].pct_change().dropna()

    def get_fundamentals(self, tickers: List[str]) -> pd.DataFrame:
        data = {}
        for t in tickers:
            try:
                info = yf.Ticker(t).info
                data[t] = info
            except Exception as e:
                raise RuntimeError(f"Yahoo fundamentals failed for {t}: {e}")
        return pd.DataFrame(data).T

    def get_market_cap(self, tickers: List[str]) -> pd.Series:
        fundamentals = self.get_fundamentals(tickers)
        return fundamentals["marketCap"]

    def get_volume(self, tickers: List[str], start_date: str, end_date: str) -> pd.DataFrame:
        prices = self.get_prices(tickers, start_date, end_date)
        return prices["Volume"]

    def get_fx_rates(self, base: str, quote: str, start_date: str, end_date: str) -> pd.Series:
        pair = f"{base}{quote}=X"
        df = yf.download(pair, start=start_date, end=end_date)
        return df["Close"]