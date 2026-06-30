# config/universe.py — EURO STOXX 50 (50 composants, tous en EUR)
#
# Source : composition officielle STOXX au rebalancement du 22 septembre 2025
# Mapping Yahoo Finance vérifié (suffixes .DE Frankfurt, .PA Paris, .AS Amsterdam,
#   .MC Madrid, .MI Milan, .BR Bruxelles, .HE Helsinki)
# Avantage vs Nikkei : une seule devise (EUR), couverture Yahoo Finance complète,
#   meilleures données fondamentales sur les large caps européennes.

from __future__ import annotations
import logging
from typing import Dict, List

logger = logging.getLogger("Universe")

# ═══════════════════════════════════════════════════════════════════
#  50 COMPOSANTS — EURO STOXX 50
# ═══════════════════════════════════════════════════════════════════

EURO_STOXX_50: List[str] = [
    # ── Allemagne (17) ────────────────────────────────────────────
    "ADS.DE", "ALV.DE", "BAS.DE", "BAYN.DE", "BMW.DE", "DBK.DE", "DB1.DE",
    "DHL.DE", "DTE.DE", "IFX.DE", "MBG.DE", "MUV2.DE", "RHM.DE", "SAP.DE",
    "SIE.DE", "ENR.DE", "VOW.DE",
    # ── France (15) ───────────────────────────────────────────────
    "AI.PA", "AIR.PA", "CS.PA", "BNP.PA", "BN.PA", "EL.PA", "RMS.PA",
    "OR.PA", "MC.PA", "SAF.PA", "SGO.PA", "SAN.PA", "SU.PA", "TTE.PA", "DG.PA",
    # ── Pays-Bas (8) ──────────────────────────────────────────────
    "ADYEN.AS", "AD.AS", "ARGX.BR", "ASML.AS", "INGA.AS", "PRX.AS",
    "RACE.MI", "WKL.AS",
    # ── Espagne (4) ───────────────────────────────────────────────
    "BBVA.MC", "SAN.MC", "IBE.MC", "ITX.MC",
    # ── Italie (4) ────────────────────────────────────────────────
    "ENEL.MI", "ENI.MI", "ISP.MI", "UCG.MI",
    # ── Belgique (1) ──────────────────────────────────────────────
    "ABI.BR",
    # ── Finlande (1) ──────────────────────────────────────────────
    "NDA-FI.HE",
]

# Alias de compatibilité : l'ancien code référence NIKKEI_225
NIKKEI_225 = EURO_STOXX_50


# ═══════════════════════════════════════════════════════════════════
#  NOMS COMPLETS
# ═══════════════════════════════════════════════════════════════════

TICKER_NAMES: Dict[str, str] = {
    "ADS.DE": "Adidas", "ALV.DE": "Allianz", "BAS.DE": "BASF", "BAYN.DE": "Bayer",
    "BMW.DE": "BMW", "DBK.DE": "Deutsche Bank", "DB1.DE": "Deutsche Börse",
    "DHL.DE": "DHL Group", "DTE.DE": "Deutsche Telekom", "IFX.DE": "Infineon Technologies",
    "MBG.DE": "Mercedes-Benz Group", "MUV2.DE": "Munich Re", "RHM.DE": "Rheinmetall",
    "SAP.DE": "SAP", "SIE.DE": "Siemens", "ENR.DE": "Siemens Energy",
    "VOW.DE": "Volkswagen Group",
    "AI.PA": "Air Liquide", "AIR.PA": "Airbus", "CS.PA": "AXA", "BNP.PA": "BNP Paribas",
    "BN.PA": "Danone", "EL.PA": "EssilorLuxottica", "RMS.PA": "Hermès", "OR.PA": "L'Oréal",
    "MC.PA": "LVMH", "SAF.PA": "Safran", "SGO.PA": "Saint-Gobain", "SAN.PA": "Sanofi",
    "SU.PA": "Schneider Electric", "TTE.PA": "TotalEnergies", "DG.PA": "Vinci",
    "ADYEN.AS": "Adyen", "AD.AS": "Ahold Delhaize", "ARGX.BR": "Argenx",
    "ASML.AS": "ASML Holding", "INGA.AS": "ING Group", "PRX.AS": "Prosus",
    "RACE.MI": "Ferrari", "WKL.AS": "Wolters Kluwer",
    "BBVA.MC": "BBVA", "SAN.MC": "Banco Santander", "IBE.MC": "Iberdrola",
    "ITX.MC": "Inditex",
    "ENEL.MI": "Enel", "ENI.MI": "Eni", "ISP.MI": "Intesa Sanpaolo", "UCG.MI": "UniCredit",
    "ABI.BR": "Anheuser-Busch InBev",
    "NDA-FI.HE": "Nordea Bank",
}


# ═══════════════════════════════════════════════════════════════════
#  SECTEURS (GICS-like)
# ═══════════════════════════════════════════════════════════════════

