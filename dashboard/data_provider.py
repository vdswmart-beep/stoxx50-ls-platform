# dashboard/data_provider.py — FIXED: get_portfolio() retourne TOUJOURS (nav_df, dict)

from __future__ import annotations
import logging
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger("DashboardDataProvider")

# NAV paper trading (modifiable via .env ou ici)
import os
PAPER_NAV_EUR = float(os.getenv("PAPER_NAV", "1000000"))   # €1M EUR par défaut


class DashboardDataProvider:

    def __init__(self, data_service, tickers, start, end,
                 backtest_result=None, mode="backtest"):
        self.ds = data_service
        self.tickers = tickers
        self.start = start
        self.end = end
        self.backtest_result = backtest_result
        self.mode = mode
        self.data_provider = self.ds          # alias rétrocompatibilité
        self._prices_cache = self._returns_cache = self._fundamentals_cache = None
        self._nav_cache = self._ideas_cache = self._risk_cache = None
        self._factor_cache = self._ic_cache = None
        self.target_weights: Dict[str, float] = {}
        self._last_prices: Dict[str, float] = {}
        self._last_backtest = backtest_result
        self.paper_nav = PAPER_NAV_EUR   # NAV paper trading en EUR
        self._exec_engine = None         # moteur IBKR (injecté en mode live)
        logger.info(
            f"DataProvider init | {len(tickers)} tickers | mode={mode} | "
            f"Paper NAV: €{PAPER_NAV_EUR:,.0f}"
        )

    # ── Compte IBKR réel (mode live) ──────────────────────────────
    def _ibkr(self):
        """Retourne le moteur IBKR connecté, ou None."""
        eng = self._exec_engine
        try:
            if eng is not None and getattr(eng, "is_connected", False):
                return eng
        except Exception:
            pass
        return None

    def get_live_account(self):
        """
        Lit le VRAI compte IBKR paper (NAV, cash, P&L, positions).
        Retourne None si pas connecté (mode backtest).
        Structure : {
            'nav': float, 'cash': float,
            'unrealized_pnl': float, 'realized_pnl': float,
            'positions': [{'ticker','qty','avg_cost','market_price',
                           'market_value','unrealized_pnl','side'}, ...]
        }
        """
        eng = self._ibkr()
        if eng is None:
            return None
        try:
            summary = eng.get_account_summary() or {}
            def _val(key, default=0.0):
                item = summary.get(key)
                if isinstance(item, dict):
                    try: return float(item.get("value", default))
                    except Exception: return default
                return default

            nav = eng.get_account_value() or _val("nav", self.paper_nav)

            # Positions réelles avec détail (via ib.positions())
            positions = []
            try:
                ib = getattr(eng, "_ib", None)
                if ib is not None:
                    for p in ib.positions(eng._account_id) if eng._account_id else ib.positions():
                        try:
                            qty = float(p.position)
                            if abs(qty) < 1e-9:
                                continue
                            sym = p.contract.symbol
                            avg = float(p.avgCost) if p.avgCost else 0.0
                            # avgCost IBKR = coût total par action (déjà par unité)
                            positions.append({
                                "ticker": sym,
                                "qty": int(qty),
                                "avg_cost": avg,
                                "side": "LONG" if qty > 0 else "SHORT",
                            })
                        except Exception:
                            continue
            except Exception as e:
                logger.debug(f"positions detail: {e}")

            # Enrichir avec prix de marché + P&L via portfolio items
            try:
                ib = getattr(eng, "_ib", None)
                if ib is not None:
                    pf = {item.contract.symbol: item for item in ib.portfolio()}
                    for pos in positions:
                        it = pf.get(pos["ticker"])
                        if it is not None:
                            pos["market_price"]   = float(it.marketPrice) if it.marketPrice else None
                            pos["market_value"]   = float(it.marketValue) if it.marketValue else None
                            pos["unrealized_pnl"] = float(it.unrealizedPNL) if it.unrealizedPNL else None
            except Exception as e:
                logger.debug(f"portfolio items: {e}")

            return {
                "nav": nav,
                "cash": _val("cash"),
                "unrealized_pnl": _val("unrealized_pnl"),
                "realized_pnl": _val("realized_pnl"),
                "gross_pos": _val("gross_pos"),
                "buying_power": _val("buying_power"),
                "positions": positions,
            }
        except Exception as e:
            logger.error(f"get_live_account: {e}")
            return None

    # ── Prix & Rendements ─────────────────────────────────────────
    def get_prices(self, tickers=None, start=None, end=None):
        if self._prices_cache is not None: return self._prices_cache
        try:
            self._prices_cache = self.ds.get_prices(
                tickers or self.tickers, start or self.start, end or self.end)
        except Exception as e:
            logger.error(f"get_prices: {e}"); self._prices_cache = pd.DataFrame()
        return self._prices_cache

    def get_returns(self, tickers=None, start=None, end=None):
        if self._returns_cache is not None: return self._returns_cache
        try:
            self._returns_cache = self.ds.get_returns(
                tickers or self.tickers, start or self.start, end or self.end)
        except Exception as e:
            logger.error(f"get_returns: {e}"); self._returns_cache = pd.DataFrame()
        return self._returns_cache

    def get_price_history(self, ticker):
        try:
            prices = self.get_prices()
            if isinstance(prices.index, pd.MultiIndex):
                lvl = "ticker" if "ticker" in prices.index.names else prices.index.names[1]
                if ticker in prices.index.get_level_values(lvl):
                    df = prices.xs(ticker, level=lvl).reset_index()
                    df.columns = [c.lower() for c in df.columns]
                    return df
        except Exception: pass
        try:
            import yfinance as yf
            df = yf.download(ticker, start=self.start, end=self.end,
                             progress=False, auto_adjust=True,
                             multi_level_index=False)
            # yfinance 1.x peut renvoyer un MultiIndex même pour 1 ticker
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = [str(c).lower() for c in df.columns]
            return df.reset_index().rename(columns={"Date":"date","index":"date"})
        except Exception as e:
            logger.error(f"get_price_history({ticker}): {e}"); return pd.DataFrame()

    def get_current_prices(self):
        if self._last_prices: return self._last_prices
        try:
            import yfinance as yf
            data = yf.download(self.tickers, period="2d", progress=False,
                               auto_adjust=True)
            if not data.empty:
                # yfinance 1.x : colonnes MultiIndex (Field, Ticker)
                if isinstance(data.columns, pd.MultiIndex):
                    lvl0 = data.columns.get_level_values(0)
                    close = data["Close"] if "Close" in lvl0 else data
                else:
                    close = data["Close"] if "Close" in data.columns else data
                if isinstance(close, pd.Series): close = close.to_frame(self.tickers[0])
                self._last_prices = close.iloc[-1].dropna().to_dict()
        except Exception as e: logger.warning(f"get_current_prices: {e}")
        return self._last_prices

    def get_live_prices(self): return self.get_current_prices()

    def get_ticker_info(self, ticker):
        try:
            import yfinance as yf; return yf.Ticker(ticker).info
        except Exception as e: logger.error(f"get_ticker_info: {e}"); return {}

    def get_fundamentals(self, tickers=None):
        if self._fundamentals_cache is not None: return self._fundamentals_cache
        try:
            self._fundamentals_cache = self.ds.get_fundamentals(tickers or self.tickers)
        except Exception as e:
            logger.error(f"get_fundamentals: {e}"); self._fundamentals_cache = pd.DataFrame()
        return self._fundamentals_cache

    def get_company_data(self, ticker):
        price_df = self.get_price_history(ticker)
        info = self.get_ticker_info(ticker)
        keys = ["trailingPE","priceToBook","returnOnEquity","returnOnAssets",
                "grossMargins","operatingMargins","freeCashflow","marketCap",
                "beta","dividendYield","revenueGrowth","debtToEquity"]
        rows = [{"metric":k,"value":info.get(k)} for k in keys if info.get(k) is not None]
        return price_df, pd.DataFrame(rows)

    # ── Helpers ───────────────────────────────────────────────────
    def _compute_port_returns(self, nav_base: float = None):
        """
        Calcule les rendements du portefeuille.
        Si target_weights est vide → equal-weight long-only (fallback).
        """
        returns = self.get_returns()
        if returns.empty: return pd.Series(dtype=float)
        w = self.target_weights
        tickers = [t for t in w if t in returns.columns]
        if tickers:
            w_arr = np.array([w[t] for t in tickers], dtype=float)
            total = np.abs(w_arr).sum()
            if total > 0: w_arr = w_arr / total
            return (returns[tickers].fillna(0) * w_arr).sum(axis=1)
        # Fallback: equal-weight long-only (indicatif seulement)
        return returns.mean(axis=1)

    # ── Portfolio ─────────────────────────────────────────────────
    def get_portfolio(self):
        """
        Retourne TOUJOURS (nav_df, weights_dict) :
          nav_df       : DataFrame["date","nav"]   — courbe NAV
          weights_dict : dict {ticker: float}       — poids signés L/S

        Compatible avec overview.py ET portfolio_lab.py.
        """
        # Cas 1 : backtest disponible → utilise ses résultats
        if self._last_backtest is not None:
            try:
                equity = self._last_backtest.equity_curve
                # Rescaler sur la NAV paper trading réelle
                equity_scaled = equity / equity.iloc[0] * self.paper_nav
                nav_df = equity_scaled.reset_index()
                nav_df.columns = ["date", "nav"]
                if self._last_backtest.windows:
                    self.target_weights = dict(self._last_backtest.windows[-1].weights)
                return nav_df, dict(self.target_weights)
            except Exception as e:
                logger.warning(f"portfolio from backtest: {e}")

        # Cas 2 : rendements dispo → calculer NAV
        try:
            pr = self._compute_port_returns()
            if not pr.empty:
                # Rescaler sur la NAV paper trading réelle
                equity = (1 + pr).cumprod() * self.paper_nav
                nav_df = equity.reset_index()
                nav_df.columns = ["date", "nav"]
                return nav_df, dict(self.target_weights)
        except Exception as e:
            logger.error(f"get_portfolio nav: {e}")

        return pd.DataFrame(columns=["date","nav"]), {}

    def get_positions_df(self):
        """
        Retourne un DataFrame des positions courantes.
        Appelé par portfolio_lab.py pour afficher le tableau.
        """
        w = self.target_weights
        if w:
            rows = [{"ticker":t, "weight":round(v,4),
                     "side":"LONG" if v>0 else "SHORT",
                     "weight_pct":f"{v:.2%}",
                     "notional":f"€{abs(v)*self.paper_nav/1e6:.1f}M"}
                    for t,v in w.items() if abs(v)>1e-5]
        else:
            n = len(self.tickers)
            ew = 1.0/n if n>0 else 0
            rows = [{"ticker":t,"weight":round(ew,4),"side":"LONG",
                     "weight_pct":f"{ew:.2%}",
                     "notional":f"€{ew*self.paper_nav/1e6:.1f}M"}
                    for t in self.tickers]
        return pd.DataFrame(rows)

    def get_portfolio_kpis(self):
        """Clés attendues par portfolio_lab.py: nav, total_ret, sharpe, vol, max_dd

        En mode LIVE : lit le VRAI compte IBKR (NAV, P&L, positions réelles).
        En mode BACKTEST : simulation depuis le capital fictif.
        """
        # ── MODE LIVE : vrai compte IBKR ──────────────────────────
        live = self.get_live_account()
        if live is not None:
            nav      = live["nav"]
            n_pos    = len(live["positions"])
            n_longs  = sum(1 for p in live["positions"] if p["side"] == "LONG")
            n_shorts = sum(1 for p in live["positions"] if p["side"] == "SHORT")
            u_pnl    = live["unrealized_pnl"]
            # total_ret = P&L latent / (NAV - P&L) ; si pas de position → 0
            base     = nav - u_pnl
            tr       = (u_pnl / base * 100) if base > 0 and n_pos > 0 else 0.0
            return {
                "nav": nav, "total_ret": tr, "ann_ret": 0.0,
                "sharpe": 0.0, "vol": 0.0, "max_dd": 0.0,
                "n_longs": n_longs, "n_shorts": n_shorts,
                "unrealized_pnl": u_pnl, "realized_pnl": live["realized_pnl"],
                "cash": live["cash"], "paper_nav_eur": nav,
                "is_live": True,
            }

        # ── MODE BACKTEST : simulation ────────────────────────────
        try:
            nav_df, w = self.get_portfolio()
            pr = self._compute_port_returns()
            last  = float(nav_df["nav"].iloc[-1]) if not nav_df.empty else self.paper_nav
            first = float(nav_df["nav"].iloc[0])  if not nav_df.empty else self.paper_nav
            tr    = (last/first - 1)*100 if first > 0 else 0.0
            vol   = float(pr.std()*np.sqrt(252)*100) if len(pr)>1 else 0.0
            aret  = float(pr.mean()*252*100) if len(pr)>0 else 0.0
            shr   = aret/vol if vol>0 else 0.0
            eq    = (1+pr).cumprod()
            mdd   = float((eq/eq.cummax()-1).min()*100) if len(eq)>0 else 0.0
            return {"nav":last,"total_ret":tr,"ann_ret":aret,"sharpe":shr,
                    "vol":vol,"max_dd":mdd,
                    "n_longs":sum(1 for v in w.values() if v>0.001),
                    "n_shorts":sum(1 for v in w.values() if v<-0.001),
                    "paper_nav_eur": self.paper_nav, "is_live": False}
        except Exception as e:
            logger.error(f"get_portfolio_kpis: {e}")
            return {"nav":self.paper_nav,"total_ret":0,"sharpe":0,"vol":0,"max_dd":0,
                    "n_longs":0,"n_shorts":0,"paper_nav_eur":PAPER_NAV_EUR,"is_live":False}

    # ── Risk ──────────────────────────────────────────────────────
    def get_risk_metrics(self):
        """Tuple de 5 : (summary_df, port_rets, dd_series, var_val, cvar_val)"""
        if self._risk_cache is not None: return self._risk_cache
        try:
            pr = self._compute_port_returns()
            if pr.empty: return self._empty_risk()
            vol   = float(pr.std()*np.sqrt(252))
            var95 = abs(float(np.percentile(pr, 5)))
            mask  = pr <= -var95
            cvar  = abs(float(pr[mask].mean())) if mask.any() else var95
            shr   = float(pr.mean()/pr.std()*np.sqrt(252)) if pr.std()>0 else 0.0
            eq    = (1+pr).cumprod(); dd = eq/eq.cummax()-1; mdd = float(dd.min())
            summary = pd.DataFrame([
                {"metric":"Sharpe Ratio",   "value":f"{shr:.3f}"},
                {"metric":"Ann. Vol",       "value":f"{vol*100:.2f}%"},
                {"metric":"VaR 95% (1d)",   "value":f"{var95*100:.2f}%"},
                {"metric":"CVaR 95% (1d)",  "value":f"{cvar*100:.2f}%"},
                {"metric":"Max Drawdown",   "value":f"{mdd*100:.2f}%"},
                {"metric":"Win Rate",       "value":f"{(pr>0).mean()*100:.1f}%"},
                {"metric":"Skewness",       "value":f"{pr.skew():.3f}"},
                {"metric":"Kurtosis",       "value":f"{pr.kurtosis():.3f}"},
            ])
            result = (summary, pr, dd, var95, cvar)
            self._risk_cache = result; return result
        except Exception as e:
            logger.error(f"get_risk_metrics: {e}"); return self._empty_risk()

    def _empty_risk(self):
        df = pd.DataFrame([{"metric":"—","value":"—"}])
        return (df, pd.Series(dtype=float), pd.Series(dtype=float), 0.0, 0.0)

    def get_stress_tests(self):
        try:
            pr = self._compute_port_returns()
            if pr.empty: return pd.DataFrame([{"scenario":"—","impact":"—"}])
            scenarios = {
                "2008 Crisis (worst 20d)": pr.nsmallest(20).sum(),
                "COVID Crash (worst 5d)":  pr.nsmallest(5).sum(),
                "Flash Crash (worst day)": float(pr.min()),
                "EUR +10% (export hit)":   pr.mean()*252*-0.15,
                "ECB rate hike +50bps":    pr.mean()*252*-0.08,
                "EURO STOXX -20% scenario": -0.20*0.85,
            }
            return pd.DataFrame([{"scenario":k,"impact":f"{v*100:.2f}%"}
                                  for k,v in scenarios.items()])
        except Exception as e:
            return pd.DataFrame([{"scenario":"Erreur","impact":str(e)}])

    # ── Trade Ideas ───────────────────────────────────────────────
    def get_trade_ideas(self):
        """DataFrame avec colonne side=LONG/SHORT"""
        if self._ideas_cache is not None: return self._ideas_cache
        try:
            returns = self.get_returns()
            if returns.empty: return pd.DataFrame()
            mom = returns.tail(252).mean()*252
            vol = returns.tail(63).std()*np.sqrt(252)
            fund = self.get_fundamentals()
            from config.universe import TICKER_NAMES
            rows = []
            for ticker in self.tickers:
                if ticker not in returns.columns: continue
                m12 = float(mom.get(ticker, 0))
                v   = float(vol.get(ticker, 0.2)) or 0.2
                # Skip tickers sans données exploitables (NaN momentum/vol)
                if not np.isfinite(m12) or not np.isfinite(v) or v <= 0:
                    continue
                raw = 50 + 30 * (m12 / v)
                sc  = float(np.clip(raw, 0, 100))
                if not np.isfinite(sc):
                    sc = 50.0
                side= "LONG" if sc>=55 else "SHORT"
                conv= "HIGH" if abs(sc-50)>25 else "MEDIUM" if abs(sc-50)>10 else "LOW"
                pe = roe = None
                if not fund.empty and ticker in fund.index:
                    r = fund.loc[ticker]
                    pe  = r.get("trailingPE")     if "trailingPE"     in fund.columns else None
                    roe = r.get("returnOnEquity") if "returnOnEquity" in fund.columns else None
                rows.append({"ticker":ticker,"name":TICKER_NAMES.get(ticker,ticker),
                             "side":side,"score":round(sc,1),"conviction":conv,
                             "mom_12m":round(m12,4),"vol_63d":round(v,4),
                             "pe":round(float(pe),2) if pe and not pd.isna(pe) else None,
                             "roe":round(float(roe),4) if roe and not pd.isna(roe) else None,
                             "thesis":f"{ticker}: momentum {m12:+.1%} | vol {v:.1%}",
                             "catalysts":f"Momentum 12M: {m12:+.1%}",
                             "risks":f"Volatilité: {v:.1%}"})
            df = pd.DataFrame(rows).sort_values("score",ascending=False)
            self._ideas_cache = df; return df
        except Exception as e:
            logger.error(f"get_trade_ideas: {e}"); return pd.DataFrame()

    # ── Factor / IC ───────────────────────────────────────────────
    def get_factor_data(self):
        if self._factor_cache is not None: return self._factor_cache
        try:
            returns = self.get_returns()
            if returns.empty: return pd.DataFrame()
            rows = []
            for ticker in returns.columns:
                ret = returns[ticker].dropna()
                if len(ret)<30: continue
                d=ret.tail(14).diff(); g=d.clip(lower=0).mean(); l=(-d.clip(upper=0)).mean()
                rsi=float(100-100/(1+g/l)) if l>0 else 50.0
                rows.append({"ticker":ticker,
                    "mom_1m":round(float(ret.tail(21).mean()*252),4),
                    "mom_3m":round(float(ret.tail(63).mean()*252),4),
                    "mom_6m":round(float(ret.tail(126).mean()*252),4),
                    "mom_12m":round(float(ret.tail(252).mean()*252),4),
                    "vol_20d":round(float(ret.tail(20).std()*np.sqrt(252)),4),
                    "vol_63d":round(float(ret.tail(63).std()*np.sqrt(252)),4),
                    "rsi":round(rsi,2)})
            df=pd.DataFrame(rows)
            fund=self.get_fundamentals()
            if not fund.empty and not df.empty:
                for col in ["trailingPE","priceToBook","returnOnEquity","returnOnAssets","grossMargins","revenueGrowth"]:
                    if col in fund.columns: df[col]=df["ticker"].map(fund[col].to_dict())
            self._factor_cache=df; return df
        except Exception as e:
            logger.error(f"get_factor_data: {e}"); return pd.DataFrame()

    def get_ic_series(self):
        if self._ic_cache is not None: return self._ic_cache
        try:
            returns=self.get_returns()
            if returns.empty: return pd.DataFrame([{"date":pd.Timestamp.now(),"ic":0.0}])
            rows=[]
            for i in range(42,len(returns.index),21):
                w=returns.iloc[i-21:i]; fwd=returns.iloc[i:i+21] if i+21<=len(returns) else None
                if fwd is None or fwd.empty: break
                aligned=pd.concat([w.mean(),fwd.mean()],axis=1).dropna()
                if len(aligned)<3: continue
                c=float(aligned.iloc[:,0].corr(aligned.iloc[:,1],method="spearman"))
                rows.append({"date":returns.index[i],"ic":c})
            df=pd.DataFrame(rows) if rows else pd.DataFrame([{"date":pd.Timestamp.now(),"ic":0.0}])
            self._ic_cache=df; return df
        except Exception as e:
            logger.error(f"get_ic_series: {e}"); return pd.DataFrame([{"date":pd.Timestamp.now(),"ic":0.0}])

    # ── Backtest ─────────────────────────────────────────────────
    def get_backtest_result(self): return self._last_backtest
    def set_target_weights(self, w: Dict[str, float]):
        self.target_weights = w
        self._risk_cache = None   # invalider le cache risk

    def invalidate_cache(self):
        self._prices_cache=self._returns_cache=self._fundamentals_cache=None
        self._nav_cache=self._ideas_cache=self._risk_cache=None
        self._factor_cache=self._ic_cache=None; self._last_prices={}