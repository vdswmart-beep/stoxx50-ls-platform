# dashboard/pages/risk_lab.py — EURO STOXX 50: real sector exposure, bigger layout

from dash import html, dcc, get_app
from dashboard.components.charts import area_fill_chart, hbar_chart, bar_chart
from dashboard.components.tables import base_table
import pandas as pd
import numpy as np


def layout():
    app = get_app()
    dp = app.data_provider

    summary_df, port_rets, dd_series, var_val, cvar_val = dp.get_risk_metrics()
    stress_df = dp.get_stress_tests()

    # Drawdown dataframe
    dd_df = dd_series.reset_index()
    dd_df.columns = ["date", "drawdown"]
    dd_df["date"] = pd.to_datetime(dd_df["date"])

    # ── Exposition sectorielle RÉELLE (depuis les poids du portefeuille) ──
    try:
        from config.universe import SECTOR_MAP
        _, weights = dp.get_portfolio()
        if not isinstance(weights, dict):
            weights = {}
        sector_exp = {}
        for ticker, w in weights.items():
            if abs(w) < 1e-5:
                continue
            sector = SECTOR_MAP.get(ticker, "Other")
            sector_exp[sector] = sector_exp.get(sector, 0) + abs(w) * 100
        sector_exp = dict(sorted(sector_exp.items(), key=lambda x: x[1], reverse=True))
        sector_labels = list(sector_exp.keys())
        sector_vals   = list(sector_exp.values())
    except Exception:
        sector_labels, sector_vals = [], []

    return html.Div([
        html.Div("Risk Lab", className="section-title"),

        html.Div(className="grid", children=[

            html.Div(className="panel col-3", children=[
                html.Div(className="kpi", children=[
                    html.Div("VaR 95% (1d)", className="kpi-label"),
                    html.Div(f"-{var_val*100:.2f}%",
                             className="kpi-value", style={"color": "#f0a500"}),
                    html.Div("Historical", className="kpi-sub kpi-neutral"),
                ])
            ]),
            html.Div(className="panel col-3", children=[
                html.Div(className="kpi", children=[
                    html.Div("CVaR 95% (1d)", className="kpi-label"),
                    html.Div(f"-{cvar_val*100:.2f}%",
                             className="kpi-value kpi-negative"),
                    html.Div("Expected shortfall", className="kpi-sub kpi-neutral"),
                ])
            ]),
            html.Div(className="panel col-3", children=[
                html.Div(className="kpi", children=[
                    html.Div("Max Drawdown", className="kpi-label"),
                    html.Div(f"{dd_series.min()*100:.2f}%",
                             className="kpi-value kpi-negative"),
                    html.Div("Peak-to-trough", className="kpi-sub kpi-neutral"),
                ])
            ]),
            html.Div(className="panel col-3", children=[
                html.Div(className="kpi", children=[
                    html.Div("Ann. Vol", className="kpi-label"),
                    html.Div(f"{port_rets.std()*np.sqrt(252)*100:.2f}%",
                             className="kpi-value"),
                    html.Div("Realised", className="kpi-sub kpi-neutral"),
                ])
            ]),

            # Drawdown
            html.Div(className="panel col-8", children=[
                html.Div("Drawdown Profile", className="section-title"),
                dcc.Graph(
                    figure=area_fill_chart(dd_df, "date", "drawdown", height=260),
                    config={"displayModeBar": False},
                )
            ]),

            # Stress tests
            html.Div(className="panel col-4", children=[
                html.Div("Stress Tests", className="section-title"),
                base_table(stress_df, id="risk-stress-tbl", sort=False, page_size=10),
            ]),

            # Sector exposure bar
            html.Div(className="panel col-6", children=[
                html.Div("Sector Exposure (Gross %)", className="section-title"),
                dcc.Graph(
                    figure=hbar_chart(sector_labels, sector_vals, height=260),
                    config={"displayModeBar": False},
                ) if sector_labels else html.Div(
                    "Aucune exposition — lancez le pipeline ou un Backtest",
                    style={"color": "#5a7080", "fontSize": "12px", "padding": "16px 0"}),
            ]),

            # Risk summary table
            html.Div(className="panel col-6", children=[
                html.Div("Risk Summary", className="section-title"),
                base_table(summary_df, id="risk-summary-tbl", sort=False, page_size=10),
            ]),
        ])
    ])