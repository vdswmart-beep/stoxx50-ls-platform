# NK225 — Long/Short Equity Research & Derivatives Platform

> A professional-grade quantitative research, trading and options platform built to hedge fund standards. Generates, analyses and executes long/short equity strategies on the Nikkei 225 and a buy-side watchlist, with a full European-options analytics desk.

[![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)](https://python.org)
[![Dash](https://img.shields.io/badge/Dash-2.18-cyan?logo=plotly)](https://dash.plotly.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## Why This Project

I built this platform out of a genuine passion for long/short equity investing and quantitative finance. Long/short strategies fascinate me because they separate alpha generation from market direction — the goal is not to predict whether the market goes up or down, but to identify **relative mispricings** between securities.

The Nikkei 225 is a particularly interesting universe for L/S strategies: high dispersion across sectors (automotive, semiconductors, financials, healthcare) creates abundant pair opportunities, macro sensitivity to USD/JPY and Bank of Japan policy generates recurring factor rotations, and structural inefficiencies persist due to cross-shareholding structures and the late adoption of shareholder returns.

This tool is my attempt to build the research infrastructure a fundamental L/S analyst would actually use — from factor scoring to walk-forward backtesting, paper-trade execution, and a complete options pricing desk for hedging and expressing views with convexity.

---

## What It Does

Most retail investors either go long-only or have no systematic framework to evaluate short candidates. This platform provides a rigorous, data-driven workflow to:

1. **Score** every stock in the Nikkei 225 across multiple factor dimensions
2. **Rank** them into long and short candidates with conviction levels and an estimated holding horizon
3. **Validate** each idea manually with a full fundamental + momentum fiche before committing
4. **Backtest** the resulting L/S strategy with realistic transaction costs
5. **Execute** paper trades (Interactive Brokers or local simulation) with an automatic −6% stop-loss per position
6. **Price options** on the watchlist with a full Black-Scholes desk (Greeks, strategies, parity, vol surface)

---

## Platform Map

```
Data (Yahoo Finance) ─────────────────► Research & Idea Generation
                                          │
IBKR (execution only) ◄── Paper trades ──┤
                                          ▼
   Factor Scoring → Idea Lab → Manual validation → Execution → Track record
                                          │
                                          ├─► Pair Trading (Math Lab)
                                          ├─► Walk-forward Backtest
                                          ├─► Risk (VaR, CVaR, stress)
                                          └─► Options Lab (Black-Scholes desk)
```

---

## Dashboard Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | Overview | Real portfolio: positions, P&L per position, sector exposure, NAV |
| `/research` | Research Lab | IC analysis, rolling Spearman, factor scores |
| `/ideas` | Idea Lab | Long/short candidates ranked by conviction — click any card for a full fiche (price, fundamentals, momentum, vol, beta, Z-scores) + one-click execution |
| `/math` | Math Lab | **Pair trading**: spread, z-score signals, cointegration, rolling beta/correlation, spread backtest |
| `/ai` | AI Lab | AI-generated investment hypotheses (Groq / Llama 3.3) |
| `/backtest` | Backtest Lab | Walk-forward backtesting with full performance metrics |
| `/portfolio` | Portfolio | NAV, allocation, positions table |
| `/risk` | Risk Lab | VaR, CVaR, drawdown profile, stress tests |
| `/watchlist` | Watchlist | Buy-side deep dive on JPM · ISRG · SPCX · Eni — price, technicals, valuation, financials, bull/bear, trade buttons |
| `/options` | **Options Lab** | European options desk: Pricer · Greeks · Strategies · Parity · Vol Surface |
| `/execution` | Execution Lab | Paper trading, order blotter, delta vs target weights |
| `/company` | Company Analyzer | Price history + fundamentals vs sector peers for any Nikkei name |

---

## Options Lab — European Options Desk

A complete equity-derivatives analytics suite, priced on the watchlist underlyings (JPM, ISRG, SPCX, Eni). The pricing engine is fully vectorised and framework-agnostic.

- **Pricer** — Black-Scholes price + full Greeks (desk units: vega/ρ per 1%, θ per day) for any strike/expiry/type, with a live payoff diagram.
- **Greeks Explorer** — interactive sliders (spot, strike, vol, maturity) that reprice Greeks instantly, with a delta-vs-spot profile for call and put.
- **Strategy Builder** — 11 strategies (spreads, butterflies, straddles, strangles, iron butterfly, covered call, protective put, fiduciary call…), each with net cost, max profit/loss, break-evens, aggregated book Greeks and a P&L payoff chart.
- **Put-Call Parity** — residual check against the cash-and-carry relation `C − P = S·e⁻qT − K·e⁻rT`, with an honest reminder that flags are a screening signal, not free money.
- **Volatility Surface** — 3-D IV surface (strike × maturity × IV), vol smiles by expiry, and the ATM term structure.

The option chain is generated by a `MockProvider` that pulls the **live spot from Yahoo Finance** and synthesises a self-consistent European chain with a realistic equity skew. Every premium is the model value at the assumed vol surface — an honest theoretical pricer suitable for a research and track-record context. The architecture supports plugging in a live provider (Barchart, IBKR) without touching the analytics layer.

---

## Key Features (Equity)

- **Idea Lab with manual validation** — the workflow of a junior L/S analyst: the scoring engine generates ranked long/short candidates with an estimated holding horizon by conviction (HIGH long 3–6 months, etc.); clicking a card opens a full fiche with price chart, fundamentals, momentum (1M/3M/6M/12M), realised vol, beta and cross-sectional Z-scores (momentum / quality / value / sector) so every trade is checked before execution.
- **Sector-aware L/S scoring** — composite of momentum (40%), quality (25%), value (20%) and intra-sector positioning (15%), with Z-scores computed cross-sectionally and within each sector.
- **Pair trading** — spread = log(A) − β·log(B) with rolling OLS beta, z-score entry/exit signals, Engle-Granger cointegration and ADF tests, rolling correlation, and a spread backtest (Sharpe, number of trades).
- **Automatic −6% stop-loss** — a monitor checks open positions every 60 seconds and closes any position breaching −6% P&L automatically (IBKR or simulated).
- **Walk-forward backtesting** — train/test windows that avoid look-ahead bias, realistic slippage and commission, full metrics (Sharpe, Sortino, Calmar, Max Drawdown, Win Rate, Profit Factor, VaR/CVaR), monthly PnL heatmap, and one-click Excel export.

---

## Technical Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| Dashboard | Dash 2.18 · Plotly · Dash Bootstrap Components |
| Data | Yahoo Finance (yfinance) · IBKR TWS API (ib-insync, execution only) |
| Computation | pandas · NumPy · SciPy · statsmodels |
| Options engine | Vectorised Black-Scholes-Merton · Newton-Raphson + Brent IV solver · scattered-data vol surface (griddata) |
| AI | Groq API (Llama 3.3-70B) with auto-routing |
| Reporting | openpyxl (Excel track record) |

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/vdswmart-beep/nk225-platform.git
cd nk225-platform
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Add your Groq API key (free at console.groq.com): GROQ_API_KEY=gsk_...

# 3. Launch
python run_dashboard.py                      # Full Nikkei 225 (185 tickers, ~3 min first load)
python run_dashboard.py --universe liquid40   # 40 most liquid tickers (fast start)
python run_dashboard.py --mode live           # Connect IBKR paper trading (port 7497)
```

**IBKR paper trading** (optional): open TWS, enable *Edit → Global Configuration → API → Enable ActiveX and Socket Clients*, port 7497, then run with `--mode live`. Yahoo Finance is always used for research data; IBKR is used only to route orders. Without `--mode live`, paper trading is simulated locally in Python.

---

## Architecture

```
nk225-platform/
├── config/        # Universe (185 tickers), settings, factor weights
├── data/          # Provider pattern: Yahoo Finance, loaders, cache
├── features/      # Momentum, volatility, value, quality, technical factors
├── ideas/         # Sector-aware L/S scoring engine with duration estimates
├── research/      # IC analysis, statistical tests
├── portfolio/     # Risk Parity, HRP, Mean-Variance optimiser
├── risk/          # VaR, CVaR, drawdown, stress testing
├── backtesting/   # Walk-forward engine, performance metrics
├── execution/     # Paper trading simulation + IBKR live connector (thread-safe)
├── reporting/     # Excel track-record exporter
├── ai/            # Groq / Grok / Ollama clients with auto-routing
├── options/       # European-options desk (framework-agnostic engine)
│   ├── pricing/     # Black-Scholes, implied vol solver, put-call parity
│   ├── volatility/  # Smiles, term structure, 3-D surface
│   ├── strategies/  # 11 strategies + registry, payoff/Greek analytics
│   ├── option_chain.py   # Tidy DataFrame wrapper (lingua franca)
│   └── mock_provider.py  # Synthetic chain from live Yahoo spot
├── pipelines/     # Master pipeline: Data → Ideas → Portfolio → Risk
└── dashboard/     # 12-page Dash application (dark theme)
```

---

## Roadmap

- [ ] Custom pair-trade backtesting wired into the Math Lab (e.g. Long Toyota / Short Honda)
- [ ] Cointegration-based pairs scanner across the full Nikkei 225
- [ ] Live option chains via IBKR (the provider interface is already in place)
- [ ] Factor regime detection (risk-on / risk-off auto-switching)
- [ ] Multi-strategy portfolio with correlation-aware position sizing

---

## Disclaimer

This project is built for educational and research purposes. The signals and option prices generated do not constitute investment advice. Always validate strategies in paper trading before deploying real capital. Trading involves risk of loss.

---

*Built with Python 3.12 — Nikkei 225 Long/Short Equity Research & Derivatives Platform*
