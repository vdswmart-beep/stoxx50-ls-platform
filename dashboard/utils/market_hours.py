# dashboard/utils/market_hours.py — statut d'ouverture des marchés (boule verte/rouge)
"""
Détermine si un marché boursier est ouvert selon l'heure UTC courante.
Approximation pratique : horaires réguliers, jours de semaine, hors jours fériés
(les fériés ne sont pas gérés — pour un dashboard de suivi c'est suffisant).

Horaires (heure locale → UTC) :
  - NYSE / NASDAQ (US)  : 09:30–16:00 ET  → 13:30–20:00 UTC (hiver) / 14:30–21:00 (été)
  - Euronext / Xetra / Borsa Italiana / BME : 09:00–17:30 CET → 08:00–16:30 UTC (hiver)
  - Helsinki (HEX)      : 10:00–18:30 EET → idem zone euro décalé
  - TSX (Toronto)       : mêmes heures que NYSE

Note : on utilise une heure d'été/hiver simplifiée (DST US ~mars-nov, EU ~mars-oct).
"""

from datetime import datetime, timezone


def _is_us_dst(dt: datetime) -> bool:
    # DST US : 2e dimanche de mars → 1er dimanche de novembre (approx par mois)
    return 3 <= dt.month <= 11


def _is_eu_dst(dt: datetime) -> bool:
    # DST EU : dernier dimanche de mars → dernier dimanche d'octobre (approx par mois)
    return 3 <= dt.month <= 10


def market_status(exchange: str, now_utc: datetime = None) -> dict:
    """
    Retourne {'open': bool, 'label': str, 'color': str} pour une bourse donnée.
    'exchange' peut être un nom libre ('NYSE', 'NASDAQ', 'Milan (ENI.MI)...', 'SBF'...).
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    exch = (exchange or "").upper()
    wd   = now_utc.weekday()          # 0=lundi … 6=dimanche
    h    = now_utc.hour + now_utc.minute / 60.0

    # Week-end : tout fermé
    if wd >= 5:
        return {"open": False, "label": "Fermé (week-end)", "color": "#f87171"}

    # ── Marchés européens (Euronext Paris/SBF, Xetra/IBIS, Milan/BVME, BME, Helsinki) ──
    # Vérifié EN PREMIER : pour les doubles cotations type "Milan / NYSE", la
    # cotation primaire européenne prime.
    if any(k in exch for k in ("SBF", "PARIS", "IBIS", "XETRA", "FRANKFURT", "MILAN",
                                "BVME", "BORSA", "BME", "MADRID", "AEB", "AMSTERDAM",
                                "HEX", "HELSINKI", "ENEXT", "BRUSSELS", "EUR")):
        if _is_eu_dst(now_utc):
            open_h, close_h = 7.0, 15.5      # été : 09:00–17:30 CEST = 07:00–15:30 UTC
        else:
            open_h, close_h = 8.0, 16.5      # hiver : 09:00–17:30 CET = 08:00–16:30 UTC
        is_open = open_h <= h < close_h
        return {
            "open": is_open,
            "label": "Ouvert" if is_open else "Fermé",
            "color": "#4ade80" if is_open else "#f87171",
        }

    # ── Marchés US (NYSE, NASDAQ, TSX suit les mêmes heures) ──
    if any(k in exch for k in ("NYSE", "NASDAQ", "US", "ARCA", "TSX", "TORONTO")):
        if _is_us_dst(now_utc):
            open_h, close_h = 13.5, 20.0     # été : 13:30–20:00 UTC
        else:
            open_h, close_h = 14.5, 21.0     # hiver : 14:30–21:00 UTC
        is_open = open_h <= h < close_h
        return {
            "open": is_open,
            "label": "Ouvert" if is_open else "Fermé",
            "color": "#4ade80" if is_open else "#f87171",
        }

    # Inconnu → gris neutre
    return {"open": None, "label": "Horaires inconnus", "color": "#7090a8"}


def status_dot(exchange: str, now_utc: datetime = None, with_label: bool = True):
    """
    Retourne un composant Dash html.Span : boule colorée + label optionnel.
    Vert = ouvert, rouge = fermé, gris = inconnu.
    """
    from dash import html
    st = market_status(exchange, now_utc)
    children = [
        html.Span("●", style={
            "color": st["color"], "fontSize": "12px", "marginRight": "5px",
        }),
    ]
    if with_label:
        children.append(html.Span(st["label"], style={
            "fontSize": "10px", "color": st["color"], "fontWeight": "600",
        }))
    return html.Span(children, style={"display": "inline-flex", "alignItems": "center"},
                     title=f"Marché : {st['label']}")