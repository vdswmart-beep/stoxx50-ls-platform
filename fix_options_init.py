#!/usr/bin/env python3
# fix_options_init.py — Répare les __init__.py du package options
#
# Usage : place ce fichier à la racine du projet (NKY_225/) et lance :
#     python fix_options_init.py
#
# Il réécrit les 4 __init__.py du package options avec les bons exports.
# C'est la cause du bug "cannot import name 'BlackScholes' from 'options.pricing'".

import os

ROOT = os.path.dirname(os.path.abspath(__file__))

# Détecte le dossier options (minuscule ou majuscule)
OPT = None
for name in ("options", "Options"):
    if os.path.isdir(os.path.join(ROOT, name)):
        OPT = os.path.join(ROOT, name)
        break
if OPT is None:
    raise SystemExit("❌ Dossier 'options' introuvable à la racine du projet.")

print(f"📂 Package options : {OPT}")

FILES = {
    "pricing/__init__.py": '''"""Pricing engine (framework-agnostic)."""
from .black_scholes import BlackScholes, BSParams, Greeks, OptionType
from .implied_vol import ImpliedVolatilitySolver, IVResult, IVStatus
from .parity import ParityResult, check_put_call_parity

__all__ = [
    "BlackScholes", "BSParams", "Greeks", "OptionType",
    "ImpliedVolatilitySolver", "IVResult", "IVStatus",
    "ParityResult", "check_put_call_parity",
]
''',

    "volatility/__init__.py": '''"""Volatility analytics: smiles, term structure, 3D surface."""
from .surface import SurfaceGrid, VolatilitySurface
__all__ = ["SurfaceGrid", "VolatilitySurface"]
''',

    "strategies/__init__.py": '''"""Multi-leg option strategies and payoff/Greek analytics."""
from .base import LegKind, OptionLeg, Strategy, as_vol_fn
from .strategies import STRATEGY_REGISTRY, StrategySpec, build_strategy
__all__ = [
    "LegKind", "OptionLeg", "Strategy", "as_vol_fn",
    "StrategySpec", "STRATEGY_REGISTRY", "build_strategy",
]
''',

    "__init__.py": '''"""Options analytics package — European option pricing for the STOXX 50."""
from .option_chain import OptionChain
from .mock_provider import MockProvider, get_option_chain, TICKER_MARKET
from .ibkr_provider import IBKRProvider
from .pricing import (
    BlackScholes, BSParams, Greeks, OptionType,
    ImpliedVolatilitySolver, check_put_call_parity,
)
from .volatility import VolatilitySurface, SurfaceGrid
from .strategies import STRATEGY_REGISTRY, build_strategy

__all__ = [
    "OptionChain", "MockProvider", "IBKRProvider", "get_option_chain", "TICKER_MARKET",
    "BlackScholes", "BSParams", "Greeks", "OptionType",
    "ImpliedVolatilitySolver", "check_put_call_parity",
    "VolatilitySurface", "SurfaceGrid",
    "STRATEGY_REGISTRY", "build_strategy",
]
''',
}

for rel, content in FILES.items():
    path = os.path.join(OPT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    print(f"  ✓ écrit : {rel}")

# Test d'import immédiat
print("\n🔍 Test d'import...")
import sys
sys.path.insert(0, ROOT)
try:
    from options.pricing import BlackScholes
    from options.volatility import VolatilitySurface
    from options.strategies import build_strategy
    from options import get_option_chain
    print("✅ SUCCÈS : tous les imports fonctionnent. L'Options Lab va marcher.")
except Exception as e:
    print(f"❌ Import encore cassé : {e}")
    print("   → Vérifie que black_scholes.py, implied_vol.py, parity.py,")
    print("     surface.py, base.py, strategies.py sont bien dans options/")