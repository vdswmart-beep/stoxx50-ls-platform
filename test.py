#!/usr/bin/env python3
# test_order.py — teste l'exécution d'un ordre SANS le dashboard
# Usage : place à la racine ~/STOXX50/ et lance : python test_order.py

import sys, logging
sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")

print("=" * 60)
print("TEST 1 : Connexion IBKR (auto dans le constructeur)")
print("=" * 60)

from execution.ibkr_live import IBKRLiveEngine, IBKROrder

# La connexion se fait automatiquement dans __init__
engine = IBKRLiveEngine(host="127.0.0.1", port=7497, client_id=99)

# is_connected est une PROPRIÉTÉ (pas de parenthèses)
print(f"\n→ Connecté : {engine.is_connected}")

if not engine.is_connected:
    print("❌ Pas de connexion. TWS ouvert avec API activée ?")
    sys.exit(1)

print(f"→ NAV compte : €{engine.get_account_value():,.0f}")
print(f"→ Positions actuelles : {engine.get_positions()}")

print("\n" + "=" * 60)
print("TEST 2 : BUY 10 MC.PA (MARKET)")
print("=" * 60)

order = IBKROrder(
    ticker="MC.PA", action="BUY", qty=10,
    order_type="MARKET", currency="EUR", exchange="SBF",
)

print("\n→ Envoi de l'ordre (peut prendre jusqu'à 8s)...\n")
fill = engine.execute_order(order)

if fill:
    print(f"\n✅ ORDRE REMPLI : {fill.qty} × {fill.ticker} @ €{fill.fill_price}")
else:
    print(f"\n⚠️  Ordre non rempli immédiatement.")
    print("   Regarde les logs ci-dessus : cherche 'MARKET→LIMIT' et le statut.")

print(f"\n→ Positions après : {engine.get_positions()}")

print("\n" + "=" * 60)
print("TEST 3 : BUY 10 JPM (action US, MARKET)")
print("=" * 60)

order_us = IBKROrder(
    ticker="JPM", action="BUY", qty=10,
    order_type="MARKET", currency="USD", exchange="SMART",
)
print("\n→ Envoi ordre JPM...\n")
fill_us = engine.execute_order(order_us)
if fill_us:
    print(f"\n✅ JPM REMPLI : {fill_us.qty} × JPM @ ${fill_us.fill_price}")
else:
    print(f"\n⚠️  JPM non rempli (marché US ouvre 15h30 Paris)")

engine.disconnect()
print("\n✓ Test terminé.")