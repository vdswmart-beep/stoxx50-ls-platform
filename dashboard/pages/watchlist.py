# dashboard/pages/watchlist.py — FIXED: SPCX data + status stores persistants

from dash import html, dcc, get_app
import dash_bootstrap_components as dbc
import pandas as pd
import numpy as np
import plotly.graph_objects as go

try:
    from dashboard.utils.market_hours import status_dot as _mkt_status_dot
except Exception:
    def _mkt_status_dot(exchange, *a, **k):
        from dash import html
        return html.Span()  # fallback silencieux si le module manque

_BG="#0f141b";_BG2="#0a0d12";_GRID="rgba(255,255,255,0.04)"
_TEXT="#c8d8e8";_MUTED="#7090a8";_BORDER="1px solid #1e2a38"
_FONT=dict(family="Inter, system-ui, sans-serif",color=_TEXT,size=11)
_CARD={"backgroundColor":_BG,"border":"1px solid #1e2a38","borderRadius":"8px","padding":"16px","marginBottom":"14px"}
_LABEL={"fontSize":"10px","color":"#7eb8d8","textTransform":"uppercase","letterSpacing":".08em","marginBottom":"8px","fontWeight":"600"}
_H1={"fontSize":"11px","color":"#7eb8d8","textTransform":"uppercase","letterSpacing":".1em","marginBottom":"18px","fontWeight":"600"}

WATCHLIST = {
    "JPM":   {"name":"JPMorgan Chase & Co.","sector":"Financials","exchange":"NYSE",
               "currency":"USD","yf_ticker":"JPM",
               "thesis":"Largest US bank. Higher-for-longer rates boost NII. Best-in-class risk management.",
               "bull":["NII resilience","IB fee recovery","$12B+ buybacks"],
               "bear":["Credit loss cycle","Regulatory capital","Recession"],
               "comps":["BAC","WFC","C","GS","MS"]},
    "ISRG":  {"name":"Intuitive Surgical Inc.","sector":"Healthcare MedTech","exchange":"NASDAQ",
               "currency":"USD","yf_ticker":"ISRG",
               "thesis":"~80% robotic surgery market share. Razor/razorblade model. Global procedure volume secular growth.",
               "bull":["Volume growth globally","Ion platform expansion","International penetration"],
               "bear":["Competition Hugo/Ottava","Hospital capex cuts","50x PE valuation"],
               "comps":["MDT","SYK","ABT","BSX","EW"]},
    "SPCX":  {"name":"Space Exploration Technologies Corp.","sector":"Aerospace / AI","exchange":"NASDAQ",
               "currency":"USD","yf_ticker":"SPCX",
               "thesis":"IPO historique 12 juin 2026 ($135/sh, $1.75T). 3 segments: Starlink (profitable), Space, AI/xAI (cash-burning). Pari sur dominance spatiale et IA long terme.",
               "bull":["Starlink 10M+ abonnés","Monopole launch ~60% PDM","xAI Grok vs OpenAI"],
               "bear":["Perte nette $4.9B 2025","Valorisation élevée P/S>100x","Lock-up expiry 180j"],
               "comps":["RKLB","LMT","BA","ASTS","TSLA"],
               "ipo_note":"IPO 12/06/2026 · $135 → ATH $225.64 · Lock-up 180j"},
    "ENI-MI":{"name":"Eni S.p.A.","sector":"Energy / Oil & Gas","exchange":"Milan (ENI.MI) / NYSE (E)",
               "currency":"EUR","yf_ticker":"ENI.MI","yf_ticker_adr":"E",
               "thesis":"Major européen oil&gas avec transition: Enilive (biocarburants), Plenitude (renouvelables), GNL Afrique. Div ~4.5%.",
               "bull":["Dividende 4.5%+","Biocarburants Enilive","GNL Afrique croissance"],
               "bear":["Prix pétrole","Actifs risqués (Libye)","Pression ESG"],
               "comps":["SHEL","BP","TTE","XOM","CVX"],
               "earnings_next":"29 juillet 2026"},
    "XNDU":  {"name":"Xanadu Quantum Technologies Ltd.","sector":"Quantum Computing / Deep Tech","exchange":"NASDAQ",
               "currency":"USD","yf_ticker":"XNDU",
               "thesis":"Premier pure-player coté en photonique quantique (IPO via SPAC Crane Harbor, mars 2026). Pari deep-tech long terme sur l'informatique quantique fault-tolerant. Très spéculatif : cash-burn élevé, revenus minimes.",
               "bull":["Leader photonique quantique","IPO 2026 → $272M+ de cash","Soutien gouv. Canada/Ontario (Projet OPTIMISM)"],
               "bear":["Perte opérationnelle Q1 -$23M","Revenus infimes ($2.8M Q1)","Dilution (facilité ATM $300M)","Techno pré-commerciale"],
               "comps":["IONQ","RGTI","QBTS","INFQ"]},
}

