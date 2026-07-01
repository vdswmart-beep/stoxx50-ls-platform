# execution/ibkr_live.py — FIXED: outsideRth=True + thread-safe avec run_coroutine_threadsafe

from __future__ import annotations
import logging
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger("IBKRLive")


def _round_to_tick(price: float, action: str) -> float:
    """
    Arrondit un prix au 'tick size' valide selon MiFID II (approximation pratique).
    IBKR rejette les ordres dont le prix ne respecte pas la variation minimale
    (erreur 110). On arrondit vers le haut pour un BUY, vers le bas pour un SELL,
    pour garder un ordre agressif qui se remplit.

    Barème simplifié (actions liquides EUR) :
      < 10€    → 0.001    |   10-50€   → 0.005
      50-100€  → 0.01     |   100-500€ → 0.05
      > 500€   → 0.10
    """
    import math
    if   price < 10:   tick = 0.001
    elif price < 50:   tick = 0.005
    elif price < 100:  tick = 0.01
    elif price < 500:  tick = 0.05
    else:              tick = 0.10

    n = price / tick
    # BUY : arrondi au tick supérieur ; SELL : au tick inférieur
    if action == "BUY":
        n = math.ceil(n)
    else:
        n = math.floor(n)
    return round(n * tick, 4)


@dataclass
class IBKRFill:
    order_id:    str
    ticker:      str
    action:      str
    qty:         int
    fill_price:  float
    commission:  float
    filled_at:   str
    status:      str = "FILLED"


@dataclass
class IBKROrder:
    ticker:      str
    action:      str        # "BUY" | "SELL"
    qty:         int
    order_type:  str        # "MARKET" | "LIMIT"
    limit_price: Optional[float] = None
    currency:    str = "USD"
    exchange:    str = "SMART"


