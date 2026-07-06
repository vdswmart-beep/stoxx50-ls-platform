# dashboard/pages/research_lab.py — validation de facteurs (IC sur le VRAI signal)

from dash import html, dcc, get_app
from dashboard.components.charts import bar_chart, line_chart
from dashboard.components.tables import base_table
from dashboard.components.filters import dropdown, radio_pills


def _ic_comparison_table(summary):
    """Table de comparaison des facteurs : IC Mean / IR / Hit / n."""
    if not summary:
        return html.Div("Pas assez de données pour la comparaison de facteurs.",
                        style={"color": "#5a7080", "fontSize": "12px", "padding": "12px 0"})
    th_style = {"textAlign": "left", "padding": "6px 10px", "fontSize": "10px",
                "color": "#7090a8", "textTransform": "uppercase",
                "borderBottom": "1px solid #1e2a38"}
    header = html.Tr([html.Th(h, style=th_style)
                      for h in ["Facteur", "IC Mean", "IC IR", "Hit %", "Obs.", "Verdict"]])
    rows = [header]
    for r in summary:
        is_strategy = r["factor"] == "mom_12_1"
        ir = r["ic_ir"]
        ic_color = "#4ade80" if r["ic_mean"] > 0.02 else "#f87171" if r["ic_mean"] < -0.02 else "#f0a500"
        if ir >= 0.4:
            verdict, v_color = "Signal exploitable", "#4ade80"
        elif ir >= 0.15:
            verdict, v_color = "Faible mais positif", "#f0a500"
        elif ir <= -0.15:
            verdict, v_color = "Prédit à l'envers (reversal)", "#f87171"
        else:
            verdict, v_color = "Pas de pouvoir prédictif", "#7090a8"
        row_style = {"backgroundColor": "rgba(74,158,255,.06)"} if is_strategy else {}
        rows.append(html.Tr([
            html.Td([
                html.Span(r["label"], style={"fontSize": "12px", "color": "#e8f2ff",
                          "fontWeight": "700" if is_strategy else "400"}),
                html.Span("  ← STRATÉGIE", style={"fontSize": "9px", "color": "#4a9eff",
                          "fontWeight": "700"}) if is_strategy else None,
            ], style={"padding": "7px 10px"}),
            html.Td(f"{r['ic_mean']:+.3f}", style={"padding": "7px 10px", "color": ic_color,
                    "fontWeight": "600", "fontSize": "12px"}),
            html.Td(f"{r['ic_ir']:+.2f}", style={"padding": "7px 10px", "color": ic_color,
                    "fontSize": "12px"}),
            html.Td(f"{r['hit']:.0f}%", style={"padding": "7px 10px", "color": "#c8d8e8",
                    "fontSize": "12px"}),
            html.Td(f"{r['n_obs']}", style={"padding": "7px 10px", "color": "#7090a8",
                    "fontSize": "11px"}),
            html.Td(verdict, style={"padding": "7px 10px", "color": v_color,
                    "fontSize": "11px", "fontStyle": "italic"}),
        ], style=row_style))
    return html.Table(rows, style={"width": "100%", "borderCollapse": "collapse"})


def layout():
    app = get_app()
    dp = app.data_provider

    df_factor = dp.get_factor_data()
    # IC calculé sur LE facteur de la stratégie (12M-1M), plus comparaison
    df_ic      = dp.get_ic_series(factor="mom_12_1")
    ic_summary = dp.get_ic_summary()

    return html.Div([
        html.Div("Research Lab", className="section-title"),

        html.Div(className="grid", children=[

            # IC stats KPIs — sur le facteur de la STRATÉGIE
            html.Div(className="panel col-3", children=[
                html.Div(className="kpi", children=[
                    html.Div("IC Mean — Momentum 12M-1M", className="kpi-label"),
                    html.Div(
                        f"{df_ic['ic'].mean():+.3f}" if not df_ic.empty else "—",
                        className="kpi-value",
                    ),
                    html.Div("Facteur de la stratégie", className="kpi-sub kpi-neutral"),
                ])
            ]),
            html.Div(className="panel col-3", children=[
                html.Div(className="kpi", children=[
                    html.Div("IC IR", className="kpi-label"),
                    html.Div(
                        f"{df_ic['ic'].mean()/df_ic['ic'].std():+.2f}" if (not df_ic.empty and df_ic['ic'].std()>0) else "—",
                        className="kpi-value",
                    ),
                    html.Div("IC / IC-Std (stabilité)", className="kpi-sub kpi-neutral"),
                ])
            ]),
            html.Div(className="panel col-3", children=[
                html.Div(className="kpi", children=[
                    html.Div("Hit Ratio", className="kpi-label"),
                    html.Div(
                        f"{(df_ic['ic']>0).mean()*100:.1f}%" if not df_ic.empty else "—",
                        className="kpi-value",
                    ),
                    html.Div("% mois avec IC > 0", className="kpi-sub kpi-neutral"),
                ])
            ]),
            html.Div(className="panel col-3", children=[
                html.Div(className="kpi", children=[
                    html.Div("Observations", className="kpi-label"),
                    html.Div(f"{len(df_ic)}", className="kpi-value"),
                    html.Div("Points mensuels", className="kpi-sub kpi-neutral"),
                ])
            ]),

            # ── Comparaison de facteurs (la vraie valeur ajoutée) ──
            html.Div(className="panel col-12", children=[
                html.Div("Validation de facteurs — IC par facteur (Spearman, forward 1M)",
                         className="section-title"),
                _ic_comparison_table(ic_summary),
                html.Div(
                    "Le Momentum 1M a typiquement un IC négatif : c'est le short-term "
                    "reversal (Jegadeesh 1990) — les gagnants du dernier mois corrigent. "
                    "C'est précisément pourquoi la stratégie utilise le 12M-1M (skip du "
                    "dernier mois) plutôt que le momentum brut.",
                    style={"fontSize": "10px", "color": "#5a7080", "marginTop": "10px",
                           "fontStyle": "italic", "lineHeight": "1.5"}),
            ]),

            # IC series du facteur stratégie
            html.Div(className="panel col-12", children=[
                html.Div("Série d'IC — Momentum 12M-1M (Spearman glissant)", className="section-title"),
                dcc.Graph(
                    figure=bar_chart(df_ic.tail(252), "date", "ic", color="diverging", height=180),
                    config={"displayModeBar": False},
                )
            ]),

            # Factor table
            html.Div(className="panel col-12", children=[
                html.Div("Derniers scores factoriels par titre", className="section-title"),
                base_table(df_factor, id="research-factor-tbl", filter_row=True),
            ]),
        ])
    ])