# Note: on utilise "ENI-MI" (tiret) au lieu de "ENI.MI" (point) pour les IDs Dash


def _safe(v):
    if v is None: return None
    try:
        f=float(v); return None if(np.isnan(f) or np.isinf(f)) else f
    except Exception: return None

def _fmt_large(v,sym="$"):
    if not v or(_isinstance:=isinstance(v,float)) and np.isnan(v): return "—"
    v=float(v)
    if v>=1e12: return f"{sym}{v/1e12:.2f}T"
    if v>=1e9:  return f"{sym}{v/1e9:.1f}B"
    if v>=1e6:  return f"{sym}{v/1e6:.0f}M"
    return f"{sym}{v:,.0f}"

def _fmt_pct(v):
    if v is None or(isinstance(v,float) and np.isnan(v)): return "—"
    return f"{float(v)*100:.1f}%"

def _fmt_x(v,mx=500):
    if v is None or(isinstance(v,float) and np.isnan(v)): return "—"
    v=float(v); return "—" if v<=0 or v>mx else f"{v:.1f}x"

def _row(label,val,color="#c8d8e8"):
    return html.Div([
        html.Span(label,style={"color":_MUTED,"fontSize":"10px","flex":"1"}),
        html.Span(str(val),style={"color":color,"fontSize":"11px","fontWeight":"600","fontVariantNumeric":"tabular-nums"}),
    ],style={"display":"flex","justifyContent":"space-between","padding":"5px 0","borderBottom":"1px solid #1a2030"})


def _decision_panel(info, close):
    """
    Panneau de décision : score 0-100 décomposé en 4 piliers, chaque point
    justifié. C'est la synthèse « en un coup d'œil » de tout le reste.
    """
    try:
        from dashboard.utils.decision_score import compute_decision
        d = compute_decision(info or {}, close)
    except Exception:
        return html.Div()

    score   = d["score"]
    verdict = d["verdict"]
    v_color = {"BUY": "#4ade80", "HOLD": "#f0a500", "AVOID": "#f87171"}[verdict]
    pillar_names = {"momentum": "MOMENTUM", "quality": "QUALITÉ",
                    "valuation": "VALORISATION", "risk": "RISQUE"}

    pillar_rows = []
    for key, p in d["pillars"].items():
        ps = p["score"]
        bar_color = "#4ade80" if ps >= 60 else "#f0a500" if ps >= 40 else "#f87171"
        # Ligne pilier : nom + barre + score
        pillar_rows.append(html.Div([
            html.Div([
                html.Span(pillar_names[key], style={"fontSize":"10px","color":"#94b8cc",
                          "fontWeight":"600","width":"110px","display":"inline-block"}),
                html.Span(f"{ps:.0f}", style={"fontSize":"11px","color":bar_color,
                          "fontWeight":"700","marginLeft":"6px"}),
                html.Span(f"  ×{p['weight']:.0%}", style={"fontSize":"9px","color":_MUTED}),
            ]),
            html.Div(style={"height":"5px","backgroundColor":"#1a2030","borderRadius":"3px",
                            "marginTop":"3px","marginBottom":"4px"},
                     children=html.Div(style={"height":"100%","width":f"{ps:.0f}%",
                              "backgroundColor":bar_color,"borderRadius":"3px"})),
            # Détails justificatifs : chaque composante avec ses points
            html.Div([
                html.Div([
                    html.Span(f"{label} : ", style={"fontSize":"9px","color":_MUTED}),
                    html.Span(f"{val}", style={"fontSize":"9px","color":"#c8d8e8","fontWeight":"600"}),
                    html.Span(f" ({vdict})", style={"fontSize":"9px","color":_MUTED,"fontStyle":"italic"}),
                    html.Span(f"  {'+' if pts>0 else ''}{pts}",
                              style={"fontSize":"9px","fontWeight":"700",
                                     "color":"#4ade80" if pts>0 else "#f87171" if pts<0 else _MUTED}),
                ], style={"lineHeight":"1.5"})
                for label, val, vdict, pts in p["details"]
            ], style={"paddingLeft":"4px","marginBottom":"8px"}),
        ]))

    return html.Div([
        html.Div("DÉCISION — SCORE JUSTIFIÉ", style=_LABEL),
        # Gros verdict
        html.Div([
            html.Span(f"{score:.0f}", style={"fontSize":"36px","fontWeight":"800",
                      "color":v_color,"letterSpacing":"-1px"}),
            html.Span("/100  ", style={"fontSize":"14px","color":_MUTED}),
            html.Span(verdict, style={"fontSize":"18px","fontWeight":"800","color":v_color,
                      "backgroundColor":f"rgba({'74,222,128' if verdict=='BUY' else '240,165,0' if verdict=='HOLD' else '248,113,113'},.12)",
                      "border":f"1px solid {v_color}","borderRadius":"6px",
                      "padding":"3px 14px","marginLeft":"10px"}),
        ], style={"marginBottom":"12px","display":"flex","alignItems":"baseline"}),
        html.Div(pillar_rows),
        html.Div("Pondération : Momentum 35% · Qualité 25% · Valo 20% · Risque 20%. "
                 "Chaque ligne montre sa contribution en points.",
                 style={"fontSize":"8px","color":"#3a5060","marginTop":"6px","fontStyle":"italic"}),
    ], style=_CARD)