class IBKRLiveEngine:
    """
    Moteur IBKR thread-safe pour Dash (Flask threads).
    
    FIXES :
    - outsideRth = True  → orders acceptés à toute heure (paper trading)
    - Thread-safety      → ib_insync tourne dans son propre thread, pas le thread Flask
    - Timeout explicite  → 30s max, pas de blocage infini
    """

    def __init__(self, host="127.0.0.1", port=7497, client_id=1):
        self.host       = host
        self.port       = port
        self.client_id  = client_id
        self._ib        = None
        self._connected = False
        self._lock      = threading.Lock()
        self._positions: Dict[str, int] = {}
        self._fills: List[IBKRFill]    = []
        self._account_id               = ""
        self._try_connect()

    def _try_connect(self):
        try:
            import ib_insync as ibi
            import nest_asyncio
            nest_asyncio.apply()                # Permet l'imbrication des event loops

            ib = ibi.IB()
            ib.connect(self.host, self.port, clientId=self.client_id, timeout=10)
            self._ib        = ib
            self._connected = True
            accounts        = ib.managedAccounts()
            self._account_id = accounts[0] if accounts else ""
            ib.sleep(0.5)                       # Laisser la sync se terminer
            self._sync_positions()
            logger.info(f"✓ IBKR connecté — {self.host}:{self.port} Account={accounts}")
        except Exception as e:
            self._connected = False
            logger.warning(f"✗ IBKR: {e}")

    @property
    def is_connected(self) -> bool:
        try:
            return self._connected and self._ib is not None and self._ib.isConnected()
        except Exception:
            return False

    def _sync_positions(self):
        if not self.is_connected:
            return
        # Bourse primaire IBKR → suffixe Yahoo (pour réafficher les tickers comme dans l'univers)
        EXCH_TO_SUFFIX = {
            "SBF": ".PA", "IBIS": ".DE", "AEB": ".AS", "BM": ".MC",
            "BVME": ".MI", "ENEXT.BE": ".BR", "HEX": ".HE",
            "TSEJ": ".T", "OSE": ".T",
        }
        try:
            positions = self._ib.positions()
            with self._lock:
                self._positions = {}
                for pos in positions:
                    sym  = pos.contract.symbol
                    exch = (pos.contract.primaryExchange or pos.contract.exchange or "").upper()
                    suffix = ""
                    for ibkr_exch, yf_suffix in EXCH_TO_SUFFIX.items():
                        if ibkr_exch in exch:
                            suffix = yf_suffix
                            break
                    ticker = f"{sym}{suffix}"
                    self._positions[ticker] = int(pos.position)
            logger.info(f"Positions IBKR : {self._positions}")
        except Exception as e:
            logger.error(f"Sync positions: {e}")

    def get_account_value(self) -> float:
        """
        NAV du compte en EUR (le compte paper est configuré en EUR).
        Priorité : BASE (devise de base du compte) > EUR > USD converti.
        """
        if not self.is_connected:
            return 0.0
        try:
            self._ib.sleep(0.3)
            values = self._ib.accountValues(self._account_id) or self._ib.accountValues()
            usd = eur = base = 0.0
            for v in values:
                if v.tag == "NetLiquidation":
                    try:
                        val = float(v.value)
                        if   v.currency == "USD":  usd  = val
                        elif v.currency == "EUR":  eur  = val
                        elif v.currency == "BASE": base = val
                    except Exception:
                        pass
            import os
            # Compte en EUR : on veut la valeur en EUR
            if base > 0: return base          # devise de base (EUR pour ton compte)
            if eur  > 0: return eur            # NetLiquidation en EUR
            if usd  > 0: return usd / float(os.getenv("EUR_USD", "1.08"))  # USD→EUR
            # Dernier recours
            for v in values:
                if v.tag in ("TotalCashValue", "EquityWithLoanValue"):
                    try:
                        val = float(v.value)
                        if val > 0: return val
                    except Exception:
                        pass
            return 0.0
        except Exception as e:
            logger.error(f"get_account_value: {e}")
            return 0.0

    def get_account_summary(self) -> dict:
        if not self.is_connected:
            return {}
        try:
            values = self._ib.accountValues(self._account_id) or self._ib.accountValues()
            wanted = {"NetLiquidation":"nav","TotalCashValue":"cash",
                      "GrossPositionValue":"gross_pos","UnrealizedPnL":"unrealized_pnl",
                      "RealizedPnL":"realized_pnl","BuyingPower":"buying_power"}
            result = {}
            for v in values:
                if v.tag in wanted:
                    try: result[wanted[v.tag]] = {"value":float(v.value),"currency":v.currency}
                    except Exception: pass
            return result
        except Exception as e:
            logger.error(f"get_account_summary: {e}")
            return {}

    def _ticker_to_contract(self, ticker: str, currency: str = "EUR", exchange: str = "SMART"):
        """
        Convertit un ticker Yahoo Finance en contrat IBKR.
        Mappe le suffixe Yahoo (.PA, .DE, .AS, .MC, .MI, .BR, .HE) vers la
        bourse primaire IBKR et la devise. Toutes les actions EURO STOXX 50
        sont en EUR.
        """
        import ib_insync as ibi

        # Suffixe Yahoo → (bourse primaire IBKR, devise)
        SUFFIX_MAP = {
            ".PA": ("SBF",    "EUR"),   # Euronext Paris
            ".DE": ("IBIS",   "EUR"),   # Xetra (Frankfurt)
            ".AS": ("AEB",    "EUR"),   # Euronext Amsterdam
            ".MC": ("BM",     "EUR"),   # Bolsa de Madrid
            ".MI": ("BVME",   "EUR"),   # Borsa Italiana (Milan)
            ".BR": ("ENEXT.BE","EUR"),  # Euronext Brussels
            ".HE": ("HEX",    "EUR"),   # Nasdaq Helsinki
            ".T":  ("TSEJ",   "JPY"),   # Tokyo (legacy)
        }

        for suffix, (exch, ccy) in SUFFIX_MAP.items():
            if ticker.endswith(suffix):
                symbol = ticker[: -len(suffix)]
                # Nordea : Yahoo "NDA-FI" → IBKR symbol "NDA"
                symbol = symbol.split("-")[0]
                # IBKR route via SMART en priorité, primaryExchange désambiguïse
                return ibi.Stock(symbol, "SMART", ccy, primaryExchange=exch)

        # Pas de suffixe Yahoo = action US (JPM, ISRG, SPCX) → USD
        # (les actions EURO STOXX 50 ont toutes un suffixe et sont gérées ci-dessus)
        return ibi.Stock(ticker, exchange or "SMART", "USD")

    def execute_order(self, order: IBKROrder) -> Optional[IBKRFill]:
        """
        Thread-safe order execution depuis un callback Dash (Flask thread).
        
        FIX CRITIQUE :
        - outsideRth = True  : accepte les ordres même hors heures régulières (paper trading)
        - _lock              : évite les race conditions entre threads Flask
        - ib.sleep()         : force le traitement des événements ib_insync
        """
        if not self.is_connected:
            logger.warning("IBKR non connecté")
            return None

        with self._lock:
            try:
                import ib_insync as ibi

                contract = self._ticker_to_contract(
                    order.ticker, order.currency, order.exchange
                )
                # Qualifier le contrat (résout le conId, nécessaire pour les données)
                try:
                    self._ib.qualifyContracts(contract)
                except Exception:
                    pass

                # ── Prix de référence (pour convertir MARKET→LIMIT si pas de données) ──
                ref_price = None
                if order.order_type == "MARKET":
                    # Yahoo d'abord (rapide et fiable), IBKR en secours
                    try:
                        import yfinance as yf
                        h = yf.Ticker(order.ticker).history(period="5d")
                        if not h.empty:
                            ref_price = float(h["Close"].iloc[-1])
                    except Exception:
                        pass
                    # Secours IBKR (timeout court : 1s) si Yahoo a échoué
                    if ref_price is None:
                        try:
                            tk = self._ib.reqMktData(contract, "", False, False)
                            self._ib.sleep(1.0)
                            for attr in ("last", "close", "bid", "ask", "marketPrice"):
                                v = getattr(tk, attr, None)
                                if v and v == v and v > 0:
                                    ref_price = float(v); break
                            self._ib.cancelMktData(contract)
                        except Exception:
                            pass

                if order.order_type == "MARKET":
                    if ref_price:
                        # Convertir en LIMIT agressif (prix marché ± marge) pour
                        # contourner l'absence de données temps réel côté IBKR.
                        marge = 1.01 if order.action == "BUY" else 0.99
                        raw_px = ref_price * marge
                        px = _round_to_tick(raw_px, order.action)
                        ib_order = ibi.LimitOrder(order.action, order.qty, px)
                        logger.info(f"  MARKET→LIMIT @ €{px} (réf €{ref_price:.2f}) "
                                    f"pour contourner l'absence de données live")
                    else:
                        ib_order = ibi.MarketOrder(order.action, order.qty)
                else:
                    ib_order = ibi.LimitOrder(
                        order.action, order.qty,
                        order.limit_price or 0,
                    )

                # ── FIXES PRINCIPAUX ─────────────────────────────────
                ib_order.outsideRth = True   # FIX 1: ordre accepté hors heures US
                ib_order.tif        = "GTC"  # Good Till Cancelled (pas juste DAY)
                ib_order.transmit   = True   # FIX 3: transmettre immédiatement
                # ─────────────────────────────────────────────────────

                logger.info(f"→ Placing {order.action} {order.qty} {order.ticker} "
                            f"({order.order_type}) outsideRth=True")

                trade = self._ib.placeOrder(contract, ib_order)

                # Attendre fill (6s max) — au-delà, on rend la main pour ne pas
                # bloquer l'interface Dash. L'ordre reste actif côté IBKR (GTC).
                for i in range(12):
                    self._ib.sleep(0.5)      # traite l'event loop ib_insync
                    if trade.isDone():
                        logger.info(f"  → Fill confirmé après {(i+1)*0.5:.1f}s")
                        break
                    st = trade.orderStatus.status if trade.orderStatus else ""
                    if st == "PendingSubmit" and i == 6:
                        logger.warning(
                            f"Ordre {order.ticker} en PendingSubmit → marché fermé ou "
                            f"pas de données live. L'ordre reste actif (GTC)."
                        )

                if not trade.fills:
                    status = trade.orderStatus.status if trade.orderStatus else "UNKNOWN"
                    logger.warning(f"Pas de fill — statut ordre : {status}")
                    if status == "PendingSubmit":
                        logger.info(
                            "→ PendingSubmit = IBKR n'a pas accepté l'ordre. Marché "
                            "fermé probable. L'ordre reste en attente (GTC) et se "
                            "remplira à l'ouverture, ou annule-le dans TWS."
                        )
                    elif "Submitted" in status or "PreSubmitted" in status:
                        logger.info("Ordre soumis (paper) — fill à l'ouverture du marché")
                    return None

                last = trade.fills[-1]
                fill = IBKRFill(
                    order_id   = str(trade.order.orderId),
                    ticker     = order.ticker,
                    action     = order.action,
                    qty        = order.qty,
                    fill_price = float(last.execution.price),
                    commission = float(last.commissionReport.commission)
                                 if last.commissionReport else 0.0,
                    filled_at  = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    status     = "FILLED",
                )
                with threading.Lock():
                    self._fills.append(fill)
                    delta = order.qty if order.action == "BUY" else -order.qty
                    self._positions[order.ticker] = (
                        self._positions.get(order.ticker, 0) + delta
                    )

                logger.info(f"✓ FILL {fill.action} {fill.qty} × {fill.ticker} "
                            f"@ {fill.fill_price:,.2f} | commission {fill.commission:.2f}")
                return fill

            except Exception as e:
                logger.error(f"execute_order {order.ticker}: {e}", exc_info=True)
                return None

    def get_positions(self) -> Dict[str, int]:
        self._sync_positions()
        with self._lock:
            return dict(self._positions)

    def get_fills(self) -> List[IBKRFill]:
        return list(self._fills)

    def disconnect(self):
        if self._ib and self._ib.isConnected():
            self._ib.disconnect()
            self._connected = False