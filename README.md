# Helios Capital — EURO STOXX 50 Long/Short Equity & Options Platform

A systematic long/short equity research platform covering the 50 constituents of the
EURO STOXX 50 — from signal generation to live order execution. Built in Python with
an interactive Dash interface and live Interactive Brokers integration.

**Repository:** https://github.com/vdswmart-beep/stoxx50-ls-platform

---

## What it does

Helios reproduces the full workflow of a systematic equity desk:

- **Alpha signal** — a market-neutral momentum long/short (12M-1M, inverse-volatility
  weighting); multi-factor and Hierarchical Risk Parity variants also implemented.
- **Backtesting** — strict walk-forward, out-of-sample, **net of transaction costs**.
- **Risk** — VaR/CVaR, drawdown analytics, stress tests (2008, COVID, ECB shocks).
- **Factor validation** — Information Coefficient (Spearman) per factor.
- **Options desk** — Black-Scholes pricing, full Greeks, implied-vol solver, 11
  strategies, a **custom structured-products builder**, put-call parity, vol surface.
- **Pair trading** — OLS cointegration spread with z-score mean reversion.
- **Live execution** — IBKR paper-trading: signal → target portfolio → one-click orders.

---

## Signal validation — three independent checks

The default momentum strategy on the 50-name universe (2022–2026), evaluated three
separate ways that all point the same direction:

| Check | Result |
|---|---|
| **Walk-forward backtest** (net of costs) | Sharpe ≈ 1.6 · ann. return ≈ 20% · max DD < 10% · 10/12 windows positive |
| **Robustness** — sensitivity to settings | Sharpe 1.3–1.6 across 3–8 positions · positive across all look-backs · positive every calendar year |
| **Information Coefficient** — signal quality | Spearman IC ≈ +0.11 · IC IR ≈ 0.57 · hit rate 66% |

Multi-factor (Sharpe ≈ 0.8) and HRP (≈ 1.1) variants were benchmarked; on this universe
the pure momentum signal proved most robust — the low-volatility factor actually
predicted returns inversely (IC ≈ −0.08), so adding it hurt. A deliberate finding:
added complexity does not guarantee better performance.

> Transaction costs (~8 bps per unit turnover) are modelled in the backtest, so the
> reported Sharpe is **net of costs**, not gross.

---

## How the strategy works (short version)

**Stock selection**, at each rebalancing date:
1. Rank all 50 stocks by momentum = mean daily return over months −12 to −1 (skip the
   last month to avoid short-term reversal).
2. Go **long the top 5**, **short the bottom 5**; ignore the middle 40.
3. Size each position by **inverse volatility** (risk parity), scaled to 50% long /
   50% short → gross 100%, net ≈ 0% (market-neutral).

**Rebalancing** (the "Rebalancing" tab, one click): compute the target portfolio in
shares → read current IBKR positions → `order = target − current` → review the order
list → route all orders to IBKR.

**How often:** rebalance on a **fixed quarterly schedule** (matches the tested holding
period). Check the Overview daily for monitoring, but only act off-schedule on a risk
breach (−6% stop-loss) or sustained signal decay (2+ negative windows). Do not
performance-chase.

See the **Strategy & Operating Manual** and **Methodology Guide** for step-by-step detail.

---

## The 13 pages

Overview (+ Strategy Monitor) · Research Lab (factor IC) · Idea Lab (4-pillar scoring) ·
Math Lab (cointegration pairs) · AI Lab · Backtest Lab · Portfolio · Risk Lab ·
Watchlist (decision score) · Options Lab (incl. structured products) · Execution ·
Rebalancing · Company Analyzer.

---

## Architecture

```
config/          Universe (50 tickers), sectors, settings
data/            yfinance loader (robust MultiIndex handling, caching)
backtesting/     Walk-forward engine (net of costs), strategy pipelines, HRP
execution/       IBKR live engine, rebalancer (signal → orders)
options/         Black-Scholes, Greeks, implied vol, 11 strategies, vol surface
dashboard/       Dash app: 13 pages, callbacks, router, decision-score engine
run_dashboard.py Entry point
```

---

## Installation

```bash
git clone https://github.com/vdswmart-beep/stoxx50-ls-platform.git
cd stoxx50-ls-platform
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt   # requires yfinance >= 1.5.1
```

## Running

```bash
# Backtest mode (simulation, no broker)
python run_dashboard.py --mode backtest

# Live mode (real IBKR paper account; TWS open, API enabled on port 7497)
ulimit -n 4096 && python run_dashboard.py --mode live
```

Open http://127.0.0.1:8050.

### Live execution setup (Interactive Brokers)
1. Open Trader Workstation (TWS), log into the **paper** account.
2. File → Global Configuration → API → Settings → enable "ActiveX and Socket Clients", port **7497**.
3. Launch with `--mode live`; use the **Rebalancing** tab to route the target portfolio.

---

## Validation scripts

```bash
python audit_backtest.py       # walk-forward metrics + per-window breakdown
python test_robustness.py      # sensitivity to parameters, per-year stability
python test_ic.py              # Information Coefficient per factor
python test_frequency.py       # rebalancing frequency: turnover & net-of-cost Sharpe
python test_strategies_full.py # momentum vs multi-factor vs HRP
```

---

## Key technical choices

- **Walk-forward, not in-sample** — weights computed only on the training window, tested
  on the following unseen window. No look-ahead bias.
- **Costs modelled** — the backtest subtracts turnover-based costs, so Sharpe is net.
- **Genuine HRP** — López de Prado's algorithm (correlation distance → hierarchical
  clustering → quasi-diagonalisation → recursive bisection).
- **Single-threaded server in live mode** — `ib_insync` is not thread-safe; the server
  runs single-threaded when connected so orders execute in the connection thread.
- **MARKET → LIMIT conversion** — without a real-time European data subscription, market
  orders become tick-size-aligned aggressive limit orders using a reference price.

---

## Limitations (honest scope)

- **Market data.** The IBKR paper account has no real-time European data subscription, so
  European orders fill at market open rather than instantly, and the options desk runs on
  theoretical (Black-Scholes) inputs rather than live market implied volatility.
- **Fundamentals.** The multi-factor signal uses price-based factors only (momentum,
  low-vol, reversal). Value/quality need point-in-time historical fundamentals not
  reliably available from the free data source, so they inform live scoring but are not
  backtested.
- **Universe.** Fixed to the 50 current EURO STOXX 50 members — no survivorship-bias-free
  historical index reconstitution.

---

## Disclaimer

Personal research project. Paper trading only — not investment advice. Past backtested
performance does not guarantee future results.