def _fetch(yf_ticker,period="2y"):
    """Fetch Yahoo Finance avec fallback pour tickers récents (SPCX)."""
    try:
        import yfinance as yf
        tk   = yf.Ticker(yf_ticker)
        info = tk.info or {}
        # Pour les tickers très récents, essayer une période plus courte
        for p in [period,"1y","6mo","3mo","1mo"]:
            try:
                hist = tk.history(period=p,interval="1d")
                if not hist.empty:
                    hist = hist.reset_index()
                    hist.columns=[c.lower() for c in hist.columns]
                    return info, hist
            except Exception:
                continue
        return info, pd.DataFrame()
    except Exception as e:
        logger.error(f"fetch {yf_ticker}: {e}")
        return {}, pd.DataFrame()


def _price_fig(df,ticker,sym="$",height=260):
    if df is None or df.empty:
        return go.Figure().update_layout(
            paper_bgcolor=_BG,plot_bgcolor=_BG,height=height,
            annotations=[dict(text=f"Données non disponibles pour {ticker}",
                              xref="paper",yref="paper",x=0.5,y=0.5,
                              font=dict(color=_MUTED,size=12),showarrow=False)])
    df=df.copy(); df.columns=[c.lower() for c in df.columns]
    date_col ="date"  if"date"  in df.columns else df.columns[0]
    close_col="close" if"close" in df.columns else df.columns[1]
    vol_col  ="volume"if"volume"in df.columns else None
    close=df[close_col].astype(float); dates=df[date_col]
    if len(close)<2: return go.Figure()
    chg=(close.iloc[-1]/close.iloc[0]-1)*100
    lc="#4ade80" if chg>=0 else "#f87171"
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=dates,y=close,name="Prix",mode="lines",
        line=dict(color=lc,width=2),fill="tozeroy",
        fillcolor=f"rgba({'74,222,128' if chg>=0 else '248,113,113'},0.05)",
        hovertemplate=f"%{{x|%Y-%m-%d}}<br><b>{sym}%{{y:.2f}}</b><extra></extra>"))
    if len(close)>=50:
        fig.add_trace(go.Scatter(x=dates,y=close.rolling(50).mean(),name="MA50",line=dict(color="#f0a500",width=1,dash="dot")))
    if len(close)>=200:
        fig.add_trace(go.Scatter(x=dates,y=close.rolling(200).mean(),name="MA200",line=dict(color="#c084fc",width=1,dash="dash")))
    if vol_col:
        fig.add_trace(go.Bar(x=dates,y=df[vol_col].astype(float),name="Vol",yaxis="y2",
            marker=dict(color="rgba(124,200,255,0.55)",line=dict(width=0))))
    fig.update_layout(
        paper_bgcolor=_BG,plot_bgcolor=_BG,font=_FONT,height=height,
        margin=dict(l=50,r=60,t=36,b=30),hovermode="x unified",
        legend=dict(orientation="h",y=1.05,font=dict(size=9,color=_MUTED)),
        title=dict(text=f"{ticker}  {sym}{close.iloc[-1]:.2f}  <span style='color:{lc}'>{chg:+.1f}% (période)</span>",
                   font=dict(size=12,color=_TEXT),x=0),
        xaxis=dict(gridcolor=_GRID,tickfont=dict(size=9,color=_MUTED)),
        yaxis=dict(gridcolor=_GRID,tickprefix=sym,tickformat=",.2f",tickfont=dict(size=9,color=_MUTED)),
        yaxis2=dict(overlaying="y",side="right",showgrid=False,
            range=[0,df[vol_col].astype(float).max()*5] if vol_col else [0,1],
            tickfont=dict(size=8,color="#2a3d50")),
    )
    return fig


