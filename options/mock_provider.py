"""Mock option-chain provider driven by live Yahoo Finance spot prices.

Generates a deterministic, self-consistent European option chain for ANY
EURO STOXX 50 underlying (or the US watchlist tickers). The spot comes from
Yahoo Finance in real time; strikes/expiries/IV smile are synthesised and
priced by the internal Black-Scholes engine, so:

  * put-call parity holds exactly,
  * the IV solver round-trips the inputs,
  * a realistic equity skew (downside puts richer) is baked in.

This is the FALLBACK when IBKR (real market IV) is unavailable. It is an honest
theoretical pricer: every premium is the model value at the assumed vol
surface. The ATM vol level is derived from the stock's sector.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import numpy as np

from options.option_chain import OptionChain
from options.pricing.black_scholes import BlackScholes, OptionType

logger = logging.getLogger("OptionsMockProvider")

# Niveau de vol ATM estimé par secteur (annualisé) — sert de base au mock.
SECTOR_ATM_VOL = {
    "Information Technology":  0.34,
    "Consumer Discretionary":  0.30,
    "Health Care":             0.26,
    "Financials":              0.28,
    "Industrials":             0.27,
    "Materials":               0.29,
    "Energy":                  0.30,
    "Consumer Staples":        0.22,
    "Utilities":               0.23,
    "Communication Services":  0.26,
    "Unknown":                 0.28,
}

# Hypothèses desk zone euro
EUR_RATE = 0.025      # taux sans risque EUR (~BCE / Bund)
US_RATE  = 0.0425     # taux USD (pour JPM/ISRG/SPCX)

# Dividend yield estimé par ticker (sinon défaut sectoriel)
DIVIDEND_OVERRIDE = {
    # EURO STOXX 50
    "ENI.MI": 0.055, "TTE.PA": 0.050, "ENEL.MI": 0.055, "IBE.MC": 0.045,
    "ALV.DE": 0.045, "MUV2.DE": 0.035, "BNP.PA": 0.060, "SAN.MC": 0.045,
    "BBVA.MC": 0.055, "ISP.MI": 0.070, "UCG.MI": 0.065, "INGA.AS": 0.060,
    "DTE.DE": 0.035, "BAS.DE": 0.060, "MBG.DE": 0.060, "BMW.DE": 0.055,
    "VOW.DE": 0.040, "DHL.DE": 0.040, "SAN.PA": 0.040, "BAYN.DE": 0.030,
    "AD.AS": 0.030, "DG.PA": 0.035, "MC.PA": 0.020, "OR.PA": 0.018,
    "AI.PA": 0.020, "SAP.DE": 0.012, "ASML.AS": 0.010, "SIE.DE": 0.025,
    "ADYEN.AS": 0.0, "RACE.MI": 0.007, "RMS.PA": 0.008, "ITX.MC": 0.030,
    "PRX.AS": 0.005, "ABI.BR": 0.015, "NDA-FI.HE": 0.070, "DB1.DE": 0.020,
    "DBK.DE": 0.030, "SAF.PA": 0.012, "SGO.PA": 0.025, "SU.PA": 0.020,
    "EL.PA": 0.015, "AIR.PA": 0.015, "IFX.DE": 0.010, "RHM.DE": 0.012,
    "ENR.DE": 0.0, "ADS.DE": 0.012, "CS.PA": 0.055, "BN.PA": 0.030,
    "WKL.AS": 0.013, "ARGX.BR": 0.0,
    # US watchlist
    "JPM": 0.024, "ISRG": 0.0, "SPCX": 0.0,
}

DEFAULT_SECTOR_DIV = {
    "Financials": 0.045, "Energy": 0.050, "Utilities": 0.050,
    "Consumer Staples": 0.025, "Industrials": 0.020, "Materials": 0.040,
    "Health Care": 0.020, "Consumer Discretionary": 0.020,
    "Information Technology": 0.010, "Communication Services": 0.035,
    "Unknown": 0.025,
}


def _sector_of(symbol: str) -> str:
    try:
        from config.universe import SECTOR_MAP
        return SECTOR_MAP.get(symbol, "Unknown")
    except Exception:
        return "Unknown"


def _market_params(symbol: str) -> dict:
    """Retourne rate/dividend/currency pour un symbole."""
    is_us = symbol in ("JPM", "ISRG", "SPCX", "E")
    sector = _sector_of(symbol)
    rate = US_RATE if is_us else EUR_RATE
    div  = DIVIDEND_OVERRIDE.get(symbol, DEFAULT_SECTOR_DIV.get(sector, 0.025))
    ccy  = "USD" if is_us else "EUR"
    return {"rate": rate, "dividend": div, "currency": ccy, "sector": sector}


# Table consultée par les callbacks (compat avec l'ancien TICKER_MARKET)
class _MarketTable:
    """Accès dict-like : TICKER_MARKET[symbol] → {rate, dividend, currency}."""
    def get(self, symbol, default=None):
        if symbol is None:
            return default or {"rate": EUR_RATE, "dividend": 0.025, "currency": "EUR"}
        return _market_params(symbol)
    def __getitem__(self, symbol):
        return _market_params(symbol)

TICKER_MARKET = _MarketTable()


def _fetch_spot(yf_ticker: str) -> float | None:
    """Récupère le spot temps réel depuis Yahoo Finance."""
    try:
        import yfinance as yf
        tk = yf.Ticker(yf_ticker)
        info = tk.info or {}
        spot = (info.get("currentPrice") or info.get("regularMarketPrice")
                or info.get("previousClose"))
        if spot:
            return float(spot)
        hist = tk.history(period="5d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception as e:
        logger.warning(f"Spot fetch {yf_ticker}: {e}")
    return None


class MockProvider:
    """Génère une chaîne d'options synthétique self-consistent (fallback)."""

    def __init__(self, symbol: str, *, spot: float | None = None,
                 rate: float | None = None, dividend: float | None = None,
                 atm_vol: float | None = None):
        self.symbol = symbol
        mk = _market_params(symbol)
        self.rate     = rate     if rate     is not None else mk["rate"]
        self.dividend = dividend if dividend is not None else mk["dividend"]
        self.currency = mk["currency"]
        self.atm_vol  = atm_vol if atm_vol is not None else SECTOR_ATM_VOL.get(mk["sector"], 0.28)
        self.spot = spot or _fetch_spot(symbol) or 100.0
        self.name = f"mock[{symbol}]"

    def _skew_vol(self, strike: float, maturity: float) -> float:
        """Vol implicite avec skew actions réaliste."""
        moneyness = np.log(strike / self.spot)
        skew      = -0.6 * moneyness + 1.2 * moneyness**2
        term_adj  = 1.0 - 0.05 * np.sqrt(max(maturity, 0.01))
        vol = self.atm_vol * term_adj + skew * 0.5
        return float(np.clip(vol, 0.05, 1.5))

    def fetch_chain(self) -> OptionChain:
        as_of = date.today()
        spot  = self.spot

        n_strikes = 21
        lo, hi    = spot * 0.70, spot * 1.30
        strikes   = np.linspace(lo, hi, n_strikes)
        step = max(1.0, round(spot * 0.025))
        strikes = np.unique(np.round(strikes / step) * step)

        dte_list  = [30, 60, 91, 182, 273, 365]
        expiries  = [as_of + timedelta(days=d) for d in dte_list]

        records = []
        for expiry in expiries:
            maturity = max((expiry - as_of).days, 1) / 365.0
            for K in strikes:
                for ot in (OptionType.CALL, OptionType.PUT):
                    vol = self._skew_vol(float(K), maturity)
                    price = float(BlackScholes.price(
                        spot, float(K), maturity, self.rate, vol, self.dividend, ot))
                    spread = max(0.02, price * 0.015)
                    atm_dist = abs(np.log(float(K) / spot))
                    liquidity = max(1, int(5000 * np.exp(-8 * atm_dist)))
                    records.append({
                        "expiry": expiry, "strike": float(K),
                        "option_type": ot.value,
                        "bid": round(max(0.0, price - spread), 2),
                        "ask": round(price + spread, 2),
                        "mid": round(price, 2), "last": round(price, 2),
                        "volume": liquidity, "open_interest": liquidity * 3,
                        "iv": round(vol, 4),
                    })

        logger.info(f"MockProvider[{self.symbol}] : {len(records)} contrats @ "
                    f"spot {spot:.2f} (vol ATM {self.atm_vol:.0%}, secteur {_sector_of(self.symbol)})")
        return OptionChain.from_records(
            self.symbol, spot, records, as_of=as_of, source="mock (theoretical IV)")


