"""Plotly figure builders."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

GREEN, RED, BLUE, GREY, ORANGE = "#1e8449", "#c0392b", "#1f4e79", "#95a5a6", "#f39c12"
LAYOUT = dict(template="plotly_white", margin=dict(l=10, r=10, t=40, b=10), hovermode="x unified",
              font=dict(family="Inter, Segoe UI, sans-serif", size=12))


def heatmap(df: pd.DataFrame, title: str = "", zmid: float = 0.0, fmt: str = "{:+.1f}%") -> go.Figure:
    """df: rows = entities, columns = periods, values in %."""
    z = df.values.astype(float)
    text = [[("" if np.isnan(v) else fmt.format(v)) for v in row] for row in z]
    lim = np.nanpercentile(np.abs(z - zmid), 95) if np.isfinite(z).any() else 1
    fig = go.Figure(go.Heatmap(z=z, x=list(df.columns), y=list(df.index), text=text, texttemplate="%{text}",
                               colorscale="RdYlGn", zmid=zmid, zmin=zmid - lim, zmax=zmid + lim,
                               hovertemplate="%{y}<br>%{x}: %{text}<extra></extra>", showscale=False))
    fig.update_layout(**{**LAYOUT, "hovermode": "closest"}, title=title, height=max(260, 26 * len(df) + 80))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(side="top")
    return fig


def bar(df: pd.DataFrame, x: str, y: str, title: str = "", color: str | None = None, horizontal: bool = True,
        color_map: dict | None = None, height: int | None = None) -> go.Figure:
    d = df.dropna(subset=[x]).copy()
    if color is None:
        d["_c"] = np.where(d[x] >= 0, "Positive", "Negative")
        color, color_map = "_c", {"Positive": GREEN, "Negative": RED}
    fig = px.bar(d, x=x if horizontal else y, y=y if horizontal else x, color=color, orientation="h" if horizontal else "v",
                 color_discrete_map=color_map or {}, title=title)
    fig.update_layout(**{**LAYOUT, "hovermode": "closest"}, height=height or max(280, 22 * len(d) + 90),
                      showlegend=color != "_c", legend=dict(orientation="h", y=-0.12))
    if horizontal:
        fig.update_yaxes(autorange="reversed", title=None)
        fig.update_xaxes(ticksuffix="%", title=None)
    return fig


def rebased_lines(series: dict[str, pd.Series], title: str = "", start: pd.Timestamp | None = None) -> go.Figure:
    fig = go.Figure()
    palette = [BLUE, ORANGE, GREY, GREEN, RED, "#8e44ad", "#16a085"]
    for i, (name, s) in enumerate(series.items()):
        s = s.dropna()
        if start is not None:
            s = s[s.index >= start]
        if s.empty:
            continue
        s = s / s.iloc[0] * 100
        fig.add_trace(go.Scatter(x=s.index, y=s.values, name=name, mode="lines",
                                 line=dict(width=2.2 if i == 0 else 1.6, color=palette[i % len(palette)])))
    fig.update_layout(**LAYOUT, title=title, height=380, legend=dict(orientation="h", y=1.08), yaxis_title="Rebased = 100")
    return fig


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
                                         line=dict(width=1.3, dash="dot", color=[GREY, ORANGE, "#8e44ad"][i % 3])), 1, 1)
    if kind == "Candles" and has_ohlc:
        fig.add_trace(go.Candlestick(x=view.index, open=view["Open"], high=view["High"], low=view["Low"], close=view["Close"],
                                     name=name, increasing_line_color=GREEN, decreasing_line_color=RED), 1, 1)
    else:
        fig.add_trace(go.Scatter(x=view.index, y=view["Close"], name=name, mode="lines", line=dict(color=BLUE, width=2)), 1, 1)
    for n, colr in zip(dmas, [ORANGE, "#8e44ad", GREY]):
        s = ma[n].reindex(view.index)
        fig.add_trace(go.Scatter(x=s.index, y=s.values, name=f"{n} DMA", mode="lines", line=dict(width=1.3, color=colr)), 1, 1)
    if rows == 2:
        vc = np.where(view["Close"].diff().fillna(0) >= 0, "rgba(30,132,73,0.5)", "rgba(192,57,43,0.5)")
        fig.add_trace(go.Bar(x=view.index, y=view["Volume"], name="Volume", marker_color=vc, showlegend=False), 2, 1)
    fig.update_layout(**LAYOUT, height=560, xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=1.06))
    fig.update_yaxes(type="log" if log_scale else "linear", row=1, col=1)
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    return fig


def rrg(df: pd.DataFrame, tails: pd.DataFrame | None = None, title: str = "") -> go.Figure:
    """Relative-rotation style scatter. df: name, x (RS ratio), y (RS momentum)."""
    fig = go.Figure()
    for q, (x0, x1, y0, y1, col, lab) in enumerate([
        (100, 200, 100, 200, "rgba(30,132,73,0.07)", "Leading"), (100, 200, 0, 100, "rgba(243,156,18,0.08)", "Weakening"),
        (0, 100, 0, 100, "rgba(192,57,43,0.07)", "Lagging"), (0, 100, 100, 200, "rgba(31,78,121,0.07)", "Improving")]):
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1, fillcolor=col, line_width=0, layer="below")
    if tails is not None and not tails.empty:
        for name, g in tails.groupby("name"):
            fig.add_trace(go.Scatter(x=g["x"], y=g["y"], mode="lines", line=dict(width=1, color=GREY),
                                     showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=df["x"], y=df["y"], mode="markers+text", text=df["name"], textposition="top center",
                             marker=dict(size=10, color=df["x"] - 100, colorscale="RdYlGn", cmid=0, line=dict(width=1, color="white")),
                             hovertemplate="%{text}<br>RS-ratio %{x:.1f}<br>RS-momentum %{y:.1f}<extra></extra>", showlegend=False))
    pad = 1.5
    xr = [min(df["x"].min(), 100) - pad, max(df["x"].max(), 100) + pad] if len(df) else [95, 105]
    yr = [min(df["y"].min(), 100) - pad, max(df["y"].max(), 100) + pad] if len(df) else [95, 105]
    for lab, x, y in (("Leading", xr[1], yr[1]), ("Weakening", xr[1], yr[0]), ("Lagging", xr[0], yr[0]), ("Improving", xr[0], yr[1])):
        fig.add_annotation(x=x, y=y, text=lab, showarrow=False, font=dict(color=GREY, size=13),
                           xanchor="right" if x == xr[1] else "left", yanchor="top" if y == yr[1] else "bottom")
    fig.update_layout(**{**LAYOUT, "hovermode": "closest"}, title=title, height=560,
                      xaxis=dict(range=xr, title="Relative strength vs Nifty 500 (ratio, 100 = in line)"),
                      yaxis=dict(range=yr, title="Momentum of relative strength"))
    return fig


def rank_lines(df: pd.DataFrame, title: str = "") -> go.Figure:
    """df: index = dates, columns = entities, values = rank."""
    fig = go.Figure()
    for c in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df[c], name=c, mode="lines+markers", line=dict(width=1.8), marker=dict(size=4)))
    fig.update_layout(**LAYOUT, title=title, height=460, legend=dict(orientation="h", y=-0.15))
    fig.update_yaxes(autorange="reversed", title="Rank (1 = strongest momentum)")
    return fig


def lines(df: pd.DataFrame, title: str = "", ysuffix: str = "", height: int = 360) -> go.Figure:
    fig = go.Figure()
    for c in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df[c], name=str(c), mode="lines"))
    fig.update_layout(**LAYOUT, title=title, height=height, legend=dict(orientation="h", y=1.1))
    fig.update_yaxes(ticksuffix=ysuffix)
    return fig


def components_bar(row: pd.Series, labels: dict) -> go.Figure:
    d = pd.DataFrame({"Component": list(labels.values()), "Percentile": [row.get(k) for k in labels]})
    fig = px.bar(d, x="Percentile", y="Component", orientation="h", range_x=[0, 100], text="Percentile")
    fig.update_traces(texttemplate="%{text:.0f}", marker_color=BLUE)
    fig.update_layout(**{**LAYOUT, "hovermode": "closest"}, height=260, title="Momentum score components (percentile vs peers)")
    fig.update_yaxes(autorange="reversed", title=None)
    return fig


def financial_bars(df: pd.DataFrame, title: str) -> go.Figure:
    fig = go.Figure()
    labels = [d.strftime("%b %Y") for d in df.index]
    for c, colr in zip([c for c in ("Revenue", "EBITDA", "Net Income") if c in df], [BLUE, ORANGE, GREEN]):
        fig.add_trace(go.Bar(x=labels, y=df[c], name=c, marker_color=colr))
    fig.update_layout(**LAYOUT, title=title, barmode="group", height=340, yaxis_title="₹ crore", legend=dict(orientation="h", y=1.1))
    return fig


def scatter(df: pd.DataFrame, x: str, y: str, size: str | None, text: str, color: str | None = None, title: str = "",
            color_map: dict | None = None) -> go.Figure:
    d = df.dropna(subset=[x, y]).copy()
    if size:
        d[size] = d[size].fillna(d[size].median() if d[size].notna().any() else 1)
    fig = px.scatter(d, x=x, y=y, size=size, text=text, color=color, color_discrete_map=color_map or {}, title=title,
                     size_max=40)
    fig.update_traces(textposition="top center")
    fig.update_layout(**{**LAYOUT, "hovermode": "closest"}, height=460)
    return fig


def stacked_caps(df: pd.DataFrame, x: str, title: str, colors: dict) -> go.Figure:
    """df: rows = x labels, columns = cap categories (counts)."""
    fig = go.Figure()
    for c in df.columns:
        fig.add_trace(go.Bar(y=df.index, x=df[c], name=c, orientation="h", marker_color=colors.get(c, GREY)))
    fig.update_layout(**{**LAYOUT, "hovermode": "closest"}, barmode="stack", title=title,
                      height=max(260, 24 * len(df) + 90), legend=dict(orientation="h", y=1.08))
    fig.update_yaxes(autorange="reversed")
    return fig
