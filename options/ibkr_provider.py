"""IBKR option-chain provider — REAL implied volatility from TWS.

Fetches a genuine European option chain for a STOXX 50 underlying directly from
Interactive Brokers (the TWS / IB Gateway must be running). The implied
volatility is the market IV that IBKR computes and disseminates:

  * reqSecDefOptParams() → available expiries and strikes (no throttling)
  * reqMktData(genericTickList="106") → ticker.impliedVolatility (tick 106)
  * ticker.modelGreeks → IBKR's own delta/gamma/vega/theta + IV

This is the credible data source for a track record: the IV is real market
data, not a synthetic assumption. When TWS is unavailable, the caller falls
back to the MockProvider.

IMPORTANT: European single-stock options on Eurex/Euronext require the
corresponding IBKR market-data subscription. Without it, IBKR returns delayed
or empty data; the provider then surfaces an empty chain and the caller
degrades to the mock.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime

from options.option_chain import OptionChain
from options.pricing.black_scholes import OptionType

logger = logging.getLogger("OptionsIBKRProvider")

# Sous-jacent → (bourse des options, devise). Pour les actions de la zone euro
# les options listées sont principalement sur Eurex (DTB) ; Euronext pour
# certaines. On laisse SMART router et IBKR choisit.
UNDERLYING_EXCHANGE = {
    # Allemagne / Eurex
    ".DE": ("EUREX", "EUR"),
    # France / Euronext Paris (MONEP) — options sur Eurex aussi
    ".PA": ("EUREX", "EUR"),
    # Pays-Bas / Euronext Amsterdam
    ".AS": ("EUREX", "EUR"),
    # Italie / Borsa Italiana (IDEM)
    ".MI": ("EUREX", "EUR"),
    # Espagne / MEFF
    ".MC": ("EUREX", "EUR"),
    # Belgique
    ".BR": ("EUREX", "EUR"),
    # Finlande
    ".HE": ("EUREX", "EUR"),
}


def _yahoo_to_ibkr_symbol(ticker: str) -> tuple[str, str, str]:
    """
    Retourne (symbol, exchange_options, currency) pour un ticker Yahoo.
    Le symbole IBKR du sous-jacent peut différer du symbole Yahoo.
    """
    for suffix, (opt_exch, ccy) in UNDERLYING_EXCHANGE.items():
        if ticker.endswith(suffix):
            sym = ticker[: -len(suffix)].split("-")[0]
            return sym, opt_exch, ccy
    # US (JPM, ISRG, SPCX) — options sur SMART en USD
    return ticker, "SMART", "USD"


class IBKRProvider:
    """Vraie chaîne d'options + IV de marché depuis TWS via ib_insync."""

    def __init__(self, symbol: str, ib=None, *,
                 max_expiries: int = 4, n_strikes_around_atm: int = 6,
                 timeout: float = 8.0):
        """
        Args:
            symbol: ticker Yahoo (ex "MC.PA", "SAP.DE", "JPM")
            ib: instance ib_insync.IB déjà connectée (réutilise la connexion
                de l'IBKRLiveEngine). Si None, tentative de connexion locale.
            max_expiries: nombre d'échéances à charger (les plus proches)
            n_strikes_around_atm: nombre de strikes de chaque côté de l'ATM
            timeout: secondes max pour récupérer l'IV de marché
        """
        self.symbol = symbol
        self.max_expiries = max_expiries
        self.n_strikes = n_strikes_around_atm
        self.timeout = timeout
        self._own_connection = False
        self.name = f"ibkr[{symbol}]"

        ib_sym, opt_exch, ccy = _yahoo_to_ibkr_symbol(symbol)
        self.ib_symbol = ib_sym
        self.opt_exchange = opt_exch
        self.currency = ccy

        self._ib = ib
        if self._ib is None:
            self._ib = self._try_local_connect()

    def _try_local_connect(self):
        try:
            import ib_insync as ibi
            import nest_asyncio
            nest_asyncio.apply()
            ib = ibi.IB()
            ib.connect("127.0.0.1", 7497, clientId=7, timeout=8)
            self._own_connection = True
            logger.info(f"IBKRProvider: connexion locale TWS établie pour {self.symbol}")
            return ib
        except Exception as e:
            logger.warning(f"IBKRProvider: TWS indisponible ({e})")
            return None

    @property
    def is_available(self) -> bool:
        try:
            return self._ib is not None and self._ib.isConnected()
        except Exception:
            return False

    def _underlying_contract(self):
        """Contrat du sous-jacent (action)."""
        import ib_insync as ibi
        ib_sym, _, ccy = _yahoo_to_ibkr_symbol(self.symbol)
        # Bourse primaire pour qualifier le sous-jacent
        from execution.ibkr_live import IBKRLiveEngine  # réutilise le mapping
        eng = IBKRLiveEngine.__new__(IBKRLiveEngine)
        return eng._ticker_to_contract(self.symbol)

    def fetch_chain(self) -> OptionChain:
        """
        Construit une OptionChain réelle depuis IBKR.
        Retourne une chaîne vide si TWS indisponible ou pas de données.
        """
        if not self.is_available:
            logger.warning(f"IBKRProvider[{self.symbol}]: TWS non connecté → chaîne vide")
            return OptionChain.from_records(self.symbol, 0.0, [], source="ibkr (unavailable)")

        try:
            import ib_insync as ibi

            # 1. Qualifier le sous-jacent et récupérer le spot
            under = self._underlying_contract()
            qualified = self._ib.qualifyContracts(under)
            if not qualified:
                logger.warning(f"IBKRProvider[{self.symbol}]: sous-jacent non qualifié")
                return OptionChain.from_records(self.symbol, 0.0, [], source="ibkr (no underlying)")
            under = qualified[0]

            # Spot via snapshot
            spot = self._fetch_spot(under)
            if not spot or spot <= 0:
                logger.warning(f"IBKRProvider[{self.symbol}]: spot indisponible")
                return OptionChain.from_records(self.symbol, 0.0, [], source="ibkr (no spot)")

            # 2. Paramètres de la chaîne (expiries + strikes)
            chains = self._ib.reqSecDefOptParams(
                under.symbol, "", under.secType, under.conId
            )
            if not chains:
                logger.warning(f"IBKRProvider[{self.symbol}]: pas de chaîne d'options")
                return OptionChain.from_records(self.symbol, spot, [], source="ibkr (no chain)")

            # Choisir la définition sur la bonne bourse (Eurex pour EU, SMART pour US)
            chain_def = self._select_chain(chains)
            if chain_def is None:
                return OptionChain.from_records(self.symbol, spot, [], source="ibkr (no exchange)")

            # 3. Filtrer expiries (les N plus proches) et strikes (autour de l'ATM)
            expiries = self._select_expiries(chain_def.expirations)
            strikes  = self._select_strikes(chain_def.strikes, spot)

            if not expiries or not strikes:
                return OptionChain.from_records(self.symbol, spot, [], source="ibkr (empty grid)")

            # 4. Construire les contrats d'options et récupérer l'IV de marché
            records = self._fetch_option_data(
                under, chain_def, expiries, strikes, spot
            )

            logger.info(f"IBKRProvider[{self.symbol}]: {len(records)} contrats réels "
                        f"@ spot {spot:.2f} ({len(expiries)} expiries × {len(strikes)} strikes)")

            return OptionChain.from_records(
                self.symbol, spot, records,
                as_of=date.today(), source="ibkr (live IV)",
            )

        except Exception as e:
            logger.error(f"IBKRProvider[{self.symbol}]: {e}", exc_info=True)
            return OptionChain.from_records(self.symbol, 0.0, [], source="ibkr (error)")
        finally:
            if self._own_connection:
                try:
                    self._ib.disconnect()
                except Exception:
                    pass

    def _fetch_spot(self, under) -> float | None:
        """Spot du sous-jacent via snapshot de marché."""
        try:
            ticker = self._ib.reqMktData(under, "", snapshot=False)
            for _ in range(int(self.timeout / 0.25)):
                self._ib.sleep(0.25)
                px = ticker.marketPrice()
                if px and not math.isnan(px) and px > 0:
                    self._ib.cancelMktData(under)
                    return float(px)
                # Fallback close/last
                for attr in ("last", "close"):
                    v = getattr(ticker, attr, None)
                    if v and not math.isnan(v) and v > 0:
                        self._ib.cancelMktData(under)
                        return float(v)
            self._ib.cancelMktData(under)
        except Exception as e:
            logger.warning(f"_fetch_spot {self.symbol}: {e}")
        return None

    def _select_chain(self, chains):
        """Choisit la définition de chaîne sur la bourse cible."""
        # Priorité à la bourse des options configurée, sinon la première
        for c in chains:
            if c.exchange == self.opt_exchange:
                return c
        # Fallback : SMART, puis n'importe laquelle avec des strikes
        for c in chains:
            if c.exchange == "SMART":
                return c
        return chains[0] if chains else None

    def _select_expiries(self, expirations) -> list[str]:
        """Garde les N échéances les plus proches (format YYYYMMDD)."""
        today = datetime.now().strftime("%Y%m%d")
        future = sorted(e for e in expirations if e >= today)
        return future[: self.max_expiries]

    def _select_strikes(self, strikes, spot: float) -> list[float]:
        """Garde n_strikes de chaque côté du spot."""
        s = sorted(float(k) for k in strikes)
        if not s:
            return []
        # Index du strike le plus proche du spot
        atm_idx = min(range(len(s)), key=lambda i: abs(s[i] - spot))
        lo = max(0, atm_idx - self.n_strikes)
        hi = min(len(s), atm_idx + self.n_strikes + 1)
        return s[lo:hi]

    def _fetch_option_data(self, under, chain_def, expiries, strikes, spot):
        """
        Pour chaque (expiry, strike, call/put) : crée le contrat, demande
        les données de marché avec l'IV (tick 106) et les modelGreeks.
        """
        import ib_insync as ibi

        records = []
        as_of = date.today()

        # Construire tous les contrats d'options
        contracts = []
        meta = []
        for expiry in expiries:
            for strike in strikes:
                for right, ot in (("C", OptionType.CALL), ("P", OptionType.PUT)):
                    opt = ibi.Option(
                        under.symbol, expiry, float(strike), right,
                        self.opt_exchange,
                        multiplier=chain_def.multiplier or "100",
                        currency=self.currency,
                        tradingClass=chain_def.tradingClass,
                    )
                    contracts.append(opt)
                    meta.append((expiry, float(strike), ot))

        # Qualifier en lot (remplit conId)
        try:
            self._ib.qualifyContracts(*contracts)
        except Exception as e:
            logger.warning(f"qualifyContracts partiel: {e}")

        # Demander l'IV de marché (tick 106) + modelGreeks pour chaque option
        tickers = []
        for opt in contracts:
            if not opt.conId:
                tickers.append(None)
                continue
            t = self._ib.reqMktData(opt, "106", snapshot=False)
            tickers.append(t)

        # Laisser le temps aux données d'arriver
        deadline = self.timeout
        elapsed = 0.0
        while elapsed < deadline:
            self._ib.sleep(0.5)
            elapsed += 0.5
            # Stop dès qu'une majorité a une IV
            ready = sum(1 for t in tickers
                        if t is not None and self._ticker_iv(t) is not None)
            if ready >= 0.7 * len([t for t in tickers if t is not None]):
                break

        # Collecter
        for (expiry, strike, ot), t in zip(meta, tickers):
            if t is None:
                continue
            iv = self._ticker_iv(t)
            mid = self._ticker_mid(t)
            mg = getattr(t, "modelGreeks", None)
            # Si modelGreeks dispo, prendre son IV (plus fiable) et le prix modèle
            if mg is not None:
                if mg.impliedVol and not math.isnan(mg.impliedVol):
                    iv = float(mg.impliedVol)
                if (mid is None or math.isnan(mid)) and mg.optPrice and not math.isnan(mg.optPrice):
                    mid = float(mg.optPrice)

            exp_date = datetime.strptime(expiry, "%Y%m%d").date()
            bid = self._safe(t.bid)
            ask = self._safe(t.ask)
            vol = self._safe(t.volume)
            self._ib.cancelMktData(t.contract)

            records.append({
                "expiry":        exp_date,
                "strike":        strike,
                "option_type":   ot.value,
                "bid":           bid,
                "ask":           ask,
                "mid":           mid if (mid and not math.isnan(mid)) else None,
                "last":          self._safe(t.last),
                "volume":        int(vol) if vol and not math.isnan(vol) else None,
                "open_interest": None,
                "iv":            iv,
            })

        return records

    @staticmethod
    def _ticker_iv(t):
        iv = getattr(t, "impliedVolatility", None)
        if iv is not None and not math.isnan(iv) and iv > 0:
            return float(iv)
        mg = getattr(t, "modelGreeks", None)
        if mg is not None and mg.impliedVol and not math.isnan(mg.impliedVol):
            return float(mg.impliedVol)
        return None

    @staticmethod
    def _ticker_mid(t):
        b = getattr(t, "bid", None); a = getattr(t, "ask", None)
        if b and a and not math.isnan(b) and not math.isnan(a) and b > 0 and a > 0:
            return (b + a) / 2.0
        return None

    @staticmethod
    def _safe(v):
        if v is None:
            return None
        try:
            f = float(v)
            return None if math.isnan(f) else f
        except Exception:
            return None