SECTOR_MAP: Dict[str, str] = {
    "ADS.DE": "Consumer Discretionary", "BMW.DE": "Consumer Discretionary",
    "MBG.DE": "Consumer Discretionary", "VOW.DE": "Consumer Discretionary",
    "RMS.PA": "Consumer Discretionary", "MC.PA": "Consumer Discretionary",
    "RACE.MI": "Consumer Discretionary", "ITX.MC": "Consumer Discretionary",
    "PRX.AS": "Consumer Discretionary",
    "BN.PA": "Consumer Staples", "OR.PA": "Consumer Staples",
    "AD.AS": "Consumer Staples", "ABI.BR": "Consumer Staples",
    "ALV.DE": "Financials", "DBK.DE": "Financials", "DB1.DE": "Financials",
    "MUV2.DE": "Financials", "CS.PA": "Financials", "BNP.PA": "Financials",
    "BBVA.MC": "Financials", "SAN.MC": "Financials", "INGA.AS": "Financials",
    "ISP.MI": "Financials", "UCG.MI": "Financials", "ADYEN.AS": "Financials",
    "NDA-FI.HE": "Financials",
    "BAYN.DE": "Health Care", "EL.PA": "Health Care", "SAN.PA": "Health Care",
    "ARGX.BR": "Health Care",
    "AIR.PA": "Industrials", "SAF.PA": "Industrials", "SGO.PA": "Industrials",
    "SU.PA": "Industrials", "SIE.DE": "Industrials", "ENR.DE": "Industrials",
    "DG.PA": "Industrials", "DHL.DE": "Industrials", "RHM.DE": "Industrials",
    "WKL.AS": "Industrials",
    "SAP.DE": "Information Technology", "IFX.DE": "Information Technology",
    "ASML.AS": "Information Technology",
    "BAS.DE": "Materials", "AI.PA": "Materials",
    "TTE.PA": "Energy", "ENI.MI": "Energy",
    "IBE.MC": "Utilities", "ENEL.MI": "Utilities",
    "DTE.DE": "Communication Services",
}


SECTOR_AVERAGES: Dict[str, Dict[str, float]] = {
    "Consumer Discretionary": {"pe": 18.0, "pb": 3.2, "roe": 0.18, "oper_margin": 0.13},
    "Consumer Staples":       {"pe": 21.0, "pb": 4.5, "roe": 0.22, "oper_margin": 0.16},
    "Financials":             {"pe": 9.5,  "pb": 1.1, "roe": 0.12, "oper_margin": 0.35},
    "Health Care":            {"pe": 20.0, "pb": 4.0, "roe": 0.20, "oper_margin": 0.22},
    "Industrials":            {"pe": 19.0, "pb": 3.5, "roe": 0.17, "oper_margin": 0.12},
    "Information Technology": {"pe": 32.0, "pb": 8.0, "roe": 0.25, "oper_margin": 0.28},
    "Materials":              {"pe": 16.0, "pb": 2.5, "roe": 0.14, "oper_margin": 0.15},
    "Energy":                 {"pe": 8.0,  "pb": 1.2, "roe": 0.13, "oper_margin": 0.11},
    "Utilities":              {"pe": 13.0, "pb": 1.6, "roe": 0.11, "oper_margin": 0.18},
    "Communication Services": {"pe": 15.0, "pb": 2.0, "roe": 0.13, "oper_margin": 0.16},
}


# ═══════════════════════════════════════════════════════════════════
#  SOUS-UNIVERS
# ═══════════════════════════════════════════════════════════════════

DEFAULT_UNIVERSE: List[str] = [
    "MC.PA", "ASML.AS", "SAP.DE", "TTE.PA", "SAN.PA",
    "ALV.DE", "AIR.PA", "OR.PA", "SIE.DE", "BNP.PA",
]

LIQUID_40: List[str] = [
    "MC.PA", "ASML.AS", "SAP.DE", "TTE.PA", "SIE.DE", "OR.PA", "SAN.PA",
    "ALV.DE", "AIR.PA", "BNP.PA", "RMS.PA", "IBE.MC", "ITX.MC", "ENEL.MI",
    "AI.PA", "SU.PA", "DTE.DE", "SAF.PA", "BBVA.MC", "SAN.MC", "ABI.BR",
    "ISP.MI", "UCG.MI", "BMW.DE", "MBG.DE", "BAS.DE", "ADYEN.AS", "INGA.AS",
    "DB1.DE", "MUV2.DE", "BAYN.DE", "EL.PA", "VOW.DE", "DHL.DE", "ENI.MI",
    "AD.AS", "BN.PA", "DG.PA", "IFX.DE", "RHM.DE",
]


def get_universe(name: str = "default") -> List[str]:
    """Retourne l'univers demandé. name: 'default' (10), 'liquid40' (40), 'full' (50)."""
    mapping = {
        "default":  DEFAULT_UNIVERSE,
        "liquid40": LIQUID_40,
        "full":     EURO_STOXX_50,
    }
    if name not in mapping:
        raise ValueError(f"Univers inconnu : '{name}'. Options : {list(mapping)}")
    return mapping[name]


def get_sector(ticker: str) -> str:
    return SECTOR_MAP.get(ticker, "Unknown")


def get_name(ticker: str) -> str:
    return TICKER_NAMES.get(ticker, ticker)


def refresh_universe(output_path: str = None) -> List[str]:
    """Récupère dynamiquement la composition depuis Wikipedia, fallback statique."""
    try:
        import pandas as pd
        logger.info("Fetching EURO STOXX 50 list from Wikipedia...")
        tables = pd.read_html("https://en.wikipedia.org/wiki/EURO_STOXX_50", flavor="lxml")
        for tbl in tables:
            cols = [str(c).lower() for c in tbl.columns]
            if any("ticker" in c for c in cols):
                tick_col = tbl.columns[[i for i, c in enumerate(cols) if "ticker" in c][0]]
                tickers = [str(t).strip() for t in tbl[tick_col]
                           if "." in str(t) or "-" in str(t)]
                if len(tickers) >= 40:
                    logger.info(f"✓ {len(tickers)} tickers depuis Wikipedia")
                    return tickers
    except Exception as e:
        logger.warning(f"Refresh échoué ({e}), fallback liste statique")
    return EURO_STOXX_50