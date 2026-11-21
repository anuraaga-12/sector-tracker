"""Plotly figure builders, styled to match the soft pastel light theme.

Colour roles (validated with the dataviz palette checker against the white card surface):
* SERIES  — categorical identity, fixed order, never cycled past 8.
* UP/DOWN — polarity (gain / loss); always paired with a sign, direction or shape.
* CAP_RAMP — ordinal one-hue ramp for Large → Micro.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

# ---------------------------------------------------------------- tokens
INK, INK2, MUTED = "#2b2a3d", "#5f5d73", "#8b89a0"
GRID, AXIS, SURFACE = "#eeecf4", "#d9d6e6", "#ffffff"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
BLUE, ORANGE, AQUA, YELLOW, PINK, GREEN_S, VIOLET, RED_S = SERIES
UP, DOWN, NEUTRAL = "#13976a", "#d94848", "#efeef3"
GREY = "#b4b2c4"
# Diverging (loss ↔ gain) with a neutral midpoint; ends vivid, middle soft.
DIVERGING = [[0.0, "#c93c3c"], [0.2, "#e8837c"], [0.4, "#f6cfca"], [0.5, NEUTRAL],
             [0.6, "#c4ead9"], [0.8, "#5cc49a"], [1.0, "#0f8a5f"]]
CAP_RAMP = {"Large": "#184f95", "Mid": "#2a78d6", "Small": "#5598e7", "Micro": "#86b6ef", "Unknown": "#cfcdda"}
# Back-compat names used by pages
GREEN, RED = UP, DOWN

pio.templates["tracker"] = go.layout.Template(layout=dict(
    font=dict(family="Inter, system-ui, -apple-system, Segoe UI, sans-serif", size=12, color=INK2),
    title=dict(font=dict(size=15, color=INK, family="Inter, system-ui, sans-serif", weight=600), x=0.01, xanchor="left", y=0.97),
    paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, colorway=SERIES,
    xaxis=dict(automargin=True, gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS, tickcolor=AXIS, ticks="", showline=True,
               title_font=dict(color=MUTED, size=12), tickfont=dict(color=MUTED)),
    yaxis=dict(automargin=True, gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS, tickcolor=AXIS, ticks="", showline=False,
               title_font=dict(color=MUTED, size=12), tickfont=dict(color=MUTED)),
    legend=dict(font=dict(color=INK2, size=12), bgcolor="rgba(0,0,0,0)", title_font=dict(color=MUTED)),
    hoverlabel=dict(bgcolor="#ffffff", bordercolor="#e4e1f0", font=dict(color=INK, size=12,
                                                                         family="Inter, system-ui, sans-serif")),
    barcornerradius=4, bargap=0.25,
))
LAYOUT = dict(template="tracker", margin=dict(l=12, r=12, t=48, b=12), hovermode="x unified")


def _closest(**extra) -> dict:
    return {**LAYOUT, "hovermode": "closest", **extra}


def _title_legend(fig: go.Figure, title: str) -> go.Figure:
    """Title on the first line, horizontal legend on its own line beneath it (never overlapping)."""
    fig.update_layout(title=dict(text=title, y=0.985, yanchor="top"),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, xanchor="left"),
                      margin=dict(l=12, r=12, t=84 if title else 44, b=12))
    return fig


# ---------------------------------------------------------------- charts
def heatmap(df: pd.DataFrame, title: str = "", zmid: float = 0.0, fmt: str = "{:+.1f}%") -> go.Figure:
    """df: rows = entities, columns = periods, values in %. Cells carry signed labels, so colour is never alone."""
    z = df.values.astype(float)
    text = [[("" if np.isnan(v) else fmt.format(v)) for v in row] for row in z]
    lim = np.nanpercentile(np.abs(z - zmid), 95) if np.isfinite(z).any() else 1
    fig = go.Figure(go.Heatmap(z=z, x=list(df.columns), y=list(df.index), text=text, texttemplate="%{text}",
                               textfont=dict(size=12), colorscale=DIVERGING, zmid=zmid, zmin=zmid - lim, zmax=zmid + lim,
                               xgap=3, ygap=3, hovertemplate="<b>%{y}</b><br>%{x}: %{text}<extra></extra>",
                               showscale=False))
    fig.update_layout(**_closest(margin=dict(l=12, r=12, t=92 if title else 40, b=12)), height=max(300, 30 * len(df) + 130),
                      title=dict(text=title, y=0.995, yanchor="top"))
    fig.update_yaxes(autorange="reversed", showgrid=False, showline=False, tickfont=dict(color=INK2, size=12))
    fig.update_xaxes(side="top", showgrid=False, showline=False, tickfont=dict(color=INK2, size=12))
    return fig


def bar(df: pd.DataFrame, x: str, y: str, title: str = "", color: str | None = None, horizontal: bool = True,
        color_map: dict | None = None, height: int | None = None) -> go.Figure:
    d = df.dropna(subset=[x]).copy()
    if color is None:
        d["_c"] = np.where(d[x] >= 0, "Gain", "Loss")
        color, color_map = "_c", {"Gain": UP, "Loss": DOWN}
    fig = px.bar(d, x=x if horizontal else y, y=y if horizontal else x, color=color, orientation="h" if horizontal else "v",
                 color_discrete_map=color_map or {}, title=title)
    fig.update_traces(marker_line_width=0)
    fig.update_layout(**_closest(), height=height or max(280, 24 * len(d) + 90),
                      showlegend=color != "_c", legend=dict(orientation="h", y=-0.12))
    if horizontal:
        fig.update_yaxes(autorange="reversed", title=None, showgrid=False, tickfont=dict(color=INK2))
        fig.update_xaxes(ticksuffix="%", title=None, zeroline=True, zerolinecolor=AXIS, zerolinewidth=1)
    return fig


def rebased_lines(series: dict[str, pd.Series], title: str = "", start: pd.Timestamp | None = None) -> go.Figure:
    fig = go.Figure()
    for i, (name, s) in enumerate(series.items()):
        s = s.dropna()
        if start is not None:
            s = s[s.index >= start]
        if s.empty:
            continue
        s = s / s.iloc[0] * 100
        fig.add_trace(go.Scatter(x=s.index, y=s.values, name=name, mode="lines",
                                 line=dict(width=2.4 if i == 0 else 1.8, color=SERIES[i % len(SERIES)])))
    fig.update_layout(**LAYOUT, height=400, yaxis_title="Rebased = 100")
    return _title_legend(fig, title)


def price_chart(ohlc: pd.DataFrame, name: str, kind: str = "Candles", dmas: tuple = (50, 200), volume: bool = True,
                compare: dict[str, pd.Series] | None = None, start: pd.Timestamp | None = None,
                log_scale: bool = False) -> go.Figure:
    """Screener-style price chart: candles / line + DMAs + volume (+ optional rebased comparison)."""
    full = ohlc.copy()
    has_ohlc = {"Open", "High", "Low", "Close"}.issubset(full.columns)
    close = full["Close"]
    ma = {n: close.rolling(n, min_periods=n).mean() for n in dmas}
    view = full if start is None else full[full.index >= start]
    rows = 2 if volume and "Volume" in view else 1
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22][:rows], vertical_spacing=0.03)
    if compare:
        base = view["Close"].dropna()
        for i, (lab, s) in enumerate(compare.items()):
            s = s.reindex(base.index).ffill().dropna()
            if len(s) and len(base):
                s = s / s.iloc[0] * base.loc[s.index[0]]
                fig.add_trace(go.Scatter(x=s.index, y=s.values, name=f"{lab} (rebased)", mode="lines",
                                         line=dict(width=1.6, dash="dot", color=[INK2, PINK, YELLOW][i % 3])), 1, 1)
    if kind == "Candles" and has_ohlc:
        fig.add_trace(go.Candlestick(x=view.index, open=view["Open"], high=view["High"], low=view["Low"], close=view["Close"],
                                     name=name, increasing=dict(line=dict(color=UP, width=1), fillcolor=UP),
                                     decreasing=dict(line=dict(color=DOWN, width=1), fillcolor=DOWN)), 1, 1)
    else:
        fig.add_trace(go.Scatter(x=view.index, y=view["Close"], name=name, mode="lines",
                                 line=dict(color=VIOLET, width=2.2), fill="tozeroy" if not log_scale else None,
                                 fillcolor="rgba(98,80,214,0.07)"), 1, 1)
    for n, colr in zip(dmas, [ORANGE, BLUE, AQUA]):
        s = ma[n].reindex(view.index)
        fig.add_trace(go.Scatter(x=s.index, y=s.values, name=f"{n} DMA", mode="lines", line=dict(width=1.6, color=colr)), 1, 1)
    if rows == 2:
        vc = np.where(view["Close"].diff().fillna(0) >= 0, "rgba(19,151,106,0.45)", "rgba(217,72,72,0.45)")
        fig.add_trace(go.Bar(x=view.index, y=view["Volume"], name="Volume", marker_color=vc, marker_line_width=0,
                             showlegend=False), 2, 1)
    fig.update_layout(**LAYOUT, height=580, xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=1.07, x=0))
    if not (kind == "Candles" and has_ohlc) and not log_scale:  # keep the filled line from forcing the axis to 0
        lo, hi = view["Close"].min(), view["Close"].max()
        if pd.notna(lo) and pd.notna(hi):
            fig.update_yaxes(range=[lo - (hi - lo) * 0.08, hi + (hi - lo) * 0.05], row=1, col=1)
    fig.update_yaxes(type="log" if log_scale else "linear", row=1, col=1)
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    return fig


def rrg(df: pd.DataFrame, tails: pd.DataFrame | None = None, title: str = "") -> go.Figure:
    """Relative-rotation style scatter. df: name, x (RS ratio), y (RS momentum)."""
    fig = go.Figure()
    for x0, x1, y0, y1, col in [(100, 200, 100, 200, "rgba(19,151,106,0.07)"), (100, 200, 0, 100, "rgba(237,161,0,0.08)"),
                                (0, 100, 0, 100, "rgba(217,72,72,0.06)"), (0, 100, 100, 200, "rgba(42,120,214,0.07)")]:
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1, fillcolor=col, line_width=0, layer="below")
    if tails is not None and not tails.empty:
        for name, g in tails.groupby("name"):
            fig.add_trace(go.Scatter(x=g["x"], y=g["y"], mode="lines", line=dict(width=1, color="rgba(139,137,160,0.35)"),
                                     showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=df["x"], y=df["y"], mode="markers+text", text=df["name"], textposition="top center",
                             textfont=dict(color=INK2, size=11),
                             marker=dict(size=12, color=df["x"] - 100, colorscale=DIVERGING, cmid=0,
                                         line=dict(width=2, color=SURFACE)),
                             hovertemplate="<b>%{text}</b><br>RS-ratio %{x:.1f}<br>RS-momentum %{y:.1f}<extra></extra>",
                             showlegend=False))
    pad = 1.5
    xr = [min(df["x"].min(), 100) - pad, max(df["x"].max(), 100) + pad] if len(df) else [95, 105]
    yr = [min(df["y"].min(), 100) - pad, max(df["y"].max(), 100) + pad] if len(df) else [95, 105]
    for lab, x, y, c in (("Leading", xr[1], yr[1], UP), ("Weakening", xr[1], yr[0], "#a87100"),
                         ("Lagging", xr[0], yr[0], DOWN), ("Improving", xr[0], yr[1], BLUE)):
        fig.add_annotation(x=x, y=y, text=f"<b>{lab}</b>", showarrow=False, font=dict(color=c, size=13),
                           xanchor="right" if x == xr[1] else "left", yanchor="top" if y == yr[1] else "bottom")
    fig.update_layout(**_closest(), title=title, height=580,
                      xaxis=dict(range=xr, title="Relative strength vs Nifty 500 (ratio, 100 = in line)", zeroline=False),
                      yaxis=dict(range=yr, title="Momentum of relative strength", zeroline=False))
    fig.add_vline(x=100, line=dict(color=AXIS, width=1))
    fig.add_hline(y=100, line=dict(color=AXIS, width=1))
    return fig


def rank_lines(df: pd.DataFrame, title: str = "") -> go.Figure:
    """df: index = dates, columns = entities, values = rank."""
    fig = go.Figure()
    for i, c in enumerate(df.columns):
        fig.add_trace(go.Scatter(x=df.index, y=df[c], name=c, mode="lines+markers",
                                 line=dict(width=2, color=SERIES[i % len(SERIES)]),
                                 marker=dict(size=7, line=dict(width=1.5, color=SURFACE))))
    fig.update_layout(**LAYOUT, title=title, height=480, legend=dict(orientation="h", y=-0.15, x=0))
    fig.update_yaxes(autorange="reversed", title="Rank (1 = strongest momentum)")
    return fig


def lines(df: pd.DataFrame, title: str = "", ysuffix: str = "", height: int = 360) -> go.Figure:
    fig = go.Figure()
    for i, c in enumerate(df.columns):
        fig.add_trace(go.Scatter(x=df.index, y=df[c], name=str(c), mode="lines",
                                 line=dict(width=2, color=SERIES[i % len(SERIES)])))
    fig.update_layout(**LAYOUT, height=height)
    fig.update_yaxes(ticksuffix=ysuffix)
    return _title_legend(fig, title)


def components_bar(row: pd.Series, labels: dict) -> go.Figure:
    d = pd.DataFrame({"Component": list(labels.values()), "Percentile": [row.get(k) for k in labels]})
    fig = px.bar(d, x="Percentile", y="Component", orientation="h", range_x=[0, 100], text="Percentile")
    fig.update_traces(texttemplate="%{text:.0f}", textposition="outside", marker_color=VIOLET, marker_line_width=0,
                      textfont=dict(color=INK))
    fig.update_layout(**_closest(), height=280, title="Momentum score components (percentile vs peers)")
    fig.update_yaxes(autorange="reversed", title=None, showgrid=False, tickfont=dict(color=INK2))
    fig.update_xaxes(title=None)
    return fig


def financial_bars(df: pd.DataFrame, title: str) -> go.Figure:
    fig = go.Figure()
    labels = [d.strftime("%b %Y") for d in df.index]
    for c, colr in zip([c for c in ("Revenue", "EBITDA", "Net Income") if c in df], [BLUE, ORANGE, AQUA]):
        fig.add_trace(go.Bar(x=labels, y=df[c], name=c, marker_color=colr, marker_line_width=0))
    fig.update_layout(**LAYOUT, barmode="group", bargroupgap=0.08, height=380, yaxis_title="₹ crore")
    return _title_legend(fig, title)


def scatter(df: pd.DataFrame, x: str, y: str, size: str | None, text: str, color: str | None = None, title: str = "",
            color_map: dict | None = None) -> go.Figure:
    d = df.dropna(subset=[x, y]).copy()
    if size:
        d[size] = d[size].fillna(d[size].median() if d[size].notna().any() else 1)
    fig = px.scatter(d, x=x, y=y, size=size, text=text, color=color, color_discrete_map=color_map or {}, title=title,
                     size_max=40)
    fig.update_traces(textposition="top center", textfont=dict(color=INK2, size=11),
                      marker=dict(line=dict(width=1.5, color=SURFACE), opacity=0.9))
    fig.update_layout(**_closest(), height=480)
    return fig


def stacked_caps(df: pd.DataFrame, x: str, title: str, colors: dict) -> go.Figure:
    """df: rows = x labels, columns = cap categories (counts)."""
    fig = go.Figure()
    for c in df.columns:
        fig.add_trace(go.Bar(y=df.index, x=df[c], name=c, orientation="h", marker_color=colors.get(c, GREY),
                             marker_line=dict(width=1, color=SURFACE)))
    # Long category labels push the plot far right, so a Plotly legend would wrap into a column over the bars.
    # The colour key is written into the title line instead (coloured squares + names).
    key = "   ".join(f"<span style='color:{colors.get(c, GREY)}'>■</span> {c}" for c in df.columns)
    fig.update_layout(**_closest(margin=dict(l=12, r=12, t=88, b=12)), barmode="stack", barcornerradius=0,
                      height=max(300, 26 * len(df) + 110), showlegend=False,
                      title=dict(text=f"{title}<br><span style='font-size:12px;color:{INK2};font-weight:400'>{key}</span>",
                                 y=0.965, yanchor="top"))
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color=INK2))
    return fig