def _technicals(close):
    r={"rsi":"—","macd":"—","macd_color":"#c8d8e8","bb":"—","bb_sig":"Neutre"}
    if len(close)<30: return r
    d=close.diff(); g=d.clip(lower=0).rolling(14).mean(); l=(-d.clip(upper=0)).rolling(14).mean()
    rsi=100-100/(1+g/l.replace(0,np.nan))
    if not rsi.empty and not np.isnan(rsi.iloc[-1]):
        r["rsi"]=f"{rsi.iloc[-1]:.1f}"
    e12=close.ewm(span=12,adjust=False).mean(); e26=close.ewm(span=26,adjust=False).mean()
    macd=e12-e26; sig=macd.ewm(span=9,adjust=False).mean()
    r["macd"]="Haussier ↑" if macd.iloc[-1]>sig.iloc[-1] else "Baissier ↓"
    r["macd_color"]="#4ade80" if macd.iloc[-1]>sig.iloc[-1] else "#f87171"
    if len(close)>=20:
        ma20=close.rolling(20).mean(); std20=close.rolling(20).std()
        up=ma20+2*std20; lo=ma20-2*std20
        denom=up.iloc[-1]-lo.iloc[-1]
        if denom>0:
            pos=(close.iloc[-1]-lo.iloc[-1])/denom*100
            r["bb"]=f"{pos:.0f}% bande"
            r["bb_sig"]="Suracheté" if pos>80 else "Survendu" if pos<20 else "Neutre"
    return r


import logging
logger = logging.getLogger("Watchlist")