def get_option_chain(symbol: str, ib=None, prefer_ibkr: bool = True) -> OptionChain:
    """
    Factory unifiée : essaie IBKR (vraie IV de marché) puis fallback Mock.

    Args:
        symbol: ticker Yahoo (ex "MC.PA", "SAP.DE")
        ib: instance ib_insync.IB connectée (depuis IBKRLiveEngine), ou None
        prefer_ibkr: si True, tente IBKR d'abord

    Returns:
        OptionChain — source="ibkr (live IV)" ou "mock (theoretical IV)"
    """
    if prefer_ibkr:
        try:
            from options.ibkr_provider import IBKRProvider
            provider = IBKRProvider(symbol, ib=ib)
            if provider.is_available:
                chain = provider.fetch_chain()
                # Valider : au moins quelques contrats avec IV
                if not chain.is_empty:
                    n_iv = chain.frame["iv"].notna().sum()
                    if n_iv >= 4:
                        logger.info(f"✓ Chaîne IBKR réelle pour {symbol} ({n_iv} IV de marché)")
                        return chain
                logger.info(f"IBKR sans IV exploitable pour {symbol} → fallback mock")
        except Exception as e:
            logger.warning(f"IBKR provider échec pour {symbol} ({e}) → fallback mock")

    return MockProvider(symbol).fetch_chain()