def _build_panel(ticker_key,config):
    yf_ticker=config.get("yf_ticker",ticker_key)
    currency =config.get("currency","USD")
    sym      ="$" if currency=="USD" else "€"
    ipo_note =config.get("ipo_note")
    earn_next=config.get("earnings_next")

    info,hist = _fetch(yf_ticker)

    curr_price=_safe(info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose"))
    day_chg   =_safe(info.get("regularMarketChangePercent")) or 0
    day_color ="#4ade80" if day_chg>=0 else "#f87171"

    close=hist["close"].astype(float) if not hist.empty and"close"in hist.columns else pd.Series([])
    tech =_technicals(close)
    fig  =_price_fig(hist,ticker_key,sym,height=260)

    # Info manquante pour SPCX (trop récent) → fallback
    pe       =_fmt_x(_safe(info.get("trailingPE")))
    pe_fwd   =_fmt_x(_safe(info.get("forwardPE")))
    pb       =_fmt_x(_safe(info.get("priceToBook")))
    ev_eb    =_fmt_x(_safe(info.get("enterpriseToEbitda")))
    div_yield=_fmt_pct(_safe(info.get("dividendYield")))
    mkt_cap  =_fmt_large(_safe(info.get("marketCap")),sym)
    rev      =_fmt_large(_safe(info.get("totalRevenue")),sym)
    net_inc  =_fmt_large(_safe(info.get("netIncomeToCommon")),sym)
    ebitda   =_fmt_large(_safe(info.get("ebitda")),sym)
    roe      =_fmt_pct(_safe(info.get("returnOnEquity")))
    gross_m  =_fmt_pct(_safe(info.get("grossMargins")))
    oper_m   =_fmt_pct(_safe(info.get("operatingMargins")))
    net_m    =_fmt_pct(_safe(info.get("profitMargins")))
    beta     =f"{_safe(info.get('beta')):.2f}" if _safe(info.get("beta")) else "—"
    hi52     =f"{sym}{_safe(info.get('fiftyTwoWeekHigh')):.2f}" if _safe(info.get("fiftyTwoWeekHigh")) else "—"
    lo52     =f"{sym}{_safe(info.get('fiftyTwoWeekLow')):.2f}"  if _safe(info.get("fiftyTwoWeekLow"))  else "—"
    pt       =_safe(info.get("targetMeanPrice"))
    pt_str   =f"{sym}{pt:.2f}" if pt else "—"
    pt_up    =((pt/curr_price-1)*100) if(pt and curr_price) else 0
    rec      =(info.get("recommendationKey","—") or "—").upper()
    n_anal   =info.get("numberOfAnalystOpinions",0) or 0
    rec_c    ={"BUY":"#4ade80","STRONG_BUY":"#4ade80","HOLD":"#f0a500","SELL":"#f87171"}.get(rec,"#7090a8")

    # Données SPCX spécifiques si yfinance ne les a pas
    spcx_override = {}
    if ticker_key == "SPCX" and not curr_price:
        spcx_override = {
            "curr_price_str": "~$165 (données YF en cours d'intégration)",
            "note": "SPCX IPO le 12/06/2026. Yahoo Finance met plusieurs semaines à intégrer les nouvelles cotations. Données estimées basées sur sources publiques.",
        }
        mkt_cap = "~$1.85T"
        rev     = "~$19.3B (TTM)"
        net_inc = "-$4.9B (2025)"
        pe      = "Négatif"; pe_fwd = "—"; pb = "—"

    # ID safe pour Dash (pas de points)
    safe_id = "".join(c if c.isalnum() else "-" for c in str(ticker_key))

    return html.Div([
        html.Div([
            html.Div([
                html.Span(config["name"],style={"fontSize":"16px","fontWeight":"700","color":"#e8f2ff","marginRight":"12px"}),
                html.Span(f"{sym}{curr_price:,.2f}" if curr_price else spcx_override.get("curr_price_str","—"),
                          style={"fontSize":"15px","fontWeight":"600","color":"#c8d8e8","marginRight":"8px"}),
                html.Span(f"{day_chg:+.2f}%" if day_chg else "",
                          style={"fontSize":"13px","color":day_color,"fontWeight":"600"}),
            ],style={"display":"flex","alignItems":"baseline","flexWrap":"wrap","gap":"4px"}),
            html.Div([
                html.Span(config["exchange"],style={"fontSize":"10px","color":"#5a7080","marginRight":"10px"}),
                _mkt_status_dot(config["exchange"]),
                html.Span(config["sector"],style={"fontSize":"10px","color":"#4a9eff","marginLeft":"10px",
                    "backgroundColor":"rgba(74,158,255,.1)","border":"1px solid rgba(74,158,255,.2)",
                    "borderRadius":"4px","padding":"1px 8px"}),
                html.Span(f"  Earnings : {earn_next}",style={"fontSize":"10px","color":"#f0a500","marginLeft":"10px"}) if earn_next else None,
            ],style={"marginTop":"4px","display":"flex","alignItems":"center","flexWrap":"wrap"}),
            html.Div(ipo_note,style={"fontSize":"10px","color":"#f0a500",
                "backgroundColor":"rgba(240,165,0,.08)","border":"1px solid rgba(240,165,0,.2)",
                "borderRadius":"4px","padding":"3px 10px","marginTop":"6px","display":"inline-block"}) if ipo_note else None,
            html.Div(spcx_override.get("note",""),style={"fontSize":"10px","color":"#7090a8","marginTop":"6px"}) if spcx_override.get("note") else None,
        ],style={"marginBottom":"14px"}),

        dbc.Row([
            dbc.Col([
                html.Div([dcc.Graph(figure=fig,config={"displayModeBar":False},id=f"chart-{safe_id}")],style=_CARD),
                html.Div([
                    html.Div("MÉTRIQUES CLÉS",style=_LABEL),
                    dbc.Row([
                        dbc.Col(html.Div([html.Div("Market Cap",style={"fontSize":"9px","color":_MUTED,"textTransform":"uppercase","marginBottom":"2px"}),html.Div(mkt_cap,style={"fontSize":"13px","fontWeight":"700","color":"#c8d8e8"})],style={"textAlign":"center","padding":"8px"}),width=3),
                        dbc.Col(html.Div([html.Div("52W High",style={"fontSize":"9px","color":_MUTED,"textTransform":"uppercase","marginBottom":"2px"}),html.Div(hi52,style={"fontSize":"13px","fontWeight":"700","color":"#4ade80"})],style={"textAlign":"center","padding":"8px"}),width=3),
                        dbc.Col(html.Div([html.Div("52W Low",style={"fontSize":"9px","color":_MUTED,"textTransform":"uppercase","marginBottom":"2px"}),html.Div(lo52,style={"fontSize":"13px","fontWeight":"700","color":"#f87171"})],style={"textAlign":"center","padding":"8px"}),width=3),
                        dbc.Col(html.Div([html.Div("Beta",style={"fontSize":"9px","color":_MUTED,"textTransform":"uppercase","marginBottom":"2px"}),html.Div(beta,style={"fontSize":"13px","fontWeight":"700","color":"#c8d8e8"})],style={"textAlign":"center","padding":"8px"}),width=3),
                    ],className="g-0"),
                ],style=_CARD),
                html.Div([
                    html.Div("INDICATEURS TECHNIQUES",style=_LABEL),
                    dbc.Row([
                        dbc.Col(html.Div([html.Div("RSI (14)",style={"fontSize":"9px","color":_MUTED,"textTransform":"uppercase","marginBottom":"3px"}),
                            html.Div(tech["rsi"],style={"fontSize":"20px","fontWeight":"700",
                                "color":"#f87171" if(float(tech["rsi"]) if tech["rsi"]!="—" else 50)>70
                                       else"#4ade80" if(float(tech["rsi"]) if tech["rsi"]!="—" else 50)<30 else"#c8d8e8"}),
                        ],style={**_CARD,"padding":"10px","textAlign":"center"}),width=3),
                        dbc.Col(html.Div([html.Div("MACD",style={"fontSize":"9px","color":_MUTED,"textTransform":"uppercase","marginBottom":"3px"}),
                            html.Div(tech["macd"],style={"fontSize":"13px","fontWeight":"700","color":tech["macd_color"]}),
                        ],style={**_CARD,"padding":"10px","textAlign":"center"}),width=3),
                        dbc.Col(html.Div([html.Div("Bollinger",style={"fontSize":"9px","color":_MUTED,"textTransform":"uppercase","marginBottom":"3px"}),
                            html.Div(tech["bb"],style={"fontSize":"12px","fontWeight":"600","color":"#c8d8e8"}),
                            html.Div(tech["bb_sig"],style={"fontSize":"9px","color":_MUTED}),
                        ],style={**_CARD,"padding":"10px","textAlign":"center"}),width=3),
                        dbc.Col(html.Div([html.Div("Consensus",style={"fontSize":"9px","color":_MUTED,"textTransform":"uppercase","marginBottom":"3px"}),
                            html.Div(rec,style={"fontSize":"13px","fontWeight":"700","color":rec_c}),
                            html.Div(f"{n_anal} analystes",style={"fontSize":"9px","color":_MUTED}),
                        ],style={**_CARD,"padding":"10px","textAlign":"center"}),width=3),
                    ],className="g-2"),
                ],style=_CARD),
            ],width=8),

            dbc.Col([
                _decision_panel(info, close),
                html.Div([
                    html.Div("VALORISATION",style=_LABEL),
                    _row("P/E trailing",pe),_row("P/E forward",pe_fwd),
                    _row("P/B",pb),_row("EV/EBITDA",ev_eb),
                    _row("Div. Yield",div_yield,"#4ade80" if div_yield!="—" else _MUTED),
                    _row("Price Target",f"{pt_str} ({pt_up:+.1f}%)" if pt else "—",
                         "#4ade80" if pt_up>5 else"#f87171" if pt_up<-5 else"#f0a500"),
                ],style=_CARD),
                html.Div([
                    html.Div("FINANCIALS (TTM)",style=_LABEL),
                    _row("Revenue",rev),_row("EBITDA",ebitda),_row("Net Income",net_inc),
                    _row("ROE",roe,"#4ade80" if roe!="—" else _MUTED),
                    _row("Gross Margin",gross_m),_row("Oper. Margin",oper_m),_row("Net Margin",net_m),
                ],style=_CARD),
                html.Div([
                    html.Div("THÈSE",style=_LABEL),
                    html.Div(config["thesis"],style={"fontSize":"11px","color":"#94b8cc","lineHeight":"1.6","marginBottom":"10px"}),
                    html.Div("BULL",style={**_LABEL,"fontSize":"9px","color":"#4ade80","marginBottom":"4px"}),
                    html.Ul([html.Li(b,style={"fontSize":"11px","color":"#4ade80","marginBottom":"2px"}) for b in config["bull"]],style={"paddingLeft":"14px","marginBottom":"8px"}),
                    html.Div("BEAR",style={**_LABEL,"fontSize":"9px","color":"#f87171","marginBottom":"4px"}),
                    html.Ul([html.Li(b,style={"fontSize":"11px","color":"#f87171","marginBottom":"2px"}) for b in config["bear"]],style={"paddingLeft":"14px"}),
                ],style=_CARD),
                # Ordre — utilise safe_id pour éviter les points dans les IDs
                html.Div([
                    html.Div("ORDRE RAPIDE — IBKR PAPER",style={**_LABEL,"color":"#4a9eff"}),
                    html.Div([
                        dcc.Input(id=f"wl-qty-{safe_id}",type="number",value=10,min=1,
                                  style={"backgroundColor":_BG2,"color":_TEXT,"border":_BORDER,
                                         "borderRadius":"4px","padding":"6px 10px","fontSize":"12px",
                                         "width":"70px","marginRight":"6px"}),
                        dcc.Dropdown(id=f"wl-type-{safe_id}",
                                     options=[{"label":"Market","value":"MARKET"},{"label":"Limit","value":"LIMIT"}],
                                     value="MARKET",clearable=False,
                                     style={"backgroundColor":_BG2,"border":_BORDER,"fontSize":"11px",
                                            "width":"100px","display":"inline-block","marginRight":"6px"}),
                        html.Button("▲ BUY",  id=f"wl-buy-{safe_id}",
                                    style={"backgroundColor":"rgba(74,222,128,.12)","color":"#4ade80","border":"1px solid #4ade80",
                                           "borderRadius":"4px","padding":"6px 12px","fontSize":"12px","fontWeight":"700","cursor":"pointer","marginRight":"4px"}),
                        html.Button("▼ SELL", id=f"wl-sell-{safe_id}",
                                    style={"backgroundColor":"rgba(248,113,113,.12)","color":"#f87171","border":"1px solid #f87171",
                                           "borderRadius":"4px","padding":"6px 12px","fontSize":"12px","fontWeight":"700","cursor":"pointer"}),
                    ],style={"display":"flex","alignItems":"center","flexWrap":"wrap","gap":"4px","marginBottom":"8px"}),
                    # Status lu depuis le Store (persistant, pas écrasé par le re-render)
                    html.Div(id=f"wl-status-{safe_id}"),
                    html.Div("⚠ Stop-loss auto -6% | outsideRth=True",
                             style={"fontSize":"9px","color":"#5a7080","marginTop":"6px"}),
                ],style=_CARD),
            ],width=4),
        ],className="g-3"),
    ])


def layout():
    app = get_app()
    tabs = dbc.Tabs([
        dbc.Tab(label="JPMorgan (JPM)",            tab_id="JPM",    tab_style={"minWidth":"155px"}),
        dbc.Tab(label="Intuitive Surgical (ISRG)", tab_id="ISRG",   tab_style={"minWidth":"200px"}),
        dbc.Tab(label="SpaceX (SPCX)",             tab_id="SPCX",   tab_style={"minWidth":"140px"}),
        dbc.Tab(label="Eni (ENI.MI)",              tab_id="ENI-MI", tab_style={"minWidth":"120px"}),
        dbc.Tab(label="Xanadu (XNDU)",             tab_id="XNDU",   tab_style={"minWidth":"140px"}),
    ], id="watchlist-tabs", active_tab="JPM", style={"marginBottom":"14px"})

    return html.Div([
        html.Div("Watchlist — Buy-Side Equity Analysis",style=_H1),
        html.Div("JPMorgan · Intuitive Surgical · SpaceX SPCX · Eni",
                 style={"fontSize":"11px","color":"#5a7080","marginBottom":"14px"}),
        tabs,
        dcc.Loading(html.Div(id="watchlist-content"),type="dot",color="#4a9eff"),
        dcc.Interval(id="watchlist-refresh",interval=300_000,n_intervals=0),
    ],style={"paddingBottom":"30px"})